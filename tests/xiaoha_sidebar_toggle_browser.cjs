const assert = require('node:assert/strict');
const {chromium} = require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  for (const width of [1440,390]) {
   const page = await browser.newPage({viewport:{width,height:900}});
   await page.goto(process.env.XIAOHA_SIDEBAR_TEST_URL || 'http://localhost:18519');
   const close = page.getByTestId('stSidebarCollapseButton');
   const open = page.getByTestId('stExpandSidebarButton');
   await close.waitFor({state:'visible',timeout:60000});
   for (let cycle=0;cycle<2;cycle++) {
    await close.click();
    await open.waitFor({state:'visible'});
    const box = await open.boundingBox();
    assert(box && box.x>=0 && box.y>=0 && box.x+box.width<=width,'Opener must be on screen');
    await page.waitForFunction(()=>{const el=document.querySelector('[data-testid=stExpandSidebarButton]');if(!el)return false;const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));});
    await open.click();
    await close.waitFor({state:'visible'});
   }
   assert.equal(await page.getByTestId('stException').count(),0);
   console.log(`PASS ${width}px: collapse and reopen twice`);
   await page.close();
  }
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
