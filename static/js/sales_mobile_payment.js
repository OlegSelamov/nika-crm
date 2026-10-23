(() => {
    const MOBILE_QUERY = '(max-width: 768px)';
    let placeholder = null;
    let paymentBox = null;
    let originalParent = null;
    let originalNextSibling = null;
    let sidebarObserver = null;
    let paymentResizeObserver = null;

    function syncPaymentSpace() {
        const salesPage = document.querySelector('.sales-page');
        if (!salesPage) return;
        if (!window.matchMedia(MOBILE_QUERY).matches || !paymentBox) {
            salesPage.style.removeProperty('--nika-mobile-payment-space');
            return;
        }
        // Reserve precisely the dock height so menu/cart can scroll behind it.
        const height = Math.ceil(paymentBox.getBoundingClientRect().height);
        salesPage.style.setProperty('--nika-mobile-payment-space', (height + 20) + 'px');
    }

    function syncSidebarState() {
        const sidebar = document.querySelector('.sidebar');
        const isMobile = window.matchMedia(MOBILE_QUERY).matches;
        const menuOpen = Boolean(isMobile && sidebar?.classList.contains('mobile-open'));
        document.body.classList.toggle('sales-mobile-menu-open', menuOpen);
    }

    function observeSidebar() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar || sidebarObserver) return;
        sidebarObserver = new MutationObserver(syncSidebarState);
        sidebarObserver.observe(sidebar, {
            attributes: true,
            attributeFilter: ['class']
        });
        syncSidebarState();
    }

    function mountMobilePayment() {
        paymentBox = paymentBox || document.querySelector('.payment-box');
        if (!paymentBox) return;

        const isMobile = window.matchMedia(MOBILE_QUERY).matches;

        if (isMobile) {
            if (paymentBox.parentElement !== document.body) {
                originalParent = paymentBox.parentElement;
                originalNextSibling = paymentBox.nextSibling;
                placeholder = placeholder || document.createComment('mobile-payment-placeholder');
                originalParent.insertBefore(placeholder, paymentBox);
                document.body.appendChild(paymentBox);
            }
            document.body.classList.add('sales-mobile-payment-mounted');
            if (!paymentResizeObserver && typeof ResizeObserver !== 'undefined') {
                paymentResizeObserver = new ResizeObserver(syncPaymentSpace);
                paymentResizeObserver.observe(paymentBox);
            }
            requestAnimationFrame(syncPaymentSpace);
            observeSidebar();
            syncSidebarState();
            return;
        }

        if (paymentBox.parentElement === document.body && originalParent) {
            if (placeholder && placeholder.parentNode === originalParent) {
                originalParent.insertBefore(paymentBox, placeholder);
                placeholder.remove();
            } else if (originalNextSibling && originalNextSibling.parentNode === originalParent) {
                originalParent.insertBefore(paymentBox, originalNextSibling);
            } else {
                originalParent.appendChild(paymentBox);
            }
        }

        syncPaymentSpace();
        document.body.classList.remove('sales-mobile-payment-mounted', 'sales-mobile-menu-open');
    }

    document.addEventListener('DOMContentLoaded', mountMobilePayment);
    window.addEventListener('resize', mountMobilePayment, { passive: true });
    window.addEventListener('orientationchange', () => setTimeout(mountMobilePayment, 120));
})();