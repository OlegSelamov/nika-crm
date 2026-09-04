// ================== SIDEBAR ==================
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.querySelector('.sidebar-backdrop');
    if (!sidebar) return;
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('mobile-open');
        if (backdrop) backdrop.classList.toggle('show');
    } else {
        sidebar.classList.toggle('collapsed');
        const isCollapsed = sidebar.classList.contains('collapsed');
        document.documentElement.classList.toggle('sidebar-is-collapsed', isCollapsed);
        localStorage.setItem('sidebarCollapsed', isCollapsed);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.querySelector('.sidebar-backdrop');
    if (backdrop) {
        backdrop.onclick = function () {
            sidebar?.classList.remove('mobile-open');
            backdrop.classList.remove('show');
        };
    }
    if (sidebar && window.innerWidth > 768 && localStorage.getItem('sidebarCollapsed') === 'true') {
        sidebar.classList.add('collapsed');
    }
});

document.addEventListener('DOMContentLoaded', function () { loadVoices(); });

// ================== APP SHELL / MENU STATE ==================
const APP_CURRENT_USER_ID = Number(window.NIKA_APP_CONFIG?.currentUserId || 0);
let lastNotificationUnread = 0;
let lastChatMessageId = 0;
let chatDrawerWasOpened = false;
let activeChatType = 'general';
let activeChatUserId = null;
let activeChatUserName = '';
let activeChatChannel = 'team';
let teamUnreadTotal = 0;
let whatsappUnreadTotal = 0;
let activeWhatsappChatId = null;
let activeWhatsappChatName = '';
let activeWhatsappChatPhone = '';
let activeWhatsappCustomerId = null;
let lastWhatsappMessageId = 0;
let whatsappSearchTimer = null;
let whatsappGlobalAiEnabled = false;
let activeWhatsappAiEnabled = false;

function normalizePath(path) {
    if (!path) return '/';
    const clean = path.split('?')[0].replace(/\/+$/, '');
    return clean || '/';
}

function setActiveMenuItem() {
    const current = normalizePath(window.location.pathname);
    const links = Array.from(document.querySelectorAll('.sidebar a[href]'))
        .filter(link => !link.classList.contains('logout-link'));
    let best = null;
    let bestLength = -1;
    links.forEach(link => {
        const target = normalizePath(new URL(link.href, window.location.origin).pathname);
        const exact = current === target;
        const child = target !== '/' && current.startsWith(target + '/');
        if ((exact || child) && target.length > bestLength) {
            best = link;
            bestLength = target.length;
        }
    });
    links.forEach(link => link.classList.remove('active-menu-item'));
    if (best) best.classList.add('active-menu-item');
}

function restoreSidebarState() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const collapsed = window.innerWidth > 768 && localStorage.getItem('sidebarCollapsed') === 'true';
    sidebar.classList.toggle('collapsed', collapsed);
    document.documentElement.classList.toggle('sidebar-is-collapsed', collapsed);
    const savedScroll = Number(sessionStorage.getItem('nikaSidebarScroll') || 0);
    requestAnimationFrame(() => {
        sidebar.scrollTop = savedScroll;
        requestAnimationFrame(() => document.documentElement.classList.add('ui-ready'));
    });
    sidebar.addEventListener('scroll', () => {
        sessionStorage.setItem('nikaSidebarScroll', String(sidebar.scrollTop));
    }, {passive: true});
    sidebar.querySelectorAll('a[href]').forEach(link => {
        link.addEventListener('click', () => {
            sessionStorage.setItem('nikaSidebarScroll', String(sidebar.scrollTop));
        });
    });
}

function openSystemDrawer(type) {
    closeAiAssistant();
    closeSystemDrawers(false);
    const backdrop = document.getElementById('systemDrawerBackdrop');
    const drawer = document.getElementById(type === 'chat' ? 'chatDrawer' : 'notificationsDrawer');
    backdrop?.classList.add('show');
    drawer?.classList.add('open');
    if (type === 'chat') {
        chatDrawerWasOpened = true;
        if (activeChatChannel === 'whatsapp') loadWhatsappChats(true);
        else loadChatConversations(true);
    } else loadNotifications();
}

function closeSystemDrawers(hideBackdrop = true) {
    document.querySelectorAll('.system-drawer').forEach(el => el.classList.remove('open'));
    if (hideBackdrop) document.getElementById('systemDrawerBackdrop')?.classList.remove('show');
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
        .replaceAll('"','&quot;').replaceAll("'",'&#039;');
}

