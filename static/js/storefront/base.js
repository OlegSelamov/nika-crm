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
    const mobileCount = document.getElementById('sfMobileCartCount');

    if(count) count.textContent = sfQty(sfState.cart.count);
    if(mobileCount){
        mobileCount.textContent = sfQty(sfState.cart.count);
        mobileCount.hidden = Number(sfState.cart.count || 0) <= 0;
    }

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
            add.classList.add('in-cart');
            const label = add.querySelector('span');
            if(label) label.textContent = 'В корзине';
            stepper.style.display = 'grid';
            stepper.querySelector('[data-card-qty]').textContent = sfQty(qty);
        }else{
            add.classList.remove('in-cart');
            const label = add.querySelector('span');
            if(label) label.textContent = 'В корзину';
            stepper.style.display = 'grid';
            stepper.querySelector('[data-card-qty]').textContent = '1';
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

function sfSelectedCustomerType(){
    return document.querySelector('input[name="sfCustomerType"]:checked')?.value || 'private';
}

function sfRefreshCustomerTypeUI(){
    const type = sfSelectedCustomerType();
    const isBusiness = type === 'business';

    document.querySelectorAll('[data-customer-type-card]').forEach(card=>{
        card.classList.toggle('active', card.dataset.customerTypeCard === type);
    });

    const businessFields = document.getElementById('sfBusinessFields');
    if(businessFields) businessFields.style.display = isBusiness ? '' : 'none';

    const nameLabel = document.getElementById('sfCustomerNameLabel');
    const iinLabel = document.getElementById('sfCustomerIinBinLabel');
    if(nameLabel) nameLabel.textContent = isBusiness ? 'Контактное лицо' : 'ФИО';
    if(iinLabel) iinLabel.textContent = isBusiness ? 'БИН / ИИН' : 'ИИН (необязательно)';
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

async function sfPrefillCheckout(){
    try{
        const data = await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/profile-data`);
        if(!data.authenticated) return;
        const p=data.profile||{};
        const set=(id,value)=>{const el=document.getElementById(id);if(el && value && !el.value)el.value=value};
        const type=p.customer_type||'private';
        const radio=document.querySelector(`input[name="sfCustomerType"][value="${type}"]`);
        if(radio) radio.checked=true;
        set('sfCustomerName',p.full_name); set('sfCustomerPhone',p.phone); set('sfCustomerEmail',p.email);
        set('sfCustomerIinBin',p.iin_bin); set('sfCustomerCompany',p.company_name);
        set('sfCustomerLegalAddress',p.legal_address); set('sfCustomerAddress',p.delivery_address);
        sfRefreshCustomerTypeUI();
    }catch(e){}
}

function sfOpenCheckout(){
    if(!sfState.cart.items.length){
        sfToast('Корзина пуста', true);
        return;
    }

    sfPrefillCheckout();
    document.getElementById('sfCartOverlay').classList.remove('open');
    document.getElementById('sfCheckoutOverlay').classList.add('open');
    document.body.classList.add('sf-lock');
    sfRefreshCustomerTypeUI();
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
    fd.set('customer_type', sfSelectedCustomerType());
    fd.set('customer_name', document.getElementById('sfCustomerName').value.trim());
    fd.set('phone', document.getElementById('sfCustomerPhone').value.trim());
    fd.set('email', document.getElementById('sfCustomerEmail').value.trim());
    fd.set('iin_bin', document.getElementById('sfCustomerIinBin').value.trim());
    fd.set('company_name', document.getElementById('sfCustomerCompany').value.trim());
    fd.set('legal_address', document.getElementById('sfCustomerLegalAddress').value.trim());
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

document.querySelectorAll('input[name="sfCustomerType"]').forEach(input=>{
    input.addEventListener('change', sfRefreshCustomerTypeUI);
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


/* MOBILE NAV */
function sfSyncMobileNav(){
    const params = new URLSearchParams(window.location.search);
    const kind = params.get('kind');
    const hash = window.location.hash;
    const active = (kind === 'products' || hash === '#sfCatalogStart') ? 'catalog' : 'home';
    document.querySelectorAll('[data-mobile-nav]').forEach(item=>{
        item.classList.toggle('active', item.dataset.mobileNav === active);
    });
}
document.addEventListener('DOMContentLoaded', sfSyncMobileNav);
window.addEventListener('hashchange', sfSyncMobileNav);


/* Mobile storefront conveniences */
document.addEventListener('click', event=>{
    const focusSearch = event.target.closest('[data-focus-search]');
    if(focusSearch){
        document.getElementById('sfLiveSearch')?.focus();
        document.querySelector('.sf-mobile-search-wrap')?.scrollIntoView({behavior:'smooth',block:'start'});
        return;
    }
    const favorite = event.target.closest('[data-favorite]');
    if(favorite){
        event.preventDefault(); event.stopPropagation();
        sfToggleFavorite(favorite);
    }
});


/* CUSTOMER PROFILE + FAVORITES */
function sfCustomerClose(){
  document.querySelectorAll('.sf-customer-overlay.open').forEach(x=>x.classList.remove('open'));
  document.body.classList.remove('sf-lock');
}
function sfCustomerOpen(id){
  sfCustomerClose();
  document.getElementById(id)?.classList.add('open');
  document.body.classList.add('sf-lock');
}
function sfAuthHtml(message='Войдите, чтобы видеть историю и сохранять данные'){
 return `<div class="sf-auth-card"><h3>Личный кабинет</h3><p>${message}</p>
 <div class="sf-auth-tabs"><button class="active" data-auth-mode="login">Войти</button><button data-auth-mode="register">Регистрация</button></div>
 <div class="sf-customer-error" id="sfAuthError"></div><div id="sfAuthNameWrap" style="display:none"><input id="sfAuthName" placeholder="Ваше имя"></div>
 <input id="sfAuthPhone" inputmode="tel" placeholder="Телефон">
 <input id="sfAuthPassword" type="password" placeholder="Пароль">
 <button class="sf-primary" id="sfAuthSubmit">Войти</button></div>`;
}
let sfAuthMode='login';
function sfBindAuth(){
 document.querySelectorAll('[data-auth-mode]').forEach(b=>b.onclick=()=>{
   sfAuthMode=b.dataset.authMode;
   document.querySelectorAll('[data-auth-mode]').forEach(x=>x.classList.toggle('active',x===b));
   document.getElementById('sfAuthNameWrap').style.display=sfAuthMode==='register'?'':'none';
   document.getElementById('sfAuthSubmit').textContent=sfAuthMode==='register'?'Зарегистрироваться':'Войти';
 });
 const submit=document.getElementById('sfAuthSubmit');
 if(submit) submit.onclick=async()=>{
   const fd=new FormData();
   fd.set('phone',document.getElementById('sfAuthPhone').value);
   fd.set('password',document.getElementById('sfAuthPassword').value);
   if(sfAuthMode==='register')fd.set('name',document.getElementById('sfAuthName').value);
   try{
    const err=document.getElementById('sfAuthError'); if(err){err.classList.remove('show');err.textContent=''}
    await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/${sfAuthMode}`,{method:'POST',body:fd});
    sfToast(sfAuthMode==='register'?'Профиль создан':'Вход выполнен');
    await sfLoadProfile();
   }catch(e){
    const err=document.getElementById('sfAuthError');
    if(err){err.textContent=e.message;err.classList.add('show')}
    sfToast(e.message,true)
   }
 };
}
async function sfLoadProfile(){
 sfCustomerOpen('sfProfileOverlay');
 const root=document.getElementById('sfProfileContent');
 root.innerHTML='<div class="sf-loading">Загрузка…</div>';
 try{
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/profile-data`);
  if(!data.authenticated){root.innerHTML=sfAuthHtml();sfBindAuth();return}
  const p=data.profile||{};
  root.innerHTML=`
   <div class="sf-profile-card"><div class="sf-profile-avatar">${sfEscape((p.full_name||'К').charAt(0))}</div><div class="sf-profile-identity"><small>Постоянный клиент</small><b>${sfEscape(p.full_name||'Клиент')}</b><span>+${sfEscape(p.phone||'')}</span></div><button class="sf-profile-edit-toggle" id="spfEditToggle">Реквизиты</button></div>
   <div class="sf-profile-stats">
      <div><strong>${(data.stats||{}).orders||0}</strong><span>заказов</span></div>
      <div><strong>${sfMoney((data.stats||{}).spent||0)}</strong><span>покупки</span></div>
      <div><strong>${(data.stats||{}).upcoming||0}</strong><span>предстоит</span></div>
   </div>
   <div class="sf-profile-form sf-profile-form-collapsed" id="sfProfileForm">
    <input id="spfName" value="${sfEscape(p.full_name||'')}" placeholder="ФИО / контактное лицо">
    <input id="spfEmail" value="${sfEscape(p.email||'')}" placeholder="Email">
    <select id="spfType"><option value="private" ${p.customer_type==='private'?'selected':''}>Физическое лицо</option><option value="business" ${p.customer_type==='business'?'selected':''}>ИП / ТОО</option></select>
    <input id="spfIin" value="${sfEscape(p.iin_bin||'')}" placeholder="ИИН / БИН">
    <input id="spfCompany" value="${sfEscape(p.company_name||'')}" placeholder="Название организации">
    <input id="spfLegal" value="${sfEscape(p.legal_address||'')}" placeholder="Юридический адрес">
    <input id="spfDelivery" value="${sfEscape(p.delivery_address||'')}" placeholder="Адрес доставки">
    <button class="sf-primary" id="spfSave">Сохранить данные</button>
   </div>
   <div class="sf-profile-tabs"><button class="active" data-profile-tab="orders">Заказы <i>${data.orders.length}</i></button><button data-profile-tab="bookings">Записи <i>${data.bookings.length}</i></button><button data-profile-tab="documents">Документы <i>${data.documents.length}</i></button></div>
   <div id="sfProfileHistory"></div>
   <button class="sf-logout" id="sfLogout">Выйти из профиля</button>`;
  document.getElementById('spfEditToggle').onclick=()=>document.getElementById('sfProfileForm').classList.toggle('sf-profile-form-collapsed');
  const histories={orders:data.orders,bookings:data.bookings,documents:data.documents};
  const renderHistory=type=>{
    const rows=histories[type]||[];
    const box=document.getElementById('sfProfileHistory');
    if(!rows.length){box.innerHTML='<div class="sf-empty-profile">Пока ничего нет</div>';return}
    box.innerHTML=rows.map(x=>type==='orders'?
      `<button class="sf-history-row sf-history-button" data-customer-order="${x.id}"><div><b>Заказ №${x.id}</b><span>${(x.created_at||'').slice(0,10)} · ${sfEscape(x.order_status||'new')}</span></div><strong>${sfMoney(x.total_amount)} ›</strong></button>`:
      type==='documents'?
      `<button class="sf-history-row sf-history-button" data-customer-document="${x.customer_url||''}"><div><b>${sfEscape(x.title||'Документ')}</b><span>${x.document_date||''} · ${sfEscape(x.document_number||'')}</span></div><strong>${x.amount?sfMoney(x.amount):'Открыть'} ›</strong></button>`:
      `<div class="sf-history-row sf-booking-history"><div><b>${sfEscape(x.service_name||'Запись №'+x.id)}</b><span>${x.booking_date||''} · ${(x.booking_time||'').slice(0,5)} · ${sfEscape(x.status||'new')}</span></div><div class="sf-booking-actions">${!['cancelled','rejected','completed'].includes(x.status)?`<button data-reschedule-booking="${x.id}">Перенести</button><button class="danger" data-cancel-booking="${x.id}">Отменить</button>`:''}</div></div>`).join('');
  };
  renderHistory('orders');
  document.querySelectorAll('[data-profile-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-profile-tab]').forEach(x=>x.classList.toggle('active',x===b));renderHistory(b.dataset.profileTab)});
  document.getElementById('spfSave').onclick=async()=>{
    const fd=new FormData();
    [['full_name','spfName'],['email','spfEmail'],['customer_type','spfType'],['iin_bin','spfIin'],['company_name','spfCompany'],['legal_address','spfLegal'],['delivery_address','spfDelivery']].forEach(([k,id])=>fd.set(k,document.getElementById(id).value));
    try{await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/profile`,{method:'POST',body:fd});sfToast('Данные сохранены')}catch(e){sfToast(e.message,true)}
  };
  document.getElementById('sfLogout').onclick=async()=>{await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/logout`,{method:'POST'});sfLoadProfile()};
 }catch(e){root.innerHTML='<div class="sf-empty-profile">Не удалось загрузить профиль</div>'}
}
async function sfLoadFavorites(){
 sfCustomerOpen('sfFavoritesOverlay');
 const root=document.getElementById('sfFavoritesContent');root.innerHTML='<div class="sf-loading">Загрузка…</div>';
 try{
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/favorites/data`);
  if(!data.authenticated){root.innerHTML=sfAuthHtml('Войдите, чтобы избранное сохранялось на всех устройствах');sfBindAuth();return}
  if(!data.items.length){root.innerHTML='<div class="sf-empty-profile">В избранном пока ничего нет</div>';return}
  root.innerHTML='<div class="sf-favorites-list">'+data.items.map(x=>`<button class="sf-favorite-row" data-favorite-product="${x.id}"><span>${x.image?`<img src="${sfEscape(x.image)}">`:'♡'}</span><div><b>${sfEscape(x.name)}</b><strong>${sfMoney(x.price)}</strong><small>Подробнее ›</small></div></button>`).join('')+'</div>';
 }catch(e){root.innerHTML='<div class="sf-empty-profile">Не удалось загрузить избранное</div>'}
}
async function sfToggleFavorite(button){
 try{
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/favorites/${button.dataset.favorite}`,{method:'POST'});
  button.classList.toggle('active',data.active);button.textContent=data.active?'♥':'♡';
 }catch(e){if(e.message.includes('Войдите'))sfLoadProfile();else sfToast(e.message,true)}
}
document.addEventListener('click',e=>{
 if(e.target.closest('[data-open-profile]')){sfLoadProfile();return}
 if(e.target.closest('[data-open-favorites]')){sfLoadFavorites();return}
 if(e.target.closest('[data-close-customer]')){sfCustomerClose();return}
});


async function sfOpenFavoriteProduct(itemId){
  const favorites=document.getElementById('sfFavoritesOverlay');
  const wasOpen=favorites?.classList.contains('open');
  await sfOpenProduct(itemId);
  const product=document.getElementById('sfProductOverlay');
  if(product){
    product.classList.add('sf-product-over-favorites');
    product.dataset.returnFavorites=wasOpen?'1':'';
  }
}
async function sfOpenCustomerOrder(orderId){
 try{
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/order/${orderId}`);
  const o=data.order;
  const html=`<div class="sf-order-detail">
   <div class="sf-order-detail-top"><span>Заказ №${o.id}</span><strong>${sfMoney(o.total_amount)}</strong></div>
   <div class="sf-order-statuses"><span>${sfEscape(o.order_status||'new')}</span><span>${sfEscape(o.payment_status||'unpaid')}</span></div>
   <div class="sf-order-items">${data.items.map(i=>`<div><span>${sfEscape(i.name)} × ${sfQty(i.quantity)}</span><b>${sfMoney(i.total)}</b></div>`).join('')}</div>
   ${o.address?`<p><b>Адрес:</b> ${sfEscape(o.address)}</p>`:''}
   ${o.comment?`<p><b>Комментарий:</b> ${sfEscape(o.comment)}</p>`:''}
   <button class="sf-primary" data-repeat-order="${o.id}">Повторить заказ</button>
  </div>`;
  const box=document.getElementById('sfProfileHistory');box.innerHTML='<button class="sf-history-back" id="sfHistoryBack">← К списку заказов</button>'+html;
  document.getElementById('sfHistoryBack').onclick=()=>sfLoadProfile();
 }catch(e){sfToast(e.message,true)}
}
document.addEventListener('click',e=>{
 const fp=e.target.closest('[data-favorite-product]');
 if(fp){e.preventDefault();sfOpenFavoriteProduct(fp.dataset.favoriteProduct);return}
 const order=e.target.closest('[data-customer-order]');
 if(order){e.preventDefault();sfOpenCustomerOrder(order.dataset.customerOrder);return}
});


