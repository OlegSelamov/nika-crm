(() => {
    const MOBILE_QUERY = '(max-width: 768px)';
    let placeholder = null;
    let paymentBox = null;
    let originalParent = null;
    let originalNextSibling = null;
    let sidebarObserver = null;

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

        document.body.classList.remove('sales-mobile-payment-mounted', 'sales-mobile-menu-open');
    }

    document.addEventListener('DOMContentLoaded', mountMobilePayment);
    window.addEventListener('resize', mountMobilePayment, { passive: true });
    window.addEventListener('orientationchange', () => setTimeout(mountMobilePayment, 120));
})();