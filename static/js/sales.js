let cart = [];
let selectedClientData = null;
let selectedClient = null;
let currentBarcodeData = {};
let currentDocumentType = "check";
let currentDocumentId = null;
let pendingQuantityItem = null;

const documentConfig = {
    check: {
        title: "Чек",
        url: id => `/docs/check/${id}`,
        pdfUrl: id => `/docs/pdf/check/${id}`,
        filename: id => `check-${id}.pdf`
    },
    refundCheck: {
        title: "Чек возврата",
        url: id => `/docs/refund-check/${id}`,
        pdfUrl: id => `/docs/pdf/refund-check/${id}`,
        filename: id => `refund-check-${id}.pdf`
    },
    invoice: {
        title: "Счёт на оплату",
        url: id => `/docs/invoice/${id}`,
        pdfUrl: id => `/docs/pdf/invoice/${id}`,
        filename: id => `schet-na-oplatu-${id}.pdf`
    },
    nakladnaya: {
        title: "Накладная",
        url: id => `/docs/nakladnaya/${id}`,
        pdfUrl: id => `/docs/pdf/nakladnaya/${id}`,
        filename: id => `nakladnaya-${id}.pdf`
    },
    schetFactura: {
        title: "Счёт-фактура",
        url: id => `/docs/schet-factura/${id}`,
        pdfUrl: id => `/docs/pdf/schet-factura/${id}`,
        filename: id => `schet-factura-${id}.pdf`
    },
    act: {
        title: "Акт выполненных работ",
        url: id => `/docs/act/${id}`,
        pdfUrl: id => `/docs/pdf/act/${id}`,
        filename: id => `akt-vypolnennyh-rabot-${id}.pdf`
    }
};

let company = {}; // 👈 вот сюда

fetch("/api/company/active")
.then(res => res.json())
.then(data => {
    company = data;
});

// Товары больше не загружаются целиком. При большом каталоге поиск
// выполняется на сервере и возвращает не более 30 подходящих позиций.
function loadItems() {
    const itemsList = document.getElementById("itemsList");
    if (itemsList) {
        itemsList.innerHTML = "";
        itemsList.style.display = "none";
    }
}

// единицы, для которых количество вводится перед добавлением
function normalizeUnit(unit) {
    return String(unit || "шт").trim().toLowerCase();
}

function isVariableQuantityUnit(unit) {
    return [
        "кг", "килограмм", "килограммы",
        "г", "гр", "грамм", "граммы",
        "литр", "л", "литры",
        "мл", "миллилитр", "миллилитры"
    ].includes(normalizeUnit(unit));
}

function selectItemForSale(id, name, price, unit = "шт", gtin = "", ntin = "") {
    if (isVariableQuantityUnit(unit)) {
        openQuantityModal({ id, name, price, unit, gtin, ntin });
        return;
    }

    addToCart(id, name, price, 1, gtin, ntin, unit);
}

function openQuantityModal(item) {
    pendingQuantityItem = item;

    const unit = normalizeUnit(item.unit);
    const input = document.getElementById("quantityInput");
    const quick = document.getElementById("quantityQuickButtons");

    document.getElementById("quantityProductName").textContent = item.name;
    document.getElementById("quantityProductPrice").textContent =
        `${Number(item.price || 0).toLocaleString("ru-RU")} ₸ / ${item.unit}`;
    document.getElementById("quantityUnitLabel").textContent = item.unit;

    const wholeOnly = ["г", "гр", "грамм", "граммы", "мл", "миллилитр", "миллилитры"].includes(unit);
    input.step = wholeOnly ? "1" : "0.001";
    input.min = wholeOnly ? "1" : "0.001";
    input.value = wholeOnly ? "100" : "1";

    const values = wholeOnly
        ? [50, 100, 250, 500, 1000]
        : [0.1, 0.25, 0.5, 1, 2];

    quick.innerHTML = values.map(value => `
        <button type="button" onclick="setQuantityValue(${value})">
            ${String(value).replace('.', ',')} ${item.unit}
        </button>
    `).join("");

    updateQuantityPreview();
    document.getElementById("quantityModal").style.display = "flex";

    setTimeout(() => {
        input.focus();
        input.select();
    }, 50);
}

function closeQuantityModal() {
    document.getElementById("quantityModal").style.display = "none";
    pendingQuantityItem = null;
}

function setQuantityValue(value) {
    document.getElementById("quantityInput").value = value;
    updateQuantityPreview();
}

function updateQuantityPreview() {
    if (!pendingQuantityItem) return;

    const raw = String(document.getElementById("quantityInput").value || "").replace(",", ".");
    const qty = parseFloat(raw) || 0;
    const total = Number(pendingQuantityItem.price || 0) * qty;

    document.getElementById("quantityTotalPreview").textContent =
        total.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₸";
}

function confirmQuantity() {
    if (!pendingQuantityItem) return;

    const input = document.getElementById("quantityInput");
    const qty = parseFloat(String(input.value || "").replace(",", "."));

    if (!Number.isFinite(qty) || qty <= 0) {
        input.focus();
        return;
    }

    const item = pendingQuantityItem;
    addToCart(item.id, item.name, item.price, qty, item.gtin, item.ntin, item.unit);
    closeQuantityModal();
}

// добавление в корзину
function addToCart(id, name, price, qty = 1, gtin = "", ntin = "", unit = "шт") {

    const existing = cart.find(i => i.id === id);

    if (existing) {
        existing.qty += Number(qty) || 1;
    } else {
		cart.push({
			id,
			name,
			price,
			qty,
			gtin,
			ntin,
            unit
		});
    }

    renderCart();
	document.getElementById("itemsList").style.display = "none";
    document.getElementById("search").value = "";
}

function formatQuantity(qty, unit) {
    const value = Number(qty || 0);
    const formatted = value.toLocaleString("ru-RU", { maximumFractionDigits: 3 });
    return `${formatted}${unit ? ` ${unit}` : ""}`;
}

// отрисовка корзины
function renderCart() {
    let html = "";
    let total = 0;

    cart.forEach((item, index) => {
        let qty = item.qty || 1;
        let sum = item.price * qty;

        total += sum;

        html += `
            <tr>
                <td>
                    <div class="cart-product-name">${item.name}</div>
                    ${(item.gtin || item.ntin) ? `<div class="cart-product-code">${item.gtin || item.ntin}</div>` : ""}
                </td>
                <td>
                    <div class="qty-control">
                        <button type="button" onclick="changeQty(${index}, -1)">−</button>
                        <span>${formatQuantity(qty, item.unit)}</span>
                        <button type="button" onclick="changeQty(${index}, 1)">+</button>
                    </div>
                </td>
                <td><strong>${sum.toLocaleString("ru-RU")} ₸</strong></td>
                <td>
                    <button type="button" class="remove-cart-btn" onclick="removeItem(${index})" aria-label="Удалить"><img src="/static/icons/delete-item.png" alt=""></button>
                </td>
            </tr>
        `;
    });

    document.getElementById("cart").innerHTML = html;
	    renderMobileCart();
	document.getElementById("totalAmount").innerText =
		total.toLocaleString("ru-RU") + " ₸";
}

function renderMobileCart() {

	let html = "";

	cart.forEach((item, index) => {

		let qty = item.qty || 1;
		let sum = item.price * qty;

		html += `
			<div class="mobile-cart-item">

				<div class="mobile-cart-top">

					<div class="mobile-cart-name">
						${item.name}
					</div>

					<div class="mobile-cart-price">
						${sum} ₸
					</div>

				</div>

				<div class="mobile-cart-bottom">

					<div class="mobile-qty">
						<button onclick="changeQty(${index}, -1)">−</button>
						<span>${formatQuantity(qty, item.unit)}</span>
						<button onclick="changeQty(${index}, 1)">+</button>
					</div>

					<button onclick="removeItem(${index})" class="mobile-remove-btn" aria-label="Удалить">
						<img src="/static/icons/delete-item.png" alt="">
					</button>

				</div>

			</div>
		`;
	});

	let mobile = document.getElementById("mobileCart");

	if (mobile) {
		mobile.innerHTML = html;
	}
}

function changeQty(index, delta) {
    const item = cart[index];
    const unit = normalizeUnit(item.unit);
    const step = ["кг", "килограмм", "килограммы", "литр", "л", "литры"].includes(unit) ? 0.1 : 1;
    item.qty = Number(((item.qty || step) + (delta * step)).toFixed(3));

    if (cart[index].qty <= 0) {
        cart.splice(index, 1);
    }

    renderCart();
}

function removeItem(i) {
    cart.splice(i, 1);
    renderCart();
}

function resetSaleAmounts() {
    document.getElementById("cashInput").value = "";
    document.getElementById("cardInput").value = "";
    document.getElementById("kaspiInput").value = "";
    document.getElementById("totalAmount").innerText = "0 ₸";

    window.lastKaspiTransactionId = "";
    window.lastKaspiMethod = "";
}

// оплата
function pay() {

    if (!selectedClient) {
        alert("Сначала выбери клиента");
        return;
    }

    let cash = document.getElementById("cashInput").value || 0;
    let card = document.getElementById("cardInput").value || 0;
    let kaspi = document.getElementById("kaspiInput").value || 0;
	
	let paymentMethod = "cash";

	if (parseFloat(card) > 0) {
		paymentMethod = "card";
	}

	if (parseFloat(kaspi) > 0) {
		paymentMethod = "kaspi";
	}

    fetch("/sales/pay", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
		body: JSON.stringify({
			client_id: selectedClient,
			cart: cart,

			payment_method: paymentMethod,

			cash: cash,
			card: card,
			kaspi: kaspi,

			kaspi_transaction_id:
				window.lastKaspiTransactionId || "",

			kaspi_method:
				window.lastKaspiMethod || "",

			company_id: null
		})
    })
    .then(res => res.json().catch(() => null))
    .then(data => {

        if (!data) {
            alert("Ошибка ответа сервера");
            return;
        }

        openSaleModal(data.sale_id);

        cart = [];
        renderCart();
        resetSaleAmounts();
        window.dispatchEvent(new CustomEvent("nika:sale-completed"));

    })
    .catch(err => {
        console.error("PAY ERROR:", err);
    });
}

let itemSearchController = null;