function showSystemToast(title, message) {
    const wrap = document.getElementById('systemToastWrap');
    if (!wrap) return;
    const toast = document.createElement('div');
    toast.className = 'system-toast';
    toast.innerHTML = `<b>${escapeHtml(title)}</b><span>${escapeHtml(message)}</span>`;
    wrap.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function updateBadge(id, count) {
    const badge = document.getElementById(id);
    if (!badge) return;
    badge.textContent = count > 99 ? '99+' : count;
    badge.classList.toggle('show', count > 0);
}
function updateCombinedChatBadge() {
    updateBadge('chatBadge', Number(teamUnreadTotal || 0) + Number(whatsappUnreadTotal || 0));
    updateBadge('teamChatTabBadge', Number(teamUnreadTotal || 0));
    updateBadge('whatsappChatTabBadge', Number(whatsappUnreadTotal || 0));
}

function switchChatChannel(channel) {
    activeChatChannel = channel === 'whatsapp' ? 'whatsapp' : 'team';
    document.getElementById('teamChatTab')?.classList.toggle('active', activeChatChannel === 'team');
    document.getElementById('whatsappChatTab')?.classList.toggle('active', activeChatChannel === 'whatsapp');
    document.getElementById('teamChatPanel')?.classList.toggle('active', activeChatChannel === 'team');
    document.getElementById('whatsappChatPanel')?.classList.toggle('active', activeChatChannel === 'whatsapp');
    const title = document.getElementById('chatDrawerTitle');
    const subtitle = document.getElementById('chatDrawerSubtitle');
    if (activeChatChannel === 'whatsapp') {
        if (title) title.textContent = 'WhatsApp';
        if (subtitle) subtitle.textContent = 'Диалоги с клиентами';
        loadWhatsappChats(true);
    } else {
        if (title) title.textContent = activeChatType === 'private' ? activeChatUserName : 'Общий чат';
        if (subtitle) subtitle.textContent = activeChatType === 'private' ? 'Личные сообщения' : 'Все участники компании';
        loadChatConversations(true);
    }
}

async function loadNotifications(silent = false) {
    try {
        const response = await fetch('/api/notifications?limit=30', {headers:{Accept:'application/json'}});
        if (!response.ok) return;
        const data = await response.json();
        updateBadge('notificationBadge', data.unread_count || 0);
        if (silent && lastNotificationUnread && data.unread_count > lastNotificationUnread && data.items?.length) {
            const newest = data.items.find(item => !item.is_read);
            if (newest) showSystemToast(newest.title, newest.message);
        }
        lastNotificationUnread = data.unread_count || 0;
        const list = document.getElementById('notificationsList');
        if (!list) return;
        if (!data.items?.length) {
            list.innerHTML = '<div class="drawer-empty">Новых уведомлений пока нет</div>';
            return;
        }
        list.innerHTML = data.items.map(item => `
            <article class="notification-item ${item.is_read ? '' : 'unread'}"
                     onclick="openNotification(${item.id}, '${escapeHtml(item.link || '')}')">
                <div class="notification-item__icon">${item.type === 'task' ? '✓' : '🔔'}</div>
                <div><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.message)}</p><time>${escapeHtml(item.created_at_label)}</time></div>
            </article>`).join('');
    } catch (error) { console.error('Notifications error:', error); }
}
async function openNotification(id, link) {
    try { await fetch(`/api/notifications/${id}/read`, {method:'POST'}); } catch(e) {}
    if (link) window.location.href = link; else loadNotifications();
}
async function markAllNotificationsRead() {
    try { await fetch('/api/notifications/read-all',{method:'POST'}); await loadNotifications(); }
    catch(error){ console.error(error); }
}

async function loadChatConversations(loadMessagesAfter = false) {
    try {
        const response = await fetch('/api/chat/conversations',{headers:{Accept:'application/json'}});
        if (!response.ok) return;
        const data = await response.json();
        teamUnreadTotal = data.total_unread || 0;
        updateCombinedChatBadge();
        const generalBadge = document.getElementById('generalChatUnread');
        if (generalBadge) {
            generalBadge.textContent = data.general_unread > 99 ? '99+' : data.general_unread;
            generalBadge.classList.toggle('show', data.general_unread > 0);
        }
        const contacts = document.getElementById('chatContacts');
        if (contacts) {
            if (!data.users?.length) contacts.innerHTML = '<div class="drawer-empty">Других сотрудников пока нет</div>';
            else contacts.innerHTML = data.users.map(user => `
                <button class="chat-contact ${activeChatType === 'private' && Number(activeChatUserId) === Number(user.id) ? 'active' : ''}"
                        type="button" onclick="selectChat('private', ${user.id}, '${escapeHtml(user.name)}')">
                    <span class="chat-contact__avatar ${user.is_online ? 'online' : ''}">${escapeHtml((user.name || 'U').slice(0,2).toUpperCase())}</span>
                    <span class="chat-contact__main"><b>${escapeHtml(user.name)}</b><small>${user.is_online ? 'В сети' : 'Не в сети'}</small></span>
                    <span class="chat-contact__badge ${user.unread_count > 0 ? 'show' : ''}">${user.unread_count > 99 ? '99+' : user.unread_count}</span>
                </button>`).join('');
        }
        document.getElementById('generalChatButton')?.classList.toggle('active', activeChatType === 'general');
        if (loadMessagesAfter) await loadChatMessages(true);
    } catch(error){ console.error('Chat conversations error:',error); }
}

function selectChat(type,userId=null,userName='') {
    activeChatType = type;
    activeChatUserId = type === 'private' ? Number(userId) : null;
    activeChatUserName = type === 'private' ? userName : '';
    const title = document.getElementById('chatDrawerTitle');
    const subtitle = document.getElementById('chatDrawerSubtitle');
    if (type === 'private') {
        if (title) title.textContent = userName;
        if (subtitle) subtitle.textContent = 'Личные сообщения';
    } else {
        if (title) title.textContent = 'Общий чат';
        if (subtitle) subtitle.textContent = 'Все участники компании';
    }
    loadChatConversations(false);
    loadChatMessages(true);
}

async function loadChatMessages(scrollToBottom=false) {
    try {
        const params = new URLSearchParams({limit:'100',type:activeChatType});
        if (activeChatType === 'private' && activeChatUserId) params.set('user_id',String(activeChatUserId));
        const response = await fetch(`/api/chat/messages?${params.toString()}`,{headers:{Accept:'application/json'}});
        if (!response.ok) return;
        const data = await response.json();
        const box = document.getElementById('chatMessages');
        if (!box) return;
        const newestId = data.items?.length ? data.items[data.items.length-1].id : 0;
        const drawerOpen = document.getElementById('chatDrawer')?.classList.contains('open');
        if (!drawerOpen && lastChatMessageId && newestId > lastChatMessageId) {
            const incoming = [...(data.items || [])].reverse().find(item => item.id > lastChatMessageId && !item.is_mine);
            if (incoming) showSystemToast(`Сообщение от ${incoming.sender_name}`,incoming.message);
        }
        lastChatMessageId = Math.max(lastChatMessageId,newestId);
        if (!data.items?.length) box.innerHTML='<div class="drawer-empty">Сообщений пока нет</div>';
        else box.innerHTML=data.items.map(item=>`<article class="chat-message ${item.is_mine?'mine':''}"><div class="chat-message__meta"><b>${escapeHtml(item.sender_name)}</b><time>${escapeHtml(item.created_at_label)}</time></div><p>${escapeHtml(item.message)}</p></article>`).join('');
        if (scrollToBottom || drawerOpen) box.scrollTop=box.scrollHeight;
        await loadChatConversations(false);
    } catch(error){ console.error('Chat error:',error); }
}

async function sendChatMessage() {
    const input=document.getElementById('chatInput');
    const message=input?.value.trim();
    if (!message) return;
    if (activeChatType==='private'&&!activeChatUserId){alert('Выберите сотрудника');return;}
    input.disabled=true;
    try {
        const response=await fetch('/api/chat/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,type:activeChatType,recipient_user_id:activeChatType==='private'?activeChatUserId:null})});
        const data=await response.json();
        if(!response.ok||!data.success){alert(data.error||'Не удалось отправить сообщение');return;}
        input.value=''; await loadChatMessages(true);
    } catch(error){alert('Не удалось отправить сообщение');}
    finally{input.disabled=false;input.focus();}
}

function debouncedWhatsappSearch(){clearTimeout(whatsappSearchTimer);whatsappSearchTimer=setTimeout(()=>loadWhatsappChats(false),250);}
function renderWhatsappAiControls(){
    const globalButton=document.getElementById('whatsappGlobalAiButton');
    if(globalButton){globalButton.textContent=whatsappGlobalAiEnabled?'AI включен':'AI выключен';globalButton.classList.toggle('active',whatsappGlobalAiEnabled);globalButton.classList.remove('paused');}
    const chatButton=document.getElementById('whatsappChatAiButton'); if(!chatButton)return;
    chatButton.disabled=!activeWhatsappChatId||!whatsappGlobalAiEnabled;
    chatButton.classList.toggle('active',Boolean(activeWhatsappChatId&&activeWhatsappAiEnabled));
    chatButton.classList.toggle('paused',Boolean(activeWhatsappChatId&&whatsappGlobalAiEnabled&&!activeWhatsappAiEnabled));
    if(!whatsappGlobalAiEnabled)chatButton.textContent='AI выключен';else if(activeWhatsappAiEnabled)chatButton.textContent='AI отвечает';else chatButton.textContent='Менеджер отвечает';
}
async function loadWhatsappAiStatus(){try{const r=await fetch('/whatsapp/api/ai/status',{headers:{Accept:'application/json'}});const d=await r.json();if(!r.ok||!d.ok)return;whatsappGlobalAiEnabled=Boolean(d.ai_enabled);if(!whatsappGlobalAiEnabled)activeWhatsappAiEnabled=false;renderWhatsappAiControls();}catch(e){console.error('WhatsApp AI status error:',e)}}
async function toggleWhatsappGlobalAi(){const b=document.getElementById('whatsappGlobalAiButton');if(b)b.disabled=true;try{const r=await fetch('/whatsapp/api/ai/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!whatsappGlobalAiEnabled})});const d=await r.json();if(!r.ok||!d.ok){alert(d.error||'Не удалось изменить режим AI');return;}whatsappGlobalAiEnabled=Boolean(d.ai_enabled);if(!whatsappGlobalAiEnabled)activeWhatsappAiEnabled=false;renderWhatsappAiControls();await loadWhatsappChats(Boolean(activeWhatsappChatId));showSystemToast('WhatsApp AI',whatsappGlobalAiEnabled?'AI-менеджер включён':'AI-менеджер выключен');}catch(e){alert('Не удалось изменить режим AI')}finally{if(b)b.disabled=false}}
async function toggleActiveWhatsappAi(){if(!activeWhatsappChatId||!whatsappGlobalAiEnabled)return;const b=document.getElementById('whatsappChatAiButton');if(b)b.disabled=true;try{const r=await fetch(`/whatsapp/api/chats/${activeWhatsappChatId}/ai`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!activeWhatsappAiEnabled})});const d=await r.json();if(!r.ok||!d.ok){alert(d.error||'Не удалось изменить режим чата');return;}activeWhatsappAiEnabled=Boolean(d.ai_active);renderWhatsappAiControls();await loadWhatsappChats(false);showSystemToast('WhatsApp AI',activeWhatsappAiEnabled?'Nika снова отвечает клиенту':'Диалог передан менеджеру');}catch(e){alert('Не удалось изменить режим чата')}finally{renderWhatsappAiControls()}}

async function loadWhatsappChats(loadMessagesAfter=false){
    try{
        const search=document.getElementById('whatsappChatSearch')?.value.trim()||'';const params=new URLSearchParams({limit:'100'});if(search)params.set('search',search);
        const response=await fetch(`/whatsapp/api/chats?${params.toString()}`,{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();if(!data.ok)return;
        whatsappUnreadTotal=data.total_unread||0;updateCombinedChatBadge();const contacts=document.getElementById('whatsappChatContacts');if(!contacts)return;
        if(!data.items?.length){contacts.innerHTML='<div class="drawer-empty">Диалогов WhatsApp пока нет</div>';return;}
        contacts.innerHTML=data.items.map(chat=>`<button class="chat-contact ${Number(activeWhatsappChatId)===Number(chat.id)?'active':''}" type="button" onclick='selectWhatsappChat(${JSON.stringify(chat.id)}, ${JSON.stringify(chat.display_name)}, ${JSON.stringify(chat.phone)}, ${JSON.stringify(chat.customer_id)}, ${JSON.stringify(chat.ai_active)})'><span class="chat-contact__avatar whatsapp-avatar">${escapeHtml((chat.display_name||'WA').slice(0,2).toUpperCase())}</span><span class="chat-contact__main"><b>${escapeHtml(chat.display_name||chat.phone||'Клиент')}</b><small>${escapeHtml(chat.last_message||chat.phone||'Новый диалог')}</small></span><time class="wa-chat-time">${escapeHtml(chat.last_message_at_short||'')}</time><span class="chat-contact__badge ${chat.unread_count>0?'show':''}">${chat.unread_count>99?'99+':chat.unread_count}</span></button>`).join('');
        if(loadMessagesAfter&&activeWhatsappChatId)await loadWhatsappMessages(true);
    }catch(e){console.error('WhatsApp chats error:',e)}
}
function selectWhatsappChat(chatId,chatName='',phone='',customerId=null,aiActive=false){
    activeWhatsappChatId=Number(chatId);activeWhatsappChatName=chatName||phone||'Клиент';activeWhatsappChatPhone=phone||'';activeWhatsappCustomerId=customerId||null;activeWhatsappAiEnabled=Boolean(aiActive);
    const name=document.getElementById('whatsappActiveName'),phoneBox=document.getElementById('whatsappActivePhone'),input=document.getElementById('whatsappChatInput'),button=document.getElementById('whatsappSendButton');
    if(name)name.textContent=activeWhatsappChatName;if(phoneBox)phoneBox.textContent=activeWhatsappChatPhone||'WhatsApp';if(input)input.disabled=false;if(button)button.disabled=false;
    const cardButton=document.getElementById('whatsappClientCardButton');if(cardButton)cardButton.disabled=false;renderWhatsappAiControls();loadWhatsappChats(false);loadWhatsappMessages(true);loadWhatsappClientContext();
}
async function loadWhatsappMessages(scrollToBottom=false){
    if(!activeWhatsappChatId)return;try{const response=await fetch(`/whatsapp/api/chats/${activeWhatsappChatId}/messages?limit=200`,{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();if(!data.ok)return;whatsappGlobalAiEnabled=Boolean(data.chat?.integration_ai_enabled);activeWhatsappAiEnabled=Boolean(data.chat?.ai_active);renderWhatsappAiControls();const box=document.getElementById('whatsappMessages');if(!box)return;const newestId=data.items?.length?data.items[data.items.length-1].id:0;const drawerOpen=document.getElementById('chatDrawer')?.classList.contains('open');if((!drawerOpen||activeChatChannel!=='whatsapp')&&lastWhatsappMessageId&&newestId>lastWhatsappMessageId){const incoming=[...(data.items||[])].reverse().find(item=>item.id>lastWhatsappMessageId&&!item.is_mine);if(incoming)showSystemToast(`WhatsApp: ${activeWhatsappChatName}`,incoming.message)}lastWhatsappMessageId=Math.max(lastWhatsappMessageId,newestId);if(!data.items?.length)box.innerHTML='<div class="drawer-empty">Сообщений пока нет</div>';else box.innerHTML=data.items.map(item=>`<article class="chat-message ${item.is_mine?'mine':''} ${item.is_ai?'whatsapp-message-ai':''}"><div class="chat-message__meta"><b>${item.is_mine?(item.is_ai?'Nika AI':'Вы'):escapeHtml(activeWhatsappChatName)}</b><time>${escapeHtml(item.created_at_label)}</time></div><p>${escapeHtml(item.message||`[${item.message_type}]`)}</p>${item.is_mine?renderWhatsappStatus(item.status):''}</article>`).join('');if(scrollToBottom||(drawerOpen&&activeChatChannel==='whatsapp'))box.scrollTop=box.scrollHeight;await loadWhatsappChats(false);}catch(e){console.error('WhatsApp messages error:',e)}}
async function sendWhatsappChatMessage(){const input=document.getElementById('whatsappChatInput'),button=document.getElementById('whatsappSendButton'),message=input?.value.trim();if(!activeWhatsappChatId){alert('Выберите WhatsApp-диалог');return}if(!message)return;input.disabled=true;if(button)button.disabled=true;try{const response=await fetch(`/whatsapp/api/chats/${activeWhatsappChatId}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});const data=await response.json();if(!response.ok||!data.ok){alert(data.error||'Не удалось отправить сообщение');return}input.value='';activeWhatsappAiEnabled=false;renderWhatsappAiControls();await loadWhatsappMessages(true)}catch(e){alert('Не удалось отправить сообщение')}finally{input.disabled=false;if(button)button.disabled=false;input.focus()}}
async function pingPresence(){try{await fetch('/api/presence/ping',{method:'POST'})}catch(e){}}

function formatMoneyKzt(value){return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(Number(value||0))+' ₸'}
function renderWhatsappStatus(status){const map={queued:['✓','В очереди',''],sent:['✓','Отправлено',''],delivered:['✓✓','Доставлено',''],read:['✓✓','Прочитано','read'],failed:['!','Ошибка','failed'],received:['','Получено','']};const row=map[String(status||'').toLowerCase()]||['✓',status||'Отправлено',''];return `<span class="wa-message-status ${row[2]}">${row[0]} ${escapeHtml(row[1])}</span>`}
function openWhatsappClientModal(){if(!activeWhatsappChatId){alert('Сначала выберите WhatsApp-диалог');return}const b=document.getElementById('whatsappClientModalBackdrop');if(!b)return;b.classList.add('open');document.body.classList.add('wa-modal-open');loadWhatsappClientContext()}
function closeWhatsappClientModal(event=null){const b=document.getElementById('whatsappClientModalBackdrop'),m=document.getElementById('whatsappClientModal');if(event&&m&&m.contains(event.target))return;b?.classList.remove('open');document.body.classList.remove('wa-modal-open')}
async function loadWhatsappClientContext(){const panel=document.getElementById('whatsappClientModalBody');if(!panel||!activeWhatsappChatId)return;panel.innerHTML='<div class="wa-empty-client">Загрузка карточки клиента…</div>';try{const response=await fetch(`/whatsapp/api/chats/${activeWhatsappChatId}/context`,{headers:{Accept:'application/json'}});const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'Ошибка');const c=data.client||{},s=data.stats||{},initials=((c.full_name||activeWhatsappChatName||'WA').slice(0,2)).toUpperCase(),avatar=c.photo?`<img src="${escapeHtml(c.photo)}" alt="">`:escapeHtml(initials);panel.innerHTML=`<div class="wa-client-card"><div class="wa-client-avatar">${avatar}</div><div class="wa-client-card__copy"><h4>${escapeHtml(c.full_name||activeWhatsappChatName||'Клиент WhatsApp')}</h4><p>${escapeHtml(c.phone||activeWhatsappChatPhone||'')}</p><span class="wa-client-state ${c.id?'':'unlinked'}">${c.id?'Клиент привязан':'Новый контакт'}</span></div></div><div class="wa-stats"><div class="wa-stat"><span>Покупок</span><b>${Number(s.sales_count||0)}</b></div><div class="wa-stat"><span>Выручка</span><b>${formatMoneyKzt(s.total_revenue)}</b></div><div class="wa-stat"><span>Средний чек</span><b>${formatMoneyKzt(s.average_check)}</b></div><div class="wa-stat"><span>Долг</span><b>${formatMoneyKzt(s.debt)}</b></div></div><div class="wa-last-sale"><small>Последняя продажа</small><b>${s.last_sale_at?escapeHtml(s.last_sale_at)+' · '+formatMoneyKzt(s.last_sale_total):'Продаж пока нет'}</b></div><div class="wa-quick-actions">${c.id?`<a class="wa-action-btn primary" href="/clients/${c.id}">Открыть клиента</a>`:`<button class="wa-action-btn green" onclick="createClientFromWhatsapp()">Создать клиента</button>`}<a class="wa-action-btn green" href="/sales${c.id?`?client_id=${c.id}`:''}">Создать продажу</a><a class="wa-action-btn" href="/tasks${c.id?`?client_id=${c.id}`:''}">Создать задачу</a><button class="wa-action-btn" type="button" onclick="copyWhatsappPhone()">Копировать номер</button></div>`}catch(e){panel.innerHTML='<div class="wa-empty-client">Не удалось загрузить карточку клиента.</div>'}}
async function createClientFromWhatsapp(){if(!activeWhatsappChatId)return;const suggested=activeWhatsappChatName&&activeWhatsappChatName!==activeWhatsappChatPhone?activeWhatsappChatName:'Клиент WhatsApp';const fullName=prompt('Имя клиента',suggested);if(!fullName)return;const response=await fetch(`/whatsapp/api/chats/${activeWhatsappChatId}/create-client`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:fullName})});const data=await response.json();if(!response.ok||!data.ok){alert(data.error||'Не удалось создать клиента');return}activeWhatsappCustomerId=data.customer_id;showSystemToast('WhatsApp','Клиент создан и привязан к диалогу');await loadWhatsappChats(false);await loadWhatsappClientContext()}
function copyWhatsappPhone(){navigator.clipboard?.writeText(activeWhatsappChatPhone||'');showSystemToast('Номер скопирован',activeWhatsappChatPhone||'')}
function refreshActiveWhatsappChat(){loadWhatsappChats(false);loadWhatsappMessages(false);loadWhatsappClientContext()}

// ================== ГОЛОС ==================
let voiceEnabled=true,selectedVoice=null,currentAiAudio=null,currentAiAudioUrl=null,currentVoiceAbortController=null,voicePlaybackToken=0;
const phrases={open:['Открываю','Сейчас покажу','Перехожу','Уже открываю'],search:['Секунду, ищу','Нашла, сейчас покажу','Ищу в базе','Проверяю'],error:['Я не совсем поняла','Повтори пожалуйста','Попробуй сказать иначе']};
function say(type){const arr=phrases[type]||['Готово'];return arr[Math.floor(Math.random()*arr.length)]}
function loadVoices(){const voices=speechSynthesis.getVoices();if(!voices.length)return;const russianVoices=voices.filter(v=>/^ru(?:-|_)/i.test(v.lang));const score=v=>{const n=String(v.name||'').toLowerCase();let s=0;if(/natural|нейрон|neural|online/.test(n))s+=100;if(/svetlana|светлана|daria|дарья|irina|ирина/.test(n))s+=50;if(/google/.test(n))s+=35;if(/microsoft/.test(n))s+=25;if(v.localService===false)s+=10;return s};selectedVoice=[...russianVoices].sort((a,b)=>score(b)-score(a))[0]||voices[0]}
window.speechSynthesis.onvoiceschanged=loadVoices;
function prepareSpeechText(text){return String(text||'').replace(/```[\s\S]*?```/g,' ').replace(/!\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/https?:\/\/\S+|www\.\S+/gi,' ').replace(/^\s{0,3}#{1,6}\s*/gm,'').replace(/^\s*>\s?/gm,'').replace(/^\s*[-+*•]\s+/gm,'').replace(/\*\*|__|~~|`/g,'').replace(/(\d)\s*\/\s*(\d)/g,'$1 из $2').replace(/[\\/|]+/g,' ').replace(/[_*#<>\[\]{}]+/g,' ').replace(/\s+/g,' ').trim()}
function stopVoicePlayback(){voicePlaybackToken+=1;speechSynthesis.cancel();if(currentVoiceAbortController){currentVoiceAbortController.abort();currentVoiceAbortController=null}if(currentAiAudio){currentAiAudio.pause();currentAiAudio.src='';currentAiAudio=null}if(currentAiAudioUrl){URL.revokeObjectURL(currentAiAudioUrl);currentAiAudioUrl=null}return voicePlaybackToken}
function splitSpeechText(text,maxLength=260){const sentences=String(text||'').match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g)||[],chunks=[];sentences.forEach(sentence=>{const clean=sentence.trim();if(!clean)return;if(clean.length<=maxLength){chunks.push(clean);return}let part='';clean.split(/\s+/).forEach(word=>{if(part&&`${part} ${word}`.length>maxLength){chunks.push(part);part=word}else part=part?`${part} ${word}`:word});if(part)chunks.push(part)});return chunks}
function waitForVoiceRetry(delay,signal){return new Promise((resolve,reject)=>{const timer=setTimeout(resolve,delay);signal.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Voice request cancelled','AbortError'))},{once:true})})}
async function parseJsonResponse(response){const contentType=response.headers.get('content-type')||'';if(!contentType.includes('application/json'))return{};return await response.json()}
async function fetchAiVoiceChunk(text,signal){let lastError=null;for(let attempt=0;attempt<2;attempt+=1){try{const response=await fetch('/api/ai/voice',{method:'POST',headers:{'Content-Type':'application/json',Accept:'audio/mpeg'},body:JSON.stringify({text}),signal});if(!response.ok){const details=await parseJsonResponse(response);const error=new Error(details.error||'AI voice is unavailable');error.status=response.status;throw error}return await response.blob()}catch(error){if(error.name==='AbortError')throw error;lastError=error;const canRetry=!error.status||error.status===408||error.status===429||error.status>=500;if(!canRetry||attempt===1)break;await waitForVoiceRetry(350,signal)}}throw lastError||new Error('AI voice is unavailable')}
function playAiVoiceChunk(audioBlob,token,signal){return new Promise((resolve,reject)=>{if(token!==voicePlaybackToken||!voiceEnabled){resolve();return}const audioUrl=URL.createObjectURL(audioBlob),audio=new Audio(audioUrl);currentAiAudioUrl=audioUrl;currentAiAudio=audio;audio.preload='auto';let finished=false;const finish=error=>{if(finished)return;finished=true;signal.removeEventListener('abort',cancelPlayback);URL.revokeObjectURL(audioUrl);if(currentAiAudio===audio)currentAiAudio=null;if(currentAiAudioUrl===audioUrl)currentAiAudioUrl=null;error?reject(error):resolve()};const cancelPlayback=()=>{audio.pause();finish()};audio.onended=()=>finish();audio.onerror=()=>finish(new Error('Не удалось воспроизвести голос'));signal.addEventListener('abort',cancelPlayback,{once:true});audio.play().catch(finish)})}
async function speak(text,callback=null){if(recognition){try{recognition.stop()}catch(e){}}const speechText=prepareSpeechText(text);if(!speechText||!voiceEnabled)return;const token=stopVoicePlayback(),controller=new AbortController();currentVoiceAbortController=controller;const chunks=splitSpeechText(speechText);if(!chunks.length)return;try{let nextAudio=fetchAiVoiceChunk(chunks[0],controller.signal);for(let index=0;index<chunks.length;index+=1){const audioBlob=await nextAudio;if(token!==voicePlaybackToken||!voiceEnabled)return;nextAudio=index+1<chunks.length?fetchAiVoiceChunk(chunks[index+1],controller.signal):null;await playAiVoiceChunk(audioBlob,token,controller.signal)}if(token===voicePlaybackToken&&callback)callback()}catch(error){if(error.name!=='AbortError'&&token===voicePlaybackToken&&voiceEnabled)console.error('Nika AI voice error:',error)}finally{if(currentVoiceAbortController===controller)currentVoiceAbortController=null}}
function toggleVoice(){voiceEnabled=!voiceEnabled;const button=document.getElementById('aiSoundButton'),label=document.getElementById('aiSoundText'),icon=document.getElementById('aiSoundIcon');if(button)button.classList.toggle('active',voiceEnabled);if(voiceEnabled){if(label)label.textContent='Озвучивание включено';if(icon)icon.src='/static/icons/ai-sound-on.png';speak('Голос включен')}else{if(label)label.textContent='Озвучивание выключено';if(icon)icon.src='/static/icons/ai-sound-off.png';stopVoicePlayback()}}

// ================== NIKA AI ==================
let aiConversationId=null,aiSending=false,aiHistoryLoaded=false;
const NIKA_PAGE_CONTEXTS=[
{prefixes:['/sales'],label:'Продажи',description:'Помогу найти товар, собрать продажу, выбрать клиента и проверить чеки.',suggestions:[['Продажи сегодня','Покажи продажи и выручку за сегодня'],['Найти товар','Найди товар по названию или штрихкоду'],['Помощь по разделу','Что я могу сделать в разделе продаж?']]},
{prefixes:['/stock/income'],label:'Приход товара',description:'Помогу найти позицию, подготовить приход и проверить закупочные цены.',suggestions:[['Подготовить приход','Помоги подготовить приход товара'],['Найти товар','Найди товар в каталоге'],['Низкие остатки','Покажи товары с низким остатком']]},
{prefixes:['/stock/writeoff'],label:'Списание',description:'Помогу найти товар, проверить остаток и подготовить безопасное списание.',suggestions:[['Подготовить списание','Помоги подготовить списание товара'],['Проверить остаток','Покажи остаток товара'],['Движения товара','Покажи последние движения товара']]},
{prefixes:['/stock/movements'],label:'Движение товара',description:'Помогу разобраться в приходах, продажах, возвратах и списаниях.',suggestions:[['Последние движения','Покажи последние движения товаров'],['Найти товар','Найди товар и покажи его движение'],['Низкие остатки','Покажи товары с низким остатком']]},
{prefixes:['/stock'],label:'Склад',description:'Помогу проверить остатки, найти дефицит и подготовить складскую операцию.',suggestions:[['Низкие остатки','Покажи товары с низким остатком'],['Остаток товара','Покажи остаток товара'],['Помощь по складу','Что я могу сделать в разделе склада?']]},
{prefixes:['/items'],label:'Товары и услуги',description:'Помогу найти позицию, проверить цену и подготовить добавление или изменение.',suggestions:[['Найти позицию','Найди товар или услугу в каталоге'],['Проверить цены','Покажи товары без розничной цены'],['Добавить товар','Помоги добавить новый товар']]},
{prefixes:['/clients'],label:'Клиенты',description:'Помогу найти клиента, посмотреть историю и подготовить сообщение или карточку.',suggestions:[['Найти клиента','Найди клиента по имени или номеру телефона'],['Лучшие клиенты','Покажи лучших клиентов по покупкам'],['Создать клиента','Помоги создать нового клиента']]},
{prefixes:['/accounting'],label:'Бухгалтерия',description:'Помогу проверить обязательства, документы, налоги и задолженности.',suggestions:[['Задолженности','Покажи текущие задолженности'],['Ближайшие налоги','Какие налоговые события ближайшие?'],['Помощь по разделу','Что я могу сделать в бухгалтерии?']]},
{prefixes:['/reports'],label:'Отчёты',description:'Помогу подобрать отчёт и объяснить показатели бизнеса.',suggestions:[['Итоги месяца','Покажи основные итоги текущего месяца'],['Лучшие товары','Какие товары продаются лучше всего?'],['Помощь по отчётам','Какой отчёт мне лучше открыть?']]},
{prefixes:['/analytics'],label:'Аналитика',description:'Помогу объяснить выручку, прибыль, средний чек и динамику продаж.',suggestions:[['Итоги сегодня','Какая выручка и прибыль сегодня?'],['Динамика продаж','Как изменилась выручка за последнее время?'],['Лучшие товары','Какие товары продаются лучше всего?']]},
{prefixes:['/expenses'],label:'Расходы',description:'Помогу найти расходы, посчитать сумму и подготовить новую запись.',suggestions:[['Расходы месяца','Покажи расходы за текущий месяц'],['Крупные расходы','Какие расходы были самыми крупными?'],['Добавить расход','Помоги добавить новый расход']]},
{prefixes:['/tasks'],label:'Задачи',description:'Помогу проверить сроки, найти просроченные задачи и подготовить новую.',suggestions:[['Просроченные','Покажи просроченные задачи'],['Задачи сегодня','Какие задачи нужно выполнить сегодня?'],['Создать задачу','Помоги создать новую задачу']]},
{prefixes:['/users'],label:'Пользователи',description:'Помогу найти сотрудника и разобраться с ролями и доступами.',suggestions:[['Список сотрудников','Покажи пользователей компании'],['Добавить сотрудника','Помоги добавить нового сотрудника'],['Права доступа','Объясни роли и права пользователей']]},
{prefixes:['/cto','/rekassa'],label:'ККМ и ЦТО',description:'Помогу с кассой, reKassa, сменами, отчётами и оборудованием.',suggestions:[['Статус кассы','Что нужно проверить в настройках кассы?'],['Смена и отчёты','Объясни работу X- и Z-отчётов'],['Помощь по разделу','Что я могу настроить в ККМ и ЦТО?']]},
{prefixes:['/storefront/orders'],label:'Заказы',description:'Помогу проверить и обработать заказы с онлайн-витрины.',suggestions:[['Новые заказы','Покажи новые заказы с онлайн-витрины'],['Заказы сегодня','Покажи заказы за сегодня'],['Помощь по разделу','Что можно сделать с онлайн-заказами?']]},
{prefixes:['/storefront/bookings'],label:'Записи',description:'Помогу проверить и обработать онлайн-записи клиентов.',suggestions:[['Новые записи','Покажи новые онлайн-записи'],['Записи сегодня','Какие записи на сегодня?'],['Помощь по разделу','Что можно сделать с записями?']]},
{prefixes:['/storefront'],label:'Онлайн-витрина',description:'Помогу проверить опубликованные позиции, заказы и настройки витрины.',suggestions:[['Товары на витрине','Покажи товары, опубликованные на онлайн-витрине'],['Проверить заказы','Помоги проверить заказы с онлайн-витрины'],['Настроить витрину','Что нужно настроить на онлайн-витрине?']]},
{prefixes:['/subscription'],label:'Подписка и модули',description:'Помогу понять состав подписки, модули и доступные возможности.',suggestions:[['Моя подписка','Объясни мою текущую подписку'],['Нужные модули','Какие модули нужны моему бизнесу?'],['Помощь по разделу','Что можно изменить в подписке?']]},
{prefixes:['/settings','/company'],label:'Настройки',description:'Помогу найти нужную настройку компании, интеграции или оборудования.',suggestions:[['Настройки компании','Что важно заполнить в настройках компании?'],['Интеграции','Какие интеграции можно подключить?'],['Найти настройку','Помоги найти нужную настройку']]},
{prefixes:['/profile'],label:'Профиль',description:'Помогу разобраться с аккаунтом, компанией и вашей активностью.',suggestions:[['Моя компания','Покажи основные данные моей компании'],['Мои задачи','Покажи мои текущие задачи'],['Помощь по профилю','Что можно сделать в профиле?']]},
{prefixes:['/dashboard','/'],label:'Главная',description:'Помогу быстро оценить состояние бизнеса и перейти к нужному действию.',suggestions:[['Итоги сегодня','Какая выручка и прибыль сегодня?'],['Низкие остатки','Покажи товары с низким остатком'],['Что требует внимания','Что в бизнесе сейчас требует моего внимания?']]}
];
function getNikaPageContext(){const path=window.location.pathname.replace(/\/+$/,'')||'/';return NIKA_PAGE_CONTEXTS.find(context=>context.prefixes.some(prefix=>prefix==='/'?path==='/':path===prefix||path.startsWith(`${prefix}/`)))||NIKA_PAGE_CONTEXTS[NIKA_PAGE_CONTEXTS.length-1]}
function renderNikaPageContext(){const context=getNikaPageContext(),contextLabel=document.getElementById('aiContextLabel'),welcomeTitle=document.getElementById('aiWelcomeTitle'),welcomeText=document.getElementById('aiWelcomeText'),suggestions=document.getElementById('aiSuggestions');if(contextLabel)contextLabel.textContent=`Помогаю: ${context.label}`;if(welcomeTitle)welcomeTitle.textContent=`Помогу в разделе «${context.label}»`;if(welcomeText)welcomeText.textContent=context.description;if(suggestions){suggestions.replaceChildren();context.suggestions.forEach(([label,command])=>{const button=document.createElement('button');button.className='ai-suggestion';button.type='button';button.textContent=label;button.addEventListener('click',()=>useAiSuggestion(command));suggestions.appendChild(button)})}}
function appendAiMessage(role,text,options={}){const messages=document.getElementById('aiMessages');if(!messages||!text)return null;const message=document.createElement('div');message.className=`ai-message ai-message--${role==='user'?'user':'assistant'}`;if(options.typing)message.classList.add('ai-message--typing');if(options.id)message.id=options.id;message.textContent=text;messages.appendChild(message);messages.scrollTop=messages.scrollHeight;return message}
function appendAiConfirmation(confirmation){const messages=document.getElementById('aiMessages');if(!messages||!confirmation?.id)return null;messages.querySelectorAll('.ai-confirmation').forEach(existing=>existing.remove());const card=document.createElement('div');card.className='ai-confirmation';card.dataset.actionId=confirmation.id;const label=document.createElement('div');label.className='ai-confirmation__label';const isClientMessage=confirmation.kind==='client_message';label.textContent=isClientMessage?'Проверьте сообщение':'Требуется подтверждение';const summary=document.createElement('div');summary.className='ai-confirmation__summary';summary.textContent=confirmation.summary||'Выполнить подготовленное действие?';const actions=document.createElement('div');actions.className='ai-confirmation__actions';const confirmButton=document.createElement('button');confirmButton.type='button';confirmButton.className='ai-confirmation__button ai-confirmation__button--confirm';confirmButton.textContent=isClientMessage?'Отправить':'Подтвердить';confirmButton.onclick=()=>decideAiAction(confirmation.id,'confirm',card);const cancelButton=document.createElement('button');cancelButton.type='button';cancelButton.className='ai-confirmation__button ai-confirmation__button--cancel';cancelButton.textContent='Отменить';cancelButton.onclick=()=>decideAiAction(confirmation.id,'cancel',card);actions.append(confirmButton,cancelButton);card.append(label,summary,actions);messages.appendChild(card);messages.scrollTop=messages.scrollHeight;return card}
async function decideAiAction(actionId,decision,card){const buttons=card?.querySelectorAll('button')||[];buttons.forEach(button=>button.disabled=true);try{const response=await fetch(`/api/ai/action/${encodeURIComponent(actionId)}`,{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({decision})});const data=await parseJsonResponse(response);if(!response.ok)throw new Error(data.error||'Не удалось выполнить действие');card?.remove();const reply=data.reply||(decision==='confirm'?'Действие выполнено.':'Действие отменено.');appendAiMessage('assistant',reply);if(voiceEnabled)speak(reply)}catch(error){buttons.forEach(button=>button.disabled=false);appendAiMessage('assistant',error.message||'Не удалось выполнить действие.')}}
function setAiSending(sending){aiSending=sending;const button=document.getElementById('aiSendButton');if(button)button.disabled=sending}
function useAiSuggestion(text){const input=document.getElementById('agent-input');if(!input)return;input.value=text;sendCommand()}
async function runLegacyAgentAction(data){if(data.action==='redirect'&&data.url){setTimeout(()=>{window.location.href=data.url},700);return data.reply||data.message||'Открываю нужный раздел.'}if(data.action==='search_client'){setTimeout(()=>{window.location.href='/clients?search='+encodeURIComponent(data.query||'')},700);return `Ищу клиента: ${data.query||''}`}if(data.action==='open_drawer'){closeAiAssistant();openSystemDrawer(data.target==='notifications'?'notifications':'chat');return data.reply||data.message||'Открываю.'}if(data.action==='access_denied')return data.reply||data.message||'Этот раздел недоступен для вашей учётной записи.';if(data.action==='get_revenue'){const response=await fetch('/api/revenue',{headers:{Accept:'application/json'}});const revenue=await parseJsonResponse(response);return `Сегодня выручка ${formatMoneyKzt(revenue.total)}.`}if(data.action==='create_sale_smart'){if(typeof openClientSheet==='function')openClientSheet();setTimeout(()=>{const clientInput=document.getElementById('clientSearchInput');if(!clientInput)return;clientInput.value=data.client_name||'';if(typeof filterClients==='function')filterClients()},300);return `Подготовила поиск клиента ${data.client_name||''} для новой продажи.`}if(data.action==='create_client')return `Могу создать клиента ${data.name||''}. Подтвердите это действие в следующем сообщении.`;return data.reply||data.answer||data.message||data.error||'Команда обработана.'}
async function requestAiReply(text){const pagePath=window.location.pathname.slice(0,200);let response=await fetch('/api/ai/chat',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({message:text,conversation_id:aiConversationId,page_path:pagePath})});if(response.status===404||response.status===405)response=await fetch('/api/agent/command',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({text})});const data=await parseJsonResponse(response);if(!response.ok)throw new Error(data.error||data.message||'Не удалось получить ответ AI');aiConversationId=data.conversation_id||aiConversationId;if(data.action)return{reply:await runLegacyAgentAction(data),confirmation:null};return{reply:data.reply||data.answer||data.message||data.output_text||'Готово.',confirmation:data.confirmation||null,actionStatus:data.action_status||null}}
async function sendCommand(){const input=document.getElementById('agent-input'),text=input?.value.trim();if(!text||aiSending)return;input.value='';appendAiMessage('user',text);setAiSending(true);appendAiMessage('assistant','Nika AI думает…',{typing:true,id:'aiTypingMessage'});try{const result=await requestAiReply(text),reply=result.reply;document.getElementById('aiTypingMessage')?.remove();if(result.actionStatus)document.querySelectorAll('#aiMessages .ai-confirmation').forEach(card=>card.remove());appendAiMessage('assistant',reply);if(result.confirmation)appendAiConfirmation(result.confirmation);if(voiceEnabled)speak(reply)}catch(error){document.getElementById('aiTypingMessage')?.remove();appendAiMessage('assistant','Не удалось связаться с AI. Проверьте подключение сервера и попробуйте ещё раз.');console.error('Nika AI error:',error)}finally{setAiSending(false);input.focus()}}
async function loadAiHistory(){if(aiHistoryLoaded)return;aiHistoryLoaded=true;try{const response=await fetch('/api/ai/history?limit=50',{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await parseJsonResponse(response);aiConversationId=data.conversation_id||aiConversationId;const items=data.items||data.messages||[];items.forEach(item=>appendAiMessage(item.role==='user'?'user':'assistant',item.content||item.text||''));if(data.confirmation)appendAiConfirmation(data.confirmation)}catch(e){console.debug('AI history is not available yet')}}
let recognition,silenceTimer;
function startVoice(){if(!('webkitSpeechRecognition' in window)){alert('Браузер не поддерживает голос');return}recognition=new webkitSpeechRecognition();recognition.lang='ru-RU';recognition.continuous=true;recognition.interimResults=false;document.getElementById('aiMicButton')?.classList.add('active');let finalText='';recognition.start();recognition.onresult=function(event){let text=event.results[event.results.length-1][0].transcript;finalText+=' '+text;clearTimeout(silenceTimer);silenceTimer=setTimeout(()=>{recognition.stop();finalText=finalText.trim();if(finalText.length===0){speak('Я не услышала');return}document.getElementById('agent-input').value=finalText;sendCommand()},1500)};recognition.onerror=function(){document.getElementById('aiMicButton')?.classList.remove('active')};recognition.onend=function(){document.getElementById('aiMicButton')?.classList.remove('active')}}
function toggleAiAssistant(){const panel=document.getElementById('aiAssistantPanel');if(!panel)return;if(panel.classList.contains('open'))closeAiAssistant();else openAiAssistant()}
function syncAiAssistantState(isOpen){document.querySelectorAll('[onclick="toggleAiAssistant()"]')?.forEach(button=>button.setAttribute('aria-expanded',isOpen?'true':'false'))}
function openAiAssistant(options={}){const panel=document.getElementById('aiAssistantPanel');if(!panel)return;closeSystemDrawers();panel.classList.add('open');syncAiAssistantState(true);sessionStorage.setItem('nikaAiPanelOpen','1');loadAiHistory();if(options.focus!==false)setTimeout(()=>document.getElementById('agent-input')?.focus(),80)}
function closeAiAssistant(options={}){document.getElementById('aiAssistantPanel')?.classList.remove('open');syncAiAssistantState(false);if(options.remember!==false)sessionStorage.setItem('nikaAiPanelOpen','0');if(recognition)recognition.stop()}

document.addEventListener('DOMContentLoaded',()=>{
    restoreSidebarState();
    setActiveMenuItem();
    document.getElementById('agent-input')?.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendCommand()}});
    document.getElementById('chatInput')?.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMessage()}});
    document.getElementById('whatsappChatInput')?.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendWhatsappChatMessage()}});
    renderNikaPageContext();
    if(sessionStorage.getItem('nikaAiPanelOpen')==='1')openAiAssistant({focus:false});else syncAiAssistantState(false);
    loadNotifications();loadChatConversations(true);loadWhatsappAiStatus();loadWhatsappChats(false);pingPresence();
    setInterval(()=>loadNotifications(true),15000);
    setInterval(()=>{const drawerOpen=document.getElementById('chatDrawer')?.classList.contains('open');loadChatConversations(false);loadWhatsappChats(false);if(drawerOpen&&activeChatChannel==='team')loadChatMessages(false);if(drawerOpen&&activeChatChannel==='whatsapp'&&activeWhatsappChatId)loadWhatsappMessages(false)},5000);
    setInterval(pingPresence,30000);
});
document.addEventListener('click',event=>{const panel=document.getElementById('aiAssistantPanel'),aiButton=event.target.closest('[onclick="toggleAiAssistant()"]');if(panel&&panel.classList.contains('open')&&!panel.contains(event.target)&&!aiButton)closeAiAssistant()});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeWhatsappClientModal();closeAiAssistant()}});
(function preserveAppShellState(){function saveSidebarScroll(){const sidebar=document.getElementById('sidebar');if(sidebar)sessionStorage.setItem('nikaSidebarScroll',String(sidebar.scrollTop))}document.addEventListener('click',event=>{const link=event.target.closest('.sidebar a[href]');if(link)saveSidebarScroll()},true);window.addEventListener('pagehide',saveSidebarScroll)})();
