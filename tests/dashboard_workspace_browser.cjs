const { chromium } = require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
    const output = path.resolve(__dirname, '../outputs/workspace-audit');
    fs.mkdirSync(output, { recursive: true });
    const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
    try {
        const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
        const page = await context.newPage();
        const errors = [];
        let catalogRequests = 0;
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => { if (request.url().includes('/api/dashboard/workspace/catalog')) catalogRequests += 1; });
        await page.goto('http://127.0.0.1:8000/dev_login?user_type=developer', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('.workspace-card', { timeout: 45000 });
        const catalog = await page.locator('#workspaceCatalog').evaluate(element => JSON.parse(element.textContent));
        assert.equal(catalog.success, true);
        assert.equal(await page.locator('.workspace-description').count(), 0);
        assert.equal(await page.locator('.workspace-notice:visible').count(), 0);
        const overviewSearch = page.locator('#overviewFeatureSearch');
        assert.equal(await overviewSearch.count(), 1);
        assert.equal(await page.locator('.workspace-title').count(), 0);
        assert.equal(await page.locator('.workspace > :not([hidden])').first().evaluate(element => element.classList.contains('workspace-overview-search')), true);
        const permissionOrder = await page.locator('.workspace-card').evaluateAll(cards => cards.map(card => card.classList.contains('locked')));
        const firstLocked = permissionOrder.indexOf(true);
        if (firstLocked >= 0) {
            assert.ok(permissionOrder.slice(firstLocked).every(Boolean));
            assert.equal(await page.locator('.workspace-locked-divider').count(), 1);
            assert.equal(await page.locator('.workspace-locked-divider').evaluate(element => element.nextElementSibling.classList.contains('locked')), true);
        }
        const overviewTotal = await page.locator('.workspace-card:visible').count();
        await overviewSearch.fill('视频');
        assert.ok(await page.locator('.workspace-card:visible').count() > 0);
        assert.ok((await page.locator('.workspace-card:visible strong').allTextContents()).every(name => name.includes('视频')));
        assert.equal(await page.locator('#featureSearch').inputValue(), '视频');
        await overviewSearch.fill('不存在的功能_workspace_search_test');
        assert.equal(await page.locator('.workspace-card:visible').count(), 0);
        assert.equal(await page.locator('.workspace-search-empty').isVisible(), true);
        if (firstLocked >= 0) assert.equal(await page.locator('.workspace-locked-divider').isVisible(), false);
        assert.match(await page.locator('#overviewSearchStatus').textContent(), /找到 0/);
        await page.locator('.workspace-search-clear').click();
        assert.equal(await page.locator('.workspace-card:visible').count(), overviewTotal);
        assert.equal(await page.locator('.workspace-search-empty').isVisible(), false);
        await page.locator('#featureSearch').fill('gMv');
        assert.equal(await overviewSearch.inputValue(), 'gMv');
        assert.ok((await page.locator('.workspace-card:visible strong').allTextContents()).every(name => name.toLowerCase().includes('gmv')));
        await overviewSearch.press('Escape');
        assert.equal(await page.locator('#featureSearch').inputValue(), '');
        assert.equal(await page.locator('.workspace-card:visible').count(), overviewTotal);
        assert.equal(await page.locator('.side-nav-item[data-group="business"]').count(), 0);
        const innovationLink = page.locator('.side-nav a.side-nav-item').filter({ hasText: '创新提案管理' });
        assert.equal(await innovationLink.count(), 1);
        assert.ok(await innovationLink.getAttribute('href'));
        assert.equal(await innovationLink.evaluate(element => element.previousElementSibling.dataset.group), 'favorites');
        const sidebar = await page.locator('.side-nav').evaluate(element => ({ left: element.getBoundingClientRect().left, position: getComputedStyle(element).position }));
        assert.equal(sidebar.left, 0);
        assert.equal(sidebar.position, 'fixed');
        for (const width of [2207, 1440, 768, 600]) {
            await page.setViewportSize({ width, height: 960 });
            await page.evaluate(() => window.scrollTo(0, 0));
            await page.waitForTimeout(120);
            const shell = await page.evaluate(() => {
                const header = document.querySelector('.topbar').getBoundingClientRect();
                const navigation = document.querySelector('.side-nav').getBoundingClientRect();
                const brand = document.querySelector('.brand-wrap').getBoundingClientRect();
                const title = document.querySelector('.workspace-overview-search, .workspace-title').getBoundingClientRect();
                return { headerTop: header.top, headerBottom: header.bottom, navigationTop: navigation.top, navigationRight: navigation.right, brandRight: brand.right, titleTop: title.top };
            });
            assert.equal(shell.headerTop, 0, `header at ${width}px`);
            assert.ok(Math.abs(shell.navigationTop - shell.headerBottom) <= 1, `navigation offset at ${width}px`);
            assert.ok(shell.brandRight <= shell.navigationRight + 1, `brand width at ${width}px`);
            assert.ok(shell.titleTop >= shell.headerBottom, `content offset at ${width}px`);
            await page.evaluate(() => window.scrollTo(0, 400));
            assert.equal(await page.locator('.topbar').evaluate(element => element.getBoundingClientRect().top), 0);
        }
        await page.setViewportSize({ width: 1440, height: 960 });
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.waitForTimeout(120);
        await page.screenshot({ path: path.join(output, 'workspace-shell.png') });
        const groups = [];
        for (const group of catalog.groups) {
            assert.deepEqual(group.errors, []);
            await page.locator(`.side-nav-item[data-group="${group.key}"]`).click();
            assert.equal(await page.locator('.workspace-description').count(), 0);
            assert.equal(await page.locator('.workspace-notice:visible').count(), 0);
            assert.equal(await page.locator('.workspace-card').count(), group.items.length, group.key);
            assert.equal(await page.locator('.workspace-card.locked').count(), group.items.filter(item => item.allowed === false).length, group.key);
            const ordered = await page.locator('.workspace-card').evaluateAll(cards => cards.map(card => card.classList.contains('locked')));
            const start = ordered.indexOf(true);
            if (start >= 0) assert.ok(ordered.slice(start).every(Boolean), `locked features must be last in ${group.key}`);
            groups.push({ key: group.key, name: group.name, total: group.items.length, available: group.items.filter(item => item.allowed).length, features: group.items.map(item => ({ name: item.menu, href: item.href, allowed: item.allowed, required_permissions: item.required_permissions })) });
            if (['tk_project_group', 'ai_dept'].includes(group.key)) await page.screenshot({ path: path.join(output, `${group.key}.png`), fullPage: true });
        }
        const hasAi = catalog.groups.some(group => group.key === 'ai_dept');
        if (!hasAi) {
            assert.equal(await page.locator('.side-nav-item[data-group="ai_dept"]').count(), 0);
            assert.equal((await context.request.get('http://127.0.0.1:8000/ai_modules')).status(), 403);
        }
        await page.locator(`.side-nav-item[data-group="${hasAi ? 'ai_dept' : 'operations'}"]`).click();
        const locked = page.locator('.workspace-card.locked').first();
        if (await locked.count()) {
            await Promise.all([
                page.waitForEvent('dialog').then(dialog => dialog.dismiss()),
                locked.click({ force: true })
            ]);
        }
        await page.locator('.side-nav-item[data-group="tk_project_group"]').click();
        await page.locator('#featureSearch').fill('视频');
        assert.ok(await page.locator('.workspace-card:visible').count() > 0);
        await page.locator('#featureSearch').fill('');
        await page.locator('.side-nav-item[data-group="favorites"]').click();
        assert.equal(await page.locator('.workspace-card').count(), await page.locator('.workspace-card:not(.locked)').count());
        const privateItem = { menu: 'AI private test', href: '/__workspace_ai_test__', id: 'ai-private-test', allowed: true, iconClass: 'fas fa-robot' };
        const simulated = { ...catalog, can_access_ai_workspace: true, groups: catalog.groups.filter(group => group.key !== 'ai_dept').concat({ key: 'ai_dept', name: 'AI部', items: [privateItem], errors: [] }) };
        await page.route('**/dashboard?workspace_test=ai', async route => {
            const response = await route.fetch();
            const body = (await response.text()).replace(/<script id="workspaceCatalog" type="application\/json">[\s\S]*?<\/script>/, `<script id="workspaceCatalog" type="application/json">${JSON.stringify(simulated).replace(/</g, '\\u003c')}</script>`);
            await route.fulfill({ response, body });
        });
        await page.goto('http://127.0.0.1:8000/dashboard?workspace_test=ai', { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('.side-nav-item[data-group="ai_dept"]');
        assert.equal(await page.locator('.workspace-card').filter({ hasText: privateItem.menu }).count(), 0);
        await page.locator('.side-nav-item[data-group="ai_dept"]').click();
        assert.equal(await page.locator('.workspace-card').filter({ hasText: privateItem.menu }).count(), 1);
        await page.locator('.side-nav-item[data-group="overview"]').click();
        assert.equal(await page.locator('.workspace-card').filter({ hasText: privateItem.menu }).count(), 0);
        assert.equal(catalogRequests, 0, 'Department switching must not fetch the catalog again');
        assert.deepEqual(errors, []);
        const report = { groups, javascript_errors: errors, additional_catalog_requests: catalogRequests, result: 'passed' };
        fs.writeFileSync(path.join(output, 'audit.json'), JSON.stringify(report, null, 2));
        console.log(JSON.stringify({ ...report, groups: groups.map(({ features, ...group }) => group) }, null, 2));
        await context.close();
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