function renderItemSearchResults(items, hasMore) {
    const itemsList = document.getElementById("itemsList");
    itemsList.innerHTML = "";

    if (!items.length) {
        itemsList.innerHTML = '<div class="items-search-message">Товары не найдены</div>';
        itemsList.style.display = "block";
        return;
    }

    items.forEach(item => {
        const card = document.createElement("div");
        card.className = "item-card";

        const imageBlock = document.createElement("div");
        imageBlock.className = "item-image";

        const showImagePlaceholder = () => {
            imageBlock.innerHTML = "";
            const placeholder = document.createElement("span");
            placeholder.className = "item-image-placeholder";
            placeholder.textContent = "Нет фото";
            imageBlock.appendChild(placeholder);
        };

        if (item.image) {
            const image = document.createElement("img");
            image.src = item.image;
            image.alt = "";
            image.addEventListener("error", showImagePlaceholder, { once: true });
            imageBlock.appendChild(image);
        } else {
            showImagePlaceholder();
        }

        if (Number(item.discount_percent || 0) > 0) {
            const badge = document.createElement("div");
            badge.className = "discount-badge";
            badge.textContent = `-${item.discount_percent}%`;
            imageBlock.appendChild(badge);
        }

        const info = document.createElement("div");
        info.className = "item-info";

        const name = document.createElement("div");
        name.className = "item-name";
        name.textContent = item.name || "Без названия";

        const priceBlock = document.createElement("div");
        priceBlock.className = "item-price-block";

        if (item.old_price) {
            const oldPrice = document.createElement("div");
            oldPrice.className = "old-price";
            oldPrice.textContent = `${item.old_price} ₸`;
            priceBlock.appendChild(oldPrice);
        }

        const price = document.createElement("div");
        price.className = "new-price";
        price.textContent = `${item.retail_price || 0} ₸`;
        priceBlock.appendChild(price);

        info.appendChild(name);
        info.appendChild(priceBlock);
        card.appendChild(imageBlock);
        card.appendChild(info);

        card.addEventListener("click", () => {
            selectItemForSale(
                item.id,
                item.name,
                Number(item.retail_price || 0),
                item.unit || "шт",
                item.gtin || "",
                item.ntin || ""
            );
        });

        itemsList.appendChild(card);
    });

    if (hasMore) {
        const hint = document.createElement("div");
        hint.className = "items-search-message";
        hint.textContent = "Показаны первые 30 товаров. Уточните запрос.";
        itemsList.appendChild(hint);
    }

    itemsList.style.display = "grid";
}

async function searchItems(query) {
    if (itemSearchController) itemSearchController.abort();
    itemSearchController = new AbortController();

    try {
        const response = await fetch(
            `/api/items/search?q=${encodeURIComponent(query)}`,
            { signal: itemSearchController.signal }
        );

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        renderItemSearchResults(data.items || [], Boolean(data.has_more));
    } catch (error) {
        if (error.name === "AbortError") return;
        console.error("ITEM SEARCH ERROR:", error);
        const itemsList = document.getElementById("itemsList");
        itemsList.innerHTML = '<div class="items-search-message">Не удалось выполнить поиск</div>';
        itemsList.style.display = "block";
    }
}

// шторка выбора клиента
function openClientSheet() {
    document.getElementById("clientSheet").classList.add("active");
    loadClients();
}

function closeClientSheet() {
    document.getElementById("clientSheet").classList.remove("active");
}

function loadClients() {

    fetch("/api/clients")
    .then(res => res.json())
    .then(data => {

        let html = "<div class='table-wrapper'><table class='client-table'>";

        data.forEach(c => {

            const company = c.company_name || "Без компании";
            const name = c.full_name || "";

            html += `
                <tr onclick='selectClient(${JSON.stringify(c)})'>
                    <td>
                        <div style="display:flex; justify-content:space-between;">
                            
                            <span style="font-weight:600;">
                                ${company}
                            </span>

                            <span style="color:#64748b;">
                                ${name}
                            </span>

                        </div>

                        <div style="font-size:12px; color:#94a3b8;">
                            ${c.phone || ""}
                        </div>
                    </td>
                </tr>
            `;
        });

        html += "</table></div>";

        document.getElementById("clientList").innerHTML = html;
		
    });
}

function selectDefaultPrivateClient() {

    fetch("/api/clients")
    .then(res => res.json())
    .then(clients => {

        const privateClient = clients.find(client => {
            const companyName = (client.company_name || "").trim().toLowerCase();
            const fullName = (client.full_name || "").trim().toLowerCase();

            return companyName === "частное лицо" || fullName === "частное лицо";
        });

        if (!privateClient) {
            console.warn('Клиент "Частное лицо" не найден');
            return;
        }

        selectedClientData = privateClient;
        selectedClient = privateClient.id;

        const clientInput = document.getElementById("clientSearch");
        if (clientInput) {
            clientInput.value =
                privateClient.company_name ||
                privateClient.full_name ||
                "Частное лицо";
        }
    })
    .catch(error => {
        console.error("DEFAULT CLIENT ERROR:", error);
    });
}

function filterClients() {
    const input = document.getElementById("clientSearchInput");
    const query = input.value.toLowerCase().trim();

    const rows = document.querySelectorAll("#clientList tr");

    rows.forEach(row => {

        // 🔥 берем ТОЛЬКО текст без HTML
        const text = row.textContent.toLowerCase();

        if (text.includes(query)) {
            row.style.display = "";
        } else {
            row.style.display = "none";
        }

    });
}

function selectClient(client) {

    selectedClientData = client;

    document.getElementById("selectedClient").innerHTML = `
        <b>${client.company_name || ""}</b><br>
        ${client.full_name || ""}<br>
        <span class="client-detail-line"><img src="/static/icons/phone.png" alt="">${client.phone || ""}</span>
        <span class="client-detail-line"><img src="/static/icons/iin.png" alt="">${client.iin || ""}</span>
        <span class="client-detail-line"><img src="/static/icons/location.png" alt="">${client.address || ""}</span>
    `;
}

function confirmClient() {

    if (!selectedClientData) {
        alert("Выберите клиента");
        return;
    }

    selectedClient = selectedClientData.id;

    document.getElementById("clientSearch").value = selectedClientData.full_name;

    closeClientSheet();
}

const searchInput = document.getElementById("search");
const itemsBox = document.getElementById("itemsList");
let itemSearchTimer = null;

if (searchInput) {

    searchInput.addEventListener("input", function () {
        clearTimeout(itemSearchTimer);
        const query = this.value.trim();

        if (query.length < 2) {
            if (itemSearchController) itemSearchController.abort();
            itemsBox.innerHTML = query
                ? '<div class="items-search-message">Введите ещё один символ</div>'
                : "";
            itemsBox.style.display = query ? "block" : "none";
            return;
        }

        itemSearchTimer = setTimeout(() => {
            searchItems(query);
        }, 300);
    });

    searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
            clearTimeout(itemSearchTimer);
            if (itemSearchController) itemSearchController.abort();
            itemsBox.style.display = "none";
        }
    });

    // 🔥 клик вне — закрывает
    document.addEventListener("click", function(e) {
        if (!e.target.closest(".search-box")) {
            itemsBox.style.display = "none";
        }
    });
}

function fillPayment(type) {

    let total = parseInt(document.getElementById("totalAmount").innerText.replace(/\D/g, ""));

    let cash = parseInt(document.getElementById("cashInput").value || 0);
    let card = parseInt(document.getElementById("cardInput").value || 0);
    let kaspi = parseInt(document.getElementById("kaspiInput").value || 0);

    let currentSum = cash + card + kaspi;

    let remaining = total - currentSum;

    if (remaining <= 0) {
        return;
    }

    if (type === "cash") {
        document.getElementById("cashInput").value = cash + remaining;
    }

    if (type === "card") {
        document.getElementById("cardInput").value = card + remaining;
    }

    if (type === "kaspi") {
        document.getElementById("kaspiInput").value = kaspi + remaining;
    }
}

function sendAssistant(text) {

    fetch("/api/agent/command", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            text: text
        })
    })
    .then(res => res.json())
    .then(data => {

        console.log("ASSISTANT:", data);

        // 👉 если есть ответ (диалог)
        if (data.reply) {
            alert(data.reply); // пока просто
            return;
        }

        // 👉 если успех
        if (data.success) {
            alert(data.message || "Готово");
            location.reload();
            return;
        }

    });
}

function openSaleModal(id) {

    currentDocumentType = "check";
    currentDocumentId = id;
    const saveBtn = document.getElementById("saveDocumentBtn");
    if (saveBtn) saveBtn.style.display = "";

    const modal =
        document.getElementById("saleModal");

    const body =
        document.getElementById("saleBody");

    document.getElementById("saleTitle").innerText = "Чек";
    document.getElementById(
        "saleTitle"
    ).dataset.saleId = id;

    modal.classList.remove("invoice-mode");
    modal.style.display = "flex";

    body.innerHTML = `
        <div style="
            padding:30px;
            text-align:center;
            font-size:14px;
        ">
            Загрузка чека...
        </div>
    `;

    fetch("/docs/check/" + id)

    .then(res => res.text())

    .then(html => {

        body.innerHTML = html;

    })

    .catch(err => {

        console.error(err);

        body.innerHTML = `
            <div style="
                padding:30px;
                text-align:center;
                color:red;
            ">
                Ошибка загрузки
            </div>
        `;
    });
}


function openInvoiceModal(id) {
    openDocumentModal(id, "invoice");
}

function openRefundCheckModal(id) {
    openDocumentModal(id, "refundCheck");
}

function openDocumentModal(id, type) {
    const config = documentConfig[type];
    if (!config || type === "check") {
        openSaleModal(id);
        return;
    }

    currentDocumentType = type;
    currentDocumentId = id;

    const modal = document.getElementById("saleModal");
    const body = document.getElementById("saleBody");
    const title = document.getElementById("saleTitle");

    title.innerText = config.title;
    title.dataset.saleId = id;

    modal.classList.add("invoice-mode");
    modal.style.display = "flex";
    body.innerHTML = `
        <iframe
            id="documentFrame"
            title="${config.title}"
            src="${config.url(id)}"
            onload="this.dataset.loaded='true'"
        ></iframe>
    `;
}

function printCurrentDocument(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    if (currentDocumentType !== "check") {
        const frame = document.getElementById("documentFrame");
        if (frame && frame.contentWindow) {
            frame.contentWindow.focus();
            frame.contentWindow.print();
        }
        return;
    }

    printCheck();
}

function closeSaleModal() {
    const modal = document.getElementById("saleModal");
    modal.style.display = "none";
    modal.classList.remove("invoice-mode");
    document.getElementById("saleBody").innerHTML = "Загрузка...";
}

function formatDate(dateStr) {

    if (!dateStr) return "";

    const date = new Date(dateStr);

    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const year = date.getFullYear();

    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");

    return `${day}.${month}.${year}, ${hours}:${minutes}`;
}

function printCheck() {
	const saleBody = document.getElementById("saleBody");

	if (!saleBody || !saleBody.textContent.trim()) {
		alert("Чек ещё не загрузился");
		return;
	}

	// В Electron сохраняем штатную печать на настроенный чековый принтер.
	if (window.require) {
		try {
			const { ipcRenderer } = require("electron");
			ipcRenderer.send("print-receipt");
			return;
		} catch (error) {
			console.error("Electron print is unavailable", error);
		}
	}

	printCheckInIsolatedFrame(saleBody);
}

