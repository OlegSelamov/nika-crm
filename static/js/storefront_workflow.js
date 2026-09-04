(() => {
    'use strict';

    let notificationActionBusy = false;
    let notificationEnhanceTimer = null;
    let storefrontSyncBusy = false;
    let globalOrderState = {id: null, notificationId: null};

    function storefrontAllowedInMenu() {
        return Boolean(document.querySelector('.sidebar a[href="/storefront/"]'));
    }

    function insertStorefrontMenuLinks() {
        const storefrontLink = document.querySelector('.sidebar a[href="/storefront/"]');
        if (!storefrontLink || document.querySelector('.sidebar a[href="/storefront/orders"]')) return;

        const makeLink = (href, icon, label) => {
            const link = document.createElement('a');
            link.href = href;
            link.className = 'sfw-menu-link';

            const img = document.createElement('img');
            img.src = icon;
            img.className = 'menu-icon';
            img.alt = '';
            img.onerror = function () {
                this.onerror = null;
                this.src = '/static/icons/storefront.png';
            };

            const text = document.createElement('span');
            text.className = 'text';
            text.textContent = label;

            link.append(img, text);
            return link;
        };

        const orders = makeLink('/storefront/orders', '/static/icons/sales-history.png', 'Заказы');
        const bookings = makeLink('/storefront/bookings', '/static/icons/calendar-date.png', 'Записи');

        storefrontLink.insertAdjacentElement('afterend', bookings);
        storefrontLink.insertAdjacentElement('afterend', orders);
    }

    function money(value) {
        return new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(Number(value || 0)) + ' ₸';
    }

    function qty(value) {
        const n = Number(value || 0);
        return Number.isInteger(n) ? String(n) : String(n).replace('.', ',');
    }

    function esc(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    async function markNotificationRead(notificationId) {
        if (!notificationId) return;
        try {
            await fetch(`/api/notifications/${notificationId}/read`, {
                method: 'POST',
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
        } catch (error) {
            console.debug('Notification read error:', error);
        }
    }

    function refreshNotificationsSoon() {
        window.setTimeout(() => {
            if (typeof window.loadNotifications === 'function') {
                window.loadNotifications(true);
            }
            scheduleNotificationEnhance(250);
        }, 120);
    }

    async function syncStorefrontNotifications(showToast = false) {
        if (storefrontSyncBusy) return 0;
        storefrontSyncBusy = true;

        try {
            const response = await fetch('/api/storefront/notifications/sync', {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            if (!response.ok) return 0;

            const data = await response.json();
            const count = Number(data.created_count || 0);

            if (count > 0) {
                if (typeof window.loadNotifications === 'function') {
                    await window.loadNotifications(true);
                }
                if (showToast && typeof window.showSystemToast === 'function') {
                    const created = Array.isArray(data.created) ? data.created : [];
                    const hasOrder = created.some(item => item.type === 'storefront_order');
                    const hasBooking = created.some(item => item.type === 'storefront_booking');
                    const title = hasOrder && hasBooking
                        ? 'Новые обращения'
                        : (hasOrder ? 'Новый заказ' : 'Новая запись');
                    window.showSystemToast(title, `Новых событий: ${count}`, hasOrder ? '🛒' : '📅');
                }
                scheduleNotificationEnhance(200);
            }

            return count;
        } catch (error) {
            console.debug('Storefront notification sync error:', error);
            return 0;
        } finally {
            storefrontSyncBusy = false;
        }
    }

    async function navigateFromNotification(notificationId, url) {
        await markNotificationRead(notificationId);
        window.location.href = url;
    }

    async function runStatusAction(notificationId, kind, relatedId, status, button) {
        if (!relatedId || notificationActionBusy) return;

        const endpoint = kind === 'order'
            ? `/storefront/orders/${relatedId}/status-ajax`
            : `/storefront/bookings/${relatedId}/status-ajax`;

        const oldText = button.textContent;
        notificationActionBusy = true;
        button.disabled = true;
        button.textContent = 'Сохраняем…';

        const fd = new FormData();
        fd.set('status', status);

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                body: fd,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const data = await response.json();
            if (!response.ok || data.ok === false) {
                throw new Error(data.error || 'Не удалось изменить статус');
            }

            await markNotificationRead(notificationId);
            if (typeof window.showSystemToast === 'function') {
                window.showSystemToast(
                    kind === 'order' ? 'Заказ обновлён' : 'Запись обновлена',
                    data.status_label || 'Статус сохранён',
                    kind === 'order' ? '🛒' : '📅'
                );
            }
            refreshNotificationsSoon();
        } catch (error) {
            button.disabled = false;
            button.textContent = oldText;
            if (typeof window.showSystemToast === 'function') {
                window.showSystemToast('Ошибка', error.message || 'Не удалось выполнить действие', '⚠️');
            } else {
                alert(error.message || 'Не удалось выполнить действие');
            }
        } finally {
            notificationActionBusy = false;
        }
    }

    function ensureGlobalOrderModal() {
        let modal = document.getElementById('sfwGlobalOrderModal');
        if (modal) return modal;

        modal = document.createElement('div');
        modal.id = 'sfwGlobalOrderModal';
        modal.className = 'sfw-order-overlay';
        modal.innerHTML = `
            <section class="sfw-order-modal" role="dialog" aria-modal="true" aria-labelledby="sfwGlobalOrderTitle">
                <div class="sfw-order-head">
                    <div>
                        <div class="sfw-order-kicker">Онлайн-заказ</div>
                        <h2 id="sfwGlobalOrderTitle">Заказ</h2>
                        <p id="sfwGlobalOrderSubtitle"></p>
                    </div>
                    <button class="sfw-order-close" type="button" aria-label="Закрыть">×</button>
                </div>
                <div id="sfwGlobalOrderBody" class="sfw-order-body">
                    <div class="sfw-order-loading">Загрузка заказа…</div>
                </div>
            </section>`;

        document.body.appendChild(modal);
        modal.querySelector('.sfw-order-close').addEventListener('click', closeGlobalOrderModal);
        modal.addEventListener('click', event => {
            if (event.target === modal) closeGlobalOrderModal();
        });
        return modal;
    }

    function closeGlobalOrderModal() {
        const modal = document.getElementById('sfwGlobalOrderModal');
        if (!modal) return;
        modal.classList.remove('open');
        document.body.classList.remove('sfw-modal-open');
        globalOrderState = {id: null, notificationId: null};
    }

    function orderStatusOptions(selected) {
        const options = [
            ['new', 'Новый'],
            ['accepted', 'Принят'],
            ['assembling', 'Собирается'],
            ['ready', 'Готов'],
            ['completed', 'Выполнен'],
            ['cancelled', 'Отменён']
        ];
        return options.map(([value, label]) =>
            `<option value="${value}"${value === selected ? ' selected' : ''}>${label}</option>`
        ).join('');
    }

    function renderGlobalOrder(data) {
        const o = data.order || {};
        const items = Array.isArray(data.items) ? data.items : [];
        const body = document.getElementById('sfwGlobalOrderBody');
        const title = document.getElementById('sfwGlobalOrderTitle');
        const subtitle = document.getElementById('sfwGlobalOrderSubtitle');

        title.textContent = `Заказ #${o.id || ''}`;
        subtitle.textContent = o.created_at ? `Создан ${o.created_at}` : '';

        const businessRows = o.customer_type === 'business' ? `
            <div class="sfw-info-row"><span>Организация</span><b>${esc(o.customer_company || '—')}</b></div>
            <div class="sfw-info-row"><span>БИН / ИИН</span><b>${esc(o.customer_iin_bin || '—')}</b></div>
            <div class="sfw-info-row"><span>Юр. адрес</span><b>${esc(o.customer_legal_address || '—')}</b></div>
        ` : (o.customer_iin_bin ? `
            <div class="sfw-info-row"><span>ИИН</span><b>${esc(o.customer_iin_bin)}</b></div>
        ` : '');

        body.innerHTML = `
            <div class="sfw-order-grid">
                <div class="sfw-order-column">
                    <div class="sfw-order-panel">
                        <div class="sfw-panel-title">Состав заказа</div>
                        <div class="sfw-order-items">
                            ${items.map(item => `
                                <div class="sfw-order-item">
                                    ${item.image
                                        ? `<img src="${esc(item.image)}" alt="" class="sfw-order-item-image">`
                                        : `<div class="sfw-order-item-image placeholder">🛍</div>`}
                                    <div class="sfw-order-item-copy">
                                        <b>${esc(item.name || 'Позиция')}</b>
                                        <span>${qty(item.quantity)} ${esc(item.unit || 'шт.')} × ${money(item.price)}</span>
                                    </div>
                                    <strong>${money(item.total)}</strong>
                                </div>
                            `).join('') || '<div class="sfw-order-empty">Состав заказа не найден.</div>'}
                        </div>
                        <div class="sfw-order-totals">
                            <div><span>Товары</span><b>${money(o.subtotal)}</b></div>
                            <div><span>Доставка</span><b>${Number(o.delivery_price || 0) > 0 ? money(o.delivery_price) : 'Бесплатно'}</b></div>
                            <div class="final"><span>Итого</span><b>${money(o.total_amount)}</b></div>
                        </div>
                    </div>
                </div>

                <div class="sfw-order-column">
                    <div class="sfw-order-panel">
                        <div class="sfw-panel-title">Клиент</div>
                        <div class="sfw-info-row"><span>Имя</span><b>${esc(o.customer_name || '—')}</b></div>
                        <div class="sfw-info-row"><span>Телефон</span><b>${esc(o.phone || '—')}</b></div>
                        ${o.customer_email ? `<div class="sfw-info-row"><span>Email</span><b>${esc(o.customer_email)}</b></div>` : ''}
                        ${businessRows}
                        <div class="sfw-info-row"><span>Получение</span><b>${o.delivery_method === 'delivery' ? 'Доставка' : 'Самовывоз'}</b></div>
                        ${o.delivery_method === 'delivery' ? `<div class="sfw-info-row"><span>Адрес</span><b>${esc(o.address || '—')}</b></div>` : ''}
                        <div class="sfw-info-row"><span>Оплата</span><b>${o.payment_status === 'paid' ? 'Оплачен' : 'Не оплачен'}</b></div>
                    </div>

                    <div class="sfw-order-panel">
                        <div class="sfw-panel-title">Комментарий</div>
                        <div class="sfw-order-comment">${esc(o.comment || 'Комментарий не указан')}</div>
                    </div>

                    <div class="sfw-order-panel">
                        <div class="sfw-panel-title">Обработка заказа</div>
                        <select id="sfwGlobalOrderStatus" class="sfw-order-status">
                            ${orderStatusOptions(o.order_status || 'new')}
                        </select>
                        <div class="sfw-order-footer-actions">
                            <button id="sfwGlobalOrderSave" type="button" class="sfw-order-main-btn primary">Сохранить статус</button>
                            <a class="sfw-order-main-btn dark" href="/sales?storefront_order=${encodeURIComponent(o.id)}">В продажу</a>
                        </div>
                    </div>
                </div>
            </div>`;

        document.getElementById('sfwGlobalOrderSave')?.addEventListener('click', saveGlobalOrderStatus);
    }

    async function saveGlobalOrderStatus(event) {
        const id = globalOrderState.id;
        if (!id || notificationActionBusy) return;

        const button = event.currentTarget;
        const select = document.getElementById('sfwGlobalOrderStatus');
        const oldText = button.textContent;
        button.disabled = true;
        button.textContent = 'Сохраняем…';
        notificationActionBusy = true;

        const fd = new FormData();
        fd.set('status', select?.value || 'new');

        try {
            const response = await fetch(`/storefront/orders/${id}/status-ajax`, {
                method: 'POST',
                body: fd,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const data = await response.json();
            if (!response.ok || data.ok === false) throw new Error(data.error || 'Не удалось изменить статус');

            await markNotificationRead(globalOrderState.notificationId);
            refreshNotificationsSoon();
            if (typeof window.showSystemToast === 'function') {
                window.showSystemToast('Заказ обновлён', data.status_label || 'Статус сохранён', '🛒');
            }
            button.textContent = 'Сохранено';
            window.setTimeout(() => {
                button.disabled = false;
                button.textContent = oldText;
            }, 900);
        } catch (error) {
            button.disabled = false;
            button.textContent = oldText;
            if (typeof window.showSystemToast === 'function') {
                window.showSystemToast('Ошибка', error.message || 'Не удалось выполнить действие', '⚠️');
            }
        } finally {
            notificationActionBusy = false;
        }
    }

    async function openGlobalOrder(notificationId, orderId) {
        if (!orderId) return;

        globalOrderState = {id: Number(orderId), notificationId: notificationId || null};
        if (typeof window.closeSystemDrawers === 'function') window.closeSystemDrawers();

        const modal = ensureGlobalOrderModal();
        document.getElementById('sfwGlobalOrderTitle').textContent = `Заказ #${orderId}`;
        document.getElementById('sfwGlobalOrderSubtitle').textContent = '';
        document.getElementById('sfwGlobalOrderBody').innerHTML = '<div class="sfw-order-loading">Загрузка заказа…</div>';
        modal.classList.add('open');
        document.body.classList.add('sfw-modal-open');

        try {
            const response = await fetch(`/storefront/orders/${orderId}/data`, {
                headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            });
            const data = await response.json();
            if (!response.ok || data.ok === false) throw new Error(data.error || 'Не удалось загрузить заказ');

            renderGlobalOrder(data);
            await markNotificationRead(notificationId);
            refreshNotificationsSoon();
        } catch (error) {
            document.getElementById('sfwGlobalOrderBody').innerHTML = `
                <div class="sfw-order-error">
                    <b>Не удалось открыть заказ</b>
                    <span>${esc(error.message || 'Ошибка загрузки')}</span>
                </div>`;
        }
    }

    function createActionButton(label, className, handler) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `sfw-notification-action ${className || ''}`.trim();
        button.textContent = label;
        button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            handler(button);
        });
        return button;
    }

    function addNotificationActions(article, item) {
        if (!article || !item) return;

        article.dataset.sfwNotificationId = String(item.id || '');
        const icon = article.querySelector('.notification-item__icon');

        if (item.type === 'storefront_order') {
            if (icon) icon.textContent = '🛒';
            const id = Number(item.related_id || 0);
            if (!id) return;

            const actions = document.createElement('div');
            actions.className = 'sfw-notification-actions';
            actions.append(
                createActionButton('Открыть', 'soft', () => openGlobalOrder(item.id, id)),
                createActionButton('Принять', 'primary', button =>
                    runStatusAction(item.id, 'order', id, 'accepted', button)
                ),
                createActionButton('В продажу', 'dark', () =>
                    navigateFromNotification(item.id, `/sales?storefront_order=${encodeURIComponent(id)}`)
                )
            );
            article.appendChild(actions);
        } else if (item.type === 'storefront_booking') {
            if (icon) icon.textContent = '📅';
            const id = Number(item.related_id || 0);
            if (!id) return;

            const actions = document.createElement('div');
            actions.className = 'sfw-notification-actions';
            actions.append(
                createActionButton('Открыть', 'soft', () =>
                    navigateFromNotification(item.id, `/storefront/bookings?open=${encodeURIComponent(id)}`)
                ),
                createActionButton('Подтвердить', 'primary', button =>
                    runStatusAction(item.id, 'booking', id, 'confirmed', button)
                )
            );
            article.appendChild(actions);
        }
    }

    async function enhanceNotifications() {
        const list = document.getElementById('notificationsList');
        if (!list || list.dataset.sfwLoading === '1') return;

        list.dataset.sfwLoading = '1';
        try {
            const response = await fetch('/api/notifications?limit=30', {
                headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            });
            if (!response.ok) return;
            const data = await response.json();
            const articles = Array.from(list.querySelectorAll('.notification-item'));
            const items = Array.isArray(data.items) ? data.items : [];

            articles.forEach((article, index) => {
                const item = items[index];
                if (!item) return;
                if (article.dataset.sfwEnhanced === String(item.id)) return;

                article.querySelector('.sfw-notification-actions')?.remove();
                article.dataset.sfwEnhanced = String(item.id);
                addNotificationActions(article, item);
            });
        } catch (error) {
            console.debug('Notification enhancement error:', error);
        } finally {
            list.dataset.sfwLoading = '0';
        }
    }

    function scheduleNotificationEnhance(delay = 80) {
        clearTimeout(notificationEnhanceTimer);
        notificationEnhanceTimer = window.setTimeout(enhanceNotifications, delay);
    }

    function observeNotifications() {
        const list = document.getElementById('notificationsList');
        if (!list) return;

        const observer = new MutationObserver(() => scheduleNotificationEnhance());
        observer.observe(list, {childList: true, subtree: false});
        scheduleNotificationEnhance(200);
    }

    function autoOpenStorefrontEntity() {
        const params = new URLSearchParams(window.location.search);
        const openId = Number(params.get('open') || 0);
        if (!openId) return;

        const path = window.location.pathname.replace(/\/+$/, '');
        if (path === '/storefront/orders') {
            const row = document.querySelector(`[data-order-row="${openId}"]`);
            if (row) window.setTimeout(() => row.click(), 120);
        } else if (path === '/storefront/bookings') {
            const row = document.querySelector(`[data-booking-row="${openId}"]`);
            if (row) window.setTimeout(() => row.click(), 120);
        }
    }

    function startPolling() {
        syncStorefrontNotifications(false);
        window.setInterval(() => syncStorefrontNotifications(true), 20000);
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (storefrontAllowedInMenu()) insertStorefrontMenuLinks();
        observeNotifications();
        autoOpenStorefrontEntity();
        startPolling();
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.getElementById('sfwGlobalOrderModal')?.classList.contains('open')) {
            closeGlobalOrderModal();
        }
    });
})();
