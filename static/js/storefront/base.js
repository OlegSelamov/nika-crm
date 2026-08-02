const SF_PATH_PARTS = window.location.pathname.split('/').filter(Boolean);
const SF_SLUG = decodeURIComponent(SF_PATH_PARTS[0] === 's' ? (SF_PATH_PARTS[1] || '') : '');
const sfState = {
    cart: {items:[], count:0, total:0},
    product: null,
    modalQty: 1
};

function sfApplyStoreConfig(data={}){
    const brand = String(data.brand_color || '').trim();
    if(/^#[0-9a-f]{6}$/i.test(brand)){
        document.documentElement.style.setProperty('--brand', brand);
    }
}

function sfMoney(value){
    return new Intl.NumberFormat('ru-RU',{
        maximumFractionDigits:0
    }).format(Number(value || 0)) + ' ₸';
}

function sfQty(value){
    const n = Number(value || 0);
    return Number.isInteger(n)
        ? String(n)
        : String(n).replace('.', ',');
}

function sfEscape(value){
    return String(value ?? '')
        .replaceAll('&','&amp;')
        .replaceAll('<','&lt;')
        .replaceAll('>','&gt;')
        .replaceAll('"','&quot;')
        .replaceAll("'",'&#039;');
}

function sfToast(message, error=false){
    const el = document.getElementById('sfToast');
    if(!el) return;
    el.textContent = message;
    el.classList.toggle('error', error);
    el.classList.add('show');
    clearTimeout(window.__sfToastTimer);
    window.__sfToastTimer = setTimeout(()=>{
        el.classList.remove('show');
    }, 1700);
}

async function sfJson(url, options={}){
    const response = await fetch(url, options);
    const contentType = response.headers.get('content-type') || '';

    if(!contentType.includes('application/json')){
        const text = await response.text();
        throw new Error(text || 'Сервер вернул некорректный ответ');
    }

    const data = await response.json();

    if(!response.ok || data.ok === false){
        throw new Error(data.error || 'Ошибка запроса');
    }

    return data;
}

/* CART */
async function sfLoadCart(){
    const data = await sfJson(
        `/s/${encodeURIComponent(SF_SLUG)}/cart/data`,
        {headers:{'X-Requested-With':'XMLHttpRequest'}}
    );
    sfState.cart = data;
    sfApplyStoreConfig(data);
    sfRenderCart();
    sfSyncProductCards();
    return data;
}

function sfCartQuantity(itemId){
    const item = sfState.cart.items.find(x => Number(x.id) === Number(itemId));
    return item ? Number(item.quantity) : 0;
}

function sfRenderCart(){
    const body = document.getElementById('sfCartBody');
    const foot = document.getElementById('sfCartFoot');
    const count = document.getElementById('sfCartCount');

    if(count) count.textContent = sfQty(sfState.cart.count);

    if(!sfState.cart.items.length){
        body.innerHTML = `
            <div class="sf-cart-empty">
                <div>
                    <b>Корзина пуста</b>
                    <span>Добавь товары из каталога — они появятся здесь.</span>
                </div>
            </div>
        `;
        foot.style.display = 'none';
        return;
    }

    body.innerHTML = sfState.cart.items.map(item => `
        <article class="sf-cart-item">
            ${item.image
                ? `<img class="sf-cart-item-img" src="${sfEscape(item.image)}" alt="">`
                : `<div class="sf-cart-item-img"></div>`
            }

            <div>
                <div class="sf-cart-item-name">${sfEscape(item.name)}</div>
                <div class="sf-cart-item-sub">
                    ${sfMoney(item.price)} / ${sfEscape(item.unit)}
                </div>

                <div class="sf-cart-controls">
                    <div class="sf-stepper">
                        <button type="button" data-cart-minus="${item.id}">−</button>
                        <span>${sfQty(item.quantity)}</span>
                        <button type="button" data-cart-plus="${item.id}">+</button>
                    </div>
                    <button class="sf-remove" type="button" data-cart-remove="${item.id}">
                        Удалить
                    </button>
                </div>
            </div>

            <div class="sf-cart-item-total">${sfMoney(item.line_total)}</div>
        </article>
    `).join('');

    document.getElementById('sfCartTotal').textContent = sfMoney(sfState.cart.total);
    foot.style.display = 'block';
}