function printCheckInIsolatedFrame(saleBody) {
	if (document.getElementById("checkPrintFrame")) return;

	const printFrame = document.createElement("iframe");
	printFrame.id = "checkPrintFrame";
	printFrame.setAttribute("title", "Печать чека");
	printFrame.style.cssText = [
		"position:fixed",
		"right:0",
		"bottom:0",
		"width:1px",
		"height:1px",
		"border:0",
		"opacity:0",
		"pointer-events:none"
	].join(";");

	const stylesheetLinks = Array.from(
		document.querySelectorAll('link[rel="stylesheet"]')
	).map(link => `<link rel="stylesheet" href="${link.href}">`).join("");

	printFrame.srcdoc = `
		<!doctype html>
		<html lang="ru">
		<head>
			<meta charset="utf-8">
			<meta name="viewport" content="width=device-width, initial-scale=1">
			${stylesheetLinks}
			<style>
				@page {
					size: A4 portrait;
					margin: 0;
				}
				html, body {
					margin: 0 !important;
					width: 100% !important;
					height: auto !important;
					min-height: 0 !important;
					overflow: visible !important;
					background: #fff !important;
				}
				body {
					display: flex !important;
					justify-content: center !important;
					align-items: flex-start !important;
					box-sizing: border-box !important;
					padding: 12mm 0 0 !important;
				}
				body *, #saleBody, #saleBody * {
					visibility: visible !important;
				}
				#saleBody {
					display: block !important;
					position: static !important;
					inset: auto !important;
					box-sizing: border-box !important;
					width: 280px !important;
					max-width: calc(100% - 20mm) !important;
					flex: 0 0 280px !important;
					height: auto !important;
					min-height: 0 !important;
					margin: 0 auto !important;
					padding: 8px !important;
					overflow: visible !important;
					font-family: "Courier New", monospace !important;
					font-size: 12px !important;
				}
				.receipt {
					position: static !important;
					width: 100% !important;
					max-width: 100% !important;
					height: auto !important;
					min-height: 0 !important;
					margin: 0 auto !important;
					break-inside: avoid !important;
					page-break-inside: avoid !important;
				}
			</style>
		</head>
		<body><main id="saleBody">${saleBody.innerHTML}</main></body>
		</html>
	`;

	const cleanup = () => {
		if (printFrame.parentNode) printFrame.remove();
	};

	printFrame.onload = async () => {
		const printWindow = printFrame.contentWindow;
		const printDocument = printFrame.contentDocument;

		if (!printWindow || !printDocument) {
			cleanup();
			alert("Не удалось подготовить чек к печати");
			return;
		}

		try {
			if (printDocument.fonts && printDocument.fonts.ready) {
				await printDocument.fonts.ready;
			}

			const images = Array.from(printDocument.images);
			await Promise.all(images.map(image => {
				if (image.complete) return Promise.resolve();
				return new Promise(resolve => {
					image.onload = resolve;
					image.onerror = resolve;
				});
			}));

			printWindow.addEventListener("afterprint", cleanup, { once: true });
			printWindow.focus();
			printWindow.print();
			setTimeout(cleanup, 1000);
		} catch (error) {
			console.error("Check print failed", error);
			cleanup();
			alert("Не удалось открыть печать чека");
		}
	};

	document.body.appendChild(printFrame);
}

async function downloadPDF() {
    try {
        const { blob, filename } = await createCurrentDocumentPdf();
        downloadBlob(blob, filename);
    } catch (error) {
        showDocumentError(error);
    }
}

function getCurrentDocumentFilename() {
    const config = documentConfig[currentDocumentType] || documentConfig.check;
    return config.filename(currentDocumentId || "document");
}

async function createCurrentDocumentPdf() {
    const config = documentConfig[currentDocumentType] || documentConfig.check;
    if (!currentDocumentId) {
        throw new Error("Документ не выбран");
    }

    const response = await fetch(config.pdfUrl(currentDocumentId), {
        credentials: "same-origin",
        headers: { "Accept": "application/pdf" }
    });

    if (!response.ok) {
        let message = "Не удалось сформировать PDF";
        const responseCopy = response.clone();
        try {
            const errorData = await response.json();
            if (errorData.error) message = errorData.error;
        } catch (_) {
            const errorText = await responseCopy.text();
            if (errorText && errorText.length < 300) message = errorText;
        }
        throw new Error(message);
    }

    const blob = await response.blob();
    if (blob.type && blob.type !== "application/pdf") {
        throw new Error("Сервер вернул файл неверного формата");
    }

    return { blob, filename: getCurrentDocumentFilename() };
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function shareCurrentDocument() {
    try {
        const { blob, filename } = await createCurrentDocumentPdf();
        const canShareFiles =
            navigator.share &&
            navigator.canShare &&
            typeof File !== "undefined";

        if (canShareFiles) {
            const file = new File([blob], filename, { type: "application/pdf" });

            if (!navigator.canShare({ files: [file] })) {
                downloadBlob(blob, filename);
                alert("На этом устройстве системная отправка недоступна. PDF сохранён — его можно отправить вручную.");
                return;
            }

            await navigator.share({
                title: (documentConfig[currentDocumentType] || documentConfig.check).title,
                files: [file]
            });
            return;
        }

        downloadBlob(blob, filename);
        alert("На этом устройстве системная отправка недоступна. PDF сохранён — его можно отправить вручную.");
    } catch (error) {
        if (error && error.name === "AbortError") return;
        showDocumentError(error);
    }
}

function showDocumentError(error) {
    console.error(error);
    alert(error && error.message ? error.message : "Не удалось подготовить документ");
}

function createInvoiceSale() {

    if (!selectedClient) {
        alert("Сначала выбери клиента");
        return;
    }

    if (cart.length === 0) {
        alert("Корзина пустая");
        return;
    }

    fetch("/sales/create-invoice", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            client_id: selectedClient,
            cart: cart,
        })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            throw new Error(data.error || "Не удалось выставить счёт");
        }

        return data;
    })
    .then(data => {

        if (!data.success) {
            alert(data.error || "Не удалось выставить счёт");
            return;
        }

        // открываем исходный счёт внутри модального окна
        openInvoiceModal(data.sale_id);

        // очищаем
        cart = [];
        renderCart();
        resetSaleAmounts();

    })
    .catch(error => {
        console.error("CREATE INVOICE ERROR:", error);
        alert(error.message || "Не удалось выставить счёт");
    });
}

let codeReader = null;
let selectedDeviceId = null;

async function openScanner() {

    const readerEl = document.getElementById("reader");
    document.getElementById("scannerModal").style.display = "flex";

    // 🔥 очищаем
    readerEl.innerHTML = "";

    // 🔥 создаём видео вручную
    const video = document.createElement("video");
    video.setAttribute("autoplay", true);
    video.setAttribute("playsinline", true);
    video.style.width = "100%";
    video.style.height = "auto";

    readerEl.appendChild(video);

    try {

        // 🔥 ВКЛЮЧАЕМ КАМЕРУ НАПРЯМУЮ
		const stream = await navigator.mediaDevices.getUserMedia({

			video: {

				facingMode: { ideal: "environment" },

				width: { ideal: 1920 },
				height: { ideal: 1080 }

			}

		});

        video.srcObject = stream;
		
		const track =
			stream.getVideoTracks()[0];

		const capabilities =
			track.getCapabilities();

		// 🔥 автофокус
		if (capabilities.focusMode) {

			track.applyConstraints({
				advanced: [
					{
						focusMode: "continuous"
					}
				]
			});
		}

		// 🔥 zoom
		if (capabilities.zoom) {

			track.applyConstraints({
				advanced: [
					{
						zoom:
							capabilities.zoom.max / 2
					}
				]
			});
		}

        // 🔥 ждём пока реально появится картинка
        await video.play();

		// 🔥 НАТИВНЫЙ СКАНЕР БРАУЗЕРА — вместо ZXing
		if (!("BarcodeDetector" in window)) {
			alert("Этот браузер не поддерживает быстрый сканер. Попробуй Chrome на Android.");
			return;
		}

		const barcodeDetector = new BarcodeDetector({
			formats: [
				"ean_13",
				"ean_8",
				"code_128",
				"code_39",
				"upc_a",
				"upc_e"
			]
		});

		let lastDetectedCode = "";
		let lastDetectedTime = 0;

		async function scanFrame() {
			try {
				const barcodes = await barcodeDetector.detect(video);

				if (barcodes.length > 0) {
					const code = barcodes[0].rawValue;
					const now = Date.now();

					if (code.length >= 8 && code.length <= 14) {

						// защита от дублей
						if (!(code === lastDetectedCode && now - lastDetectedTime < 1200)) {

							lastDetectedCode = code;
							lastDetectedTime = now;

							console.log("BARCODE DETECTOR:", code);

							const beep = document.getElementById("beepSound");
							if (beep) {
								beep.currentTime = 0;
								beep.play().catch(() => {});
							}

							if (navigator.vibrate) {
								navigator.vibrate(120);
							}

							fetch("/api/scan", {
								method: "POST",
								headers: {"Content-Type": "application/json"},
								body: JSON.stringify({ code: code })
							});
						}
					}
				}
			} catch (err) {
				console.log("SCAN FRAME ERROR:", err);
			}

			requestAnimationFrame(scanFrame);
		}

        scanFrame();

    } catch (err) {

        console.error("CAMERA ERROR:", err);
        alert("Не удалось запустить камеру");

    }
}

function closeScanner() {

    document.getElementById("scannerModal").style.display = "none";

    const video = document.querySelector("#reader video");

    if (video && video.srcObject) {
        video.srcObject.getTracks().forEach(track => track.stop());
    }

	if (codeReader) {
		try {
			codeReader.reset();
		} catch (e) {}
	}
}

function handleBarcode(code) {

    fetch("/api/barcode", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            barcode: code
        })
    })

    .then(res => res.json())

    .then(data => {

        // ✅ нашли товар
        if (data.found) {

            selectItemForSale(
                data.id,
                data.name,
                data.price,
                data.unit || "шт",
                data.gtin || "",
                data.ntin || ""
            );

        }

        // ❌ нет товара
        else {

            openAddItemModal(code);

        }

    });

}

function openAddItemModal(code) {

    document.getElementById(
        "addItemModal"
    ).style.display = "flex";

    document.getElementById(
        "newBarcode"
    ).value = code;
	
	// 🔥 загружаем категории
	fetch("/api/categories")

	.then(res => res.json())

	.then(categories => {

		let html = "";

		categories.forEach(c => {

			html += `
				<div
					class="category-option"
					onclick="selectQuickCategory(
						'${c.name}',
						'${c.markup_percent || 0}'
					)"
				>

					<div>
						<b>${c.name}</b>

						<span class="markup">
							${c.markup_percent || 0}%
						</span>
					</div>

				</div>
			`;

		});

		document.getElementById(
			"quickCategoryDropdown"
		).innerHTML = html;

	});

    // 🔥 пробуем National Catalog
    fetch("/api/barcode-info/" + code)

    .then(res => res.json())

	.then(data => {

		currentBarcodeData = data;

		if (data.name) {

			document.getElementById(
				"newName"
			).value = data.name;
			
			document.getElementById(
				"newGtin"
			).value = data.gtin || "";

			document.getElementById(
				"newNtin"
			).value = data.ntin || "";

			document.getElementById(
				"newIsMarked"
			).checked = data.is_marked || false;

		}

	});

}

