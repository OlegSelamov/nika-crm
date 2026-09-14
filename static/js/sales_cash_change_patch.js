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

    window.pay = () => {
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
            originalPay();
            return;
        }
        window.openCashChangeModal();
    };
})();
