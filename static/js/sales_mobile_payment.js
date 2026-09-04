(() => {
    const MOBILE_QUERY = '(max-width: 768px)';
    let placeholder = null;
    let paymentBox = null;
    let originalParent = null;
    let originalNextSibling = null;

    function mountMobilePayment() {
        paymentBox = paymentBox || document.querySelector('.payment-box');
        if (!paymentBox) return;

        const isMobile = window.matchMedia(MOBILE_QUERY).matches;

        if (isMobile) {
            if (paymentBox.parentElement === document.body) return;

            originalParent = paymentBox.parentElement;
            originalNextSibling = paymentBox.nextSibling;
            placeholder = placeholder || document.createComment('mobile-payment-placeholder');
            originalParent.insertBefore(placeholder, paymentBox);
            document.body.appendChild(paymentBox);
            document.body.classList.add('sales-mobile-payment-mounted');
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

        document.body.classList.remove('sales-mobile-payment-mounted');
    }

    document.addEventListener('DOMContentLoaded', mountMobilePayment);
    window.addEventListener('resize', mountMobilePayment, { passive: true });
    window.addEventListener('orientationchange', () => setTimeout(mountMobilePayment, 120));
})();
