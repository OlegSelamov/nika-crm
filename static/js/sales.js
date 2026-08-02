let cart = [];
let selectedClientData = null;
let selectedClient = null;
let currentBarcodeData = {};
let currentDocumentType = "check";
let pendingQuantityItem = null;

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

    currentDocumentType = "invoice";

    const modal = document.getElementById("saleModal");
    const body = document.getElementById("saleBody");
    const title = document.getElementById("saleTitle");
    const saveBtn = document.getElementById("saveDocumentBtn");

    title.innerText = "Счёт на оплату";
    title.dataset.saleId = id;

    if (saveBtn) saveBtn.style.display = "none";

    modal.classList.add("invoice-mode");
    modal.style.display = "flex";
    body.innerHTML = `
        <iframe
            id="invoiceFrame"
            src="/docs/invoice/${id}"
            style="width:100%;height:100%;min-height:65vh;border:0;background:white;"
        ></iframe>
    `;
}

function printCurrentDocument() {
    if (currentDocumentType === "invoice") {
        const frame = document.getElementById("invoiceFrame");
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

    const printContents =
        document.getElementById(
            "saleBody"
        ).innerHTML;

    const original =
        document.body.innerHTML;

    document.body.innerHTML = `
        <div style="
            width:58mm;
            margin:0 auto;
            font-family:Arial;
            font-size:13px;
        ">
            ${printContents}
        </div>
    `;

	if (window.require) {

		const { ipcRenderer } = require('electron');

		setTimeout(() => {

			ipcRenderer.send('print-receipt');

		}, 500);

		setTimeout(() => {

			document.body.innerHTML = original;
			location.reload();

		}, 1500);

	} else {

		window.print();

		document.body.innerHTML = original;

		location.reload();
	}
}	

function downloadPDF() {

    const element = document.getElementById("saleBody");

    // 🔥 делаем чек узким и центрируем
    element.style.width = "302px";
    element.style.margin = "0 auto";
    element.style.fontFamily = "Courier New, monospace";
    element.style.fontSize = "12px";
    element.style.display = "block";

    const opt = {
        margin: 0, // 🔥 убираем боковые отступы
        filename: 'check.pdf',
        image: { type: 'jpeg', quality: 1 },
        html2canvas: { 
            scale: 2,
            useCORS: true
        },
        jsPDF: {
            unit: 'mm',
            format: [80, 200],
            orientation: 'portrait'
        }
    };

    html2pdf().set(opt).from(element).save().then(() => {

        // возвращаем как было
        element.style.width = "";
        element.style.margin = "";
        element.style.fontFamily = "";
        element.style.fontSize = "";
        element.style.display = "";

    });
}

function createInvoiceSale() {

    if (!selectedClient) {
        alert("Сначала выбери клиента");
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
    .then(res => res.json())
    .then(data => {

        if (!data.success) {
            alert("Ошибка");
            return;
        }

        // открываем исходный счёт внутри модального окна
        openInvoiceModal(data.sale_id);

        // очищаем
        cart = [];
        renderCart();
        resetSaleAmounts();

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

function loadSalesHistory() {

    fetch("/api/sales/history")

    .then(res => res.json())

    .then(data => {

        let html = "";
		let mobileHtml = "";

        data.forEach(sale => {

            html += `
                <tr>

                    <td>${sale.sale_number || sale.id}</td>

                    <td>
                        ${formatDate(sale.created_at)}
                    </td>

                    <td>
                        ${sale.client_name || "-"}
                    </td>

                    <td>
                        ${sale.total || 0} ₸
                    </td>

                    <td>
                        ${sale.payment_type || "-"}
                    </td>

                    <td>

                        <div class="history-actions">

                            <button
                                onclick="openSaleModal(${sale.id})"
                                class="mini-doc-btn"
                            aria-label="Чек">
                                <img src="/static/icons/receipt.png" alt="">
                            </button>

                            <button
                                onclick="window.open('/docs/nakladnaya/${sale.id}', '_blank')"
                                class="mini-doc-btn"
                            aria-label="Накладная">
                                <img src="/static/icons/invoice-waybill.png" alt="">
                            </button>

                            <button
                                onclick="window.open('/docs/schet-factura/${sale.id}', '_blank')"
                                class="mini-doc-btn"
                            aria-label="Счёт-фактура">
                                <img src="/static/icons/invoice.png" alt="">
                            </button>

                            <button
                                onclick="window.open('/docs/act/${sale.id}', '_blank')"
                                class="mini-doc-btn"
                            aria-label="Акт">
                                <img src="/static/icons/act.png" alt="">
                            </button>
							
							<button
								onclick="refundSale(${sale.id})"
								class="mini-doc-btn"
                            aria-label="Возврат">
                                <img src="/static/icons/refund (1).png" alt="">
                            </button>

                        </div>

                    </td>

                </tr>
            `;
			
			mobileHtml += `

			<div class="mobile-sale-card">

				<div class="mobile-sale-top">

					<div class="mobile-sale-client">
						${sale.client_name || "-"}
					</div>

					<div class="mobile-sale-sum">
						${sale.total || 0} ₸
					</div>

				</div>

				<div class="mobile-sale-date">
					${formatDate(sale.created_at)}
				</div>

				<div class="mobile-sale-actions">

					<button
						onclick="openSaleModal(${sale.id})"
						class="mini-doc-btn"
					aria-label="Чек">
						<img src="/static/icons/receipt.png" alt="">
					</button>

					<button
						onclick="window.open('/docs/nakladnaya/${sale.id}', '_blank')"
						class="mini-doc-btn"
					aria-label="Накладная">
						<img src="/static/icons/invoice-waybill.png" alt="">
					</button>

					<button
						onclick="window.open('/docs/schet-factura/${sale.id}', '_blank')"
						class="mini-doc-btn"
					aria-label="Счёт-фактура">
						<img src="/static/icons/invoice.png" alt="">
					</button>

					<button
						onclick="window.open('/docs/act/${sale.id}', '_blank')"
						class="mini-doc-btn"
					aria-label="Акт">
						<img src="/static/icons/act.png" alt="">
					</button>
					
					<button
						onclick="refundSale(${sale.id})"
						class="mini-doc-btn"
					aria-label="Возврат">
						<img src="/static/icons/refund.png" alt="">
					</button>

				</div>

			</div>
			`;
        });

        document.getElementById(
            "salesHistory"
        ).innerHTML = html;
		
		document.getElementById(
			"mobileSalesHistory"
		).innerHTML = mobileHtml;

    });
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

    if(!confirm("Сделать возврат через Kaspi POS?")){
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
