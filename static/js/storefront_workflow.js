(() => {
    'use strict';

    let notificationActionBusy = false;
    let notificationEnhanceTimer = null;
    let storefrontSyncBusy = false;

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
                createActionButton('Открыть', 'soft', () =>
                    navigateFromNotification(item.id, `/storefront/orders?open=${encodeURIComponent(id)}`)
                ),
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
})();