function selectQuickCategory(name, markup) {

    document.getElementById(
        "newCategory"
    ).value = name;

    document.getElementById(
        "quickCategoryDropdown"
    ).style.display = "none";

    // 🔥 авто закупка
    const retail =
        parseFloat(
            document.getElementById(
                "newPrice"
            ).value
        ) || 0;

    if (retail > 0) {

        const purchase =
            retail -
            (retail * (parseFloat(markup) || 0) / 100);

        document.getElementById(
            "newPurchasePrice"
        ).value =
            Math.round(purchase);
    }

}

// 🔥 ВОТ СЮДА ВСТАВИТЬ
const quickCategoryInput =
    document.getElementById(
        "newCategory"
    );

const quickCategoryDropdown =
    document.getElementById(
        "quickCategoryDropdown"
    );

// 🔥 открыть список
quickCategoryInput.addEventListener(
    "focus",
    () => {

        quickCategoryDropdown.style.display =
            "block";

    }
);

// 🔥 открыть по клику
quickCategoryInput.addEventListener(
    "click",
    () => {

        quickCategoryDropdown.style.display =
            "block";

    }
);

// 🔥 закрыть вне блока
document.addEventListener(
    "click",
    (e) => {

        if (
            !e.target.closest(
                ".category-wrapper"
            )
        ) {

            quickCategoryDropdown.style.display =
                "none";

        }

    }
);

document.addEventListener("click", (e) => {

    if (
        !e.target.closest(".category-wrapper")
    ) {

        document.getElementById(
            "quickCategoryDropdown"
        ).style.display = "none";
    }

});

document.getElementById(
    "newCategory"
).addEventListener("focus", () => {

    document.getElementById(
        "quickCategoryDropdown"
    ).style.display = "block";

});

function saveNewItem() {

    fetch("/quick-add-item", {

        method: "POST",

        headers: {
            "Content-Type": "application/json"
        },

        body: JSON.stringify({

            name:
                document.getElementById(
                    "newName"
                ).value,

            retail_price:
                document.getElementById(
                    "newPrice"
                ).value,

            barcode:
                document.getElementById(
                    "newBarcode"
                ).value,
				
			category:
				document.getElementById(
					"newCategory"
				).value,

			unit:
				document.getElementById(
					"newUnit"
				).value,

			purchase_price:
				document.getElementById(
					"newPurchasePrice"
				).value,
				
			gtin: currentBarcodeData.gtin || "",
			ntin: currentBarcodeData.ntin || "",
			is_marked:
				currentBarcodeData.is_marked || 0,

        })

    })

    .then(res => res.json())

    .then(data => {

        if (data.success) {

            document.getElementById(
                "addItemModal"
            ).style.display = "none";

            addToCart(
                data.item.id,
                data.item.name,
                data.item.price
            );
			
			loadItems();

        }

    });

}

function closeAddItemModal() {

    document.getElementById(
        "addItemModal"
    ).style.display = "none";

}

let barcodeBuffer = "";
let lastKeyTime = 0;

document.addEventListener("keydown", function(e) {

    const now = Date.now();

    // 🔥 если пауза большая — новый скан
    if (now - lastKeyTime > 100) {
        barcodeBuffer = "";
    }

    lastKeyTime = now;

    // 🔥 если нажали Enter → код готов
    if (e.key === "Enter") {

        if (barcodeBuffer.length >= 8) {

            console.log("USB Скан:", barcodeBuffer);

            // Сканер уже передал полный код: отменяем отложенный ручной поиск.
            clearTimeout(itemSearchTimer);
            if (itemSearchController) itemSearchController.abort();

            // 🔊 пик
            const beep = document.getElementById("beepSound");
            if (beep) {
                beep.currentTime = 0;
                beep.play().catch(() => {});
            }

            handleBarcode(barcodeBuffer);
        }

        barcodeBuffer = "";
        return;
    }

    // 🔥 только цифры
    if (/[0-9]/.test(e.key)) {
        barcodeBuffer += e.key;
    }
});

document.getElementById("quantityInput").addEventListener("input", updateQuantityPreview);

document.getElementById("quantityInput").addEventListener("keydown", function(e) {
    if (e.key === "Enter") confirmQuantity();
    if (e.key === "Escape") closeQuantityModal();
});

document.getElementById("quantityModal").addEventListener("click", function(e) {
    if (e.target === this) closeQuantityModal();
});

window.addEventListener("load", function () {
    document.querySelector(".sales-page").classList.add("ready");
});

window.addEventListener("load", () => {

    loadItems();
    selectDefaultPrivateClient();

});

function switchSalesTab(tab) {

	const cartTable =
		document.getElementById("cartTableWrapper");

    const mobileCart =
        document.getElementById("mobileCart");

    const history =
        document.getElementById("salesHistoryBox");

    const cartBtn =
        document.getElementById("cartTabBtn");

    const historyBtn =
        document.getElementById("historyTabBtn");

    if (tab === "cart") {

        cartTable.style.display = "";
        mobileCart.style.display = "";
        history.style.display = "none";

        cartBtn.classList.add("active");
        historyBtn.classList.remove("active");

    } else {

        cartTable.style.display = "none";
        mobileCart.style.display = "none";
        history.style.display = "block";

        cartBtn.classList.remove("active");
        historyBtn.classList.add("active");

        loadSalesHistory();
    }
}

const salesShiftHistoryState = {
    generation: 0,
    closedPage: 0,
    closedSize: 10,
    receiptSize: 20,
    closedHasMore: false,
    closedKeys: new Set(),
    loading: null
};

async function salesHistoryJson(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.error || data.message || "Не удалось загрузить данные");
    }
    return data;
}

function salesShiftCore(item) {
    return item && item.data && typeof item.data === "object" ? item.data : (item || {});
}

function salesShiftValue(item, ...keys) {
    const core = salesShiftCore(item);
    for (const source of [item || {}, core]) {
        for (const key of keys) {
            if (source[key] !== undefined && source[key] !== null && source[key] !== "") {
                return source[key];
            }
        }
    }
    return null;
}

function salesClosedShiftItems(payload) {
    const found = [];
    const walk = value => {
        if (Array.isArray(value)) {
            value.forEach(walk);
            return;
        }
        if (!value || typeof value !== "object") return;
        if (salesShiftValue(value, "shiftNumber", "shift_number", "number") != null) {
            found.push(value);
            return;
        }
        ["history", "content", "items", "shifts", "records", "list", "data", "_embedded"]
            .forEach(key => walk(value[key]));
    };
    walk(payload?.history ?? payload);
    return found;
}

