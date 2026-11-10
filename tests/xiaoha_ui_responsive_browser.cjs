/* Offline browser regression of real production Streamlit components.
 * Usage: node tests/xiaoha_ui_responsive_browser.cjs
 * Requires Python + Streamlit and Playwright; env overrides are supported below.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const ROOT = path.resolve(__dirname, '..');
const OUTPUT = path.resolve(ROOT, process.env.XIAOHA_UI_OUTPUT || 'outputs/xiaoha-responsive');
const PORT = Number(process.env.XIAOHA_UI_PORT || 18511);
const URL = process.env.XIAOHA_UI_URL || `http://127.0.0.1:${PORT}`;
const runtime = 'C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || runtime);
const executablePath = process.env.XIAOHA_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const widths = process.env.XIAOHA_UI_WIDTHS ? process.env.XIAOHA_UI_WIDTHS.split(',').map(Number) : [1920, 1385, 1280, 1024, 768, 390, 320];
const features = process.env.XIAOHA_UI_FEATURES?.split(',') || ['hd_batch','remove_eyelashes','prepress_check'];
let server;
let browser;
const observations = [];
const failures = [];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function ready() {
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      if ((await fetch(`${URL}/_stcore/health`)).ok) return;
    } catch (_) {}
    if (server?.exitCode !== null && server?.exitCode !== undefined) throw new Error('Fixture server stopped early');
    await pause(250);
  }
  throw new Error('Fixture server did not become ready');
}

async function loaded(page, feature='hd_batch') {
  await page.locator('.feature-title').waitFor({timeout:30000});
  if(feature!=='prepress_check') {
    await page.locator('.feature-workbench-left-marker').waitFor({state:'attached', timeout:30000});
    await page.locator('[data-testid="stNumberInputField"]').first().waitFor();
  }
  await pause(350);
  assert.equal(await page.locator('[data-testid="stException"]').count(), 0, 'No Streamlit exception');
  if(process.env.XIAOHA_UI_EXPECTED_VERSION) assert.ok((await page.title()).endsWith(`Streamlit ${process.env.XIAOHA_UI_EXPECTED_VERSION}`),'Fixture uses the requested actual Streamlit runtime');
}

async function visualAudit(page) {
  return page.evaluate(()=>{
    const rgba=value=>{
      const parts=value.match(/[\d.]+/g)?.map(Number)||[];
      return parts.length>=3 ? [...parts.slice(0,3),parts[3]??1] : [0,0,0,0];
    };
    const mix=(front,back)=>front.slice(0,3).map((c,i)=>c*front[3]+back[i]*(1-front[3]));
    const luminance=rgb=>rgb.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((s,c,i)=>s+c*[.2126,.7152,.0722][i],0);
    const background=element=>{
      const chain=[];
      for(let e=element;e;e=e.parentElement) {
        const css=getComputedStyle(e),gradient=css.backgroundImage.includes('linear-gradient')?css.backgroundImage.match(/rgba?\([^)]+\)/g)?.at(-1):null;
        chain.push(gradient?rgba(gradient):rgba(css.backgroundColor));
      }
      return chain.reverse().reduce((back,front)=>mix(front,back),[3,8,22]);
    };
    const visible=e=>{
      const rect=e.getBoundingClientRect();
      // React Aria adds clipped 1 px DismissButtons for screen readers. They
      // retain native button colors but never paint a visible control surface.
      if(rect.width<2||rect.height<2)return false;
      for(let a=e;a;a=a.parentElement) {
        const css=getComputedStyle(a);
        if(css.display==='none'||css.visibility==='hidden'||css.opacity==='0'||css.clipPath!=='none'||css.clip!=='auto')return false;
      }
      return true;
    };
    const roots=[...document.querySelectorAll('[data-testid="stSelectbox"],[data-testid="stMultiSelect"],[data-testid="stNumberInput"],[data-testid="stFileUploader"],[data-testid="stAlertContainer"],[role="listbox"],[data-testid="stSelectboxVirtualDropdown"],[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .inline-action-row)')];
    const nodes=[...new Set(roots.flatMap(e=>[e,...e.querySelectorAll('*')]))].filter(visible);
    const whiteSurfaces=[],whiteBorders=[],unreadableText=[],text=[],surfaces=[];
    for(const e of nodes) {
      const css=getComputedStyle(e),bg=rgba(css.backgroundColor),border=rgba(css.borderTopColor);
      const identity={tag:e.tagName,testid:e.dataset.testid,role:e.getAttribute('role'),className:typeof e.className==='string'?e.className.slice(0,100):''};
      if(bg[3]>.1)surfaces.push({...identity,background:css.backgroundColor});
      if(bg[3]>.55&&bg.slice(0,3).every(c=>c>190))whiteSurfaces.push({...identity,background:css.backgroundColor});
      if(parseFloat(css.borderTopWidth)>0&&border[3]>.55&&border.slice(0,3).every(c=>c>185))whiteBorders.push({...identity,border:css.borderTopColor});
      const value=[...e.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim()||(e.matches('input:not([type="file"])')?e.value:'');
      if(!value||e.matches('svg,svg *,[data-testid="stIconMaterial"]')||e.closest('button:disabled'))continue;
      const fg=rgba(css.webkitTextFillColor!=='currentcolor'?css.webkitTextFillColor:css.color),back=background(e),ink=mix(fg,back);
      const lum=[luminance(ink),luminance(back)].sort((a,b)=>b-a),ratio=(lum[0]+.05)/(lum[1]+.05);
      const item={...identity,text:value.slice(0,100),color:css.color,background:back.map(Math.round),contrast:Math.round(ratio*100)/100};
      text.push(item);
      if(ratio<3)unreadableText.push(item);
    }
    return {title:document.title,widgets:roots.map(e=>({testid:e.dataset.testid,comboboxes:e.querySelectorAll('[role="combobox"]').length})),surfaces,text,whiteSurfaces,whiteBorders,unreadableText};
  });
}

async function inspect(page, width, feature='hd_batch') {
  return page.evaluate(({width,feature}) => {
    const round = value => Math.round(value * 100) / 100;
    const box = element => {
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      const css = getComputedStyle(element);
      return { x: round(rect.x), y: round(rect.y), width: round(rect.width), height: round(rect.height),
        right: round(rect.right), bottom: round(rect.bottom), color: css.color, background: css.backgroundColor,
        border: css.borderTopColor, borderWidth: css.borderTopWidth, display: css.display,
        scrollWidth: element.scrollWidth, clientWidth: element.clientWidth };
    };
    const owner = marker => document.querySelector(marker)?.closest('[data-testid="stColumn"], [data-testid="column"]');
    const number = document.querySelector('[data-testid="stNumberInput"]');
    const selectSurface=document.querySelector('[data-testid="stSelectbox"] .react-aria-ComboBox [role="group"], [data-testid="stSelectbox"] [data-baseweb="select"] > div');
    const modelSurface=feature==='hd_batch'?document.querySelector('.a-plus-inline-model-card'):selectSurface;
    const bright = [];
    for (const element of document.querySelectorAll('[data-testid="stSelectbox"] [data-baseweb="select"] > div, [data-testid="stNumberInputContainer"], [data-testid="stNumberInputField"], [data-testid="stExpander"] details')) {
      const css = getComputedStyle(element);
      const rgb = css.backgroundColor.match(/[\d.]+/g)?.map(Number) || [];
      if (rgb.length >= 3 && rgb.slice(0, 3).every(value => value > 200) && (rgb[3] ?? 1) > .5) bright.push({ tag: element.tagName, testid: element.dataset.testid, background: css.backgroundColor });
    }
    const overflow = [...document.querySelectorAll('body *')].filter(element => {
      const css = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return css.position !== 'fixed' && css.display !== 'none' && rect.width > 0 && rect.right > width + 2 && rect.left < width;
    }).slice(0, 10).map(element => ({tag: element.tagName, testid: element.dataset.testid, className: String(element.className).slice(0, 100), ...box(element)}));
    return {width,feature, viewport: innerWidth, documentWidth: document.documentElement.scrollWidth,
      bodyWidth: document.body.scrollWidth, app: box(document.querySelector('[data-testid="stMainBlockContainer"]')),
      sidebar: box(owner('.side-menu-shell')), left: box(owner('.feature-workbench-left-marker')),
      right: box(owner('.feature-workbench-right-marker')), select: box(selectSurface),
      number: box(number), numberInput: box(number?.querySelector('input')),
      numberLabel: box(number?.querySelector('label p')), numberButtons: [...(number?.querySelectorAll('button') || [])].map(box),
      actionRow: box(number?.closest('[data-testid="stHorizontalBlock"]')),
      actionButton: box(document.querySelector(`.st-key-process_${feature} button`)),
      modelField: box(modelSurface),
      modelLabel: box(document.querySelector('.a-plus-inline-model-card')?.closest('[data-testid="stColumn"]')?.querySelector('.panel-subtitle')),
      countField: box(document.querySelector('[data-testid="stNumberInputContainer"]')),
      actionColumns: [...(number?.closest('[data-testid="stHorizontalBlock"]')?.children || [])].map(e=>({
        ...box(e),alignSelf:getComputedStyle(e).alignSelf,minHeight:getComputedStyle(e).minHeight,
        children:[...e.children].map(c=>({...box(c),testid:c.dataset.testid,alignSelf:getComputedStyle(c).alignSelf,minHeight:getComputedStyle(c).minHeight,justifyContent:getComputedStyle(c).justifyContent,
          children:[...c.children].map(d=>({...box(d),testid:d.dataset.testid,margin:getComputedStyle(d).margin}))}))})),
      actionAncestors: (() => {const out=[]; for(let e=number;e&&out.length<7;e=e.parentElement)out.push({testid:e.dataset.testid,className:String(e.className),...box(e)});return out;})(),
      workspaceContainers: [...document.querySelectorAll('[data-testid="stVerticalBlock"]')].filter(e=>getComputedStyle(e).containerName!=='none').map(e=>({name:getComputedStyle(e).containerName,width:e.clientWidth})),
      expanders: [...document.querySelectorAll('[data-testid="stExpander"] details')].map(box), bright, overflow};
  }, {width,feature});
}

function checkMetrics(metrics) {
  const { width } = metrics;
  try {
    assert.ok(metrics.documentWidth <= width + 2, `${width}: document overflows to ${metrics.documentWidth}`);
    assert.ok(metrics.bodyWidth <= width + 2, `${width}: body overflows to ${metrics.bodyWidth}`);
    assert.deepEqual(metrics.audit.whiteSurfaces,[],`${metrics.feature}/${width}: no opaque white widget surface`);
    assert.deepEqual(metrics.audit.whiteBorders,[],`${metrics.feature}/${width}: no opaque white native border`);
    assert.deepEqual(metrics.audit.unreadableText,[],`${metrics.feature}/${width}: rendered widget labels and values are readable`);
    assert.ok(metrics.select && metrics.select.width>=35,`${metrics.feature}/${width}: real rendered select surface is inspected`);
    if(metrics.feature==='prepress_check') {
      const label=metrics.audit.text.find(item=>item.text==='上传印前源文件');
      assert.ok(label && label.contrast>=4.5,`${width}: prepress uploader label is readable`);
      assert.ok(metrics.audit.widgets.some(item=>item.testid==='stAlertContainer'),`${width}: prepress info alert is inspected`);
      return;
    }
    assert.deepEqual(metrics.bright, [], `${width}: no white controls`);
    for (const name of ['left', 'right', 'select', 'numberInput']) {
      const value = metrics[name];
      assert.ok(value && value.width >= 35, `${width}: ${name} is visible and usable`);
      assert.ok(value.right <= width + 2 && value.x >= -2, `${width}: ${name} stays inside viewport`);
      assert.ok(value.scrollWidth <= value.clientWidth + 2, `${width}: ${name} does not clip contents (${value.scrollWidth}/${value.clientWidth})`);
    }
    assert.ok(metrics.numberLabel.height > 10, `${width}: count label is visible`);
    assert.ok(metrics.numberLabel.color !== 'rgb(49, 51, 63)', `${width}: count label has dark-theme color`);
    assert.equal(metrics.actionRow.display, 'grid', `${width}: production action-row grid selector matches current DOM`);
    assert.ok(metrics.number.width >= 120, `${width}: count control has usable width (${metrics.number.width})`);
    assert.equal(metrics.numberButtons.length,2,`${width}: both count steppers remain visible`);
    assert.ok(metrics.numberButtons.every(button=>button.width>=24),`${width}: count steppers remain usable`);
    if(width>=768) {
      const bottoms=[metrics.countField.bottom,metrics.modelField.bottom,metrics.actionButton.bottom];
      const tops=[metrics.countField.y,metrics.modelField.y,metrics.actionButton.y];
      assert.ok(Math.max(...bottoms)-Math.min(...bottoms)<=2,`${width}: count, model and action fields align at bottom (${bottoms})`);
      assert.ok(Math.max(...tops)-Math.min(...tops)<=2,`${width}: count, model and action fields align at top (${tops})`);
    }
    if(width<=390) {
      assert.ok(metrics.numberInput.width>=100, `${width}: mobile numeric input width remains usable`);
      assert.ok(metrics.actionButton.width >= metrics.actionRow.width-2, `${width}: mobile action button fills its own row`);
    }
    if (width <= 1024) assert.ok(metrics.right.y >= metrics.left.bottom - 2, `${width}: workbench stacks at available narrow width`);
    if (width > 768) assert.ok(metrics.sidebar.width >= 150 && metrics.sidebar.width <= 210, `${width}: stable sidebar width`);
    if (width <= 768) assert.ok(metrics.left.y >= metrics.sidebar.bottom - 2, `${width}: menu stacks above workbench`);
  } catch (error) { failures.push(error.message); }
}

async function dropdownInteraction(page,feature) {
  const widget=page.locator('[data-testid="stSelectbox"]').first();
  const combo=widget.getByRole('combobox');
  const initialValue=await combo.inputValue();
  const initialText=await widget.innerText();
  await combo.focus();
  if(await widget.locator('[data-baseweb="select"] > div').count()) await widget.locator('[data-baseweb="select"] > div').first().click();
  else await widget.locator('button[aria-haspopup="listbox"]').click();
  const list=page.locator('[data-testid="stSelectboxVirtualDropdown"], [role="listbox"]').last();
  await list.waitFor();
  await pause(200);
  const options=await list.locator('[role="option"]').allTextContents();
  assert.ok(options.length>=2,`${feature}: actual dropdown options are available`);
  const popup=await visualAudit(page);
  assert.deepEqual(popup.whiteSurfaces,[],`${feature}: popup surfaces stay dark`);
  assert.deepEqual(popup.whiteBorders,[],`${feature}: popup border stays subtle`);
  assert.deepEqual(popup.unreadableText,[],`${feature}: popup options are readable`);
  await page.screenshot({path:path.join(OUTPUT,`dropdown-${feature}-1385.png`),fullPage:true});
  const original=options.map(o=>o.trim()).find(o=>o===initialValue)||options.map(o=>o.trim()).find(o=>initialText.includes(o))||options[0].trim();
  const selected=feature==='hd_batch'?'fixture-reference.png':feature==='prepress_check'?'包装盒':options.map(o=>o.trim()).find(o=>o!==original);
  assert.notEqual(selected,original,`${feature}: exercise a different option`);
  await page.getByRole('option',{name:selected,exact:true}).click();
  await pause(400);
  assert.ok((await combo.inputValue()).includes(selected)||(await widget.innerText()).includes(selected),`${feature}: chosen option survives widget rerender`);
  if(await widget.locator('[data-baseweb="select"] > div').count()) await widget.locator('[data-baseweb="select"] > div').first().click();
  else await widget.locator('button[aria-haspopup="listbox"]').click();
  await page.getByRole('option',{name:original,exact:true}).click();
  await pause(300);
  return {options,selected,whiteSurfaces:popup.whiteSurfaces,unreadableText:popup.unreadableText};
}

async function interactions(page) {
  const popup=await dropdownInteraction(page,'hd_batch');
  const number = page.getByRole('spinbutton', {name:'生成数量', exact:true});
  if (await number.isEnabled()) {
    await number.fill('2');
    await number.press('Enter');
    await pause(600);
    assert.equal(await page.getByRole('spinbutton', {name:'生成数量', exact:true}).inputValue(), '2', 'Count remains editable after rerender');
  }
  const process = page.locator('.st-key-process_hd_batch button');
  assert.ok(await process.isVisible(), 'Process button is visible');
  const group = page.locator('[data-testid="stExpander"]').filter({has:page.getByText('图片处理',{exact:true})}).first();
  await pause(350);
  await group.locator('summary').click();
  await page.waitForFunction(() => {
    const summary=[...document.querySelectorAll('[data-testid="stExpander"] summary')].find(e=>e.innerText.includes('图片处理'));
    return summary?.parentElement.open===false;
  });
  await group.locator('summary').click();
  await page.waitForFunction(() => {
    const summary=[...document.querySelectorAll('[data-testid="stExpander"] summary')].find(e=>e.innerText.includes('图片处理'));
    return summary?.parentElement.open===true;
  });
  await page.locator('.st-key-hide_side_menu button').click();
  await page.locator('.st-key-show_side_menu button').waitFor();
  assert.equal(await page.locator('.side-menu-shell').count(), 0, 'Menu hides');
  await page.locator('.st-key-show_side_menu button').click();
  await page.locator('.side-menu-shell').waitFor();
  await page.locator('.st-key-side_menu_feature_product_retouch button').click();
  await pause(600);
  assert.ok((await page.locator('.feature-title').innerText()).includes('产品图精修'), 'Feature navigation renders production screen');
  const genericCount = page.getByRole('spinbutton',{name:'生成数量',exact:true});
  if(await genericCount.isEnabled()) {
    await genericCount.fill('2');
    await genericCount.press('Enter');
    await pause(500);
    assert.equal(await genericCount.inputValue(),'2','Generic feature count remains editable');
    await genericCount.hover();
    const buttons=await page.locator('[data-testid="stNumberInput"] button').count();
    assert.equal(buttons,2,'Generic numeric input renders both steppers');
    const stepper=page.locator('[data-testid="stNumberInput"] button').last();
    await stepper.click();
    await pause(500);
    assert.equal(await genericCount.inputValue(),'3','Increment stepper works');
    const colors=await page.locator('[data-testid="stNumberInput"] button').evaluateAll(es=>es.map(e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})));
    assert.ok(colors.every(c=>c.background!=='rgb(255, 255, 255)'),'Steppers retain dark styling');
    console.log(JSON.stringify({genericNumberButtons:buttons,stepperColors:colors}));
  }
  await page.locator('.st-key-side_menu_feature_hd_batch button').click();
  await loaded(page);
  return {popup, countEditable:await number.isEnabled(), menuCollapse:true, menuHide:true, navigation:true};
}

(async () => {
  fs.mkdirSync(OUTPUT, {recursive:true});
  if (!process.env.XIAOHA_UI_URL) {
    try { if ((await fetch(`${URL}/_stcore/health`)).ok) throw new Error(`Port ${PORT} already has a service; use XIAOHA_UI_URL explicitly or choose another port`); }
    catch (error) { if (error.message.startsWith('Port ')) throw error; }
    const stdout = fs.openSync(path.join(OUTPUT,'server.stdout.log'),'w');
    const stderr = fs.openSync(path.join(OUTPUT,'server.stderr.log'),'w');
    server = spawn(process.env.XIAOHA_PYTHON || 'python', ['-m','streamlit','run',path.join(__dirname,'xiaoha_ui_fixture.py'),
      '--global.developmentMode','false','--server.address','127.0.0.1','--server.port',String(PORT),'--server.headless','true','--server.fileWatcherType','none','--browser.gatherUsageStats','false','--theme.base','light'],
      {cwd:ROOT, windowsHide:true, stdio:['ignore',stdout,stderr]});
    fs.closeSync(stdout); fs.closeSync(stderr);
  }
  await ready();
  browser = await chromium.launch({executablePath,headless:true,args:['--no-first-run','--disable-background-networking']});
  const context = await browser.newContext({colorScheme:'light'});
  context.setDefaultTimeout(8000);
  await context.route('**/*', route => {
    const requestUrl = new global.URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(requestUrl.hostname) ? route.continue() : route.abort();
  });
  if(process.env.XIAOHA_UI_CAPTURE) {
    for(const feature of ['hd_batch','remove_eyelashes','prepress_check']) {
      const page=await context.newPage();
      await page.setViewportSize({width:1385,height:1000});
      await page.goto(`${URL}/?feature=${feature}`);
      await page.locator('.feature-title').waitFor({timeout:30000});
      await pause(600);
      const captured=await page.evaluate(()=>{
        const describe=e=>({tag:e.tagName,testid:e.dataset.testid,role:e.getAttribute('role'),background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color,border:getComputedStyle(e).borderColor,html:e.outerHTML});
        return {title:document.title,selects:[...document.querySelectorAll('[data-testid="stSelectbox"]')].map(describe),
          number:[...document.querySelectorAll('[data-testid="stNumberInput"]')].map(describe),
          uploaders:[...document.querySelectorAll('[data-testid="stFileUploader"]')].map(describe),
          alerts:[...document.querySelectorAll('[data-testid="stAlert"]')].map(describe),
          bordered:[...document.querySelectorAll('[data-testid="stVerticalBlockBorderWrapper"],[data-testid="stVerticalBlock"][data-border="true"]')].map(describe)};
      });
      const audit=await visualAudit(page);
      observations.push({feature,...captured,audit});
      fs.writeFileSync(path.join(OUTPUT,`dom-${feature}.json`),JSON.stringify({...captured,audit},null,2));
      await page.screenshot({path:path.join(OUTPUT,`capture-${feature}-1385.png`),fullPage:true});
      console.log(JSON.stringify({feature,title:captured.title,whiteSurfaces:audit.whiteSurfaces,whiteBorders:audit.whiteBorders,unreadableText:audit.unreadableText}));
      await page.close();
    }
    return;
  }
  for (const feature of features) for (const width of widths) {
    const page = await context.newPage();
    await page.setViewportSize({width,height:1000});
    await page.goto(`${URL}/?feature=${feature}`);
    await loaded(page,feature);
    const metrics = await inspect(page,width,feature);
    metrics.audit=await visualAudit(page);
    observations.push(metrics);
    checkMetrics(metrics);
    await page.screenshot({path:path.join(OUTPUT,`responsive-${feature}-${width}.png`),fullPage:true});
    if(width<=768) {
      await page.locator(feature==='prepress_check'?'[data-testid="stSelectbox"]':'[data-testid="stNumberInput"]').first().scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(OUTPUT,`workbench-${feature}-${width}.png`),fullPage:true});
    }
    console.log(JSON.stringify({feature,width,runtime:metrics.audit.title,documentWidth:metrics.documentWidth,stacked:metrics.right?.y>metrics.left?.y,selectWidth:metrics.select?.width,countWidth:metrics.number?.width,countButtons:metrics.numberButtons.length,actionDisplay:metrics.actionRow?.display,whiteControls:metrics.audit.whiteSurfaces.length,unreadableText:metrics.audit.unreadableText}));
    if (width === 1385) {
      try {observations.push({feature,interactions:feature==='hd_batch'?await interactions(page):await dropdownInteraction(page,feature)});}
      catch (error) {failures.push(error.stack || String(error));}
    }
    await page.close();
  }
})().catch(error => failures.push(error.stack || String(error))).finally(async () => {
  fs.mkdirSync(OUTPUT,{recursive:true});
  fs.writeFileSync(path.join(OUTPUT,'metrics.json'),JSON.stringify({observations,failures},null,2));
  if (browser) await Promise.race([browser.close(),pause(5000)]);
  if (server) {
    if (process.platform === 'win32') spawnSync('taskkill',['/pid',String(server.pid),'/t','/f'],{windowsHide:true,stdio:'ignore'});
    else server.kill('SIGTERM');
  }
  console.log(JSON.stringify({passed:failures.length===0,failures,artifactDirectory:OUTPUT}));
  process.exit(failures.length?1:0);
});
