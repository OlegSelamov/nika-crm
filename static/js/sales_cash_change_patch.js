(() => {
    let selectedMethod = 'cash';
    let fallbackBusy = false;
    const originalFillPayment = window.fillPayment;
    const originalPay = window.pay;

    const numberValue = value =>
        Number(String(value || '').replace(/\s/g, '').replace(',', '.')) || 0;

    const cartTotal = () => cart.reduce((sum, item) => {
        if (typeof cartItemTotal === 'function') return sum + cartItemTotal(item);
        return sum + (Number(item.price) || 0) * (Number(item.qty) || 0);
    }, 0);

    const formatMoney = value => Number(value || 0).toLocaleString('ru-RU', {
        maximumFractionDigits: 2
    }) + ' ₸';

    async function loadUnavailableCartItems() {
        const cartIds = [...new Set(
            (Array.isArray(cart) ? cart : [])
                .map(item => Number(item?.id))
                .filter(Boolean)
        )];
        if (!cartIds.length) return [];

        const remaining = new Set(cartIds);
        const found = [];
        let offset = 0;

        while (remaining.size) {
            const params = new URLSearchParams({
                status: 'out',
                sort: 'stock-asc',
                limit: '100',
                offset: String(offset)
            });
            const response = await fetch(`/api/stock?${params.toString()}`, {
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const payload = await response.json();
            const rows = Array.isArray(payload) ? payload : (payload.items || []);

            rows.forEach(item => {
                const id = Number(item.id);
                if (!remaining.has(id)) return;
                remaining.delete(id);
                if (Number(item.stock || 0) <= 0) found.push(item);
            });

            if (!rows.length || !payload.has_more) break;
            offset += rows.length;
        }

        return found;
    }

    function showNegativeStockWarning(items) {
        return new Promise(resolve => {
            document.getElementById('negativeStockSaleModal')?.remove();
            document.getElementById('negativeStockSaleStyle')?.remove();

            const escapeText = value => String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#039;');

            const style = document.createElement('style');
            style.id = 'negativeStockSaleStyle';
            style.textContent = `
                .negative-stock-sale-modal{position:fixed;inset:0;z-index:10050;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(17,24,39,.52);backdrop-filter:blur(2px)}
                .negative-stock-sale-dialog{width:min(520px,100%);max-height:min(680px,calc(100dvh - 40px));display:flex;flex-direction:column;overflow:hidden;background:#fff;border-radius:20px;box-shadow:0 24px 70px rgba(17,24,39,.24)}
                .negative-stock-sale-head{padding:22px 22px 12px}.negative-stock-sale-head span{display:inline-block;margin-bottom:7px;font-size:11px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#b45309}.negative-stock-sale-head h3{margin:0;font-size:22px;color:#202534}.negative-stock-sale-head p{margin:8px 0 0;color:#697184;font-size:13px;line-height:1.5}
                .negative-stock-sale-list{min-height:0;overflow:auto;padding:4px 22px 8px;display:grid;gap:8px}.negative-stock-sale-item{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border:1px solid #f0d6d6;border-radius:12px;background:#fff8f8}.negative-stock-sale-item strong{display:block;font-size:13px;color:#2d3340}.negative-stock-sale-item small{display:block;margin-top:3px;color:#858c9a}.negative-stock-sale-balance{white-space:nowrap;font-size:13px;font-weight:900;color:#b42318}
                .negative-stock-sale-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:16px 22px 22px}.negative-stock-sale-actions button{min-height:46px;border:0;border-radius:12px;font-weight:900;cursor:pointer}.negative-stock-sale-cancel{background:#f1f3f7;color:#454c5d}.negative-stock-sale-confirm{background:#2f3341;color:#fff}
                @media(max-width:560px){.negative-stock-sale-modal{padding:12px}.negative-stock-sale-dialog{border-radius:18px}.negative-stock-sale-actions{grid-template-columns:1fr}.negative-stock-sale-head,.negative-stock-sale-list,.negative-stock-sale-actions{padding-left:16px;padding-right:16px}}
            `;
            document.head.appendChild(style);

            const modal = document.createElement('div');
            modal.id = 'negativeStockSaleModal';
            modal.className = 'negative-stock-sale-modal';
            modal.innerHTML = `
                <div class="negative-stock-sale-dialog" role="dialog" aria-modal="true" aria-labelledby="negativeStockSaleTitle">
                    <div class="negative-stock-sale-head">
                        <span>Проверка остатка</span>
                        <h3 id="negativeStockSaleTitle">Недостаточный остаток</h3>
                        <p>Один или несколько товаров уже имеют нулевой или отрицательный остаток. Продажу всё равно можно провести.</p>
                    </div>
                    <div class="negative-stock-sale-list">
                        ${items.map(item => `
                            <div class="negative-stock-sale-item">
                                <div>
                                    <strong>${escapeText(item.name || `Товар #${item.id}`)}</strong>
                                    <small>${escapeText(item.category || 'Без категории')}</small>
                                </div>
                                <div class="negative-stock-sale-balance">
                                    Остаток: ${Number(item.stock || 0).toLocaleString('ru-RU', {maximumFractionDigits: 3})} ${escapeText(item.unit || '')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    <div class="negative-stock-sale-actions">
                        <button type="button" class="negative-stock-sale-cancel">Не продавать</button>
                        <button type="button" class="negative-stock-sale-confirm">Продать всё равно</button>
                    </div>
                </div>
            `;

            const finish = allowed => {
                document.removeEventListener('keydown', onKeyDown);
                modal.remove();
                style.remove();
                resolve(allowed);
            };
            const onKeyDown = event => {
                if (event.key === 'Escape') finish(false);
            };

            modal.querySelector('.negative-stock-sale-cancel')?.addEventListener('click', () => finish(false));
            modal.querySelector('.negative-stock-sale-confirm')?.addEventListener('click', () => finish(true));
            modal.addEventListener('click', event => {
                if (event.target === modal) finish(false);
            });
            document.addEventListener('keydown', onKeyDown);
            document.body.appendChild(modal);
        });
    }

    async function allowSaleWithUnavailableStock() {
        try {
            const items = await loadUnavailableCartItems();
            if (!items.length) return true;
            return await showNegativeStockWarning(items);
        } catch (error) {
            console.warn('NEGATIVE STOCK CHECK ERROR:', error);
            return true;
        }
    }

    window.nikaConfirmNegativeStockSale = allowSaleWithUnavailableStock;

    function modalElements() {
        return {
            modal: document.getElementById('cashChangeModal'),
            input: document.getElementById('cashReceivedInput'),
            result: document.getElementById('cashChangeResult'),
            label: document.getElementById('cashChangeResultLabel'),
            amount: document.getElementById('cashChangeAmount'),
            hint: document.getElementById('cashChangeHint'),
            confirm: document.getElementById('cashChangeConfirm')
        };
    }

    function renderFallbackChange() {
        const nodes = modalElements();
        if (!nodes.input || !nodes.result) return;
        const total = cartTotal();
        const received = numberValue(nodes.input.value);
        const difference = received - total;
        const enough = total > 0 && difference >= -.009;
        nodes.result.classList.toggle('is-short', !enough);
        nodes.label.textContent = enough ? 'Сдача' : 'Не хватает';
        nodes.amount.textContent = formatMoney(Math.abs(difference));
        nodes.hint.textContent = enough
            ? (difference > .009 ? 'Верните покупателю эту сумму' : 'Оплата без сдачи')
            : 'Введите сумму не меньше итога';
        nodes.confirm.disabled = !enough || fallbackBusy;
        nodes.confirm.textContent = enough && difference > .009
            ? 'Провести · сдача ' + formatMoney(difference)
            : 'Провести оплату';
    }

    function openFallbackChange() {
        if (!selectedClient) {
            alert('Сначала выбери клиента');
            return;
        }
        if (!cart.length) {
            alert('Корзина пустая');
            return;
        }
        const nodes = modalElements();
        if (!nodes.modal || !nodes.input) {
            alert('Обновите страницу, чтобы открыть расчёт сдачи');
            return;
        }
        const total = cartTotal();
        nodes.input.value = Number.isInteger(total) ? total.toFixed(0) : total.toFixed(2);
        document.getElementById('cashChangeTotal').textContent = formatMoney(total);
        const quick = document.getElementById('cashQuickAmounts');
        const values = [total];
        [500, 1000, 2000, 5000, 10000, 20000].forEach(step => {
            const value = Math.ceil(total / step) * step;
            if (!values.some(existing => Math.abs(existing - value) < .009)) values.push(value);
        });
        quick.innerHTML = '';
        values.sort((a, b) => a - b).slice(0, 5).forEach(value => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = Math.abs(value - total) < .009 ? 'Без сдачи' : formatMoney(value);
            button.addEventListener('click', () => {
                nodes.input.value = Number.isInteger(value) ? value.toFixed(0) : value.toFixed(2);
                renderFallbackChange();
            });
            quick.appendChild(button);
        });
        nodes.modal.classList.add('open');
        nodes.modal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('cash-change-open');
        renderFallbackChange();
        setTimeout(() => {
            nodes.input.focus();
            nodes.input.select();
        }, 80);
    }

    function closeFallbackChange(force = false) {
        if (fallbackBusy && !force) return;
        const modal = document.getElementById('cashChangeModal');
        if (!modal) return;
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('cash-change-open');
    }

    function showFallbackNotice(change) {
        if (change <= .009) return;
        document.getElementById('cashChangeNotice')?.remove();
        const notice = document.createElement('button');
        notice.type = 'button';
        notice.id = 'cashChangeNotice';
        notice.className = 'cash-change-notice';
        notice.innerHTML =
            '<span>СДАЧА ПОКУПАТЕЛЮ</span><strong>' +
            formatMoney(change) +
            '</strong><small>Нажмите, чтобы закрыть</small>';
        notice.addEventListener('click', () => notice.remove());
        document.body.appendChild(notice);
        setTimeout(() => notice.remove(), 12000);
    }

    async function submitFallbackCash(received, change) {
        if (!(await allowSaleWithUnavailableStock())) return;

        fallbackBusy = true;
        renderFallbackChange();
        try {
            const response = await fetch('/sales/pay', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    client_id: selectedClient,
                    cart,
                    payment_method: 'cash',
                    cash: received,
                    card: 0,
                    kaspi: 0,
                    cash_received: received,
                    change_amount: change,
                    company_id: null
                })
            });
            const data = await response.json().catch(() => null);
            if (!response.ok || !data || data.success === false) {
                throw new Error(data?.error || data?.message || 'Ошибка ответа сервера');
            }
            cart = [];
            renderCart();
            resetSaleAmounts();
            closeFallbackChange(true);
            window.dispatchEvent(new CustomEvent('nika:sale-completed'));
            showFallbackNotice(change);
            if (data.fiscalized !== true) {
                const reason = data.rekassa?.message || 'reKassa отклонила чек';
                alert(
                    'Продажа сохранена, но чек не фискализирован.\n\n' +
                    reason +
                    '\n\nНе проводите оплату повторно.'
                );
                return;
            }
            openSaleModal(data.sale_id, {autoPrint: true});
        } catch (error) {
            console.error('CASH CHANGE PAYMENT ERROR:', error);
            alert(error.message || 'Не удалось провести оплату');
        } finally {
            fallbackBusy = false;
            renderFallbackChange();
        }
    }

    if (typeof window.openCashChangeModal !== 'function') {
        window.openCashChangeModal = openFallbackChange;
        window.closeCashChangeModal = closeFallbackChange;
        window.renderCashChange = renderFallbackChange;
        window.handleCashChangeKey = event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                window.confirmCashPayment();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                closeFallbackChange();
            }
        };
        window.confirmCashPayment = () => {
            if (fallbackBusy) return;
            const received = numberValue(document.getElementById('cashReceivedInput')?.value);
            const total = cartTotal();
            if (received + .009 < total) {
                renderFallbackChange();
                return;
            }
            submitFallbackCash(received, Math.max(0, received - total));
        };
    }

    window.fillPayment = type => {
        selectedMethod = type;
        ['cash', 'card', 'kaspi'].forEach(method => {
            if (method !== type) {
                const field = document.getElementById(method + 'Input');
                if (field) field.value = '';
            }
        });
        if (typeof originalFillPayment === 'function') originalFillPayment(type);
    };

    window.pay = async () => {
        if (!selectedClient) {
            alert('Сначала выбери клиента');
            return;
        }
        if (!cart.length) {
            alert('Корзина пустая');
            return;
        }
        const kaspiConfirmed = Boolean(window.lastKaspiTransactionId);
        if (kaspiConfirmed || selectedMethod === 'card' || selectedMethod === 'kaspi') {
            if (!(await allowSaleWithUnavailableStock())) return;
            originalPay();
            return;
        }
        window.openCashChangeModal();
    };
})();