async function sfSetCartQuantity(itemId, quantity){
    const fd = new FormData();
    fd.set('item_id', String(itemId));

    if(quantity <= 0){
        fd.set('remove', '1');
    }else{
        fd.set('quantity', String(quantity));
    }

    const data = await sfJson(
        `/s/${encodeURIComponent(SF_SLUG)}/cart/update`,
        {
            method:'POST',
            body:fd,
            headers:{'X-Requested-With':'XMLHttpRequest'}
        }
    );

    sfState.cart = data;
    sfRenderCart();
    sfSyncProductCards();
    return data;
}

async function sfAddToCart(itemId, quantity=1){
    const fd = new FormData();
    fd.set('item_id', String(itemId));
    fd.set('quantity', String(quantity));

    const data = await sfJson(
        `/s/${encodeURIComponent(SF_SLUG)}/cart/add`,
        {
            method:'POST',
            body:fd,
            headers:{'X-Requested-With':'XMLHttpRequest'}
        }
    );

    sfState.cart = data;
    sfRenderCart();
    sfSyncProductCards();
    return data;
}

function sfOpenCart(){
    document.getElementById('sfProductOverlay').classList.remove('open');
    document.getElementById('sfCartOverlay').classList.add('open');
    document.body.classList.add('sf-lock');
}

function sfCloseCart(){
    document.getElementById('sfCartOverlay').classList.remove('open');
    document.body.classList.remove('sf-lock');
}

/* PRODUCT CARDS */
function sfSyncProductCards(){
    document.querySelectorAll('[data-item-card]').forEach(card=>{
        const itemId = Number(card.dataset.itemCard);
        const qty = sfCartQuantity(itemId);
        const add = card.querySelector('[data-card-add]');
        const stepper = card.querySelector('[data-card-stepper]');

        if(!add || !stepper) return;

        if(qty > 0){
            add.style.display = 'none';
            stepper.style.display = 'grid';
            stepper.querySelector('[data-card-qty]').textContent = sfQty(qty);
        }else{
            add.style.display = '';
            stepper.style.display = 'none';
        }
    });
}

/* PRODUCT MODAL */
async function sfOpenProduct(itemId){
    try{
        const data = await sfJson(
            `/s/${encodeURIComponent(SF_SLUG)}/item/${itemId}/data`,
            {headers:{'X-Requested-With':'XMLHttpRequest'}}
        );

        sfState.product = data.item;
        sfState.modalQty = 1;
        sfRenderProductModal();

        document.getElementById('sfCartOverlay').classList.remove('open');
        document.getElementById('sfProductOverlay').classList.add('open');
        document.body.classList.add('sf-lock');
    }catch(error){
        sfToast(error.message, true);
    }
}

