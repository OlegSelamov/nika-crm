/* Touchscreen cashier: first tap selects the tender, second tap edits amount.
 * Do not intercept a physical mouse, barcode scanner or ordinary keyboard.
 * Intercept at WINDOW capture: Electron preload listens on DOCUMENT capture
 * and otherwise restores input focus, triggering Windows touch keyboard.
 */
(() => {
    const methods = [
        ["cash", "cashInput"],
        ["card", "cardInput"],
        ["kaspi", "kaspiInput"]
    ];
    let selectedMethod = null;
    let editingMethod = null;
    let selectWhenFocused = null;

    function init() {
        const inputs = new Map(methods.map(([method, id]) =>
            [method, document.getElementById(id)]).filter(([, input]) => !!input));
        if (inputs.size !== methods.length) return;

        function markSelected(method) {
            for (const [kind, input] of inputs) {
                input.classList.toggle("nika-payment-selected", kind === method);
            }
        }

        function choose(method) {
            for (const [kind, input] of inputs) {
                if (kind !== method) input.value = "";
            }
            if (typeof window.fillPayment === "function") window.fillPayment(method);
            selectedMethod = method;
            editingMethod = null;
            markSelected(method);
        }

        // Runs before document-level Electron focus recovery and before
        // Chromium's touch-to-focus default action.
        window.addEventListener("pointerdown", event => {
            const input = event.target;
            if (!input || !input.dataset) return;
            const method = input.dataset.paymentKind;
            if (!inputs.has(method) || inputs.get(method) !== input) return;

            const isTouch = event.pointerType === "touch" || event.pointerType === "pen";
            const wideTouch = typeof window.matchMedia === "function" &&
                window.matchMedia("(min-width: 769px)").matches;
            const isCashierTouch = isTouch &&
                (window.nikaDesktop?.isElectron === true || wideTouch);
            if (!isCashierTouch) {
                // Mouse clicks and physical-keyboard entry retain ordinary
                // single-click focus, even if the last action was a touch.
                input.readOnly = false;
                input.inputMode = "decimal";
                return;
            }

            if (selectedMethod !== method || !String(input.value || "").trim()) {
                // Readonly/inputmode guard + preventDefault: no caret or native
                // Windows touch keyboard is created by this first tap.
                input.readOnly = true;
                input.inputMode = "none";
                event.preventDefault();
                if (document.activeElement?.blur) document.activeElement.blur();
                choose(method);
                return;
            }

            // Second tap on the SAME selected tender unlocks numeric entry.
            input.readOnly = false;
            input.inputMode = "decimal";
            if (editingMethod !== method) {
                selectWhenFocused = method;
                editingMethod = method;
                // Already focused (e.g. browser restoring caret unexpectedly).
                if (document.activeElement === input) {
                    input.select();
                    selectWhenFocused = null;
                }
            }
        }, true);

        for (const [method, input] of inputs) {
            input.addEventListener("click", () => {
                // The first touchscreen tap already selected + filled via
                // pointerdown; do not enable input or change its amount here.
                if (input.readOnly) return;
                if (selectedMethod !== method || !String(input.value || "").trim()) {
                    choose(method);
                }
            });
            input.addEventListener("focus", () => {
                if (selectWhenFocused === method) {
                    input.select(); // Easy replacement of the suggested total.
                    selectWhenFocused = null;
                }
            });
        }

        window.addEventListener("nika:sale-completed", () => {
            selectedMethod = null;
            editingMethod = null;
            selectWhenFocused = null;
            for (const input of inputs.values()) {
                input.readOnly = false;
                input.inputMode = "decimal";
                input.classList.remove("nika-payment-selected");
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init, {once: true});
    } else {
        init();
    }
})();
