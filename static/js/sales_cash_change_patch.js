(() => {
    const originalPay = window.pay;
    const originalConfirmCashPayment = window.confirmCashPayment;
    const originalSubmitSalePayment = window.submitSalePayment;
    let approvedSignature = null;
    let guardPromise = null;

    function currentCartSignature() {
        return (Array.isArray(window.cart) ? window.cart : cart || [])
            .map(item => `${Number(item?.id) || 0}:${Number(item?.qty) || 0}`)
            .sort()
            .join('|');
    }

    function currentCart() {
        if (Array.isArray(window.cart)) return window.cart;
        if (typeof cart !== 'undefined' && Array.isArray(cart)) return cart;
        return [];
    }

    async function loadUnavailableCartItems() {
        const requestedById = new Map();
        currentCart().forEach(item => {
            const id = Number(item?.id);
            const qty = Number(item?.qty) || 0;
            if (!id || qty <= 0) return;
            requestedById.set(id, (requestedById.get(id) || 0) + qty);
        });
        if (!requestedById.size) return [];

        const remaining = new Set(requestedById.keys());
        const found = [];
        const maxRequested = Math.max(...requestedById.values());
        let offset = 0;

        while (remaining.size) {
            const params = new URLSearchParams({
                sort: 'stock-asc',
                limit: '100',
                offset: String(offset)
            });
            const response = await fetch(`/api/stock?${params.toString()}`, {
                cache: 'no-store',
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const payload = await response.json();
            const rows = Array.isArray(payload) ? payload : (payload.items || []);

            for (const item of rows) {
                const id = Number(item.id);
                if (!remaining.has(id)) continue;

                remaining.delete(id);
                const stock = Number(item.stock || 0);
                const requested = Number(requestedById.get(id) || 0);
                const projectedStock = stock - requested;

                if (projectedStock < -0.000001) {
                    found.push({
                        ...item,
                        requested,
                        projected_stock: projectedStock
                    });
                }
            }

            if (!rows.length || !payload.has_more || !remaining.size) break;

            const lastStock = Number(rows[rows.length - 1]?.stock || 0);
            if (lastStock >= maxRequested) break;
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
            const formatQty = value => Number(value || 0).toLocaleString('ru-RU', {
                maximumFractionDigits: 3
            });

            const style = document.createElement('style');
            style.id = 'negativeStockSaleStyle';
            style.textContent = `
                .negative-stock-sale-modal{position:fixed;inset:0;z-index:10050;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(17,24,39,.52);backdrop-filter:blur(2px)}
                .negative-stock-sale-dialog{width:min(540px,100%);max-height:min(680px,calc(100dvh - 40px));display:flex;flex-direction:column;overflow:hidden;background:#fff;border-radius:20px;box-shadow:0 24px 70px rgba(17,24,39,.24)}
                .negative-stock-sale-head{padding:22px 22px 12px}.negative-stock-sale-head span{display:inline-block;margin-bottom:7px;font-size:11px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#b45309}.negative-stock-sale-head h3{margin:0;font-size:22px;color:#202534}.negative-stock-sale-head p{margin:8px 0 0;color:#697184;font-size:13px;line-height:1.5}
                .negative-stock-sale-list{min-height:0;overflow:auto;padding:4px 22px 8px;display:grid;gap:8px}.negative-stock-sale-item{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border:1px solid #f0d6d6;border-radius:12px;background:#fff8f8}.negative-stock-sale-item strong{display:block;font-size:13px;color:#2d3340}.negative-stock-sale-item small{display:block;margin-top:3px;color:#858c9a}.negative-stock-sale-balance{white-space:nowrap;text-align:right;font-size:12px;font-weight:800;color:#5f6675}.negative-stock-sale-balance b{display:block;margin-top:3px;font-size:13px;color:#b42318}
                .negative-stock-sale-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:16px 22px 22px}.negative-stock-sale-actions button{min-height:46px;border:0;border-radius:12px;font-weight:900;cursor:pointer}.negative-stock-sale-cancel{background:#f1f3f7;color:#454c5d}.negative-stock-sale-confirm{background:#2f3341;color:#fff}
                @media(max-width:560px){.negative-stock-sale-modal{padding:12px}.negative-stock-sale-dialog{border-radius:18px}.negative-stock-sale-actions{grid-template-columns:1fr}.negative-stock-sale-head,.negative-stock-sale-list,.negative-stock-sale-actions{padding-left:16px;padding-right:16px}.negative-stock-sale-item{align-items:flex-start;flex-direction:column}.negative-stock-sale-balance{text-align:left}}
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
                        <p>Количества на складе не хватает для этой продажи. Можно отменить оплату или продать товар всё равно.</p>
                    </div>
                    <div class="negative-stock-sale-list">
                        ${items.map(item => `
                            <div class="negative-stock-sale-item">
                                <div>
                                    <strong>${escapeText(item.name || `Товар #${item.id}`)}</strong>
                                    <small>Продаётся: ${formatQty(item.requested)} ${escapeText(item.unit || '')}</small>
                                </div>
                                <div class="negative-stock-sale-balance">
                                    Сейчас: ${formatQty(item.stock)} ${escapeText(item.unit || '')}
                                    <b>После продажи: ${formatQty(item.projected_stock)} ${escapeText(item.unit || '')}</b>
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

    async function confirmStockForCurrentCart() {
        const signature = currentCartSignature();
        if (!signature) return true;
        if (approvedSignature === signature) return true;
        if (guardPromise) return guardPromise;

        guardPromise = (async () => {
            try {
                const items = await loadUnavailableCartItems();
                if (!items.length) return true;
                const allowed = await showNegativeStockWarning(items);
                if (allowed) approvedSignature = signature;
                return allowed;
            } catch (error) {
                console.error('NEGATIVE STOCK CHECK ERROR:', error);
                alert('Не удалось проверить остаток товара. Обновите страницу и повторите оплату.');
                return false;
            } finally {
                guardPromise = null;
            }
        })();

        return guardPromise;
    }

    window.nikaConfirmNegativeStockSale = confirmStockForCurrentCart;

    if (typeof originalConfirmCashPayment === 'function') {
        window.confirmCashPayment = async (...args) => {
            if (!(await confirmStockForCurrentCart())) return;
            return originalConfirmCashPayment(...args);
        };
    }

    if (typeof originalPay === 'function') {
        window.pay = async (...args) => {
            const card = Number(String(document.getElementById('cardInput')?.value || '').replace(',', '.')) || 0;
            const kaspi = Number(String(document.getElementById('kaspiInput')?.value || '').replace(',', '.')) || 0;
            const alreadyPaidByPos = Boolean(window.lastKaspiTransactionId);

            if (card > 0 || kaspi > 0 || alreadyPaidByPos) {
                if (!(await confirmStockForCurrentCart())) return;
            }
            return originalPay(...args);
        };
    }

    if (typeof originalSubmitSalePayment === 'function') {
        window.submitSalePayment = async (...args) => {
            if (!(await confirmStockForCurrentCart())) return;
            return originalSubmitSalePayment(...args);
        };
    }

    window.addEventListener('nika:sale-completed', () => {
        approvedSignature = null;
    });
})();
