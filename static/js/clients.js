let currentClientsTab = 'active';
let clientLookupTimer = null;
let clientLookupController = null;

function switchClientsTab(tab) {
    currentClientsTab = tab;
    document.querySelectorAll('.clients-tab').forEach(btn => btn.classList.toggle('is-active', btn.dataset.tab === tab));
    document.querySelectorAll('.clients-panel').forEach(panel => panel.classList.toggle('is-active', panel.dataset.panel === tab));

    const deleted = tab === 'deleted';
    document.getElementById('clientsSectionTitle').textContent = deleted ? 'Удалённые клиенты' : 'Активные клиенты';
    document.getElementById('clientsSectionNote').textContent = deleted
        ? 'Восстановите клиента или удалите его безвозвратно'
        : 'Откройте карточку клиента или измените данные прямо из списка';

    filterClients();
}

function filterClients() {
    const query = (document.getElementById('clientSearch').value || '').trim().toLowerCase();
    const panel = document.querySelector(`.clients-panel[data-panel="${currentClientsTab}"]`);
    const records = panel ? panel.querySelectorAll('.client-record') : [];
    const unique = new Set();
    let visibleCount = 0;

    records.forEach(record => {
        const visible = !query || (record.dataset.search || '').includes(query);
        record.style.display = visible ? '' : 'none';
        if (visible) {
            const key = record.dataset.id || record.querySelector('.client-main strong')?.textContent.trim() + '|' + record.querySelector('.client-main small')?.textContent.trim();
            if (!unique.has(key)) { unique.add(key); visibleCount++; }
        }
    });

    document.getElementById('clientsVisibleCount').textContent = visibleCount;
    const empty = document.getElementById('clientsSearchEmpty');
    empty.hidden = !(query && visibleCount === 0);
}

function identifierDigits(value) {
    return String(value || '').replace(/\D/g, '').slice(0, 12);
}

function lookupStatusElement(context) {
    return document.getElementById(context === 'card' ? 'clientCardLookupStatus' : 'clientLookupStatus');
}

function setClientLookupStatus(context, message = '', state = '') {
    const element = lookupStatusElement(context);
    if (!element) return;
    element.textContent = message;
    element.className = `client-lookup-status${state ? ` is-${state}` : ''}`;
}

function clientLookupTarget(context, field) {
    if (context === 'card') return document.querySelector(`[data-client-field="${field}"]`);
    return document.getElementById('clientForm')?.elements?.[field] || null;
}

function applyClientLookupData(context, data) {
    const fields = ['company_name', 'full_name', 'address', 'phone'];
    let changed = false;
    fields.forEach(field => {
        const target = clientLookupTarget(context, field);
        const value = String(data?.[field] || '').trim();
        if (target && value && !String(target.value || '').trim()) {
            target.value = value;
            changed = true;
        }
    });
    if (context === 'card' && changed) scheduleClientCardSave();
}

async function runClientIdentifierLookup(input, context) {
    const identifier = identifierDigits(input.value);
    input.value = identifier;

    clearTimeout(clientLookupTimer);
    if (clientLookupController) clientLookupController.abort();
    if (!identifier) {
        setClientLookupStatus(context);
        return;
    }
    if (identifier.length < 12) {
        setClientLookupStatus(context, `Введите ещё ${12 - identifier.length} цифр`);
        return;
    }

    clientLookupTimer = setTimeout(async () => {
        clientLookupController = new AbortController();
        setClientLookupStatus(context, 'Ищем данные…', 'loading');
        try {
            const response = await fetch('/api/clients/lookup', {
                method: 'POST',
                headers: {'Accept': 'application/json', 'Content-Type': 'application/json'},
                body: JSON.stringify({identifier}),
                signal: clientLookupController.signal,
            });
            const payload = await response.json();
            if (identifierDigits(input.value) !== identifier) return;
            if (!response.ok) throw new Error(payload.message || 'Не удалось проверить ИИН/БИН');

            if (payload.found) {
                applyClientLookupData(context, payload.data || {});
                const state = payload.source === 'local' ? 'warning' : 'success';
                setClientLookupStatus(context, payload.message || 'Данные подставлены', state);
            } else {
                setClientLookupStatus(context, payload.message || 'Данные не найдены', 'warning');
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                setClientLookupStatus(context, error.message || 'Ошибка поиска', 'error');
            }
        }
    }, 450);
}

