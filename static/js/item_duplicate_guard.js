(() => {
  'use strict';

  const form = document.querySelector('form[method="POST"]');
  if (!form) return;

  const barcode = form.querySelector('input[name="barcode"]');
  const gtin = form.querySelector('input[name="gtin"]');
  const ntin = form.querySelector('input[name="ntin"]');
  const itemType = form.querySelector('[name="item_type"]');
  if (!barcode && !gtin && !ntin) return;

  const editMatch = location.pathname.match(/^\/items\/(\d+)\/edit$/);
  const excludeId = editMatch ? editMatch[1] : '';
  let duplicate = null;
  let checkTimer = null;
  let lastSignature = '';
  let requestSerial = 0;

  const submitButtons = [...form.querySelectorAll('button[type="submit"], input[type="submit"]')];

  function clean(value) {
    return String(value || '').trim();
  }

  function ensureBanner() {
    let banner = document.getElementById('itemDuplicateWarning');
    if (banner) return banner;

    banner = document.createElement('div');
    banner.id = 'itemDuplicateWarning';
    banner.style.cssText = [
      'display:none',
      'margin:0 0 16px',
      'padding:14px 16px',
      'border:1px solid #fdba74',
      'border-radius:14px',
      'background:#fff7ed',
      'color:#9a3412',
      'font-size:14px',
      'line-height:1.45'
    ].join(';');

    form.insertAdjacentElement('beforebegin', banner);
    return banner;
  }

  function setBlocked(blocked) {
    submitButtons.forEach(button => {
      button.disabled = blocked;
      button.style.opacity = blocked ? '.55' : '';
      button.style.cursor = blocked ? 'not-allowed' : '';
    });
  }

  function renderDuplicate(item) {
    duplicate = item;
    const banner = ensureBanner();
    const name = String(item?.name || 'Товар');
    const label = String(item?.field_label || 'коду');
    const value = String(item?.value || '');
    banner.style.display = 'block';
    banner.innerHTML = `
      <b>Данный товар уже есть в каталоге.</b><br>
      ${escapeHtml(name)} — совпадение по ${escapeHtml(label)}${value ? `: <b>${escapeHtml(value)}</b>` : ''}.
      <a href="/items/${encodeURIComponent(item.id)}/edit" style="display:inline-block;margin-left:8px;color:#c2410c;font-weight:800;text-decoration:underline">Открыть товар</a>
    `;
    setBlocked(true);
  }

  function clearDuplicate() {
    duplicate = null;
    const banner = document.getElementById('itemDuplicateWarning');
    if (banner) banner.style.display = 'none';
    setBlocked(false);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  async function checkNow(force = false) {
    if (itemType && itemType.value === 'service') {
      clearDuplicate();
      return false;
    }

    const values = {
      barcode: clean(barcode?.value),
      gtin: clean(gtin?.value),
      ntin: clean(ntin?.value)
    };
    const signature = `${values.barcode}|${values.gtin}|${values.ntin}|${excludeId}`;

    if (!values.barcode && !values.gtin && !values.ntin) {
      lastSignature = signature;
      clearDuplicate();
      return false;
    }
    if (!force && signature === lastSignature) return Boolean(duplicate);
    lastSignature = signature;

    const serial = ++requestSerial;
    const params = new URLSearchParams();
    if (values.barcode) params.set('barcode', values.barcode);
    if (values.gtin) params.set('gtin', values.gtin);
    if (values.ntin) params.set('ntin', values.ntin);
    if (excludeId) params.set('exclude_id', excludeId);

    try {
      const response = await fetch(`/api/items/check-duplicate?${params.toString()}`, {
        headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
      });
      const data = await response.json();
      if (serial !== requestSerial) return Boolean(duplicate);
      if (response.ok && data.duplicate && data.item) {
        renderDuplicate(data.item);
        return true;
      }
      clearDuplicate();
      return false;
    } catch (error) {
      console.debug('Duplicate item check failed:', error);
      return Boolean(duplicate);
    }
  }

  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(() => checkNow(), 220);
  }

  [barcode, gtin, ntin].filter(Boolean).forEach(input => {
    input.addEventListener('input', scheduleCheck);
    input.addEventListener('change', scheduleCheck);
    input.addEventListener('blur', scheduleCheck);
  });
  itemType?.addEventListener('change', scheduleCheck);

  // USB/Bluetooth scanners often change input.value programmatically without
  // firing an input event in the existing item form. Poll the three identifiers
  // very lightly so a scanned duplicate is still caught immediately.
  setInterval(() => {
    const signature = `${clean(barcode?.value)}|${clean(gtin?.value)}|${clean(ntin?.value)}|${excludeId}`;
    if (signature !== lastSignature) scheduleCheck();
  }, 350);

  form.addEventListener('submit', async event => {
    if (form.dataset.duplicateValidated === '1') return;
    event.preventDefault();
    const found = await checkNow(true);
    if (found) return;
    form.dataset.duplicateValidated = '1';
    form.submit();
  });

  if (new URLSearchParams(location.search).get('duplicate') === '1') {
    const banner = ensureBanner();
    banner.style.display = 'block';
    banner.innerHTML = '<b>Данный товар уже есть в каталоге.</b> Nika открыла существующую карточку вместо создания дубля.';
    setTimeout(() => checkNow(true), 100);
  } else {
    scheduleCheck();
  }
})();