function sfRenderProductModal(){
    const item = sfState.product;
    if(!item) return;

    document.getElementById('sfPmCategory').textContent =
        item.category || (item.item_type === 'service' ? 'Услуга' : 'Товар');

    document.getElementById('sfPmTitle').textContent = item.name;
    document.getElementById('sfPmPrice').textContent = sfMoney(item.price);
    document.getElementById('sfPmDescription').textContent =
        item.description || 'Описание пока не добавлено.';

    const stock = document.getElementById('sfPmStock');
    stock.classList.remove('out');

    const serviceMode = item.service_sale_mode || 'order';

    if(item.item_type === 'service'){
        if(serviceMode === 'booking'){
            stock.textContent = `${item.booking_duration_minutes || 60} минут`;
        }else if(serviceMode === 'request'){
            stock.textContent = 'Услуга по заявке';
        }else{
            stock.textContent = 'Можно заказать онлайн';
        }
    }else if(item.stock === null){
        stock.textContent = 'В наличии';
    }else if(item.stock > 0){
        stock.textContent = `В наличии: ${sfQty(item.stock)} ${item.unit}`;
    }else{
        stock.textContent = 'Нет в наличии';
        stock.classList.add('out');
    }

    const images = item.images || [];
    const main = document.getElementById('sfPmMain');
    const thumbs = document.getElementById('sfPmThumbs');

    if(images.length){
        main.innerHTML = `<img id="sfPmMainImage" src="${sfEscape(images[0])}" alt="">`;
        thumbs.innerHTML = images.map((image,index)=>`
            <img class="sf-pm-thumb ${index===0?'active':''}"
                 src="${sfEscape(image)}"
                 data-modal-image="${sfEscape(image)}">
        `).join('');
    }else{
        main.innerHTML = `<div class="sf-pm-placeholder">□</div>`;
        thumbs.innerHTML = '';
    }

    document.getElementById('sfPmQty').textContent = '1';

    const productControls = document.getElementById('sfPmProductControls');
    const serviceControls = document.getElementById('sfPmServiceControls');

    const bookingButton = document.getElementById('sfPmBooking');
    const requestButton = document.getElementById('sfPmRequest');

    if(item.item_type === 'service'){
        if(serviceMode === 'booking'){
            productControls.style.display = 'none';
            serviceControls.style.display = '';
            bookingButton.style.display = '';
            requestButton.style.display = 'none';
            bookingButton.href = `/s/${encodeURIComponent(SF_SLUG)}/booking/${item.id}`;
        }else if(serviceMode === 'request'){
            productControls.style.display = 'none';
            serviceControls.style.display = '';
            bookingButton.style.display = 'none';
            requestButton.style.display = '';
        }else{
            productControls.style.display = '';
            serviceControls.style.display = 'none';
            document.getElementById('sfPmAdd').disabled = false;
            document.getElementById('sfPmBuy').disabled = false;
            document.getElementById('sfPmAdd').style.opacity = '1';
            document.getElementById('sfPmBuy').style.opacity = '1';
        }
    }else{
        productControls.style.display = '';
        serviceControls.style.display = 'none';

        const disabled = item.stock !== null && item.stock <= 0;
        document.getElementById('sfPmAdd').disabled = disabled;
        document.getElementById('sfPmBuy').disabled = disabled;
        document.getElementById('sfPmAdd').style.opacity = disabled ? '.45' : '1';
        document.getElementById('sfPmBuy').style.opacity = disabled ? '.45' : '1';
    }
}

function sfCloseProduct(){
    document.getElementById('sfProductOverlay').classList.remove('open');
    document.body.classList.remove('sf-lock');
}

function sfModalStep(delta){
    const item = sfState.product;
    if(!item) return;
    if(item.item_type === 'service' && (item.service_sale_mode || 'order') !== 'order') return;

    let next = Math.max(1, sfState.modalQty + delta);

    // Ограничение по остатку применяется только к физическим товарам.
    // Для услуги в режиме order количество можно менять свободно.
    if(item.item_type !== 'service' && item.stock !== null){
        next = Math.min(next, Math.max(1, Number(item.stock)));
    }

    sfState.modalQty = next;
    document.getElementById('sfPmQty').textContent = sfQty(next);
}


/* CHECKOUT */
function sfSelectedDelivery(){
    return document.querySelector('input[name="sfDeliveryMethod"]:checked')?.value || 'pickup';
}

function sfRefreshDeliveryUI(){
    const method = sfSelectedDelivery();

    document.querySelectorAll('[data-delivery-card]').forEach(card=>{
        card.classList.toggle(
            'active',
            card.dataset.deliveryCard === method
        );
    });

    const address = document.getElementById('sfAddressField');
    if(address){
        address.style.display = method === 'delivery' ? '' : 'none';
    }

    sfRefreshCheckoutTotal();
}

function sfRefreshCheckoutTotal(){
    const method = sfSelectedDelivery();
    const subtotal = Number(sfState.cart.total || 0);
    const deliveryPrice =
        method === 'delivery'
            ? Number(sfState.cart.delivery_price || 0)
            : 0;

    document.getElementById('sfCheckoutSubtotal').textContent =
        sfMoney(subtotal);

    document.getElementById('sfCheckoutDelivery').textContent =
        deliveryPrice > 0 ? sfMoney(deliveryPrice) : 'Бесплатно';

    document.getElementById('sfCheckoutTotal').textContent =
        sfMoney(subtotal + deliveryPrice);
}