function openClientModal(record = null) {
    const modal = document.getElementById('clientModal');
    const form = document.getElementById('clientForm');
    form.reset();
    setClientLookupStatus('form');

    if (record) {
        const d = record.dataset;
        form.action = `/clients/${d.id}/edit`;
        document.getElementById('clientModalTitle').textContent = 'Редактировать клиента';
        document.getElementById('clientModalNote').textContent = 'Измените данные и сохраните клиента';
        document.getElementById('clientSubmitBtn').textContent = 'Сохранить изменения';

        form.elements.company_name.value = d.companyName || '';
        form.elements.full_name.value = d.fullName || '';
        form.elements.iin.value = d.iin || '';
        form.elements.contract_number.value = d.contractNumber || '';
        form.elements.contract_date.value = normalizeDateValue(d.contractDate || '');
        form.elements.phone.value = d.phone || '';
        form.elements.address.value = d.address || '';
        form.elements.status.value = d.status || 'Новый';
        form.elements.category.value = d.category || 'Клиент';
        form.elements.payment.value = d.payment || 'Не оплачено';
        form.elements.comment.value = d.comment || '';
    } else {
        form.action = '/clients/add';
        document.getElementById('clientModalTitle').textContent = 'Новый клиент';
        document.getElementById('clientModalNote').textContent = 'Заполните основные данные клиента';
        document.getElementById('clientSubmitBtn').textContent = 'Сохранить клиента';
        form.elements.status.value = 'Новый';
        form.elements.category.value = 'Клиент';
        form.elements.payment.value = 'Не оплачено';
    }

    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('client-modal-open');
    setTimeout(() => (record ? form.elements.full_name : form.elements.iin).focus(), 80);
}

function normalizeDateValue(value) {
    if (!value) return '';
    const match = String(value).match(/^\d{4}-\d{2}-\d{2}/);
    return match ? match[0] : '';
}

function closeClientModal() {
    const modal = document.getElementById('clientModal');
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('client-modal-open');
}



document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('clientModal');
    if (modal && modal.parentElement !== document.body) {
        document.body.appendChild(modal);
    }
});

document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeClientModal();
});

