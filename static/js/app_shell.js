(function () {
    'use strict';

    const MESSAGE_SOURCE = 'nika-app-shell';

    function cleanUrl(value) {
        const url = new URL(value, window.location.origin);
        url.searchParams.delete('nika_embedded');
        return url.pathname + url.search + url.hash;
    }

    function embeddedUrl(value) {
        const url = new URL(value, window.location.origin);
        url.searchParams.set('nika_embedded', '1');
        return url.pathname + url.search + url.hash;
    }

    function isNavigableLink(link, event) {
        if (!link || link.classList.contains('logout-link')) return false;
        if (event && (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)) return false;
        if (link.hasAttribute('download') || (link.target && link.target !== '_self')) return false;
        const href = link.getAttribute('href') || '';
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return false;
        const url = new URL(link.href, window.location.origin);
        return url.origin === window.location.origin;
    }

    function announceEmbeddedNavigation(type) {
        if (window.parent === window) return;
        window.parent.postMessage({
            source: MESSAGE_SOURCE,
            type: type,
            url: cleanUrl(window.location.href),
            title: document.title
        }, window.location.origin);
    }

    if (window.NIKA_EMBEDDED_PAGE) {
        document.addEventListener('DOMContentLoaded', function () {
            announceEmbeddedNavigation('ready');
        });
        document.addEventListener('click', function (event) {
            const link = event.target.closest('a[href]');
            if (isNavigableLink(link, event)) announceEmbeddedNavigation('loading');
        });
        document.addEventListener('submit', function (event) {
            if (!event.defaultPrevented) announceEmbeddedNavigation('loading');
        });
        return;
    }

    const frame = document.getElementById('nikaPageFrame');
    const loader = document.getElementById('nikaFrameLoader');
    if (!frame || !loader) return;

    let requestedUrl = cleanUrl(window.location.href);
    let loadTimer = null;
    let loadSafetyTimer = null;

    function setLoading(isLoading) {
        window.clearTimeout(loadTimer);
        window.clearTimeout(loadSafetyTimer);
        if (isLoading) {
            loadTimer = window.setTimeout(function () {
                loader.classList.add('active');
                frame.classList.add('is-loading');
            }, 90);
            loadSafetyTimer = window.setTimeout(function () {
                loader.classList.remove('active');
                frame.classList.remove('is-loading');
            }, 15000);
            return;
        }
        loader.classList.remove('active');
        frame.classList.remove('is-loading');
        frame.classList.add('ready');
    }

    function updateActiveMenu(value) {
        const current = new URL(value, window.location.origin).pathname.replace(/\/+$/, '') || '/';
        const links = Array.from(document.querySelectorAll('.sidebar a[href]'))
            .filter(function (link) { return !link.classList.contains('logout-link'); });
        let best = null;
        let bestLength = -1;
        links.forEach(function (link) {
            const target = new URL(link.href, window.location.origin).pathname.replace(/\/+$/, '') || '/';
            if ((current === target || (target !== '/' && current.startsWith(target + '/'))) && target.length > bestLength) {
                best = link;
                bestLength = target.length;
            }
        });
        links.forEach(function (link) { link.classList.toggle('active-menu-item', link === best); });
    }

    function navigate(value, options) {
        const config = options || {};
        const next = cleanUrl(value);
        requestedUrl = next;
        setLoading(true);
        frame.src = embeddedUrl(next);
        updateActiveMenu(next);
        closeSystemDrawers?.();
        document.getElementById('sidebar')?.classList.remove('mobile-open');
        document.querySelector('.sidebar-backdrop')?.classList.remove('show');
        if (config.push && cleanUrl(window.location.href) !== next) {
            window.history.pushState({nikaShell: true}, '', next);
        }
        if (typeof renderNikaPageContext === 'function') renderNikaPageContext();
    }

    document.addEventListener('click', function (event) {
        const link = event.target.closest('.sidebar a[href], .app-topbar a[href], .system-drawer a[href], .ai-assistant-panel a[href]');
        if (!isNavigableLink(link, event)) return;
        event.preventDefault();
        navigate(link.href, {push: true});
    }, true);

    window.addEventListener('message', function (event) {
        if (event.origin !== window.location.origin || event.source !== frame.contentWindow) return;
        const data = event.data || {};
        if (data.source !== MESSAGE_SOURCE) return;
        if (data.type === 'loading') {
            setLoading(true);
            return;
        }
        if (data.type !== 'ready') return;
        const current = cleanUrl(data.url || requestedUrl);
        requestedUrl = current;
        if (cleanUrl(window.location.href) !== current) {
            window.history.pushState({nikaShell: true}, '', current);
        }
        if (data.title) document.title = data.title;
        updateActiveMenu(current);
        setLoading(false);
    });

    frame.addEventListener('load', function () {
        try {
            if (frame.contentWindow.location.pathname === '/login') {
                window.location.href = '/login';
                return;
            }
            const frameTitle = frame.contentDocument?.title;
            if (frameTitle) document.title = frameTitle;
        } catch (error) {
            // Внешние платёжные страницы могут законно открываться внутри рабочей области.
        }
        setLoading(false);
    });

    window.addEventListener('popstate', function () {
        navigate(window.location.href, {push: false});
    });

    window.nikaShellNavigate = function (value) {
        navigate(value, {push: true});
    };

    updateActiveMenu(requestedUrl);
    frame.src = embeddedUrl(requestedUrl);
}());
