(function () {
    'use strict';

    const CARD_SELECTOR = '.module-card, .dept-feature-card, .quick-card[data-href], .mini-card[data-href]';
    const itemId = (menu, href) => `${menu}::${href}`;

    function readItems(storageKey) {
        try {
            const parsed = JSON.parse(localStorage.getItem(storageKey) || '[]');
            return Array.isArray(parsed) ? parsed.filter(item => item && item.menu && item.href) : [];
        } catch (_) {
            return [];
        }
    }

    function cardInfo(card) {
        if (card.dataset.allowed === 'false' || card.closest('[data-allowed="false"]')) return null;
        const link = card.querySelector('a[href]');
        const href = (card.dataset.href || (link && link.getAttribute('href')) || '').trim();
        const title = card.querySelector('h3, .quick-name, .mini-name');
        const menu = (card.dataset.menu || (title && title.textContent) || '').trim();
        if (!menu || !href || href === '#') return null;
        const icon = card.querySelector('.module-icon i, .dept-feature-icon i, .quick-icon i, .mini-icon i, i');
        const description = card.querySelector('p, .quick-desc, .mini-desc');
        return {
            id: itemId(menu, href),
            menu,
            href,
            permission: (card.dataset.permission || card.dataset.function || '').trim(),
            search: `${menu} ${(description && description.textContent) || ''}`.trim(),
            iconClass: (icon && icon.className) || 'fa-solid fa-star'
        };
    }

    function install(userKey) {
        if (!userKey || userKey === 'guest') return;
        const storageKey = `dashboard_favorite_items:${userKey}`;
        const cards = Array.from(document.querySelectorAll(CARD_SELECTOR));
        const entries = cards.map(card => ({card, info: cardInfo(card)})).filter(entry => entry.info);
        if (!entries.length) return;

        function render() {
            const selected = new Set(readItems(storageKey).map(item => item.id || itemId(item.menu, item.href)));
            entries.forEach(({card, info}) => {
                let button = card.querySelector(':scope > .secondary-favorite-toggle');
                if (!button) {
                    button = document.createElement('button');
                    button.type = 'button';
                    button.className = 'secondary-favorite-toggle';
                    button.dataset.favoriteId = info.id;
                    button.addEventListener('click', event => {
                        event.preventDefault();
                        event.stopPropagation();
                        let items = readItems(storageKey);
                        const exists = items.some(item => (item.id || itemId(item.menu, item.href)) === info.id);
                        items = exists
                            ? items.filter(item => (item.id || itemId(item.menu, item.href)) !== info.id)
                            : [...items, info];
                        localStorage.setItem(storageKey, JSON.stringify(items));
                        render();
                    });
                    card.appendChild(button);
                }
                const active = selected.has(info.id);
                button.classList.toggle('active', active);
                button.innerHTML = active ? '<i class="fa-solid fa-star"></i>' : '<i class="fa-regular fa-star"></i>';
                button.setAttribute('aria-label', active ? '取消收藏' : '收藏到首页常用功能');
                button.title = active ? '取消收藏' : '收藏到首页常用功能';
            });
        }
        render();
    }

    function start() {
        document.querySelectorAll(CARD_SELECTOR).forEach((card, index) => {
            const heading = card.querySelector('h3, .quick-name, .mini-name');
            const title = (card.dataset.menu || (heading && heading.textContent) || '').trim();
            let value = 2166136261;
            for (const character of title) value = Math.imul(value ^ character.codePointAt(0), 16777619) >>> 0;
            if (!card.id) card.id = 'workspace-feature-' + value.toString(16);
        });
        if (location.hash.startsWith('#workspace-feature-')) {
            const target = document.getElementById(location.hash.slice(1));
            if (target) target.scrollIntoView({block: 'center'});
        }
        fetch('/api/dashboard/favorites/context', {headers: {'Accept': 'application/json'}})
            .then(response => response.ok ? response.json() : null)
            .then(body => install(body && body.user_key))
            .catch(() => {});
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