function sfOpenCheckout(){
    if(!sfState.cart.items.length){
        sfToast('Корзина пуста', true);
        return;
    }

    document.getElementById('sfCartOverlay').classList.remove('open');
    document.getElementById('sfCheckoutOverlay').classList.add('open');
    document.body.classList.add('sf-lock');
    sfRefreshDeliveryUI();

    setTimeout(()=>{
        document.getElementById('sfCustomerName')?.focus();
    }, 120);
}

function sfCloseCheckout(){
    document.getElementById('sfCheckoutOverlay').classList.remove('open');
    document.body.classList.remove('sf-lock');
}

async function sfSubmitCheckout(){
    const button = document.getElementById('sfCheckoutSubmit');
    const method = sfSelectedDelivery();

    const fd = new FormData();
    fd.set('customer_name', document.getElementById('sfCustomerName').value.trim());
    fd.set('phone', document.getElementById('sfCustomerPhone').value.trim());
    fd.set('delivery_method', method);
    fd.set(
        'address',
        method === 'delivery'
            ? document.getElementById('sfCustomerAddress').value.trim()
            : ''
    );
    fd.set('comment', document.getElementById('sfOrderComment').value.trim());

    button.disabled = true;
    const oldText = button.textContent;
    button.textContent = 'Отправляем заказ…';

    try{
        const data = await sfJson(
            `/s/${encodeURIComponent(SF_SLUG)}/checkout-ajax`,
            {
                method:'POST',
                body:fd,
                headers:{'X-Requested-With':'XMLHttpRequest'}
            }
        );

        sfState.cart = {items:[],count:0,total:0};
        sfRenderCart();
        sfSyncProductCards();

        document.getElementById('sfCheckoutOverlay').classList.remove('open');
        document.getElementById('sfSuccessNumber').textContent =
            `Заказ №${data.order.id}`;
        document.getElementById('sfSuccessOverlay').classList.add('open');

        document.getElementById('sfOrderComment').value = '';
        document.getElementById('sfCustomerAddress').value = '';
    }catch(error){
        sfToast(error.message, true);
    }finally{
        button.disabled = false;
        button.textContent = oldText;
    }
}

function sfCloseSuccess(){
    document.getElementById('sfSuccessOverlay').classList.remove('open');
    document.body.classList.remove('sf-lock');
}

document.querySelectorAll('input[name="sfDeliveryMethod"]').forEach(input=>{
    input.addEventListener('change', sfRefreshDeliveryUI);
});

document.getElementById('sfOpenCheckout')?.addEventListener('click', sfOpenCheckout);
document.getElementById('sfCheckoutSubmit')?.addEventListener('click', sfSubmitCheckout);

document.getElementById('sfCheckoutOverlay')?.addEventListener('click', event=>{
    if(event.target === event.currentTarget){
        sfCloseCheckout();
    }
});

document.getElementById('sfSuccessOverlay')?.addEventListener('click', event=>{
    if(event.target === event.currentTarget){
        sfCloseSuccess();
    }
});


/* SEARCH */
function sfApplySearch(){
    const input = document.getElementById('sfLiveSearch');
    const clear = document.getElementById('sfSearchClear');
    const query = (input.value || '').trim().toLocaleLowerCase('ru-RU');

    clear.classList.toggle('show', Boolean(query));

    let visible = 0;

    document.querySelectorAll('[data-item-card]').forEach(card=>{
        const haystack = (card.dataset.search || '').toLocaleLowerCase('ru-RU');
        const show = !query || haystack.includes(query);
        card.style.display = show ? '' : 'none';
        if(show) visible += 1;
    });

    document.querySelectorAll('[data-catalog-section]').forEach(section=>{
        const hasVisible = [...section.querySelectorAll('[data-item-card]')]
            .some(card => card.style.display !== 'none');
        section.style.display = hasVisible ? '' : 'none';
    });

    const empty = document.getElementById('sfSearchEmpty');
    if(empty) empty.classList.toggle('show', visible === 0);
}

