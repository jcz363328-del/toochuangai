(() => {
    'use strict';
    const $ = id => document.getElementById(id);
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const api = '/api/operation/fba_shipping_methods';
    let tab = 'all', page = 1, pages = 1, records = [], selected = new Set(), loading = false;
    let controller, revision = 0, timer, returnFocus;
    const cacheKey = `fba-shipping-v1:${document.documentElement.dataset.cacheUser}`;
    let cache = {queries: {}, options: null, state: null};
    try { cache = JSON.parse(sessionStorage.getItem(cacheKey)) || cache; } catch (_) {}
    function saveCache() {
        cache.state = Object.fromEntries(['search','shop','shipping','status','sort','pageSize'].map(id => [id, $(id).value]));
        Object.assign(cache.state, {tab, page});
        try { sessionStorage.setItem(cacheKey, JSON.stringify(cache)); } catch (_) {}
    }
    function params() {
        const p = new URLSearchParams({tab, page: String(page), page_size: $('pageSize').value});
        for (const [id, key] of [['search','q'],['shop','dian'],['shipping','shipping'],['status','status'],['sort','sort']]) {
            if ($(id).value.trim()) p.set(key, $(id).value.trim());
        }
        return p;
    }
    function toast(message) {
        $('toast').textContent = message;
        $('toast').style.display = 'block';
        clearTimeout(toast.timer);
        toast.timer = setTimeout(() => { $('toast').style.display = 'none'; }, 2600);
    }
    function selection() {
        $('selection').textContent = `已选择当前页 ${selected.size} 条`;
        $('allCheck').checked = records.length > 0 && records.every(r => selected.has(r.key));
        $('allCheck').indeterminate = selected.size > 0 && selected.size < records.length;
        $('export').textContent = selected.size ? `↓ 导出所选 ${selected.size} 条` : '↓ 导出当前结果';
    }
    function controls() {
        $('prev').disabled = loading || page <= 1;
        $('next').disabled = loading || page >= pages;
        $('export').disabled = loading;
        $('refresh').disabled = loading;
        $('allCheck').disabled = loading || records.length === 0;
    }
    function dateParts(value) {
        if (!value) return '<span class="muted">—</span>';
        const [d, t] = value.split(' ');
        return `${esc(d)}<span class="sub">${esc(t || '')}</span>`;
    }
    function render(data) {
        records = data.records;
        page = data.page;
        pages = data.total_pages;
        const stats = data.stats;
        for (const key of ['total','filled','issues','checked']) $(key).textContent = stats[key].toLocaleString();
        for (const [id, key] of [['tabAll','total'],['tabIssue','issues'],['tabFilled','filled'],['tabUnchecked','unchecked']]) $(id).textContent = stats[key].toLocaleString();
        $('rows').innerHTML = records.map((r, index) => `<tr class="${r.issues.length ? 'attention' : ''}" data-row-detail="${index}" tabindex="0" aria-label="查看货件 ${esc(r.id)} 详情">
            <td><input type="checkbox" class="check rowcheck" data-key="${esc(r.key)}" aria-label="选择货件 ${esc(r.id)}"></td>
            <td><b>${esc(r.shop) || '—'}</b><span class="sub code cargo">${esc(r.id) || '—'}</span></td>
            <td><span class="tag ${r.ship.includes('海运') ? 'blue' : ''}">${esc(r.ship) || '—'}</span></td>
            <td class="code" title="${esc(r.log)}">${esc(r.log) || '—'}</td>
            <td title="${esc(r.tracking)}"><span class="code ${!r.codes.length ? 'muted' : ''}">${esc(r.codes[0] || '暂缺追踪码')}</span>${r.codes.length > 1 ? ` <span class="tag">+${r.codes.length - 1}</span>` : ''}<span class="sub code" title="${esc(r.ien)}">IEN ${esc(r.ien) || '—'}</span></td>
            <td><span class="tag ${r.filled ? 'green' : ''}">${r.filled ? '● 已填写' : esc(r.status) || '未标记'}</span>${r.issues.length ? `<span class="sub" style="color:#b4873d">${esc(r.issues.join('；'))}</span>` : ''}</td>
            <td><span class="count" style="color:${r.issues.includes('数量待核对') ? '#c58a27' : '#586780'}">${r.n ?? '—'}</span>${r.issues.includes('数量待核对') ? `<span class="sub" style="color:#b4873d">识别 ${r.parsed_count} 个</span>` : ''}</td>
            <td>${r.check ? dateParts(r.check) : '<span class="tag amber">待检查</span>'}</td>
            <td>${dateParts(r.date)}</td><td><button class="link" data-detail="${index}">详情 ›</button></td></tr>`).join('') || '<tr><td colspan="10" class="empty">没有符合条件的货件，请调整筛选。</td></tr>';
        $('resultCount').textContent = `共 ${data.total.toLocaleString()} 条货件 · ${$('sort').selectedOptions[0].textContent}`;
        $('updatedAt').textContent = `数据读取于 ${data.loaded_at}`;
        $('pageInfo').textContent = `${page} / ${pages}`;
        selected.clear();
        selection();
    }
    async function load(reset = false, force = false) {
        if (reset) page = 1;
        const serial = ++revision;
        if (controller) controller.abort();
        controller = new AbortController();
        const query = params().toString();
        if (!force && cache.queries[query]) {
            loading = false;
            render(cache.queries[query]);
            saveCache(); controls();
            return;
        }
        loading = true;
        selected.clear(); records = [];
        selection(); controls();
        $('resultCount').textContent = '正在读取货件数据…';
        $('rows').innerHTML = '<tr><td colspan="10" class="empty">正在读取货件数据…</td></tr>';
        try {
            const response = await fetch(`${api}?${query}${force ? '&refresh=1' : ''}`, {signal: controller.signal, credentials:'same-origin'});
            if (response.redirected) throw new Error('登录已过期，请刷新页面重新登录');
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error(payload.message || '读取失败，请检查访问权限');
            if (serial === revision) {
                if (force) cache.queries = {};
                cache.queries[query] = payload.data;
                // Bound session storage while retaining recently viewed result pages.
                const keys = Object.keys(cache.queries);
                if (keys.length > 20) delete cache.queries[keys[0]];
                render(payload.data);
                saveCache();
            }
        } catch (error) {
            if (error.name !== 'AbortError' && serial === revision) {
                $('rows').innerHTML = `<tr><td colspan="10" class="empty" style="color:#bb6b45">${esc(error.message)}</td></tr>`;
                $('resultCount').textContent = '数据读取失败，可点击刷新数据重试';
                for (const key of ['total','filled','issues','checked','tabAll','tabIssue','tabFilled','tabUnchecked']) $(key).textContent = '—';
            }
        } finally {
            if (serial === revision) { loading = false; controls(); }
        }
    }
    function close() {
        $('overlay').classList.remove('open');
        $('overlay').setAttribute('aria-hidden', 'true');
        returnFocus?.focus();
    }
    function detail(r, trigger = document.activeElement) {
        returnFocus = trigger;
        $('drawer').innerHTML = `<button class="close" id="close" aria-label="关闭详情">×</button><span class="crumb">货件详情</span><h2 class="code">${esc(r.id)}</h2><p>${esc(r.shop)} · ${esc(r.ship)}</p>
            <div class="detail-grid"><div><label>填写状态 · 原表标记</label><span class="tag ${r.filled ? 'green' : ''}">${r.filled ? '已填写 · Y' : esc(r.status) || '未标记 · 空值'}</span></div><div><label>追踪码个数 · 数据库记录</label>${r.n ?? '—'}</div><div><label>检查日期</label>${esc(r.check) || '尚未记录'}</div><div><label>导入时间</label>${esc(r.date) || '—'}</div><div><label>小包裹</label>${esc(r.package) || '—'}</div><div><label>记录序号</label>${esc(r.key)}</div></div>
            ${r.issues.length ? `<div class="note" style="margin:0;color:#b4822e;background:#fff9ec">${esc(r.issues.join('；'))}</div>` : ''}
            <div class="detail-section"><h3>亚马逊追踪码 <span class="tag">识别 ${r.parsed_count} 个</span></h3>${r.codes.map(c => `<div class="tracking">${esc(c)}</div>`).join('') || '<p>暂缺追踪码</p>'}${r.codes.length ? '<button class="btn" id="copy">复制全部追踪码</button>' : ''}</div>
            <div class="detail-section"><h3>清关与物流</h3><div class="detail-grid"><div><label>IEN</label><span class="code">${esc(r.ien) || '—'}</span></div><div><label>物流单号</label><span class="code">${esc(r.log) || '—'}</span></div></div></div><div class="detail-section"><p>本页仅供查询，不修改填写状态、检查日期或原始追踪码。</p></div>`;
        $('overlay').classList.add('open');
        $('overlay').setAttribute('aria-hidden', 'false');
        $('close').onclick = close;
        $('close').focus();
        if ($('copy')) $('copy').onclick = async () => {
            const value = r.codes.join('\n');
            try {
                await navigator.clipboard.writeText(value);
                toast('追踪码已复制');
            } catch (_) {
                // Clipboard API is unavailable on ordinary HTTP origins.
                const input = document.createElement('textarea');
                input.value = value; input.style.position = 'fixed'; input.style.opacity = '0';
                document.body.append(input); input.select();
                const copied = document.execCommand('copy'); input.remove();
                if (copied) toast('追踪码已复制'); else window.prompt('请复制以下追踪码', value);
                $('copy').focus();
            }
        };
    }
    $('rows').onclick = event => {
        const button = event.target.closest('[data-detail]');
        if (button) { detail(records[Number(button.dataset.detail)], button); return; }
        if (event.target.closest('input,button,a,select,textarea,label') || event.target.closest('td')?.cellIndex === 0) return;
        if (window.getSelection()?.toString()) return;
        const row = event.target.closest('tr[data-row-detail]');
        if (row) detail(records[Number(row.dataset.rowDetail)], row);
    };
    $('rows').onkeydown = event => {
        if (!event.target.matches('tr[data-row-detail]') || !['Enter', ' '].includes(event.key)) return;
        event.preventDefault();
        detail(records[Number(event.target.dataset.rowDetail)], event.target);
    };
    $('rows').onchange = event => {
        if (!event.target.matches('.rowcheck')) return;
        const key = event.target.dataset.key;
        event.target.checked ? selected.add(key) : selected.delete(key);
        selection();
    };
    $('allCheck').onchange = () => {
        selected = new Set($('allCheck').checked ? records.map(r => r.key) : []);
        document.querySelectorAll('.rowcheck').forEach(c => { c.checked = selected.has(c.dataset.key); });
        selection();
    };
    $('search').oninput = () => { clearTimeout(timer); timer = setTimeout(() => load(true), 300); };
    for (const id of ['shop','shipping','status','sort','pageSize']) $(id).onchange = () => load(true);
    document.querySelectorAll('[data-tab]').forEach(b => { b.onclick = () => {
        tab = b.dataset.tab;
        document.querySelectorAll('[data-tab]').forEach(t => t.classList.toggle('active', t === b));
        load(true);
    }; });
    $('refresh').onclick = async () => {
        clearTimeout(timer);
        await load(false, true);
        await options(true);
    };
    $('reset').onclick = () => {
        clearTimeout(timer);
        for (const id of ['search','shop','shipping','status']) $(id).value = '';
        $('sort').value = 'import_desc';
        document.querySelector('[data-tab="all"]').click();
    };
    $('prev').onclick = () => { page--; load(); };
    $('next').onclick = () => { page++; load(); };
    $('overlay').onclick = e => { if (e.target === $('overlay')) close(); };
    document.onkeydown = e => {
        if (!$('overlay').classList.contains('open')) return;
        if (e.key === 'Escape') close();
        if (e.key === 'Tab') {
            const buttons = [...$('drawer').querySelectorAll('button')];
            if (e.shiftKey && document.activeElement === buttons[0]) { e.preventDefault(); buttons.at(-1).focus(); }
            else if (!e.shiftKey && document.activeElement === buttons.at(-1)) { e.preventDefault(); buttons[0].focus(); }
        }
    };
    $('export').onclick = async () => {
        const p = params();
        if (selected.size) p.set('selected', [...selected].join(','));
        $('export').disabled = true;
        try {
            const response = await fetch(`${api}/export?${p}`, {credentials:'same-origin'});
            if (!response.ok || !response.headers.get('Content-Type')?.includes('text/csv')) throw new Error('导出失败，请刷新登录状态或稍后重试');
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement('a'); a.href = url; a.download = 'FBA货件追踪.csv'; a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            toast('导出完成');
        } catch (e) { toast(e.message); } finally { $('export').disabled = false; }
    };
    function renderOptions(data) {
        for (const [id, key] of [['shop','shops'],['shipping','shipping_methods']]) {
            const value = $(id).value;
            $(id).options.length = 1;
            for (const item of data[key]) $(id).add(new Option(item, item));
            $(id).value = value;
        }
    }
    async function options(force = false) {
        if (!force && cache.options) { renderOptions(cache.options); return; }
        try {
            const response = await fetch(`${api}/shops`, {credentials:'same-origin'});
            const payload = await response.json();
            if (!response.ok || !payload.success) throw new Error('筛选选项加载失败');
            cache.options = payload.data;
            renderOptions(payload.data);
            saveCache();
        } catch (_) { toast('筛选选项暂不可用，可继续搜索货件'); }
    }
    async function init() {
        const state = cache.state;
        await options();
        if (state) {
            for (const id of ['search','shop','shipping','status','sort','pageSize']) $(id).value = state[id];
            tab = state.tab; page = state.page;
            document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        }
        await load();
    }
    init();
})();
