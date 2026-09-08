(() => {
  const MAX_SIDE = 1600;
  const QUALITY = 0.82;
  const MIN_COMPRESS_BYTES = 600 * 1024;
  const pending = new WeakMap();

  function imageInputs(root = document) {
    return [...root.querySelectorAll('input[type="file"]')].filter((input) => {
      const accept = (input.getAttribute('accept') || '').toLowerCase();
      return accept.includes('image');
    });
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
    input.dataset.nikaMediaOptimizing = '1';
    try {
      const dt = new DataTransfer();
      for (const file of input.files) {
        dt.items.add(await compressFile(file));
      }
      input.files = dt.files;
    } catch (_) {
      // Browser fallback: original image will be sent.
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
