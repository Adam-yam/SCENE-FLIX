const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { once } = require('node:events');
const playwright = require('playwright');
const root = path.resolve(__dirname, '..');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
let browser, server, base;
before(async () => {
  server = http.createServer((request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      const file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
      if (!file.startsWith(root + path.sep)) throw Error('Invalid path');
      const type = {'.html':'text/html; charset=utf-8','.js':'application/javascript','.json':'application/json','.css':'text/css','.woff2':'font/woff2','.svg':'image/svg+xml','.png':'image/png','.ics':'text/calendar'}[path.extname(file)] || 'application/octet-stream';
      response.writeHead(200, {'Content-Type':type});response.end(fs.readFileSync(file));
    } catch { response.writeHead(404);response.end(); }
  });
  server.listen(0, '127.0.0.1');await once(server, 'listening');
  base = `http://127.0.0.1:${server.address().port}`;
  browser = await playwright[process.env.SCENE_BROWSER || 'chromium'].launch({
    ...(process.env.SCENE_BROWSER_PATH ? {executablePath:process.env.SCENE_BROWSER_PATH} : {}),
    headless:true
  });
});
after(async () => { await browser?.close();server?.close(); });
async function setup(width=1280) {
  const context = await browser.newContext({viewport:{width,height:900},hasTouch:width<700,reducedMotion:'reduce',serviceWorkers:'block'});
  await context.route('**/*', async route => {
    if (route.request().url().startsWith(base)) return route.continue();
    if (route.request().resourceType() === 'image') return route.fulfill({contentType:'image/png',body:png});
    if (route.request().url().includes('oembed')) return route.fulfill({json:{title:'RESCENE Pretty Girl',author_name:'RESCENE'}});
    return route.abort();
  });
  const page = await context.newPage();page.setDefaultTimeout(7000);
  const errors=[];page.on('pageerror', e=>errors.push(e.message));
  return {context,page,errors};
}
async function inViewport(locator) {
  if (!await locator.isVisible()) return false;
  return locator.evaluate(el => { const r=el.getBoundingClientRect(); return r.right>0 && r.left<innerWidth && r.bottom>0 && r.top<innerHeight; });
}
async function go(page, tab) {
  const buttons=page.locator(`[data-action="pickSection"][data-value="${tab}"]`);
  for(let i=0;i<await buttons.count();i++)if(await inViewport(buttons.nth(i))){await buttons.nth(i).click();return;}
  if(await page.locator('#mobileMenuBtn').evaluate(el=>el.classList.contains('nav-hidden'))){await page.evaluate(()=>scrollBy(0,-8));await settled(page);}
  await page.locator('#mobileMenuBtn').click();
  await page.locator(`[data-action="drawerSection"][data-value="${tab}"]`).click();
}
async function settled(page) {
  await page.waitForTimeout(350);
}
for(const width of [1280,390]) {
  test(`navigation, search, history and refresh at ${width}px`, async () => {
    const {context,page,errors}=await setup(width);
    try {
      await page.goto(base+'/?tab=allvideos');
      await page.locator('#grid .vcard').first().waitFor();
      await page.locator('#searchInput').fill('Pretty Girl');
      await page.locator('#searchInput').press('Enter');
      await settled(page);
      await go(page,'series');await page.goBack();await settled(page);
      assert.equal(await page.locator('#searchInput').inputValue(),'Pretty Girl');
      await page.reload();await settled(page);
      assert.equal(await page.locator('#searchInput').inputValue(),'Pretty Girl');
      await page.locator('#searchInput').fill('zzzzzzzznotfoundzzzzzz');await page.locator('#searchInput').press('Enter');
      await page.locator('.reset-view-filters').waitFor();await settled(page);
      assert.equal(await page.locator('.reset-view-filters').count(),1);
      await page.locator('.reset-view-filters').click();
      assert.equal(await page.locator('#searchInput').inputValue(),'');
      await page.evaluate(()=>window.scrollTo(0,1000));await settled(page);
      const y=await page.evaluate(()=>scrollY);
      await go(page,'series');await page.goBack();await settled(page);
      assert(Math.abs(await page.evaluate(()=>scrollY)-y)<15,'Back restores scroll');
      await page.reload();await settled(page);
      assert(Math.abs(await page.evaluate(()=>scrollY)-y)<15,'Reload restores scroll');
      assert.deepEqual(errors,[]);
    } finally {await context.close();}
  });
  test(`bookmark import, ordering and export at ${width}px`, async () => {
    const {context,page,errors}=await setup(width);
    try {
      await page.goto(base+'/?tab=allvideos');await page.locator('#grid .vcard').first().waitFor();
      const ids=await page.locator('#grid .vcard').evaluateAll(cards=>cards.slice(0,3).map(c=>c.dataset.vid));
      await go(page,'bookmark');await page.locator('[data-action="openBookmarkBackup"]').click();
      await page.locator('#bookmarkBackupFile').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{"bookmarks":["bad"]}')});
      assert.match(await page.locator('#bookmarkBackupStatus').innerText(),/백업/);
      const upload={name:'saved.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({app:'SCENE-FLIX',version:1,bookmarks:ids,order:[...ids].reverse()}))};
      await page.locator('#bookmarkBackupFile').setInputFiles(upload);
      await page.waitForFunction(()=>document.getElementById('bookmarkBackupStatus').textContent.includes('3개'));
      await page.locator('#bookmarkBackupFile').setInputFiles(upload);
      await page.waitForFunction(()=>document.getElementById('bookmarkBackupStatus').textContent.includes('0개'));
      const downloadEvent=page.waitForEvent('download');await page.locator('#bookmarkBackupExport').click();
      const download=await downloadEvent;
      const data=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
      assert.deepEqual(data.order,[...ids].reverse());
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#bookmarkBackupDialog').isVisible(),false);
      await page.locator('#bmManual').click();await page.locator('#bmReorder').click();
      const handle=page.locator('.bm-reorder-handle').first();await handle.waitFor();await handle.focus();await handle.press('ArrowDown');
      await page.locator('#bmReorder').click();await settled(page);
      const order=await page.locator('#grid .vcard').evaluateAll(cards=>cards.map(c=>c.dataset.vid));
      assert.deepEqual(order,[ids[1],ids[2],ids[0]]);
      await page.reload();await page.locator('#grid .vcard').first().waitFor();
      assert.deepEqual(await page.locator('#grid .vcard').evaluateAll(cards=>cards.map(c=>c.dataset.vid)),order);
      assert.deepEqual(errors,[]);
    } finally {await context.close();}
  });
  test(`calendar state, export and subscription at ${width}px`, async () => {
    const {context,page,errors}=await setup(width);
    try {
      await page.goto(base+'/?tab=schedule');
      await page.locator('#calGrid [data-action="calSelectDate"]').first().waitFor();
      await page.locator('[data-action="setScheduleSource"][data-value="blip"]').click();
      const date=page.locator('#calGrid [data-action="calSelectDate"]').nth(12);
      const value=await date.getAttribute('data-value');await date.click();await settled(page);
      await go(page,'series');await go(page,'schedule');await settled(page);
      assert.equal(await page.locator('[data-action="setScheduleSource"][data-value="blip"]').getAttribute('aria-pressed'),'true');
      assert(await page.locator(`[data-action="calSelectDate"][data-value="${value}"]`).evaluate(e=>e.classList.contains('selected')));
      await page.reload();await settled(page);
      assert(await page.locator(`[data-action="calSelectDate"][data-value="${value}"]`).evaluate(e=>e.classList.contains('selected')));
      await page.locator('[data-action="setScheduleSource"][data-value="all"]').click();
      await page.locator('#scheduleExportBtn').click();
      await page.locator('input[name="sx-mode"][value="all"]').check();
      await page.locator('#sx-confirm').check();
      await page.waitForFunction(()=>!document.getElementById('sx-download').disabled);
      const downloadEvent=page.waitForEvent('download');await page.locator('#sx-download').click();
      const data=fs.readFileSync(await (await downloadEvent).path(),'utf8');
      assert(data.includes('BEGIN:VCALENDAR'));assert(data.includes('BEGIN:VEVENT'));
      await page.keyboard.press('Escape');
      await page.locator('[data-action="openScheduleSubscription"]').click();
      assert(await page.locator('#scheduleSubscribeDialog').isVisible());
      assert.equal(await page.locator('input[name="ss-source"]').count(),3);
      await page.keyboard.press('Escape');assert.deepEqual(errors,[]);
    } finally {await context.close();}
  });
}
test('failed data request retries only the affected section',async()=>{
  const {context,page,errors}=await setup();
  try {
    let fail=true;
    await page.route('**/data/charts/chart.json*',route=>fail?route.abort():route.continue());
    await page.goto(base+'/?tab=chart');
    await page.locator('[data-retry-section="chart"]').waitFor();
    const url=page.url();fail=false;await page.locator('[data-retry-section="chart"]').click();
    await page.waitForFunction(()=>!document.getElementById('data-state-chart'));
    assert.equal(page.url(),url);assert.deepEqual(errors,[]);
  }finally{await context.close();}
});
test('schedule failure is not shown as an empty agenda and can be retried',async()=>{
  const {context,page,errors}=await setup();
  try {
    let fail=true;await page.route('**/data/schedule/**',route=>fail?route.abort():route.continue());
    await page.goto(base+'/?tab=schedule');
    await page.locator('[data-action="retrySchedule"]').waitFor();
    fail=false;await page.locator('[data-action="retrySchedule"]').click();
    await page.waitForFunction(()=>!document.getElementById('scheduleLoadStatus'));
    assert.deepEqual(errors,[]);
  }finally{await context.close();}
});
test('responsive tabs, languages, theme, QR and dialog keyboard access',async()=>{
  const {context,page,errors}=await setup();
  try{
    await page.goto(base+'/?tab=series');
    for(const width of [1280,390]){
      await page.setViewportSize({width,height:900});
      for(const lang of ['KR','EN','JP']){
        if(width>=701) await page.locator(`#langSwitcherDesktop [data-value="${lang}"]`).click();
        else {
          if(await page.locator('#mobileMenuBtn').evaluate(el=>el.classList.contains('nav-hidden'))){await page.evaluate(()=>scrollBy(0,-8));await settled(page);}
          await page.locator('#mobileMenuBtn').click();
          await page.locator(`#langSwitcher [data-value="${lang}"]`).click();
          await page.keyboard.press('Escape');
        }
        for(const tab of ['allvideos','songs','content','external','live','archive','bookmark','shorts','schedule','chart','series']){
          await go(page,tab);
          assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}/${lang}/${tab} overflows`);
        }
      }
    }
    await page.setViewportSize({width:1280,height:900});
    const theme=page.locator('[data-action="toggleTheme"]');
    for(let i=0;i<await theme.count();i++)if(await inViewport(theme.nth(i))){await theme.nth(i).click();break;}
    await page.locator('.series-qr').first().click();await page.waitForFunction(()=>!document.getElementById('qrCopy').disabled);
    for(let i=0;i<5;i++)await page.keyboard.press('Tab');
    assert(await page.evaluate(()=>document.getElementById('seriesQrDialog').contains(document.activeElement)));
    await page.keyboard.press('Escape');assert.equal(await page.locator('#seriesQrDialog').isVisible(),false);
    assert(await page.evaluate(()=>typeof window.sceneFlixPerformance==='object'));
    assert.deepEqual(errors,[]);
  }finally{await context.close();}
});
test('storage denial does not prevent browsing',async()=>{
  const {context,page,errors}=await setup();
  try{
    await page.addInitScript(()=>{Storage.prototype.setItem=function(){throw new DOMException('Denied','QuotaExceededError')};});
    await page.goto(base+'/?tab=allvideos');await page.locator('#grid .vcard').first().waitFor();
    await go(page,'series');await page.locator('.series-card').first().waitFor();assert.deepEqual(errors,[]);
  }finally{await context.close();}
});
test('backup, series and schedule meet automated accessibility checks in both themes',async()=>{
  const {context,page,errors}=await setup();
  const AxeBuilder=require('@axe-core/playwright').default;
  try{
    for(const theme of ['dark','light'])for(const tab of ['bookmark','series','schedule']){
      await page.goto(base+'/?tab='+tab);
      await page.evaluate(value=>document.documentElement.setAttribute('data-theme',value),theme);
      await settled(page);
      if(tab==='bookmark')await page.locator('[data-action="openBookmarkBackup"]').click();
      const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa']).analyze();
      assert.deepEqual(result.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[],`${theme}/${tab}`);
    }
    assert.deepEqual(errors,[]);
  }finally{await context.close();}
});
test('external category and channel survive navigation and reload',async()=>{
  const {context,page,errors}=await setup();
  try {
    await page.goto(base+'/?tab=external');
    const category=page.locator('#subSidebarContent [data-action="pickExternalCat"]').filter({visible:true}).nth(1);
    await category.waitFor();const cat=await category.getAttribute('data-value');await category.click();
    await page.locator('#subSidebarOverlay').click({position:{x:50,y:50}});
    const channel=page.locator('#externalChanBar [data-action="pickExternalChan"]').nth(1);
    await channel.waitFor();const ch=await channel.getAttribute('data-value');await channel.click();await settled(page);
    const cards=await page.locator('#grid .vcard').evaluateAll(nodes=>nodes.map(n=>n.dataset.vid));
    await go(page,'series');await page.goBack();await settled(page);
    assert.equal(await page.locator('#externalCatNav .active').getAttribute('data-value'),cat);
    assert.equal(await page.locator('#externalChanBar .active').getAttribute('data-value'),ch);
    assert.deepEqual(await page.locator('#grid .vcard').evaluateAll(nodes=>nodes.map(n=>n.dataset.vid)),cards);
    await page.reload();await settled(page);
    assert.equal(await page.locator('#externalChanBar .active').getAttribute('data-value'),ch);
    assert.deepEqual(errors,[]);
  } finally {await context.close();}
});