function salesShiftDate(value) {
    if (!value) return "—";
    if (value.value) return salesShiftDate(value.value);
    if (value.date && value.time) {
        const d = value.date;
        const t = value.time;
        return `${String(d.day).padStart(2, "0")}.${String(d.month).padStart(2, "0")}.${d.year} ` +
            `${String(t.hour).padStart(2, "0")}:${String(t.minute).padStart(2, "0")}`;
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
        ? String(value)
        : parsed.toLocaleString("ru-RU", { timeZone: "Asia/Almaty", dateStyle: "short", timeStyle: "short" });
}

function salesShiftMoney(value) {
    if (value == null || value === "") return "";
    if (typeof value === "object") {
        if (value.value != null) return salesShiftMoney(value.value);
        if (value.bills != null) value = Number(value.bills || 0) + Number(value.coins || 0) / 100;
    }
    const number = Number(value);
    return Number.isFinite(number)
        ? `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(number)} ₸`
        : "";
}

function renderSalesShiftCard(item, current = false) {
    const number = salesShiftValue(item, "shiftNumber", "shift_number", "number");
    const serial = salesShiftValue(item, "serialNumber", "serial_number", "znm") || "";
    const opened = salesShiftValue(item, "openShiftTime", "open_time", "openTime");
    const closed = salesShiftValue(item, "closeShiftTime", "close_time", "closeTime", "endTime");
    const count = salesShiftValue(item, "ticketCount", "ticket_count", "ticketsCount") || 0;
    const revenue = salesShiftValue(item, "netRevenue", "net_revenue", "revenue");
    const key = `${number}:${serial}`;

    return `
        <article class="sales-shift-card${current ? " is-current is-open" : ""}"
                 data-shift-card data-shift-number="${escapeHtml(number)}"
                 data-serial-number="${escapeHtml(serial)}" data-shift-key="${escapeHtml(key)}">
            <div class="sales-shift-summary" data-sales-shift-toggle role="button" tabindex="0" aria-expanded="${current ? "true" : "false"}">
                <span class="sales-shift-chevron">⌄</span>
                <div class="sales-shift-main">
                    <div class="sales-shift-title">
                        Смена №${escapeHtml(number)}
                        <span class="sales-shift-badge ${current ? "current" : "closed"}">${current ? "Текущая" : "Закрыта"}</span>
                    </div>
                    <div class="sales-shift-period">${escapeHtml(salesShiftDate(opened))}${closed ? ` — ${escapeHtml(salesShiftDate(closed))}` : " — сейчас"}</div>
                </div>
                <div class="sales-shift-totals">
                    ${revenue != null ? `<strong>${escapeHtml(salesShiftMoney(revenue))}</strong>` : ""}
                    <span>Чеков: ${escapeHtml(count)}</span>
                </div>
                ${current ? "" : `<button type="button" class="sales-shift-z" data-sales-z="${escapeHtml(number)}">Z‑отчёт</button>`}
            </div>
            <div class="sales-shift-body" ${current ? "" : "hidden"}>
                <div class="sales-shift-receipts"><div class="sales-shifts-loading">Загрузка чеков…</div></div>
                <button type="button" class="sales-receipts-more" data-sales-receipts-more hidden>Показать ещё чеки</button>
            </div>
        </article>
    `;
}

function renderSalesReceipt(item) {
    const refund = item.event_type === "refund" || item.status === "Возврат";
    const invoice = item.sale_type === "invoice";
    const id = Number(item.id);
    const amount = `${refund ? "−" : ""}${salesShiftMoney(item.total || 0)}`;
    const action = refund && !invoice
        ? `openRefundCheckModal(${id})`
        : (invoice ? `openInvoiceModal(${id})` : `openSaleModal(${id})`);
    const actionLabel = refund ? "Чек возврата" : (invoice ? "Счёт" : "Открыть чек");

    return `
        <div class="sales-receipt-row${refund ? " is-refund" : ""}">
            <div class="sales-receipt-icon">${refund ? "↩" : "▤"}</div>
            <div class="sales-receipt-main">
                <strong>${refund ? "Возврат" : "Продажа"} · чек №${escapeHtml(item.sale_number || item.id)}</strong>
                <span>${escapeHtml(item.client_name || "Частное лицо")} · ${escapeHtml(item.payment_type || "—")}</span>
            </div>
            <div class="sales-receipt-meta">
                <strong>${escapeHtml(amount)}</strong>
                <span>${escapeHtml(item.created_at_display || salesShiftDate(item.event_at || item.created_at))}</span>
            </div>
            <button type="button" class="sales-receipt-open" onclick="${action}">${actionLabel}</button>
        </div>
    `;
}

async function loadShiftReceipts(card, append = false) {
    if (!card || card.dataset.loading === "true") return;
    if (!append && card.dataset.loaded === "true") return;

    const page = append ? Number(card.dataset.receiptPage || 1) : 0;
    const list = card.querySelector(".sales-shift-receipts");
    const more = card.querySelector("[data-sales-receipts-more]");
    const params = new URLSearchParams({
        shift_number: card.dataset.shiftNumber,
        page: String(page),
        size: String(salesShiftHistoryState.receiptSize)
    });
    if (card.dataset.serialNumber) params.set("serial_number", card.dataset.serialNumber);

    card.dataset.loading = "true";
    if (append) more.disabled = true;
    try {
        const data = await salesHistoryJson(`/api/sales/history?${params.toString()}`);
        const items = Array.isArray(data) ? data : (data.items || []);
        const html = items.map(renderSalesReceipt).join("");
        if (append) list.insertAdjacentHTML("beforeend", html);
        else list.innerHTML = html || '<div class="sales-shifts-empty">В этой смене чеков нет</div>';
        card.dataset.loaded = "true";
        card.dataset.receiptPage = String(page + 1);
        more.hidden = items.length < salesShiftHistoryState.receiptSize;
    } catch (error) {
        if (!append) list.innerHTML = `<div class="sales-shifts-error">${escapeHtml(error.message)}</div>`;
    } finally {
        card.dataset.loading = "false";
        more.disabled = false;
    }
}

async function loadClosedSalesShifts(append = false, generation = salesShiftHistoryState.generation) {
    const list = document.getElementById("salesClosedShifts");
    const more = document.getElementById("salesShiftsMore");
    if (!append) {
        list.innerHTML = '<div class="sales-shifts-loading">Загрузка закрытых смен…</div>';
        salesShiftHistoryState.closedPage = 0;
        salesShiftHistoryState.closedKeys.clear();
    }
    more.disabled = true;
    try {
        const page = salesShiftHistoryState.closedPage;
        const data = await salesHistoryJson(`/api/rekassa/shifts?page=${page}&size=${salesShiftHistoryState.closedSize}`);
        if (generation !== salesShiftHistoryState.generation) return;
        const items = salesClosedShiftItems(data);
        const fresh = items.filter(item => {
            const key = `${salesShiftValue(item, "shiftNumber", "shift_number", "number")}:${salesShiftValue(item, "serialNumber", "serial_number", "znm") || ""}`;
            if (salesShiftHistoryState.closedKeys.has(key)) return false;
            salesShiftHistoryState.closedKeys.add(key);
            return true;
        });
        const html = fresh.map(item => renderSalesShiftCard(item, false)).join("");
        if (append) list.insertAdjacentHTML("beforeend", html);
        else list.innerHTML = html || '<div class="sales-shifts-empty">Закрытых смен пока нет</div>';
        salesShiftHistoryState.closedPage = page + 1;
        salesShiftHistoryState.closedHasMore = Boolean(data.has_more ?? (items.length >= salesShiftHistoryState.closedSize));
        more.hidden = !salesShiftHistoryState.closedHasMore;
    } catch (error) {
        if (!append) list.innerHTML = `<div class="sales-shifts-error">${escapeHtml(error.message)}</div>`;
        more.hidden = true;
    } finally {
        more.disabled = false;
    }
}

async function loadSalesHistory() {
    if (salesShiftHistoryState.loading) return salesShiftHistoryState.loading;
    const run = (async () => {
        const generation = ++salesShiftHistoryState.generation;
        const current = document.getElementById("salesCurrentShift");
        current.innerHTML = '<div class="sales-shifts-loading">Проверяем текущую смену…</div>';

        const statusPromise = salesHistoryJson("/api/rekassa/shift/status").catch(() => null);
        const closedPromise = loadClosedSalesShifts(false, generation);
        const status = await statusPromise;
        if (generation !== salesShiftHistoryState.generation) return;

        if (status?.shift_open && status.shift_number) {
            window.currentRekassaShiftNumber = status.shift_number;
            window.currentRekassaSerialNumber = status.serial_number || "";
            const shift = {
                ...(status.shift || {}),
                shiftNumber: status.shift_number,
                serialNumber: status.serial_number || "",
                openShiftTime: status.shift?.open_time,
                ticketCount: status.shift?.ticket_count || 0
            };
            current.innerHTML = renderSalesShiftCard(shift, true);
            loadShiftReceipts(current.querySelector("[data-shift-card]"));
        } else {
            window.currentRekassaShiftNumber = null;
            window.currentRekassaSerialNumber = "";
            current.innerHTML = '<div class="sales-shifts-empty">Смена не открыта</div>';
        }
        await closedPromise;
    })();
    salesShiftHistoryState.loading = run;
    try {
        return await run;
    } finally {
        if (salesShiftHistoryState.loading === run) salesShiftHistoryState.loading = null;
    }
}

document.getElementById("salesHistoryBox")?.addEventListener("click", event => {
    const zButton = event.target.closest("[data-sales-z]");
    if (zButton) {
        event.stopPropagation();
        window.dispatchEvent(new CustomEvent("nika:open-z-report", {
            detail: { shiftNumber: zButton.dataset.salesZ }
        }));
        return;
    }

    const moreReceipts = event.target.closest("[data-sales-receipts-more]");
    if (moreReceipts) {
        loadShiftReceipts(moreReceipts.closest("[data-shift-card]"), true);
        return;
    }

    const toggle = event.target.closest("[data-sales-shift-toggle]");
    if (toggle) {
        const card = toggle.closest("[data-shift-card]");
        const body = card.querySelector(".sales-shift-body");
        const opening = body.hidden;
        body.hidden = !opening;
        card.classList.toggle("is-open", opening);
        toggle.setAttribute("aria-expanded", String(opening));
        if (opening) loadShiftReceipts(card);
    }
});

document.getElementById("salesShiftsMore")?.addEventListener("click", () => loadClosedSalesShifts(true));

function getSaleStatusClass(status) {
    if (status === "Оплачено") return "is-paid";
    if (status === "Счёт выставлен") return "is-pending";
    if (status === "Возврат") return "is-refunded";
    return "is-neutral";
}

function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

async function confirmInvoicePayment(saleId, button) {
    if (!window.confirm("Подтвердить поступление оплаты по этому счёту?")) {
        return;
    }

    const originalText = button ? button.textContent : "";

    if (button) {
        button.disabled = true;
        button.textContent = "Подтверждаем…";
    }

    try {
        const response = await fetch("/sales/mark-paid", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ sale_id: saleId })
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok || !data.success) {
            throw new Error(data.error || "Не удалось подтвердить оплату");
        }

        await loadSalesHistory();
    } catch (error) {
        console.error("MARK PAID ERROR:", error);
        alert(error.message || "Не удалось подтвердить оплату");

        if (button && document.body.contains(button)) {
            button.disabled = false;
            button.textContent = originalText;
        }
    }
}

function payKaspiPOS() {

    if (!selectedClient) {
        alert("Сначала выбери клиента");
        return;
    }

    if (cart.length === 0) {
        alert("Корзина пустая");
        return;
    }

    let total = 0;

    cart.forEach(item => {
        total += item.price * item.qty;
    });

    fetch("/kaspi/start-payment", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            amount: total
        })
    })
    .then(res => res.json())
    .then(data => {

        if (!data.success) {
            alert(data.error || "Ошибка POS");
            return;
        }

        monitorKaspiPayment(data.processId);
    });
}

function monitorKaspiPayment(processId) {

    const timer = setInterval(() => {

        fetch("/kaspi/status/" + processId)
        .then(res => res.json())
        .then(data => {

            console.log("KASPI STATUS:", data);

            if (data.status === "success") {

                clearInterval(timer);

                document.getElementById("kaspiInput").value =
                    document.getElementById("totalAmount")
                        .innerText
                        .replace(/\D/g, '');
				
				window.lastKaspiTransactionId =
					data.transactionId;

				window.lastKaspiMethod =
					data.method || "qr";
					
                alert("Оплата Kaspi POS прошла успешно");

                pay();
                return;
            }

            if (data.status === "fail") {

                clearInterval(timer);

                alert(
                    data.message ||
                    "Оплата отменена или отклонена на терминале"
                );

                return;
            }

            if (data.status === "unknown") {

                clearInterval(timer);

                alert(
                    "Статус оплаты неизвестен. Проверь терминал и историю Kaspi перед повторной оплатой."
                );

                return;
            }

        })
        .catch(err => {

            clearInterval(timer);

            alert("Ошибка связи с Kaspi POS");

            console.error(err);
        });

    }, 2000);
}

function refundSale(id){

    if(!confirm("Оформить возврат продажи? Товар будет возвращён на склад.")){
        return;
    }

    fetch("/sales/refund/" + id,{
        method:"POST"
    })
    .then(r => r.json())
    .then(data => {

        if(data.success){

            alert("Возврат выполнен");

            loadSalesHistory();

            if(data.refund_check_available){
                openRefundCheckModal(id);
            }

        }else{

            alert(
                data.error ||
                "Ошибка возврата"
            );
        }

    })
    .catch(err => {

        console.error(err);

        alert("Ошибка связи");

    });
}