/* EVENTS */
document.addEventListener('click', async event=>{
    const openProduct = event.target.closest('[data-open-product]');
    if(openProduct){
        event.preventDefault();
        sfOpenProduct(Number(openProduct.dataset.openProduct));
        return;
    }

    const cardAdd = event.target.closest('[data-card-add]');
    if(cardAdd){
        try{
            await sfAddToCart(Number(cardAdd.dataset.cardAdd), 1);
            sfToast('Добавлено в корзину');
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    const cardMinus = event.target.closest('[data-card-minus]');
    if(cardMinus){
        const id = Number(cardMinus.dataset.cardMinus);
        try{
            await sfSetCartQuantity(id, sfCartQuantity(id) - 1);
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    const cardPlus = event.target.closest('[data-card-plus]');
    if(cardPlus){
        const id = Number(cardPlus.dataset.cardPlus);
        try{
            await sfSetCartQuantity(id, sfCartQuantity(id) + 1);
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    const cartMinus = event.target.closest('[data-cart-minus]');
    if(cartMinus){
        const id = Number(cartMinus.dataset.cartMinus);
        try{
            await sfSetCartQuantity(id, sfCartQuantity(id) - 1);
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    const cartPlus = event.target.closest('[data-cart-plus]');
    if(cartPlus){
        const id = Number(cartPlus.dataset.cartPlus);
        try{
            await sfSetCartQuantity(id, sfCartQuantity(id) + 1);
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    const cartRemove = event.target.closest('[data-cart-remove]');
    if(cartRemove){
        try{
            await sfSetCartQuantity(Number(cartRemove.dataset.cartRemove), 0);
        }catch(error){
            sfToast(error.message, true);
        }
        return;
    }

    if(event.target.closest('[data-open-cart]')){
        sfOpenCart();
        return;
    }

    if(event.target.closest('[data-close-cart]')){
        sfCloseCart();
        return;
    }

    if(event.target.closest('[data-close-product]')){
        sfCloseProduct();
        return;
    }

    if(event.target.closest('[data-close-checkout]')){
        sfCloseCheckout();
        return;
    }

    if(event.target.closest('[data-close-success]')){
        sfCloseSuccess();
        return;
    }

    const thumb = event.target.closest('[data-modal-image]');
    if(thumb){
        document.getElementById('sfPmMainImage').src = thumb.dataset.modalImage;
        document.querySelectorAll('.sf-pm-thumb').forEach(x=>x.classList.remove('active'));
        thumb.classList.add('active');
        return;
    }
});

document.getElementById('sfPmMinus')?.addEventListener('click',()=>sfModalStep(-1));
document.getElementById('sfPmPlus')?.addEventListener('click',()=>sfModalStep(1));

document.getElementById('sfPmAdd')?.addEventListener('click', async()=>{
    if(!sfState.product) return;
    try{
        await sfAddToCart(sfState.product.id, sfState.modalQty);
        sfToast('Добавлено в корзину');
        sfCloseProduct();
    }catch(error){
        sfToast(error.message, true);
    }
});

document.getElementById('sfPmBuy')?.addEventListener('click', async()=>{
    if(!sfState.product) return;
    try{
        await sfAddToCart(sfState.product.id, sfState.modalQty);
        sfOpenCart();
    }catch(error){
        sfToast(error.message, true);
    }
});

document.getElementById('sfPmRequest')?.addEventListener('click', async()=>{
    if(!sfState.product) return;
    try{
        await sfAddToCart(sfState.product.id, 1);
        sfOpenCart();
    }catch(error){
        sfToast(error.message, true);
    }
});

document.getElementById('sfProductOverlay')?.addEventListener('click',event=>{
    if(event.target === event.currentTarget) sfCloseProduct();
});
document.getElementById('sfCartOverlay')?.addEventListener('click',event=>{
    if(event.target === event.currentTarget) sfCloseCart();
});

const sfSearch = document.getElementById('sfLiveSearch');
const sfClear = document.getElementById('sfSearchClear');

sfSearch?.addEventListener('input', sfApplySearch);
sfClear?.addEventListener('click',()=>{
    sfSearch.value = '';
    sfSearch.focus();
    sfApplySearch();
});

document.addEventListener('keydown',event=>{
    if(event.key === 'Escape'){
        sfCloseProduct();
        sfCloseCart();
        sfCloseCheckout();
        sfCloseSuccess();
    }
});

sfLoadCart().catch(error=>{
    console.error('Cart init:', error);
});