function mountNikaDataModal(id) {
    const modal = document.getElementById(id);
    if (modal && modal.parentElement !== document.body) document.body.appendChild(modal);
    return modal;
}
function openCatalogDataModal() {
    const modal = mountNikaDataModal('catalogDataModal');
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('nika-data-modal-open');
}
function closeCatalogDataModal() {
    const modal = document.getElementById('catalogDataModal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nika-data-modal-open');
}
function openClientsDataModal() {
    const modal = mountNikaDataModal('clientsDataModal');
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('nika-data-modal-open');
}
function closeClientsDataModal() {
    const modal = document.getElementById('clientsDataModal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('nika-data-modal-open');
}
function updateCatalogDataFile(input) {
    updateNikaDataFileName(input, 'catalogDataFileName');
}
function updateClientsDataFile(input) {
    updateNikaDataFileName(input, 'clientsDataFileName');
}
function updateNikaDataFileName(input, labelId) {
    const label = document.getElementById(labelId);
    const file = input && input.files ? input.files[0] : null;
    if (!label) return;
    label.textContent = file ? file.name : 'Выберите Excel-файл';
}
function showNikaDataResult(resultId, type, message) {
    const result = document.getElementById(resultId);
    if (!result) return;
    result.className = 'nika-data-result ' + (type === 'success' ? 'is-success' : 'is-error');
    result.innerHTML = message;
}
async function submitNikaDataImport(formId, url, resultId) {
    const form = document.getElementById(formId);
    if (!form) return;
    const input = form.querySelector('input[type="file"]');
    const file = input && input.files ? input.files[0] : null;
    if (!file) {
        showNikaDataResult(resultId, 'error', 'Сначала выберите Excel-файл.');
        return;
    }
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
        showNikaDataResult(resultId, 'error', 'Поддерживается только файл формата .xlsx');
        return;
    }

    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Импортируем…';
    const result = document.getElementById(resultId);
    if (result) {
        result.className = 'nika-data-result';
        result.textContent = '';
    }

    try {
        const response = await fetch(url, { method: 'POST', body: new FormData(form) });
        const raw = await response.text();
        let data;
        try { data = raw ? JSON.parse(raw) : {}; }
        catch (_) { throw new Error(raw || 'Сервер вернул некорректный ответ'); }

        if (!response.ok || !data.success) {
            throw new Error(data.message || data.error || 'Ошибка импорта');
        }

        const errors = Array.isArray(data.errors) ? data.errors : [];
        let html = `Создано: <b>${data.created || 0}</b><br>` +
                   `Обновлено: <b>${data.updated || 0}</b><br>` +
                   `Пропущено: <b>${data.skipped || 0}</b><br>` +
                   `Ошибок: <b>${errors.length}</b>`;
        if (errors.length) {
            const errorLines = errors.slice(0, 8).map(function(error) {
                if (typeof error === 'string') return error;
                const row = error && error.row ? `Строка ${error.row}: ` : '';
                const message = error && error.message ? error.message : JSON.stringify(error);
                return row + message;
            });
            html += `<br><br><b>Причины:</b><br><small>${errorLines.join('<br>')}</small>`;
        }
        showNikaDataResult(resultId, 'success', html);
        if (!errors.length) setTimeout(() => window.location.reload(), 1100);
    } catch (error) {
        showNikaDataResult(resultId, 'error', error.message || 'Не удалось выполнить импорт');
    } finally {
        submit.disabled = false;
        submit.textContent = 'Начать импорт';
    }
}
function attachNikaDropzone(zone) {
    const input = zone.querySelector('input[type="file"]');
    if (!input) return;

    ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.add('is-dragover');
    }));
    ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
        event.preventDefault();
        event.stopPropagation();
        zone.classList.remove('is-dragover');
    }));
    zone.addEventListener('drop', event => {
        const files = event.dataTransfer && event.dataTransfer.files;
        if (!files || !files.length) return;
        try {
            const transfer = new DataTransfer();
            transfer.items.add(files[0]);
            input.files = transfer.files;
        } catch (_) {
            try { input.files = files; } catch (__){ return; }
        }
        input.dispatchEvent(new Event('change', { bubbles: true }));
    });
}
document.addEventListener('DOMContentLoaded', () => {
    mountNikaDataModal('catalogDataModal');
    mountNikaDataModal('clientsDataModal');

    const catalogInput = document.getElementById('catalogDataFileInput');
    if (catalogInput) catalogInput.addEventListener('change', () => updateCatalogDataFile(catalogInput));
    const clientsInput = document.getElementById('clientsDataFileInput');
    if (clientsInput) clientsInput.addEventListener('change', () => updateClientsDataFile(clientsInput));

    document.getElementById('catalogDataImportForm')?.addEventListener('submit', event => {
        event.preventDefault();
        submitNikaDataImport('catalogDataImportForm', '/items/import', 'catalogDataImportResult');
    });
    document.getElementById('clientsDataImportForm')?.addEventListener('submit', event => {
        event.preventDefault();
        submitNikaDataImport('clientsDataImportForm', '/clients/import', 'clientsDataImportResult');
    });

    document.querySelectorAll('.nika-data-dropzone').forEach(attachNikaDropzone);
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        closeCatalogDataModal();
        closeClientsDataModal();
    }
});

let clientCardId = null;
let clientCardData = null;
let clientCardEditMode = false;
let clientCardSaveTimer = null;
let clientCardSaveSequence = 0;

function moneyKz(value){ return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(value||0)) + ' ₸'; }

async function openClientCard(clientId, editMode = false){
    if (!clientId) return;
    setClientLookupStatus('card');
    clientCardId = Number(clientId);
    clientCardEditMode = false;
    const modal = document.getElementById('clientCardModal');
    if (modal.parentElement !== document.body) document.body.appendChild(modal);
    modal.classList.add('is-open');
    modal.classList.remove('is-editing');
    modal.setAttribute('aria-hidden','false');
    document.body.classList.add('client-card-open');
    document.getElementById('clientCardLoading').classList.add('is-visible');
    document.querySelectorAll('.client-card-panel').forEach(p=>p.classList.remove('is-active'));
    document.querySelector('[data-card-panel="overview"]').classList.add('is-active');
    document.querySelectorAll('.client-card-tab').forEach(t=>t.classList.toggle('is-active',t.dataset.cardTab==='overview'));
    setClientCardSaveState('Просмотр','');
    try{
        const response = await fetch(`/api/client/${clientCardId}`, {headers:{'Accept':'application/json'}});
        const data = await response.json();
        if(!response.ok || data.status==='error') throw new Error(data.message || 'Не удалось загрузить клиента');
        clientCardData = data;
        renderClientCard(data);
        if(editMode) enableClientCardEdit();
    }catch(error){
        document.getElementById('clientCardLoading').textContent = error.message;
    }
}

