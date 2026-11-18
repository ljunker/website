(function () {
    var root = document.documentElement;
    var button = document.getElementById('theme-toggle');

    function effectiveTheme() {
        var set = root.dataset.theme;
        if (set === 'light' || set === 'dark') return set;
        var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        return dark ? 'dark' : 'light';
    }

    function sync() {
        if (!button) return;
        var dark = effectiveTheme() === 'dark';
        button.setAttribute('aria-pressed', dark ? 'true' : 'false');
        button.setAttribute('aria-label', dark ? 'Zum hellen Design wechseln' : 'Zum dunklen Design wechseln');
    }

    if (button) {
        button.addEventListener('click', function () {
            var next = effectiveTheme() === 'dark' ? 'light' : 'dark';
            root.dataset.theme = next;
            try { localStorage.setItem('theme', next); } catch (err) {}
            sync();
        });
        sync();
        if (window.matchMedia) {
            var mq = window.matchMedia('(prefers-color-scheme: dark)');
            if (mq.addEventListener) mq.addEventListener('change', sync);
        }
    }

    // Aktiven Nav-Link markieren. Verglichen werden die aufgeloesten Pfade
    // (inkl. Praefix bei Branch-Previews), ohne Index-Datei und Schlussslash.
    function norm(path) {
        var p = path.replace(/index\.html$/, '').replace(/\/+$/, '');
        return p === '' ? '(root)' : p;
    }

    var here = norm(location.pathname);
    var links = document.querySelectorAll('.brand, #top-nav a');
    for (var i = 0; i < links.length; i++) {
        var a = links[i];
        if (a.origin !== location.origin) continue;
        if (norm(a.pathname) === here) a.setAttribute('aria-current', 'page');
    }
})();
