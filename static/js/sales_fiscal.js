(() => {
    "use strict";

    const state = {
        configured: null,
        provider: null,
        providerName: null,
        capabilities: {},
    };

    function el(id) {
        return document.getElementById(id);
    }

    function hideFiscalUi() {
        const strip = el("shiftStrip");
        if (strip) strip.style.display = "none";

        const shiftsButton = el("salesHistoryShiftsMode");
        if (shiftsButton) shiftsButton.hidden = true;

        const shiftsView = el("salesShiftsModeView");
        if (shiftsView) shiftsView.hidden = true;

        const documentsButton = el("salesHistoryDocumentsMode");
        if (documentsButton) {
            documentsButton.classList.add("active");
            documentsButton.setAttribute("aria-selected", "true");
        }

        const documentsView = el("salesDocumentsModeView");
        if (documentsView) documentsView.hidden = false;

        // Keep Sales usable as a normal non-fiscal document journal.
        if (typeof switchSalesHistoryMode === "function") {
            switchSalesHistoryMode("documents");
        }
    }

    function showFiscalUi() {
        const strip = el("shiftStrip");
        if (strip) strip.style.display = "";

        const shiftsButton = el("salesHistoryShiftsMode");
        if (shiftsButton) shiftsButton.hidden = !state.capabilities.shifts;

        const provider = state.providerName || "Касса";
        const meta = el("shiftStripMeta");
        if (meta && !String(meta.textContent || "").includes(provider)) {
            meta.dataset.providerName = provider;
        }
    }

    function providerizeVisibleText(root = document) {
        if (!state.configured || !state.providerName || state.providerName === "reKassa") return;
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            if (node.nodeValue && node.nodeValue.includes("reKassa")) {
                node.nodeValue = node.nodeValue.replaceAll("reKassa", state.providerName);
            }
        });
    }

    async function loadFiscalContext() {
        try {
            const response = await fetch("/api/fiscal/status", {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.success === false) {
                throw new Error(data.error || data.message || "Не удалось определить подключённую кассу");
            }

            state.configured = Boolean(data.configured);
            state.provider = data.provider || null;
            state.providerName = data.provider_name || null;
            state.capabilities = data.capabilities || {};
            window.nikaFiscal = { ...state };

            if (!state.configured) {
                hideFiscalUi();
                return;
            }

            showFiscalUi();
            providerizeVisibleText();
        } catch (error) {
            // Fiscal status must never block ordinary sales. If detection fails,
            // hide provider controls and leave the document journal available.
            console.warn("FISCAL CONTEXT ERROR:", error);
            state.configured = false;
            window.nikaFiscal = { ...state };
            hideFiscalUi();
        }
    }

    const observer = new MutationObserver(mutations => {
        if (!state.configured || !state.providerName || state.providerName === "reKassa") return;
        for (const mutation of mutations) {
            mutation.addedNodes.forEach(node => {
                if (node.nodeType === Node.ELEMENT_NODE) providerizeVisibleText(node);
            });
        }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Replace old COMRUN-only retry call with the neutral fiscal endpoint.
    window.nikaFiscalizeSale = async function nikaFiscalizeSale(saleId) {
        const response = await fetch(`/api/fiscal/sales/${encodeURIComponent(saleId)}/fiscalize`, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
        });
        const data = await response.json().catch(() => ({}));
        return { response, data };
    };

    loadFiscalContext();
    window.addEventListener("nika:sale-completed", () => {
        window.setTimeout(loadFiscalContext, 250);
    });
})();
