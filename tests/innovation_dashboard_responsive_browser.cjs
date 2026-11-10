/* Responsive browser regression for the innovation homepage.
 * Uses a new isolated Edge context. All API calls are mocked and writes are blocked.
 * If the running homepage is unavailable, Jinja renders its original templates
 * without importing app.py or contacting the database.
 */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { spawnSync } = require('node:child_process');
const { chromium } = require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'outputs', 'innovation-responsive');
const assets = path.join(out, 'assets');
fs.mkdirSync(assets, { recursive: true });
const mockData = {
  basic_stats: { total_count: 17, adopted_count: 2, effectiveness_rate: 11.76 },
  top_departments: [{ name: '产品研发部', score: 20 }, { name: '内容工厂', score: 10 }, { name: '销售一部', score: 8 }],
  top_persons: [{ name: '李欣纳', score: 10 }, { name: '周俊成', score: 10 }, { name: '李彩', score: 0 }, { name: '孙文杰', score: 0 }, { name: '王玉瑶', score: 0 }],
  top_proposal_counts: ['周俊成', '李欣纳', '崔燕妮', '张馨文', '林言', '刘佳', '孙佳榕', '孙文杰'].map((name, i) => ({ name, count: i > 1 && i < 5 ? 2 : 1, effective_count: i < 2 ? 1 : 0 })),
  top_highest_scores: [{ name: '李欣纳', score: 10 }, { name: '周俊成', score: 10 }],
  categories: [{ name: '工作内容及流程创新', count: 13 }, { name: '产品改善及创新', count: 4 }],
  monthly_trend: [{ month: '2026-06', count: 2 }, { month: '2026-07', count: 5 }, { month: '2026-08', count: 3 }, { month: '2026-09', count: 8 }, { month: '2026-10', count: 10 }, { month: '2026-11', count: 17 }]
};
const chartIds = ['top-department', 'top-person', 'top-proposal-counts', 'top-highest-scores', 'category-distribution', 'monthly-trend'];
const remoteAssets = new Map([
  ['bootstrap.min.css', 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css'],
  ['bootstrap.bundle.min.js', 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js'],
  ['bootstrap-icons.css', 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css'],
  ['bootstrap-icons.woff2', 'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/fonts/bootstrap-icons.woff2'],
  ['axios.min.js', 'https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js'],
  ['echarts.min.js', 'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js']
]);
const mime = name => name.endsWith('.css') ? 'text/css' : name.endsWith('.woff2') ? 'font/woff2' : name.endsWith('.js') ? 'application/javascript' : 'text/html';
const assetNotes = [];

async function prepareAssets() {
  for (const [name, url] of remoteAssets) {
    const target = path.join(assets, name);
    if (fs.existsSync(target)) continue;
    if (name === 'echarts.min.js') {
      const local = path.join(root, 'business_analysis/node_modules/echarts/dist/echarts.min.js');
      if (fs.existsSync(local)) {
        fs.copyFileSync(local, target);
        assetNotes.push(`ECharts local fallback: ${JSON.parse(fs.readFileSync(path.join(root, 'business_analysis/node_modules/echarts/package.json'), 'utf8')).version}`);
        continue;
      }
    }
    if (name === 'axios.min.js') {
      fs.writeFileSync(target, 'window.axios={get:async function(url){const r=await fetch(url);return {data:await r.json()};}};');
      assetNotes.push('Axios read-only GET shim used for mocked API responses.');
      continue;
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      fs.writeFileSync(target, Buffer.from(await response.arrayBuffer()));
    } catch (error) {
      if (name === 'bootstrap.min.css' || name === 'echarts.min.js') throw new Error(`Required asset ${name}: ${error.message}`);
      assetNotes.push(`${name} unavailable: ${error.message}`);
      fs.writeFileSync(target, '');
    }
  }
}

function renderTemplate() {
  const code = [
    'import json,sys',
    'from jinja2 import Environment,FileSystemLoader',
    'env=Environment(loader=FileSystemLoader(sys.argv[1]))',
    'def url_for(endpoint, **kw):',
    '    if "uploaded_file" in endpoint: return "/innovation/uploads/" + kw.get("filename", "")',
    '    return "/innovation/" + endpoint.rsplit(".",1)[-1]',
    'env.globals.update(url_for=url_for)',
    'sys.stdout.buffer.write(env.get_template("index.html").render(config={"DEBUG":False}).encode("utf-8"))'
  ].join('\n');
  const result = spawnSync(process.env.INNOVATION_TEST_PYTHON || 'C:/Python314/python.exe', ['-c', code, path.join(root, 'innovation/templates')], { encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  if (result.status !== 0) throw new Error(result.stderr || 'Jinja rendering failed');
  fs.writeFileSync(path.join(out, 'rendered-homepage.html'), result.stdout);
  return result.stdout;
}

async function probe(url) {
  try { const r = await fetch(url, { signal: AbortSignal.timeout(2500) }); return r.ok && (await r.text()).includes('dashboard-chart-grid'); } catch { return false; }
}

async function main() {
  await prepareAssets();
  let server;
  let source = 'running homepage with mocked GET APIs';
  let url = process.env.INNOVATION_TEST_URL || 'http://127.0.0.1:8000/innovation/';
  if (!await probe(url)) {
    const html = renderTemplate();
    source = 'original Jinja templates rendered in isolation, mocked GET APIs';
    server = http.createServer((req, res) => {
      if (req.url.startsWith('/innovation/static/js/common.js')) { res.writeHead(200, { 'Content-Type': 'application/javascript' }); return res.end(fs.readFileSync(path.join(root, 'innovation/static/js/common.js'))); }
      if (req.url.startsWith('/innovation/uploads/')) { res.writeHead(204); return res.end(); }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(html);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    url = `http://127.0.0.1:${server.address().port}/innovation/`;
  }
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  const blockedWrites = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', async route => {
    const request = route.request();
    const requestUrl = new URL(request.url());
    if (request.method() !== 'GET') { blockedWrites.push({ method: request.method(), url: request.url() }); return route.abort(); }
    if (requestUrl.pathname.includes('/api/')) {
      const data = requestUrl.pathname.endsWith('get_dashboard_data') ? mockData : requestUrl.pathname.endsWith('get_statistics') ? { total_count: 17, pending_count: 3, processing_count: 2, completed_count: 12 } : { rankings: [] };
      return route.fulfill({ json: { success: true, data } });
    }
    if (requestUrl.hostname === 'cdn.jsdelivr.net') {
      const name = path.basename(requestUrl.pathname);
      const target = path.join(assets, name);
      return route.fulfill({ status: 200, contentType: mime(name), body: fs.existsSync(target) ? fs.readFileSync(target) : '' });
    }
    return route.continue();
  });
  const results = [];
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForFunction(() => document.querySelector('#dashboardDataStatus')?.textContent.includes('已更新'), { timeout: 15000 });
    const settle = async () => { await page.waitForTimeout(850); };
    async function inspect(label) {
      await settle();
      const result = await page.evaluate(({ chartIds, label }) => {
        const rect = el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
        const grid = document.querySelector('.dashboard-chart-grid');
        const gridRect = rect(grid);
        const gridStyle = getComputedStyle(grid);
        const gridTrackCount = gridStyle.gridTemplateColumns.split(/\s+/).filter(Boolean).length;
        const expectedGridTrackCount = innerWidth <= 768 ? 1 : 12;
        const cards = [...grid.querySelectorAll('.dashboard-chart-card')].map(el => ({ title: el.querySelector('h6').textContent, span: getComputedStyle(el).gridColumnEnd, ...rect(el) }));
        const failures = [];
        if (document.documentElement.scrollWidth > innerWidth + 1) failures.push(`page overflows: ${document.documentElement.scrollWidth} > ${innerWidth}`);
        if (gridTrackCount !== expectedGridTrackCount) failures.push(`grid has ${gridTrackCount} tracks instead of ${expectedGridTrackCount} (implicit column or breakpoint mismatch)`);
        if (cards.length !== 6) failures.push(`expected 6 cards, got ${cards.length}`);
        cards.forEach((card, i) => {
          if (card.width <= 0 || card.height <= 0) failures.push(`card ${i} is hidden`);
          if (card.x < gridRect.x - 1 || card.right > gridRect.right + 1 || card.y < gridRect.y - 1 || card.bottom > gridRect.bottom + 1) failures.push(`card ${i} is outside grid`);
          cards.slice(i + 1).forEach((other, offset) => { if (Math.min(card.right, other.right) - Math.max(card.x, other.x) > 1 && Math.min(card.bottom, other.bottom) - Math.max(card.y, other.y) > 1) failures.push(`cards ${i}/${i + offset + 1} overlap`); });
        });
        const charts = chartIds.map(id => {
          const el = document.getElementById(id);
          const canvas = el.querySelector('canvas');
          const chart = echarts.getInstanceByDom(el);
          const bounds = rect(el);
          if (!canvas || !chart || bounds.width <= 0 || bounds.height <= 0) failures.push(`${id} is not rendered`);
          if (canvas && Math.abs(canvas.getBoundingClientRect().width - bounds.width) > 1) failures.push(`${id} canvas width differs from container`);
          const option = chart?.getOption();
          const media = id === 'category-distribution' ? { legendOrient: option.legend[0].orient, labels: option.series[0].label.show } : id === 'top-proposal-counts' || id === 'top-highest-scores' ? { axisRotation: option.xAxis[0].axisLabel.rotate || 0 } : null;
          if (id === 'category-distribution' && media.legendOrient !== (bounds.width <= 520 ? 'horizontal' : 'vertical')) failures.push(`${id} legend media query did not restore`);
          if ((id === 'top-proposal-counts' || id === 'top-highest-scores') && bounds.width <= 480 && media.axisRotation !== 40) failures.push(`${id} narrow label rotation missing`);
          if (id === 'top-proposal-counts' && bounds.width > 480 && media.axisRotation !== 0) failures.push(`${id} wide label rotation did not restore`);
          return { id, ...bounds, canvasWidth: canvas?.getBoundingClientRect().width, media };
        });
        return { label, viewportWidth: innerWidth, pageWidth: document.documentElement.scrollWidth, grid: { ...gridRect, trackCount: gridTrackCount, trackWidths: gridStyle.gridTemplateColumns, gap: gridStyle.gap }, cards, charts, failures };
      }, { chartIds, label });
      results.push(result);
      console.log(`${label}: ${result.failures.length ? 'FAIL: ' + result.failures.join('; ') : 'PASS'}`);
      return result;
    }
    for (const width of [375, 768, 769, 900, 992, 993, 1024, 1200, 1201, 1440, 1920, 2211]) {
      await page.setViewportSize({ width, height: 1080 });
      await inspect(`viewport-${width}`);
      if ([375, 900, 2211].includes(width)) await page.locator('.innovation-dashboard').screenshot({ path: path.join(out, `dashboard-${width}.png`) });
    }
    for (const width of [1440, 375, 1920, 900]) { await page.setViewportSize({ width, height: 1080 }); await inspect(`dynamic-${width}`); }
    await page.setViewportSize({ width: 1920, height: 1080 });
    const before = await inspect('container-before');
    await page.evaluate(() => { document.querySelector('.innovation-dashboard').style.width = '78%'; });
    const changed = await inspect('container-narrowed-at-fixed-viewport');
    if (Math.abs(changed.charts[0].width - before.charts[0].width) < 20) changed.failures.push('container resize did not change chart width enough to exercise observer');
    await page.evaluate(() => { document.querySelector('.innovation-dashboard').style.width = ''; });
    await inspect('container-restored-at-fixed-viewport');
    const report = { generatedAt: new Date().toISOString(), source, browser: 'isolated headless Microsoft Edge', assetNotes, mockData, errors, blockedWrites, results };
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
    const failures = results.flatMap(result => result.failures.map(failure => `${result.label}: ${failure}`));
    fs.writeFileSync(path.join(out, 'report.md'), [
      '# Innovation dashboard responsive browser verification', '',
      `Source: ${source}.`, `Browser: isolated headless Microsoft Edge; new context, no saved cookies.`, '',
      'All API reads used synthetic statistics; non-GET requests were blocked.', '',
      '| Check | Result |', '| --- | --- |',
      ...results.map(result => `| ${result.label} | ${result.failures.length ? result.failures.join('; ') : 'PASS'} |`), '',
      `Browser JavaScript errors: ${errors.length}. Blocked writes: ${blockedWrites.length}.`, '',
      'Checks: all six charts rendered; expected explicit grid columns (1 at <=768px, otherwise 12) without implicit overflow columns; cards inside grid without overlaps; no horizontal page overflow; each chart canvas matches its container; ECharts media options recover after resize; container-only resize updates canvas and category legend mode at a fixed 1920px viewport.', '',
      ...assetNotes, '',
      'Screenshots: dashboard-375.png (phone), dashboard-900.png (tablet), dashboard-2211.png (wide desktop).', '',
      ...(failures.length ? failures : ['All responsive checks passed.'])
    ].join('\n'));
    if (failures.length || errors.length) process.exitCode = 1;
  } finally { await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
