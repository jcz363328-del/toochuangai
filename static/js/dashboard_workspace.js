(async function () {
    'use strict';
    const sidebar = document.querySelector('.side-nav');
    const content = document.querySelector('.dashboard-content');
    if (!sidebar || !content) return;
    const topbar = document.querySelector('.topbar');
    const syncHeaderHeight = () => {
        if (topbar) document.documentElement.style.setProperty('--workspace-header-height', `${Math.ceil(topbar.getBoundingClientRect().height)}px`);
    };
    syncHeaderHeight();
    if (topbar && typeof ResizeObserver !== 'undefined') new ResizeObserver(syncHeaderHeight).observe(topbar);
    window.addEventListener('resize', syncHeaderHeight);
    const workspace = document.createElement('section');
    workspace.className = 'workspace';
    workspace.setAttribute('aria-live', 'polite');
    workspace.textContent = '正在加载功能目录…';
    content.append(workspace);
    const sources = Array.from(document.querySelectorAll('.nav-item[data-menu][data-href]')).filter(item => item.dataset.allowed !== 'false' && item.dataset.href);
    const innovationSource = document.querySelector('[data-menu="创新提案管理"][data-href]');
    const departments = new Set(['tk_project_group', 'tech_dept', 'visual_design_dept', 'photography_dept', 'ai_dept', 'warehouse_group', 'procurement_dept', 'general_office', 'rd_dept', 'finance_dept', 'hr_admin_dept', 'newcomer_group', 'shenzhen_dept']);
    const operations = new Set(['operation_dept_1', 'operation_dept_2', 'operation_dept_3', 'operation_dept_6', 'operation_dept_7']);
    operations.add('newcomer_group');
    const groups = new Map([['overview', {name: '总览', sources: []}], ['favorites', {name: '我的收藏', sources: []}], ['business', {name: '业务管理', sources: []}], ['operations', {name: '运营部功能', sources: []}]]);
    const departmentNames = {'内容生产工厂': 'tk_project_group', '仓储部组功能': 'warehouse_group', '采购部功能': 'procurement_dept', '总经办功能': 'general_office', '研发部功能': 'rd_dept', '财务部功能': 'finance_dept', '人力行政部功能': 'hr_admin_dept', '新人组功能': 'newcomer_group', '深圳功能模块': 'shenzhen_dept'};
    sources.forEach(item => {
        const key = departmentNames[item.dataset.menu] || item.dataset.department;
        if (operations.has(key)) groups.get('operations').sources.push(item);
        else if (departments.has(key)) groups.set(key, {name: item.dataset.menu.replace(/功能模块$|功能$/, ''), sources: [item]});
        else groups.get('business').sources.push(item);
    });
    let catalogError = '';
    let routePermissions = new Map();
    let catalogUserKey = '';
    try {
        const embedded = document.getElementById('workspaceCatalog');
        let catalog = embedded ? JSON.parse(embedded.textContent) : null;
        if (!catalog || !catalog.success) {
            const response = await fetch('/api/dashboard/workspace/catalog', {credentials: 'same-origin'});
            if (!response.ok) throw new Error('功能目录请求失败，请刷新重试');
            catalog = await response.json();
        }
        routePermissions = new Map(catalog.routes.map(route => [route.path, route.allowed]));
        Array.from(groups.keys()).filter(key => !['overview', 'favorites', 'business'].includes(key)).forEach(key => groups.delete(key));
        catalogUserKey = catalog.user_key || '';
        catalog.groups.forEach(group => groups.set(group.key, {name: group.name, sources: [], items: group.items, errors: group.errors, unavailableReason: group.unavailable_reason}));
    } catch (error) { catalogError = error.message; }
    sidebar.replaceChildren();
    let revision = 0;
    let selected = 'overview';
    const userKey = catalogUserKey;
    const storageKey = `dashboard_favorite_items:${userKey}`;
    function saved() { try { return JSON.parse(localStorage.getItem(storageKey) || '[]'); } catch (_) { return []; } }
    const currentItems = Array.from(groups.values()).flatMap(group => group.items || group.sources.map(entry).filter(Boolean));
    const aiFeatureTargets = new Set((groups.get('ai_dept')?.items || []).map(item => {
        const url = new URL(item.href, location.href);
        url.searchParams.delete('source');
        return url.pathname + url.search + url.hash;
    }));
    function currentFavorite(item) {
        const url = new URL(item.href, location.href);
        if (url.origin !== location.origin) return null;
        url.searchParams.delete('source');
        const match = currentItems.find(candidate => {
            const target = new URL(candidate.href, location.href);
            target.searchParams.delete('source');
            const exact = target.pathname + target.search + target.hash === url.pathname + url.search + url.hash;
            const legacyAnchor = /^#workspace-feature-\d+$/.test(url.hash) && candidate.menu === item.menu && target.pathname === url.pathname;
            return (exact || legacyAnchor) && candidate.allowed !== false;
        });
        return match ? {...match, menu: item.menu, id: item.id || match.id} : null;
    }
    function entry(item) {
        const title = item.querySelector('h3, .quick-name, .mini-name, .nav-name');
        const link = item.querySelector('a[href]');
        const menu = (item.dataset.menu || (title && title.textContent) || '').trim();
        const href = item.dataset.href || (link && link.getAttribute('href'));
        if (!menu || !href || href === '#' || item.dataset.allowed === 'false' || item.closest('[data-allowed="false"]')) return null;
        const url = new URL(href, location.href);
        if (!['http:', 'https:'].includes(url.protocol) || url.origin !== location.origin) return null;
        return {menu, href: url.pathname + url.search, iconClass: (item.querySelector('i') || {}).className || 'fa-solid fa-circle-dot', permission: item.dataset.permission || '', id: `${menu}::${url.pathname + url.search}`};
    }
    function applyWorkspaceSearch(value) {
        const query = value.trim().toLocaleLowerCase();
        const cards = Array.from(workspace.querySelectorAll('.workspace-card'));
        let matches = 0;
        cards.forEach(card => {
            const matched = card.querySelector('strong').textContent.toLocaleLowerCase().includes(query);
            card.hidden = !matched;
            card.style.display = matched ? '' : 'none';
            if (matched) matches += 1;
        });
        const divider = workspace.querySelector('.workspace-locked-divider');
        if (divider) {
            const lockedMatches = cards.filter(card => card.classList.contains('locked') && !card.hidden).length;
            divider.hidden = lockedMatches === 0;
            divider.textContent = `未开通功能（${lockedMatches}）`;
        }
        const input = workspace.querySelector('#overviewFeatureSearch');
        if (input && input.value !== value) input.value = value;
        const status = workspace.querySelector('#overviewSearchStatus');
        if (status) status.textContent = query ? `找到 ${matches} / ${cards.length} 项功能` : `共 ${cards.length} 项功能`;
        const empty = workspace.querySelector('.workspace-search-empty');
        if (empty) empty.hidden = !query || matches > 0 || cards.length === 0;
        const clear = workspace.querySelector('.workspace-search-clear');
        if (clear) clear.disabled = value.length === 0;
    }

    async function render(key) {
        selected = key;
        const currentRevision = ++revision;
        sidebar.querySelectorAll('button').forEach(button => { const active = button.dataset.group === key; button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active)); });
        workspace.replaceChildren();
        const heading = document.createElement('h1'); heading.className = 'workspace-title'; heading.textContent = groups.get(key).name;
        const notice = document.createElement('p'); notice.className = 'workspace-notice'; notice.setAttribute('role', 'alert'); notice.hidden = true;
        const grid = document.createElement('div'); grid.className = 'workspace-grid'; grid.setAttribute('aria-live', 'polite');
        if (key !== 'overview') workspace.append(heading);
        workspace.append(notice, grid);
        if (key === 'overview') {
            const search = document.createElement('div'); search.className = 'workspace-overview-search'; search.setAttribute('role', 'search'); search.setAttribute('aria-label', '总览功能搜索');
            const label = document.createElement('label'); label.htmlFor = 'overviewFeatureSearch'; label.textContent = '搜索功能';
            const input = document.createElement('input'); input.id = 'overviewFeatureSearch'; input.type = 'search'; input.placeholder = '输入功能名称，例如：视频、补货、看板'; input.setAttribute('aria-controls', 'workspaceFeatureGrid');
            const status = document.createElement('span'); status.id = 'overviewSearchStatus'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
            const clear = document.createElement('button'); clear.type = 'button'; clear.className = 'workspace-search-clear'; clear.textContent = '清空';
            const update = value => {
                const headerSearch = document.getElementById('featureSearch');
                if (headerSearch) { headerSearch.value = value; headerSearch.dispatchEvent(new Event('input')); }
                else applyWorkspaceSearch(value);
            };
            input.addEventListener('input', () => update(input.value));
            input.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); update(''); } });
            clear.addEventListener('click', () => { update(''); input.focus(); });
            search.append(label, input, clear, status);
            workspace.insertBefore(search, grid);
            const empty = document.createElement('p'); empty.className = 'workspace-search-empty'; empty.textContent = '没有找到匹配的功能，请更换关键词或清空搜索。'; empty.hidden = true; workspace.append(empty);
        }
        grid.id = 'workspaceFeatureGrid';
        grid.textContent = '正在加载功能…';
        let items = [];
        try {
            if (key === 'favorites') items = Array.from(document.querySelectorAll('#quickFavorites .quick-card')).filter(card => !card.classList.contains('favorite-hidden') && card.dataset.allowed !== 'false').map(entry).filter(Boolean).concat(saved()).map(currentFavorite).filter(Boolean);
            else {
                const targets = key === 'overview' ? Array.from(groups.entries()).filter(([name]) => !['overview', 'favorites', 'ai_dept'].includes(name)) : [[key, groups.get(key)]];
                for (const [name, group] of targets) {
                    if (name === 'business') items.push(...group.sources.map(entry).filter(Boolean));
                    else if (group.items) {
                        items.push(...group.items);
                        if (group.errors.length) { notice.textContent = '部分部门功能加载失败，请刷新重试；已加载的功能仍可使用。'; notice.hidden = false; }
                    }
                }
            }
            if (currentRevision !== revision) return;
            if (key === 'overview') items = items.filter(item => {
                const url = new URL(item.href, location.href);
                url.searchParams.delete('source');
                return !aiFeatureTargets.has(url.pathname + url.search + url.hash);
            });
            const unique = Array.from(new Map(items.map(item => { const url = new URL(item.href, location.href); url.searchParams.delete('source'); return [item.menu + '::' + url.pathname + url.search + url.hash, item]; })).values());
            if (catalogError) { notice.textContent = catalogError; notice.hidden = false; }
            grid.replaceChildren();
            if (!unique.length) { grid.textContent = groups.get(key).unavailableReason || (key === 'favorites' ? '暂无收藏，请到部门功能中点击星标添加。' : '当前部门尚未配置功能。'); return; }
            const ordered = unique.filter(item => item.allowed !== false).concat(unique.filter(item => item.allowed === false));
            let lockedDividerAdded = false;
            ordered.forEach(item => {
                const card = document.createElement('div'); card.className = 'workspace-card'; card.tabIndex = 0; card.setAttribute('role', 'link');
                const locked = item.allowed === false;
                if (locked && !lockedDividerAdded) {
                    const divider = document.createElement('div'); divider.className = 'workspace-locked-divider'; divider.setAttribute('role', 'separator'); divider.setAttribute('aria-label', '未开通功能');
                    grid.append(divider);
                    lockedDividerAdded = true;
                }
                card.classList.toggle('locked', locked);
                card.setAttribute('aria-disabled', String(locked));
                const open = () => { if (locked) { window.alert('暂无该功能权限，请联系管理员开通。'); return; } if (typeof _logMenuClick === 'function') _logMenuClick(item.menu, item.href); window.location.href = item.href; };
                card.addEventListener('click', event => { if (!event.target.closest('button')) open(); });
                card.addEventListener('keydown', event => { if (event.target === card && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); open(); } });
                const icon = document.createElement('i'); icon.className = item.iconClass;
                const title = document.createElement('strong'); title.textContent = item.menu;
                const favorite = document.createElement('button'); favorite.type = 'button'; favorite.className = 'favorite-toggle';
                const refresh = () => { const active = saved().some(value => value.id === item.id); favorite.classList.toggle('active', active); favorite.innerHTML = active ? '<i class="fa-solid fa-star"></i>' : '<i class="fa-regular fa-star"></i>'; favorite.setAttribute('aria-label', active ? '取消收藏' : '收藏功能'); };
                favorite.addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); const values = saved(); const exists = values.some(value => value.id === item.id); localStorage.setItem(storageKey, JSON.stringify(exists ? values.filter(value => value.id !== item.id) : values.concat(item))); refresh(); if (selected === 'favorites') render('favorites'); });
                refresh(); card.append(icon, title);
                if (locked) { const label = document.createElement('span'); label.className = 'workspace-lock'; label.textContent = '未开通权限'; card.append(label); }
                else card.append(favorite);
                grid.append(card);
            });
            applyWorkspaceSearch(document.getElementById('featureSearch')?.value || '');
        } catch (error) { if (currentRevision === revision) grid.textContent = '加载失败：' + error.message + '。点击部门可重试。'; }
    }
    groups.forEach((group, key) => {
        if (key === 'business') return;
        if (!['overview', 'favorites'].includes(key) && !group.items && !group.sources.length) return;
        const button = document.createElement('button'); button.type = 'button'; button.className = 'side-nav-item'; button.dataset.group = key; button.textContent = group.name;
        if (group.items) { const count = document.createElement('span'); count.className = 'workspace-count'; count.textContent = group.items.length; button.append(count); }
        button.addEventListener('click', () => render(key)); sidebar.append(button);
        if (key === 'favorites' && innovationSource) {
            const link = document.createElement('a');
            link.className = 'side-nav-item';
            link.href = innovationSource.dataset.href;
            link.textContent = '创新提案管理';
            link.addEventListener('click', () => { if (typeof _logMenuClick === 'function') _logMenuClick('创新提案管理', link.href); });
            sidebar.append(link);
        }
    });
    document.getElementById('featureSearch')?.addEventListener('input', event => applyWorkspaceSearch(event.target.value));
    render('overview');
})();