function renderClientCard(data){
    const c=data.client||{}; const deals=Array.isArray(data.deals)?data.deals:[];
    document.getElementById('clientCardLoading').classList.remove('is-visible');
    document.getElementById('clientCardName').textContent=c.full_name||'Без имени';
    document.getElementById('clientCardCompany').textContent=c.company_name||'Без организации';
    const avatar=document.getElementById('clientCardAvatar');
    avatar.innerHTML=c.photo?`<img src="${escapeHtml(c.photo)}" alt="">`:escapeHtml((c.full_name||c.company_name||'К').slice(0,1).toUpperCase());
    updateClientCardStatus(c.status||'Новый');
    document.querySelectorAll('[data-client-field]').forEach(el=>{ const key=el.dataset.clientField; el.value=key==='contract_date'?normalizeDateValue(c[key]||''):(c[key]||''); el.disabled=true; });
    const total=deals.reduce((sum,s)=>sum+Number(s.total_amount||0),0);
    const paid=deals.reduce((sum,s)=>sum+Number(s.paid_amount||(s.status==='Оплачено'?s.total_amount:0)||0),0);
    document.getElementById('clientCardTotal').textContent=moneyKz(total);
    document.getElementById('clientCardPaid').textContent=moneyKz(paid);
    document.getElementById('clientCardDebt').textContent=moneyKz(Math.max(0,total-paid));
    document.getElementById('clientCardSalesCount').textContent=deals.length;
    document.getElementById('clientCardSales').innerHTML=deals.length?deals.map(s=>`<article class="client-card-sale" onclick="openSaleModal(${Number(s.id)})"><div><b>Продажа #${escapeHtml(String(s.sale_number||s.id))}</b><small>${escapeHtml(formatClientSaleDate(s.created_at))} · ${escapeHtml(s.status||'')}</small></div><strong>${moneyKz(s.total_amount)}</strong></article>`).join(''):'<div class="client-card-empty">Продаж пока нет</div>';
    const photos=String(c.comment_photos||'').split('|').filter(Boolean);
    document.getElementById('clientCardGallery').innerHTML=photos.length?photos.map(src=>`<img src="${escapeHtml(src)}" alt="Фото клиента">`).join(''):'<div class="client-card-empty">Фотографий пока нет</div>';
    document.getElementById('clientCardEditBtn').textContent='Редактировать';
}

function enableClientCardEdit(){
    if(!clientCardId) return;
    clientCardEditMode=true;
    const modal=document.getElementById('clientCardModal');
    modal.classList.add('is-editing');
    document.querySelectorAll('[data-client-field]').forEach(el=>el.disabled=false);
    document.getElementById('clientCardEditBtn').textContent='Готово';
    document.getElementById('clientCardEditBtn').onclick=finishClientCardEdit;
    setClientCardSaveState('Редактирование','');
    document.querySelector('[data-client-field="full_name"]')?.focus();
}

async function finishClientCardEdit(){
    clearTimeout(clientCardSaveTimer);
    await saveClientCardNow();
    clientCardEditMode=false;
    document.getElementById('clientCardModal').classList.remove('is-editing');
    document.querySelectorAll('[data-client-field]').forEach(el=>el.disabled=true);
    const btn=document.getElementById('clientCardEditBtn'); btn.textContent='Редактировать'; btn.onclick=enableClientCardEdit;
    setClientCardSaveState('Просмотр','');
}

function scheduleClientCardSave(){
    if(!clientCardEditMode) return;
    clearTimeout(clientCardSaveTimer);
    setClientCardSaveState('Есть изменения','is-saving');
    clientCardSaveTimer=setTimeout(saveClientCardNow,650);
}

