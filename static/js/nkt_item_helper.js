(() => {
    'use strict';

    const barcode = document.querySelector('input[name="barcode"]');
    const gtin = document.querySelector('input[name="gtin"]');
    const ntin = document.querySelector('input[name="ntin"]');
    const nameInput = document.querySelector('input[name="name"]');
    const marked = document.querySelector('input[name="is_marked"]');
    const form = barcode?.closest('form') || document.querySelector('form');

    if (!form || !barcode || !gtin || !ntin) return;

    const box = document.createElement('div');
    box.id = 'nktStatusBox';
    box.style.gridColumn = '1 / -1';
    box.style.padding = '12px 14px';
    box.style.border = '1px solid #dbe3ec';
    box.style.borderRadius = '12px';
    box.style.background = '#f8fafc';
    box.style.display = 'none';
    box.style.fontSize = '14px';
    box.style.lineHeight = '1.4';

    const anchor = ntin.nextElementSibling || ntin;
    anchor.insertAdjacentElement('afterend', box);

    let timer = null;
    let lastCode = '';

    function currentCode() {
        return String(barcode.value || gtin.value || ntin.value || '').trim();
    }

    function show(html, kind = 'neutral') {
        box.style.display = 'block';
        box.style.background = kind === 'ok' ? '#ecfdf5' : kind === 'warn' ? '#fff7ed' : '#f8fafc';
        box.style.borderColor = kind === 'ok' ? '#a7f3d0' : kind === 'warn' ? '#fed7aa' : '#dbe3ec';
        box.style.color = kind === 'ok' ? '#047857' : kind === 'warn' ? '#9a3412' : '#334155';
        box.innerHTML = html;
    }

    function hide() {
        box.style.display = 'none';
        box.innerHTML = '';
    }

    async function lookup(force = false) {
        const code = currentCode();
        if (!code) {
            lastCode = '';
            hide();
            return;
        }
        if (!force && code === lastCode) return;
        lastCode = code;

        show('Проверяем товар в Национальном каталоге…');

        try {
            const response = await fetch('/api/nkt/lookup/' + encodeURIComponent(code), {
                headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}
            });
            const data = await response.json();

            if (response.ok && data.found) {
                if (data.name && !nameInput.value.trim()) nameInput.value = data.name;
                if (data.gtin && !gtin.value.trim()) gtin.value = data.gtin;
                if (data.ntin && !ntin.value.trim()) ntin.value = data.ntin;
                if (marked && data.is_marked === true) marked.checked = true;

                show(
                    '<b>Товар найден в НКТ.</b>' +
                    (data.ntin ? '<br>NTIN: ' + escapeHtml(data.ntin) : '') +
                    (data.gtin ? '<br>GTIN: ' + escapeHtml(data.gtin) : ''),
                    'ok'
                );
                return;
            }

            const registrationUrl = data.registration_url || 'https://nationalcatalog.kz/';
            if (response.ok && data.found === false) {
                show(
                    '<b>Товар не найден в НКТ.</b><br>' +
                    'Это не мешает сохранить товар в Nika. При необходимости его можно зарегистрировать в Национальном каталоге.' +
                    '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px">' +
                    '<a href="' + escapeAttr(registrationUrl) + '" target="_blank" rel="noopener" class="btn" style="text-decoration:none">Создать в НКТ</a>' +
                    '<button type="button" id="nktRetryBtn" class="btn">Проверить снова</button>' +
                    '</div>',
                    'warn'
                );
                document.getElementById('nktRetryBtn')?.addEventListener('click', () => {
                    lastCode = '';
                    lookup(true);
                });
                return;
            }

            show(
                '<b>Не удалось проверить НКТ.</b><br>' +
                'Товар всё равно можно сохранить в Nika.' +
                (registrationUrl ? '<div style="margin-top:10px"><a href="' + escapeAttr(registrationUrl) + '" target="_blank" rel="noopener" class="btn" style="text-decoration:none">Открыть НКТ</a></div>' : ''),
                'neutral'
            );
        } catch (error) {
            console.debug('NKT lookup error:', error);
            show('<b>НКТ временно недоступен.</b><br>Товар всё равно можно сохранить в Nika.');
        }
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function escapeAttr(value) {
        return escapeHtml(value);
    }

    function scheduleLookup() {
        clearTimeout(timer);
        timer = setTimeout(() => lookup(false), 450);
    }

    [barcode, gtin, ntin].forEach(input => {
        input.addEventListener('change', scheduleLookup);
        input.addEventListener('blur', scheduleLookup);
    });

    // USB/Bluetooth scanners usually finish with Enter; check immediately.
    barcode.addEventListener('keydown', event => {
        if (event.key === 'Enter') {
            setTimeout(() => {
                lastCode = '';
                lookup(true);
            }, 120);
        }
    });

    if (currentCode()) scheduleLookup();
})();