async function sfRepeatCustomerOrder(id){
 try{
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/order/${id}/repeat`,{method:'POST'});
  if(data.cart) sfApplyCart(data.cart);
  sfToast(data.skipped?`Добавлено: ${data.added}. Недоступно: ${data.skipped}`:'Товары добавлены в корзину');
  sfCustomerClose();
  sfOpenCart();
 }catch(e){sfToast(e.message,true)}
}
async function sfCancelCustomerBooking(id){
 if(!confirm('Отменить эту запись?')) return;
 try{
  await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/booking/${id}/cancel`,{method:'POST'});
  sfToast('Запись отменена');sfLoadProfile();
 }catch(e){sfToast(e.message,true)}
}
async function sfRescheduleCustomerBooking(id){
 const box=document.getElementById('sfProfileHistory');
 const today=new Date().toISOString().slice(0,10);
 box.innerHTML=`<button class="sf-history-back" id="sfBookingBack">← Назад</button><div class="sf-reschedule-card"><h3>Перенести запись</h3><label>Новая дата<input type="date" id="sfMoveDate" min="${today}" value="${today}"></label><div id="sfMoveSlots" class="sf-move-slots"></div></div>`;
 document.getElementById('sfBookingBack').onclick=()=>sfLoadProfile();
 const load=async()=>{
  const d=document.getElementById('sfMoveDate').value;
  const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/booking/${id}/slots?date=${encodeURIComponent(d)}`);
  const slots=document.getElementById('sfMoveSlots');
  slots.innerHTML=data.slots.length?data.slots.map(t=>`<button data-move-time="${t}">${t}</button>`).join(''):'<p>Свободного времени нет</p>';
 };
 document.getElementById('sfMoveDate').onchange=load; await load();
}
async function sfSubmitReschedule(id,time){
 const fd=new FormData();fd.set('date',document.getElementById('sfMoveDate').value);fd.set('time',time);
 try{await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/customer/booking/${id}/reschedule`,{method:'POST',body:fd});sfToast('Запись перенесена');sfLoadProfile()}catch(e){sfToast(e.message,true)}
}
let sfMovingBookingId=null;
document.addEventListener('click',e=>{
 const repeat=e.target.closest('[data-repeat-order]');if(repeat){sfRepeatCustomerOrder(repeat.dataset.repeatOrder);return}
 const cancel=e.target.closest('[data-cancel-booking]');if(cancel){sfCancelCustomerBooking(cancel.dataset.cancelBooking);return}
 const move=e.target.closest('[data-reschedule-booking]');if(move){sfMovingBookingId=move.dataset.rescheduleBooking;sfRescheduleCustomerBooking(sfMovingBookingId);return}
 const mt=e.target.closest('[data-move-time]');if(mt&&sfMovingBookingId){sfSubmitReschedule(sfMovingBookingId,mt.dataset.moveTime);return}
 const doc=e.target.closest('[data-customer-document]');if(doc&&doc.dataset.customerDocument){window.open(doc.dataset.customerDocument,'_blank');return}
});