async function saveClientCardNow(){
    if(!clientCardId || !clientCardEditMode) return;
    const payload={}; document.querySelectorAll('[data-client-field]').forEach(el=>payload[el.dataset.clientField]=el.value);
    if(!payload.full_name.trim()){ setClientCardSaveState('Укажите ФИО','is-error'); return; }
    const seq=++clientCardSaveSequence; setClientCardSaveState('Сохранение…','is-saving');
    try{
        const response=await fetch(`/api/client/${clientCardId}/update`,{method:'PATCH',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(payload)});
        const data=await response.json(); if(!response.ok||data.status!=='ok') throw new Error(data.message||'Ошибка сохранения');
        if(seq!==clientCardSaveSequence) return; clientCardData.client=data.client; updateClientCardAfterSave(data.client); setClientCardSaveState('✓ Сохранено','is-saved');
    }catch(error){ if(seq===clientCardSaveSequence) setClientCardSaveState(error.message||'Ошибка','is-error'); }
}

function updateClientCardAfterSave(c){
    document.getElementById('clientCardName').textContent=c.full_name||'Без имени'; document.getElementById('clientCardCompany').textContent=c.company_name||'Без организации'; updateClientCardStatus(c.status||'Новый');
    document.querySelectorAll(`.client-record[data-id="${clientCardId}"]`).forEach(record=>{
        record.dataset.fullName=c.full_name||''; record.dataset.companyName=c.company_name||''; record.dataset.iin=c.iin||''; record.dataset.phone=c.phone||''; record.dataset.address=c.address||''; record.dataset.status=c.status||'Новый'; record.dataset.category=c.category||''; record.dataset.payment=c.payment||''; record.dataset.comment=c.comment||''; record.dataset.contractNumber=c.contract_number||''; record.dataset.contractDate=c.contract_date||'';
        record.dataset.search=[c.full_name,c.company_name,c.iin,c.phone,c.address,c.category,c.status].filter(Boolean).join(' ').toLowerCase();
        const strong=record.querySelector('.client-main strong'); const small=record.querySelector('.client-main small'); if(strong)strong.textContent=c.full_name||'Без имени'; if(small)small.textContent=c.company_name||'Без компании';
        const cells=record.querySelectorAll('td'); if(cells.length){ if(cells[1])cells[1].textContent=c.iin||'—'; if(cells[2])cells[2].textContent=c.phone||'—'; if(cells[3])cells[3].textContent=c.category||'—'; }
        const status=record.querySelector('.client-status'); if(status){status.textContent=c.status||'Новый';status.className='client-status client-status--'+statusClass(c.status||'Новый');}
        record.querySelectorAll('.mobile-client-info>span').forEach(block=>{const label=block.querySelector('small')?.textContent.trim(); if(label==='Телефон')block.lastChild.textContent=c.phone||'—'; if(label==='ИИН')block.lastChild.textContent=c.iin||'—'; if(label==='Категория')block.lastChild.textContent=c.category||'—'; if(label==='Адрес')block.lastChild.textContent=c.address||'—';});
    });
}

function updateClientCardStatus(value){const el=document.getElementById('clientCardStatus');el.textContent=value;el.className='client-status client-status--'+statusClass(value);}
function statusClass(value){return String(value||'Новый').toLowerCase().replaceAll(' ','-');}
function setClientCardSaveState(text,cls){const el=document.getElementById('clientCardSaveState');el.textContent=text;el.className='client-card-save-state '+(cls||'');}
function switchClientCardTab(tab){document.querySelectorAll('.client-card-tab').forEach(b=>b.classList.toggle('is-active',b.dataset.cardTab===tab));document.querySelectorAll('.client-card-panel').forEach(p=>p.classList.toggle('is-active',p.dataset.cardPanel===tab));}
function closeClientCard(){clearTimeout(clientCardSaveTimer);const modal=document.getElementById('clientCardModal');modal.classList.remove('is-open','is-editing');modal.setAttribute('aria-hidden','true');document.body.classList.remove('client-card-open');clientCardId=null;clientCardData=null;clientCardEditMode=false;}
function escapeHtml(value){return String(value??'').replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));}
function formatClientSaleDate(value){if(!value)return '';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):d.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});}

document.addEventListener('DOMContentLoaded',()=>{
    const modal=document.getElementById('clientCardModal'); if(modal&&modal.parentElement!==document.body)document.body.appendChild(modal);
    document.querySelectorAll('[data-client-field]').forEach(el=>el.addEventListener(el.tagName==='SELECT'?'change':'input',scheduleClientCardSave));
    document.querySelectorAll('[data-client-identifier]').forEach(input=>input.addEventListener('input',()=>runClientIdentifierLookup(input,input.dataset.clientIdentifier)));
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.getElementById('clientCardModal')?.classList.contains('is-open'))closeClientCard();});
