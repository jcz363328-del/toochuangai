const { chromium } = require('C:/Users/admin/AppData/Local/OpenAI/Codex/runtimes/cua_node/ecfc0d9aa02807e3/bin/node_modules/playwright');
(async()=>{
 const browser=await chromium.connectOverCDP('http://127.0.0.1:9222');
 let page; for(const candidate of browser.contexts().flatMap(c=>c.pages())) { if(candidate.url().includes('omniakey.com') || (await candidate.title())==='omniakey.com') { page=candidate; break; } }
 if(!page){console.log(JSON.stringify({found:false}));await browser.close();return;}
 const content=await page.locator('body').innerText();
 console.log(JSON.stringify({found:true,origin:new URL(page.url()).origin,path:new URL(page.url()).pathname,title:await page.title(),login_form:await page.locator('input[type=password]').count()>0,browser_network_error:/ERR_[A-Z_]+/.exec(content)?.[0]||null,has_balance_label:/余额|Balance/.test(content)}));
 await browser.close();
})();