/* STOREFRONT SHARING */
async function sfNativeShare({title,text,url}){
    if(navigator.share){
        try{
            await navigator.share({title,text,url});
            return true;
        }catch(error){
            if(error?.name === 'AbortError') return false;
        }
    }
    const value = [text,url].filter(Boolean).join('\n');
    try{
        await navigator.clipboard.writeText(value);
        sfToast('Ссылка скопирована');
        return true;
    }catch(error){
        window.prompt('Скопируйте ссылку', url || value);
        return true;
    }
}
async function sfShareCurrentProduct(){
    const product=sfState.product;
    if(!product) return;
    const url=new URL(window.location.href);
    url.searchParams.set('product',product.id);
    url.hash='';
    await sfNativeShare({
        title:product.name || document.title,
        text:`${product.name || 'Товар'} — ${sfMoney(product.price || 0)}`,
        url:url.toString()
    });
}
async function sfShareCurrentCart(){
    try{
        const data=await sfJson(`/s/${encodeURIComponent(SF_SLUG)}/cart/share`,{method:'POST'});
        await sfNativeShare({
            title:'Корзина',
            text:'Посмотрите мою корзину',
            url:data.url
        });
    }catch(error){
        sfToast(error.message,true);
    }
}
document.getElementById('sfPmShare')?.addEventListener('click',sfShareCurrentProduct);
document.getElementById('sfShareCart')?.addEventListener('click',sfShareCurrentCart);

document.addEventListener('DOMContentLoaded',()=>{
    const params=new URLSearchParams(window.location.search);
    const product=params.get('product');
    if(product && /^\d+$/.test(product)){
        sfOpenProduct(Number(product)).catch(()=>{});
    }
    if(params.get('shared_cart')==='1'){
        setTimeout(()=>sfOpenCart(),120);
    }
});