/* Предыдущая реализация управления сменой оставлена только для истории сборки.
// Управление сменой reKassa поверх существующей страницы продаж.
(() => {
    const state = { status: null, report: null, reportType: null };
    const $ = id => document.getElementById(id);
    const operationNames = {
        OPERATION_SELL: "Продажи",
        OPERATION_SELL_RETURN: "Возвраты продаж",
        OPERATION_BUY: "Покупки",
        OPERATION_BUY_RETURN: "Возвраты покупок",
        OPERATION_DEPOSIT: "Внесения",
        OPERATION_WITHDRAWAL: "Изъятия"
    };

    if (!$('shiftStrip')) return;

    function escapeHtml(value) {
        return String(value == null ? "" : value).replace(/[&<>'"]/g, char => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
        })[char]);
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
            ...options
        });
        const data = await response.json().catch(() => ({ error: "Некорректный ответ сервера" }));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || "Ошибка reKassa");
        }
        return data;
    }

    function toast(message, isError = false) {
        const node = $('shiftToast');
        node.textContent = message;
        node.className = `shift-toast show${isError ? " error" : ""}`;
        clearTimeout(toast.timer);
        toast.timer = setTimeout(() => { node.className = "shift-toast"; }, 4000);
    }

    function setBusy(button, busy, busyLabel) {
        if (!button.dataset.label) button.dataset.label = button.textContent;
        button.disabled = busy;
        button.textContent = busy ? busyLabel : button.dataset.label;
    }

    function money(value) {
        if (value == null || value === "") return "—";
        if (typeof value === "object") {
            if (value.value != null) return money(value.value);
            if (value.sum != null) return money(value.sum);
            if (value.bills != null) {
                value = Number(value.bills || 0) + Number(value.coins || 0) / 100;
            } else {
                return "—";
            }
        }
        const number = Number(value);
        return Number.isFinite(number)
            ? `${new Intl.NumberFormat("ru-RU").format(number)} ₸`
            : "—";
    }

    function dateTime(value) {
        if (!value) return "—";
        if (value.value) return dateTime(value.value);
        if (value.date && value.time) {
            const d = value.date;
            const t = value.time;
            return `${String(d.day).padStart(2, "0")}.${String(d.month).padStart(2, "0")}.${d.year} ` +
                `${String(t.hour).padStart(2, "0")}:${String(t.minute).padStart(2, "0")}:${String(t.second || 0).padStart(2, "0")}`;
        }
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime())
            ? String(value)
            : parsed.toLocaleString("ru-RU", { timeZone: "Asia/Almaty" });
    }

    function coreReport(report) {
        return report && report.data && typeof report.data === "object"
            ? report.data
            : (report || {});
    }

    function reportRows(report, type) {
        const core = coreReport(report);
        const shiftNumber = report.shiftNumber || core.shiftNumber || state.status?.shift_number || "—";
        const opened = report.openTime || core.openShiftTime || core.openTime;
        const closed = report.closeTime || core.closeShiftTime || core.closeTime;
        const operations = core.ticketOperations || report.ticketOperations || [];
        const rows = [
            ["Смена", `№ ${shiftNumber}`],
            ["Начало", dateTime(opened)],
            ...(type === "Z" ? [["Закрытие", dateTime(closed)]] : []),
            ["Выручка", money(report.revenue ?? core.revenue)],
            ["Наличные в кассе", money(core.cashSum ?? report.cashSum)]
        ];
        return { core, shiftNumber, operations, rows };
    }

    function openModal() {
        $('shiftReportModal').classList.add('open');
        $('shiftReportModal').setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        $('shiftReportModal').classList.remove('open');
        $('shiftReportModal').setAttribute('aria-hidden', 'true');
    }

    function renderReport(report, type) {
        state.report = report;
        state.reportType = type;
        const { core, shiftNumber, operations, rows } = reportRows(report, type);
        const operationsHtml = operations.length ? `
            <div class="shift-report-section">Операции</div>
            ${operations.map(item => `
                <div class="shift-report-operation">
                    <span>${escapeHtml(operationNames[item.operation] || item.operation || "Операции")}</span>
                    <strong>${escapeHtml(money(item.sum))}</strong>
                    <small>Чеков: ${escapeHtml(item.ticketsCount ?? item.operationsCount ?? 0)}</small>
                </div>
            `).join("")}
        ` : "";

        $('shiftHistoryList').hidden = true;
        $('shiftReportPaper').hidden = false;
        $('shiftReportActions').hidden = false;
        $('shiftReportTitle').textContent = `${type}‑отчёт · смена №${shiftNumber}`;
        $('shiftReportPaper').innerHTML = `
            <div class="shift-report-logo">NIKA BUSINESS</div>
            <div class="shift-report-kind">${type}‑ОТЧЁТ · СМЕНА №${escapeHtml(shiftNumber)}</div>
            ${rows.map(([label, value]) => `
                <div class="shift-report-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
            `).join("")}
            ${operationsHtml}
            <details class="shift-report-json"><summary>Технические данные reKassa</summary><pre>${escapeHtml(JSON.stringify(core, null, 2))}</pre></details>
        `;
        openModal();
    }

    function reportShareText() {
        if (!state.report) return "";
        const { rows } = reportRows(state.report, state.reportType);
        return [
            "Nika Business",
            `${state.reportType}-отчёт reKassa`,
            ...rows.map(([label, value]) => `${label}: ${value}`)
        ].join("\n");
    }

    function historyItems(payload) {
        const root = payload?.history || {};
        const embedded = root._embedded || {};
        const items = embedded.shifts || root.content || root.items || root.shifts || [];
        return Array.isArray(items) ? items : [];
    }

    async function loadStatus(showMessage = false) {
        const button = $('shiftRefreshBtn');
        button.disabled = true;
        try {
            const data = await api('/api/rekassa/shift/status');
            state.status = data;
            const open = Boolean(data.shift_open);
            window.currentRekassaShiftNumber = open ? data.shift_number : null;
            window.currentRekassaSerialNumber = open ? (data.serial_number || "") : "";
            $('shiftStripDot').classList.toggle('open', open);
            $('shiftStripTitle').textContent = open
                ? `Смена №${data.shift_number || "—"} открыта`
                : "Смена закрыта";
            $('shiftStripMeta').textContent = open
                ? `${data.shift?.ticket_count ?? 0} чеков${data.shift?.open_time ? ` · с ${dateTime(data.shift.open_time)}` : ""}`
                : "Первая фискальная продажа откроет новую смену";
            $('shiftXReportBtn').disabled = !open;
            $('shiftCloseBtn').disabled = !open;
            if (showMessage) toast('Состояние смены обновлено');

            const historyVisible = $('salesHistoryBox')?.style.display === 'block';
            if (historyVisible) loadSalesHistory();
        } catch (error) {
            window.currentRekassaShiftNumber = null;
            window.currentRekassaSerialNumber = "";
            $('shiftStripDot').classList.remove('open');
            $('shiftStripTitle').textContent = 'reKassa недоступна';
            $('shiftStripMeta').textContent = error.message;
            $('shiftXReportBtn').disabled = true;
            $('shiftCloseBtn').disabled = true;
            toast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function makeXReport() {
        const button = $('shiftXReportBtn');
        setBusy(button, true, 'Формируем…');
        try {
            const data = await api('/api/rekassa/reports/x', { method: 'POST', body: '{}' });
            renderReport(data.report, 'X');
        } catch (error) {
            toast(error.message, true);
        } finally {
            setBusy(button, false);
            button.disabled = !state.status?.shift_open;
        }
    }

    async function closeShift() {
        if (!window.confirm('Закрыть текущую смену и сформировать Z‑отчёт? Отменить закрытие нельзя.')) return;
        const button = $('shiftCloseBtn');
        setBusy(button, true, 'Закрываем…');
        try {
            const data = await api('/api/rekassa/shifts/close', { method: 'POST', body: '{}' });
            toast(data.message || 'Смена закрыта');
            renderReport(data.report, 'Z');
            await loadStatus();
            loadSalesHistory();
        } catch (error) {
            toast(error.message, true);
        } finally {
            setBusy(button, false);
            button.disabled = !state.status?.shift_open;
        }
    }

    async function showHistory() {
        state.report = null;
        state.reportType = null;
        $('shiftReportTitle').textContent = 'История Z‑отчётов';
        $('shiftReportPaper').hidden = true;
        $('shiftReportActions').hidden = true;
        $('shiftHistoryList').hidden = false;
        $('shiftHistoryList').innerHTML = '<div class="shift-history-empty">Загрузка…</div>';
        openModal();
        try {
            const data = await api('/api/rekassa/shifts?page=0&size=30');
            const items = historyItems(data).sort((a, b) =>
                Number(b.shiftNumber || 0) - Number(a.shiftNumber || 0)
            );
            $('shiftHistoryList').innerHTML = items.length
                ? items.map(item => {
                    const core = coreReport(item);
                    const number = item.shiftNumber || core.shiftNumber;
                    return `
                        <div class="shift-history-item">
                            <div class="shift-history-code">Z · ${escapeHtml(number)}</div>
                            <div class="shift-history-main">
                                <strong>Смена №${escapeHtml(number)}</strong>
                                <span>${escapeHtml(dateTime(item.closeTime || core.closeShiftTime || core.closeTime))}</span>
                            </div>
                            <button type="button" class="shift-history-open" data-shift="${escapeHtml(number)}">Открыть</button>
                        </div>
                    `;
                }).join("")
                : '<div class="shift-history-empty">Закрытых смен пока нет</div>';
        } catch (error) {
            $('shiftHistoryList').innerHTML = `<div class="shift-history-empty">${escapeHtml(error.message)}</div>`;
        }
    }

    async function openZReport(shiftNumber) {
        try {
            const data = await api(`/api/rekassa/shifts/${encodeURIComponent(shiftNumber)}/report`);
            renderReport(data.report, 'Z');
        } catch (error) {
            toast(error.message, true);
        }
    }

    function printReport() {
        document.body.classList.add('shift-report-printing');
        const cleanup = () => document.body.classList.remove('shift-report-printing');
        window.addEventListener('afterprint', cleanup, { once: true });
        window.print();
        setTimeout(cleanup, 1200);
    }

    $('shiftRefreshBtn').addEventListener('click', () => loadStatus(true));
    $('shiftXReportBtn').addEventListener('click', makeXReport);
    $('shiftCloseBtn').addEventListener('click', closeShift);
    $('shiftHistoryBtn').addEventListener('click', showHistory);
    $('shiftReportCloseBtn').addEventListener('click', closeModal);
    $('shiftReportCancelBtn').addEventListener('click', closeModal);
    $('shiftReportModal').addEventListener('click', event => {
        if (event.target === $('shiftReportModal')) closeModal();
    });
    $('shiftHistoryList').addEventListener('click', event => {
        const button = event.target.closest('[data-shift]');
        if (button) openZReport(button.dataset.shift);
    });
    $('shiftReportPrintBtn').addEventListener('click', printReport);
    $('shiftReportPdfBtn').addEventListener('click', () => {
        toast('В окне печати выберите «Сохранить как PDF»');
        setTimeout(printReport, 200);
    });
    $('shiftReportShareBtn').addEventListener('click', async () => {
        const text = reportShareText();
        try {
            if (navigator.share) {
                await navigator.share({ title: `${state.reportType}-отчёт reKassa`, text });
            } else {
                await navigator.clipboard.writeText(text);
                toast('Отчёт скопирован');
            }
        } catch (error) {
            if (error.name !== 'AbortError') toast('Не удалось поделиться отчётом', true);
        }
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') closeModal();
    });
    window.addEventListener('nika:sale-completed', () => {
        setTimeout(() => loadStatus(), 350);
    });

    loadStatus();
})();
*/

