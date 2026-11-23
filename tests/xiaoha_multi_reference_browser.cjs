const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const output = path.resolve(__dirname, '../outputs/multi-reference-composer');
fs.mkdirSync(output, {recursive: true});

(async () => {
  const browser = await chromium.launch({executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:18531', {waitUntil: 'domcontentloaded'});
    const analyze = page.locator('.st-key-composer_analyze button');
    await analyze.waitFor({timeout: 45000});
    await analyze.click();
    await page.getByText('图 1 · background.png · 已完成', {exact: true}).waitFor();
    await page.getByText('图 2 · subject.png · 已完成', {exact: true}).waitFor();
    async function pick(title, filename) {
      await page.getByRole('tab', {name: title, exact: true}).click();
      const panel = page.getByRole('tabpanel', {name: title, exact: true});
      await panel.getByRole('combobox').click();
      await page.getByRole('option', {name: new RegExp(filename.replace('.', '\\.'))}).click();
      await page.keyboard.press('Escape');
      await panel.locator('textarea').waitFor();
    }
    await pick('背景', 'background.png');
    await pick('主体', 'subject.png');
    await page.locator('.st-key-composer_compose button').click();
    const prompt = page.locator('.st-key-composer_prompt textarea');
    await assert.doesNotReject(() => prompt.waitFor());
    await page.waitForFunction(() => document.querySelector('.st-key-composer_prompt textarea')?.value.includes('暖金色圆角护肤瓶'));
    assert.ok((await prompt.inputValue()).includes('蓝色渐变背景'));
    assert.ok(!(await prompt.inputValue()).includes('透明玻璃道具'));
    const edited = (await prompt.inputValue()) + '\n前景保留自然阴影';
    await prompt.fill(edited);
    await prompt.press('Tab');
    await page.locator('.st-key-composer_generate button').click();
    await page.frameLocator('iframe').last().locator('#result_viewer img.zoom-thumb').waitFor({timeout: 15000});
    await page.screenshot({path: path.join(output, 'desktop.png'), fullPage: true});
    await page.getByRole('tab', {name: '质感', exact: true}).click();
    await pick('质感', 'background.png');
    await page.waitForFunction(() => document.querySelector('.st-key-composer_generate button')?.disabled === true);
    await page.locator('.st-key-composer_compose button').click();
    await page.waitForFunction(() => document.querySelector('.st-key-composer_generate button')?.disabled === false);
    for (const width of [1440, 390]) {
      await page.setViewportSize({width, height: 1100});
      await page.waitForTimeout(300);
      const dimensions = await page.evaluate(() => ({width: innerWidth, scroll: document.documentElement.scrollWidth}));
      assert.ok(dimensions.scroll <= dimensions.width + 2, `No horizontal overflow at ${width}: ${JSON.stringify(dimensions)}`);
      const columns = await page.locator('.st-key-composer_sources').evaluate(root => {
        const row = root.querySelector('[data-testid="stHorizontalBlock"]');
        return [...row.children].filter(element => element.dataset.testid === 'stColumn').map(element => ({x:element.getBoundingClientRect().x,y:element.getBoundingClientRect().y,bottom:element.getBoundingClientRect().bottom,width:element.getBoundingClientRect().width}));
      });
      if (width < 850) {
        assert.ok(columns[0].width >= width - 40, 'Mobile uploader uses the available width');
        assert.ok(columns[1].y >= columns[0].bottom - 2, 'Mobile reference analysis stacks below uploads');
      }
      await page.getByText('① 上传参考图', {exact:true}).scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, `responsive-${width}.png`), fullPage: true});
    }
    assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({passed: true, flows: ['separate analysis', 'cross-image selection', 'manual edit', 'base generation', 'stale selection blocked', 'desktop and mobile'], output}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
