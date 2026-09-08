(() => {
  const MAX_SIDE = 1600;
  const QUALITY = 0.82;
  const MIN_COMPRESS_BYTES = 600 * 1024;
  const pending = new WeakMap();

  function imageInputs(root = document) {
    return [...root.querySelectorAll('input[type="file"]')].filter((input) => {
      const accept = (input.getAttribute('accept') || '').toLowerCase();
      const name = (input.getAttribute('name') || '').toLowerCase();
      return accept.includes('image') ||
        ['images', 'image', 'photo', 'comment_photos', 'logo', 'cover', 'banner'].includes(name);
    });
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return '';
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' КБ';
    return (bytes / 1024 / 1024).toFixed(1) + ' МБ';
  }

  function ensurePreview(input) {
    let wrap = input.parentElement?.querySelector(':scope > .nika-media-preview');
    if (wrap) return wrap;
    wrap = document.createElement('div');
    wrap.className = 'nika-media-preview';
    wrap.innerHTML = '<div class="nika-media-preview__status"></div><div class="nika-media-preview__grid"></div>';
    input.insertAdjacentElement('afterend', wrap);
    return wrap;
  }

  function renderPreview(input, files, statusText, ready = false) {
    const wrap = ensurePreview(input);
    const status = wrap.querySelector('.nika-media-preview__status');
    const grid = wrap.querySelector('.nika-media-preview__grid');
    status.textContent = statusText || '';
    status.classList.toggle('is-ready', ready);
    grid.innerHTML = '';

    for (const file of files || []) {
      const tile = document.createElement('div');
      tile.className = 'nika-media-preview__tile';

      const img = document.createElement('img');
      const url = URL.createObjectURL(file);
      img.src = url;
      img.alt = '';
      img.onload = () => URL.revokeObjectURL(url);

      const meta = document.createElement('div');
      meta.className = 'nika-media-preview__meta';
      meta.innerHTML = '<b></b><span></span>';
      meta.querySelector('b').textContent = file.name || 'Фото';
      meta.querySelector('span').textContent = formatBytes(file.size);

      tile.append(img, meta);
      grid.appendChild(tile);
    }
  }

  async function compressFile(file) {
    if (!file || !file.type.startsWith('image/') || file.size < MIN_COMPRESS_BYTES) {
      return file;
    }
    if (!('createImageBitmap' in window) || typeof DataTransfer === 'undefined') {
      return file;
    }

    let bitmap;
    try {
      bitmap = await createImageBitmap(file);
      const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      const width = Math.max(1, Math.round(bitmap.width * scale));
      const height = Math.max(1, Math.round(bitmap.height * scale));

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      canvas.getContext('2d', { alpha: false }).drawImage(bitmap, 0, 0, width, height);

      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/webp', QUALITY));
      if (!blob || blob.size >= file.size) return file;

      const base = (file.name || 'image').replace(/\.[^.]+$/, '');
      return new File([blob], base + '.webp', {
        type: 'image/webp',
        lastModified: Date.now(),
      });
    } catch (_) {
      return file;
    } finally {
      try { if (bitmap) bitmap.close(); } catch (_) {}
    }
  }

  async function optimizeInput(input) {
    if (!input.files || !input.files.length) return;
    const originals = [...input.files];
    renderPreview(input, originals, 'Подготавливаем фото…');
    input.dataset.nikaMediaOptimizing = '1';

    try {
      const dt = new DataTransfer();
      for (const file of originals) {
        dt.items.add(await compressFile(file));
      }
      input.files = dt.files;
      const optimized = [...input.files];
      const before = originals.reduce((sum, file) => sum + (file.size || 0), 0);
      const after = optimized.reduce((sum, file) => sum + (file.size || 0), 0);
      const saved = before > after ? ' • ' + formatBytes(before - after) + ' сэкономлено' : '';
      renderPreview(
        input,
        optimized,
        'Фото готово к загрузке • ' + formatBytes(after) + saved,
        true
      );
    } catch (_) {
      renderPreview(input, originals, 'Фото готово к загрузке', true);
    } finally {
      delete input.dataset.nikaMediaOptimizing;
    }
  }

  function bindInput(input) {
    if (input.dataset.nikaMediaBound === '1') return;
    input.dataset.nikaMediaBound = '1';
    input.addEventListener('change', () => {
      const promise = optimizeInput(input);
      pending.set(input, promise);
      promise.finally(() => {
        if (pending.get(input) === promise) pending.delete(input);
      });
    });
  }

  function bindAll(root = document) {
    imageInputs(root).forEach(bindInput);
  }

  document.addEventListener('DOMContentLoaded', () => bindAll());

  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (node.nodeType === 1) bindAll(node);
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if ((form.enctype || '').toLowerCase() !== 'multipart/form-data') return;

    if (form.dataset.nikaSubmitting === '1') {
      event.preventDefault();
      return;
    }

    const waits = imageInputs(form).map((input) => pending.get(input)).filter(Boolean);
    const buttons = [...form.querySelectorAll('button[type="submit"], input[type="submit"]')];

    const lock = () => {
      form.dataset.nikaSubmitting = '1';
      buttons.forEach((button) => {
        button.disabled = true;
        button.dataset.nikaOldText = button.tagName === 'INPUT' ? button.value : button.textContent;
        if (button.tagName === 'INPUT') button.value = 'Сохраняем…';
        else button.textContent = 'Сохраняем…';
      });
    };

    if (!waits.length) {
      lock();
      return;
    }

    event.preventDefault();
    lock();
    await Promise.allSettled(waits);
    form.submit();
  }, true);
})();


(() => {
  if (document.getElementById('nikaMediaPreviewStyles')) return;
  const style = document.createElement('style');
  style.id = 'nikaMediaPreviewStyles';
  style.textContent = `
    .nika-media-preview{margin-top:10px}
    .nika-media-preview__status{font-size:12px;font-weight:700;color:#7c8799;margin-bottom:8px}
    .nika-media-preview__status.is-ready{color:#16a34a}
    .nika-media-preview__grid{display:flex;gap:10px;flex-wrap:wrap}
    .nika-media-preview__tile{width:108px;border:1px solid rgba(99,102,241,.14);background:#fff;border-radius:14px;padding:6px;box-shadow:0 5px 14px rgba(15,23,42,.05)}
    .nika-media-preview__tile img{width:96px;height:76px;object-fit:cover;border-radius:10px;display:block;background:#eef2f7}
    .nika-media-preview__meta{padding:6px 2px 1px;min-width:0}
    .nika-media-preview__meta b{display:block;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#273044}
    .nika-media-preview__meta span{display:block;margin-top:2px;font-size:9px;color:#94a3b8}
    @media(max-width:600px){.nika-media-preview__tile{width:96px}.nika-media-preview__tile img{width:84px;height:68px}}
  `;
  document.head.appendChild(style);
})();