// Управление сменой reKassa: отдельные окна X, Z и истории Z.
(() => {
    const $ = id => document.getElementById(id);
    if (!$('shiftStrip')) return;

    const state = {
        status: null,
        report: null,
        reportType: null,
        cashRegister: null,
        historyPage: 0,
        historySize: 15,
        historyKeys: new Set()
    };

    const operationOrder = [
        'OPERATION_SELL',
        'OPERATION_SELL_RETURN',
        'OPERATION_BUY',
        'OPERATION_BUY_RETURN'
    ];
    const operationNames = {
        OPERATION_SELL: 'Продажа',
        OPERATION_SELL_RETURN: 'Возврат',
        OPERATION_BUY: 'Покупка',
        OPERATION_BUY_RETURN: 'Возврат покупки',
        MONEY_PLACEMENT_DEPOSIT: 'Внесение',
        MONEY_PLACEMENT_WITHDRAWAL: 'Изъятие'
    };
    const paymentNames = {
        PAYMENT_CASH: 'Наличные',
        PAYMENT_CARD: 'Карта',
        PAYMENT_CREDIT: 'Кредит',
        PAYMENT_TARE: 'Тара',
        PAYMENT_MOBILE: 'Мобильная оплата'
    };

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>'"]/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
        })[char]);
    }

    function first(...values) {
        return values.find(value => value !== undefined && value !== null && value !== '') ?? '';
    }

    async function api(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
            ...options
        });
        const data = await response.json().catch(() => ({ error: 'Некорректный ответ сервера' }));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || data.message || 'Ошибка reKassa');
        }
        return data;
    }

    function toast(message, error = false) {
        const node = $('shiftToast');
        node.textContent = message;
        node.className = `shift-toast show${error ? ' error' : ''}`;
        clearTimeout(toast.timer);
        toast.timer = setTimeout(() => { node.className = 'shift-toast'; }, 4500);
    }

    function openModal(id) {
        const modal = $(id);
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal(id) {
        const modal = $(id);
        if (!modal) return;
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
        if (id === 'shiftZModal' && !$('shiftZPaper').hidden) {
            $('shiftPinInput').value = '';
        }
    }

    function setBusy(button, busy, label) {
        if (!button.dataset.label) button.dataset.label = button.textContent;
        button.disabled = busy;
        button.textContent = busy ? label : button.dataset.label;
    }

    function coreReport(report) {
        return report && report.data && typeof report.data === 'object'
            ? report.data
            : (report || {});
    }

    function operationCode(value) {
        if (typeof value === 'string') return value;
        return ({ 0: 'OPERATION_BUY', 1: 'OPERATION_BUY_RETURN', 2: 'OPERATION_SELL', 3: 'OPERATION_SELL_RETURN' })[value] || String(value || '');
    }

    function paymentCode(value) {
        if (typeof value === 'string') return value;
        return ({ 0: 'PAYMENT_CASH', 1: 'PAYMENT_CARD', 2: 'PAYMENT_CREDIT', 3: 'PAYMENT_TARE', 4: 'PAYMENT_MOBILE' })[value] || String(value || '');
    }

    function placementCode(value) {
        if (typeof value === 'string') return value;
        return value === 1 ? 'MONEY_PLACEMENT_WITHDRAWAL' : 'MONEY_PLACEMENT_DEPOSIT';
    }

    function numberFromMoney(value) {
        if (value == null || value === '') return 0;
        if (typeof value === 'number') return value;
        if (typeof value === 'string') return Number(value.replace(/\s/g, '').replace(',', '.')) || 0;
        if (value.value != null) return numberFromMoney(value.value);
        if (value.sum != null && value.bills == null) return numberFromMoney(value.sum);
        if (value.bills != null) return Number(value.bills || 0) + Number(value.coins || 0) / 100;
        return 0;
    }

    function money(value) {
        return `${new Intl.NumberFormat('ru-RU', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(numberFromMoney(value))} ₸`;
    }

    function parseDateTime(value) {
        if (!value) return null;
        if (value.value) return parseDateTime(value.value);
        if (value.date && value.time) {
            return {
                date: `${String(value.date.day).padStart(2, '0')}-${String(value.date.month).padStart(2, '0')}-${value.date.year}`,
                time: `${String(value.time.hour).padStart(2, '0')}:${String(value.time.minute).padStart(2, '0')}:${String(value.time.second || 0).padStart(2, '0')}`
            };
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return { date: String(value), time: '—' };
        return {
            date: parsed.toLocaleDateString('ru-RU', { timeZone: 'Asia/Almaty' }).replace(/\./g, '-'),
            time: parsed.toLocaleTimeString('ru-RU', { timeZone: 'Asia/Almaty', hour12: false })
        };
    }

    function reportMeta(envelope) {
        const cash = envelope?.cash_register || state.cashRegister || state.status?.cash_register || {};
        const active = window.company || company || {};
        return {
            businessName: first(cash.business_name, active.business_name, active.name, active.title, 'Nika Business'),
            businessId: first(cash.business_id, active.business_id, active.bin, active.inn, '—'),
            address: first(cash.address, active.address, '—'),
            registrationNumber: first(cash.registration_number, '—'),
            serialNumber: first(cash.serial_number, state.status?.serial_number, '—'),
            model: first(cash.model, 'reKassa 3.0'),
            fdoTitle: first(cash.fdo_title, 'ОФД ТОО «COMRUN»'),
            fdoUrl: first(cash.fdo_url, 'https://ofd.rekassa.kz')
        };
    }

    function sumByOperation(items, code) {
        const item = (Array.isArray(items) ? items : []).find(row => operationCode(row.operation) === code);
        return item ? item.sum : 0;
    }

    function receiptLine(label, value, extra = '') {
        return `<div class="shift-receipt-line ${extra}"><span>${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div>`;
    }

    function renderReceipt(envelope, type) {
        const report = envelope.report || envelope;
        const core = coreReport(report);
        const meta = reportMeta(envelope);
        const shiftNumber = first(report.shiftNumber, core.shiftNumber, envelope.shift_number, state.status?.shift_number, '—');
        const open = parseDateTime(first(report.openTime, core.openShiftTime, core.openTime, state.status?.shift?.open_time));
        const close = parseDateTime(first(report.closeTime, core.closeShiftTime, core.closeTime));
        const operator = report.operator || core.operator || {};
        const operatorValue = first(operator.name, operator.code, '—');
        const startSums = core.startShiftNonNullableSums || report.startShiftNonNullableSums || [];
        const endSums = core.nonNullableSums || report.nonNullableSums || [];
        const ticketOperations = (core.ticketOperations || report.ticketOperations || [])
            .filter(item => Number(item.ticketsCount || 0) > 0)
            .sort((a, b) => operationOrder.indexOf(operationCode(a.operation)) - operationOrder.indexOf(operationCode(b.operation)));
        const placements = (core.moneyPlacements || report.moneyPlacements || [])
            .filter(item => Number(item.operationsCount || 0) > 0);
        const totalCount = ticketOperations.reduce((sum, item) => sum + Number(item.ticketsCount || 0), 0)
            + placements.reduce((sum, item) => sum + Number(item.operationsCount || 0), 0);

        const periodRows = `
            <div class="shift-receipt-grid">
                <span>Смена:</span><span class="value">№${escapeHtml(shiftNumber)}</span>
                <span>Кассир:</span><span class="value">${escapeHtml(operatorValue)}</span>
                <span>Начало:</span><span class="value">${escapeHtml(open?.date || '—')}</span>
                <span>Время:</span><span class="value">${escapeHtml(open?.time || '—')}</span>
                ${type === 'Z' ? `
                    <span>Конец:</span><span class="value">${escapeHtml(close?.date || '—')}</span>
                    <span>Время:</span><span class="value">${escapeHtml(close?.time || '—')}</span>
                ` : ''}
            </div>
            ${type === 'Z' && first(report.shiftDocumentNumber, core.shiftDocumentNumber)
                ? receiptLine('Документ:', first(report.shiftDocumentNumber, core.shiftDocumentNumber))
                : ''}
        `;

        const cumulative = items => operationOrder.map(code =>
            receiptLine(operationNames[code], money(sumByOperation(items, code)))
        ).join('');

        const ticketHtml = ticketOperations.map(item => {
            const code = operationCode(item.operation);
            const payments = (item.payments || []).map(payment =>
                receiptLine(paymentNames[paymentCode(payment.payment)] || paymentCode(payment.payment), money(payment.sum))
            ).join('');
            return `
                <div class="shift-receipt-block">
                    <div class="shift-receipt-operation-title">${escapeHtml(operationNames[code] || code)}</div>
                    ${receiptLine('Количество чеков', Number(item.ticketsCount || 0))}
                    ${payments}
                    ${receiptLine('Сумма', money(item.ticketsSum))}
                </div>
            `;
        }).join('');

        const placementHtml = placements.map(item => `
            <div class="shift-receipt-block">
                <div class="shift-receipt-operation-title">${escapeHtml(operationNames[placementCode(item.operation)] || placementCode(item.operation))}</div>
                ${receiptLine('Количество чеков', Number(item.operationsCount || 0))}
                ${receiptLine('Сумма', money(item.operationsSum))}
            </div>
        `).join('');

        const html = `
            <div class="shift-receipt-center">
                <div class="shift-receipt-name">${escapeHtml(meta.businessName)}</div>
                <div class="shift-receipt-id">БИН (ИИН): ${escapeHtml(meta.businessId)}</div>
                <div class="shift-receipt-address">${escapeHtml(meta.address)}</div>
            </div>
            <div class="shift-receipt-requisites">
                ${receiptLine('РНМ:', meta.registrationNumber)}
                ${receiptLine('ЗНМ:', meta.serialNumber)}
                ${receiptLine('ККМ:', meta.model)}
            </div>
            <div class="shift-receipt-kind">${type}‑отчёт</div>
            ${periodRows}
            <div class="shift-receipt-separator"></div>
            <div class="shift-receipt-section-title">Необнуляемая сумма на начало смены</div>
            ${cumulative(startSums)}
            <div class="shift-receipt-separator"></div>
            ${ticketHtml || '<div class="shift-receipt-empty">Фискальных операций в смене нет</div>'}
            ${placementHtml}
            ${receiptLine('Количество чеков за смену', totalCount, 'shift-receipt-total-count')}
            <div class="shift-receipt-separator"></div>
            <div class="shift-receipt-section-title">Необнуляемая сумма на конец смены</div>
            ${cumulative(endSums)}
            <div class="shift-receipt-section-title" style="margin-top:20px">Наличных в кассе</div>
            ${receiptLine('Сумма', money(core.cashSum || report.cashSum))}
            <div class="shift-receipt-separator"></div>
            <div class="shift-receipt-fdo">
                <div>${escapeHtml(meta.fdoTitle)}</div>
                <div>${escapeHtml(meta.fdoUrl)}</div>
            </div>
        `;

        return { html, shiftNumber, meta };
    }

    function showReport(envelope, type) {
        state.report = envelope;
        state.reportType = type;
        state.cashRegister = envelope.cash_register || state.cashRegister;
        const rendered = renderReceipt(envelope, type);
        const paper = type === 'X' ? $('shiftXPaper') : $('shiftZPaper');
        paper.innerHTML = rendered.html;
        paper.hidden = false;

        if (type === 'X') {
            $('shiftXTitle').textContent = `X‑отчёт · смена №${rendered.shiftNumber}`;
            openModal('shiftXModal');
        } else {
            $('shiftZTitle').textContent = `Z‑отчёт · смена №${rendered.shiftNumber}`;
            $('shiftZConfirm').hidden = true;
            $('shiftZActions').hidden = false;
            openModal('shiftZModal');
        }
    }

    function shareText() {
        if (!state.report) return '';
        const report = state.report.report || state.report;
        const core = coreReport(report);
        const shiftNumber = first(report.shiftNumber, core.shiftNumber, state.report.shift_number, '—');
        return [
            `${state.reportType}‑отчёт reKassa`,
            `Смена №${shiftNumber}`,
            `Наличных в кассе: ${money(core.cashSum || report.cashSum)}`
        ].join('\n');
    }

    async function loadStatus(showMessage = false) {
        const button = $('shiftRefreshBtn');
        button.disabled = true;
        try {
            const data = await api('/api/rekassa/shift/status');
            state.status = data;
            state.cashRegister = data.cash_register || state.cashRegister;
            const open = Boolean(data.shift_open);
            window.currentRekassaShiftNumber = open ? data.shift_number : null;
            window.currentRekassaSerialNumber = open ? (data.serial_number || '') : '';
            $('shiftStripDot').classList.toggle('open', open);
            $('shiftStripTitle').textContent = open ? `Смена №${data.shift_number || '—'} открыта` : 'Смена закрыта';
            $('shiftStripMeta').textContent = open
                ? `${data.shift?.ticket_count ?? 0} чеков${data.shift?.open_time ? ` · смена активна` : ''}`
                : 'Первая фискальная продажа откроет новую смену';
            $('shiftXReportBtn').disabled = !open;
            $('shiftCloseBtn').disabled = !open;
            if (showMessage) toast('Состояние смены обновлено');
            if ($('salesHistoryBox')?.style.display === 'block') loadSalesHistory();
        } catch (error) {
            window.currentRekassaShiftNumber = null;
            window.currentRekassaSerialNumber = '';
            $('shiftStripDot').classList.remove('open');
            $('shiftStripTitle').textContent = 'reKassa недоступна';
            $('shiftStripMeta').textContent = error.message;
            $('shiftXReportBtn').disabled = true;
            $('shiftCloseBtn').disabled = true;
            toast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    async function makeXReport() {
        const button = $('shiftXReportBtn');
        setBusy(button, true, 'Формируем…');
        try {
            const data = await api('/api/rekassa/reports/x', { method: 'POST', body: '{}' });
            showReport(data, 'X');
        } catch (error) {
            toast(error.message, true);
        } finally {
            setBusy(button, false);
            button.disabled = !state.status?.shift_open;
        }
    }

    function askCloseShift() {
        if (!state.status?.shift_open) return;
        $('shiftZTitle').textContent = `Закрытие смены №${state.status.shift_number || '—'}`;
        $('shiftZConfirm').hidden = false;
        $('shiftZPaper').hidden = true;
        $('shiftZActions').hidden = true;
        $('shiftCloseError').hidden = true;
        $('shiftCloseError').textContent = '';
        $('shiftPinInput').value = '';
        openModal('shiftZModal');
        setTimeout(() => $('shiftPinInput').focus(), 80);
    }

    async function confirmCloseShift() {
        const button = $('shiftConfirmCloseBtn');
        const errorBox = $('shiftCloseError');
        errorBox.hidden = true;
        setBusy(button, true, 'Закрываем смену…');
        try {
            const data = await api('/api/rekassa/shifts/close', {
                method: 'POST',
                body: JSON.stringify({ pin: $('shiftPinInput').value })
            });
            $('shiftPinInput').value = '';
            showReport(data, 'Z');
            toast(data.message || 'Смена закрыта');
            await loadStatus();
            loadSalesHistory();
        } catch (error) {
            errorBox.textContent = error.message;
            errorBox.hidden = false;
            toast(error.message, true);
            $('shiftPinInput').focus();
        } finally {
            setBusy(button, false);
        }
    }

    function historyItems(payload) {
        const items = [];
        const walk = value => {
            if (Array.isArray(value)) {
                value.forEach(walk);
                return;
            }
            if (!value || typeof value !== 'object') return;
            const core = coreReport(value);
            if (first(value.shiftNumber, value.shift_number, core.shiftNumber, core.shift_number) != null) {
                items.push(value);
                return;
            }
            ['history', 'content', 'items', 'shifts', 'records', 'list', 'data', '_embedded']
                .forEach(key => walk(value[key]));
        };
        walk(payload?.history ?? payload);
        return items;
    }

    async function showHistory(append = false) {
        const list = $('shiftHistoryList');
        const more = $('shiftHistoryMore');
        if (!append) {
            state.historyPage = 0;
            state.historyKeys.clear();
            list.innerHTML = '<div class="shift-history-empty">Загрузка…</div>';
        }
        more.disabled = true;
        openModal('shiftHistoryModal');
        try {
            const data = await api(`/api/rekassa/shifts?page=${state.historyPage}&size=${state.historySize}`);
            const items = historyItems(data).sort((a, b) => {
                const aCore = coreReport(a);
                const bCore = coreReport(b);
                return Number(first(b.shiftNumber, bCore.shiftNumber, 0)) - Number(first(a.shiftNumber, aCore.shiftNumber, 0));
            });
            const fresh = items.filter(item => {
                const core = coreReport(item);
                const key = String(first(item.shiftNumber, item.shift_number, core.shiftNumber, core.shift_number, '—'));
                if (state.historyKeys.has(key)) return false;
                state.historyKeys.add(key);
                return true;
            });
            const html = fresh.map(item => {
                const core = coreReport(item);
                const number = first(item.shiftNumber, item.shift_number, core.shiftNumber, core.shift_number, '—');
                const closed = parseDateTime(first(item.closeTime, item.close_shift_time, core.closeShiftTime, core.closeTime));
                const count = first(item.ticketCount, item.ticket_count, core.ticketCount, core.ticketsCount, 0);
                return `
                    <div class="shift-history-item">
                        <div class="shift-history-code">Z · ${escapeHtml(number)}</div>
                        <div class="shift-history-main">
                            <strong>Смена №${escapeHtml(number)}</strong>
                            <span>${escapeHtml(closed ? `${closed.date} ${closed.time}` : 'Закрытая смена')} · чеков: ${escapeHtml(count)}</span>
                        </div>
                        <button type="button" class="shift-history-open" data-shift="${escapeHtml(number)}">Открыть</button>
                    </div>
                `;
            }).join('');
            if (append) list.insertAdjacentHTML('beforeend', html);
            else list.innerHTML = html || '<div class="shift-history-empty">Закрытых смен пока нет</div>';
            state.historyPage += 1;
            more.hidden = !Boolean(data.has_more ?? (items.length >= state.historySize));
        } catch (error) {
            if (!append) list.innerHTML = `<div class="shift-history-empty">${escapeHtml(error.message)}</div>`;
            else toast(error.message, true);
            more.hidden = true;
        } finally {
            more.disabled = false;
        }
    }

    async function openHistoryReport(number, button) {
        if (button) setBusy(button, true, 'Открываем…');
        try {
            const data = await api(`/api/rekassa/shifts/${encodeURIComponent(number)}/report`);
            closeModal('shiftHistoryModal');
            showReport(data, 'Z');
        } catch (error) {
            toast(error.message, true);
        } finally {
            if (button) setBusy(button, false);
        }
    }

    function printReport(modalId) {
        const modal = $(modalId);
        modal.classList.add('print-target');
        document.body.classList.add('shift-report-printing');
        const cleanup = () => {
            document.body.classList.remove('shift-report-printing');
            modal.classList.remove('print-target');
        };
        window.addEventListener('afterprint', cleanup, { once: true });
        window.print();
        setTimeout(cleanup, 1500);
    }

    $('shiftRefreshBtn').addEventListener('click', () => loadStatus(true));
    $('shiftXReportBtn').addEventListener('click', makeXReport);
    $('shiftCloseBtn').addEventListener('click', askCloseShift);
    $('shiftHistoryBtn').addEventListener('click', showHistory);
    $('shiftConfirmCloseBtn').addEventListener('click', confirmCloseShift);
    $('shiftPinInput').addEventListener('keydown', event => {
        if (event.key === 'Enter') confirmCloseShift();
    });
    $('shiftHistoryList').addEventListener('click', event => {
        const button = event.target.closest('[data-shift]');
        if (button) openHistoryReport(button.dataset.shift, button);
    });
    $('shiftHistoryMore').addEventListener('click', () => showHistory(true));
    window.addEventListener('nika:open-z-report', event => {
        const number = event.detail?.shiftNumber;
        if (number) openHistoryReport(number, null);
    });

    document.addEventListener('click', async event => {
        const closeButton = event.target.closest('[data-shift-close]');
        if (closeButton) closeModal(closeButton.dataset.shiftClose);

        const action = event.target.closest('[data-shift-action]');
        if (!action) return;
        if (action.dataset.shiftAction === 'print') printReport(action.dataset.modal);
        if (action.dataset.shiftAction === 'pdf') {
            toast('В окне печати выберите «Сохранить как PDF»');
            setTimeout(() => printReport(action.dataset.modal), 180);
        }
        if (action.dataset.shiftAction === 'share') {
            try {
                if (navigator.share) {
                    await navigator.share({ title: `${state.reportType}‑отчёт reKassa`, text: shareText() });
                } else {
                    await navigator.clipboard.writeText(shareText());
                    toast('Отчёт скопирован');
                }
            } catch (error) {
                if (error.name !== 'AbortError') toast('Не удалось поделиться отчётом', true);
            }
        }
    });

    ['shiftXModal', 'shiftZModal', 'shiftHistoryModal'].forEach(id => {
        $(id).addEventListener('click', event => {
            if (event.target === $(id)) closeModal(id);
        });
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        ['shiftHistoryModal', 'shiftZModal', 'shiftXModal'].forEach(id => {
            if ($(id).classList.contains('open')) closeModal(id);
        });
    });
    window.addEventListener('nika:sale-completed', () => setTimeout(() => loadStatus(), 350));

    loadStatus();
})();
