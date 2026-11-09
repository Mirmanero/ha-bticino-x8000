const { chromium } = require('@playwright/test');
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const repo = path.resolve(__dirname, '../..');
const out = process.env.X8000_TEST_OUTPUT_DIR || path.join(repo, 'test-results');
fs.mkdirSync(out, {recursive:true});
const tests = [];
const server = http.createServer((req,res) => {
  const file = req.url.startsWith('/card.js') ? path.join(repo,'frontend/bticino-programs-card.js') : path.join(repo,'tests/frontend/harness.html');
  res.setHeader('Content-Type',req.url.startsWith('/card.js')?'text/javascript':'text/html');res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const url=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({headless:true});
  async function test(name, fn, query='') {
    const page=await browser.newPage({viewport:{width:1100,height:1500}});const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>route.request().url().startsWith(url)?route.continue():route.abort());
    await page.clock.install({time:new Date('2026-10-26T09:30:00Z')});
    await page.goto(url+query);
    await page.waitForFunction(()=>window.demoCard&&demoCard._attempted&&!demoCard._busy);
    try{await fn(page);assert.deepEqual(errors,[]);tests.push({name,passed:true});}
    catch(e){tests.push({name,passed:false,error:e.message});}
    await page.close();
  }
  async function edit(p) { if(!await p.locator('[data-field=name]').count()) await p.locator('[data-action=edit-day]').click(); }
  async function more(p) { await p.locator('details.more-options').evaluate(el=>el.open=true); }
  await test('week and known temperatures render',async p=>{
    assert.equal(await p.locator('.week-row').count(),7);
    assert.match(await p.locator('.periods').innerText(),/18/);
    assert.equal(await p.locator('[data-field=active]').inputValue(),'2');
    await p.locator('bticino-programs-card').screenshot({path:path.join(out,'bticino-programs-desktop.png')});
  });
  await test('edit and verified save send edited slots',async p=>{
    await p.locator('[data-action=open][data-number="1"]').click();await p.waitForFunction(()=>!demoCard._busy);
    await edit(p);await p.locator('[data-field=time][data-index="1"]').fill('10:15');
    assert.equal(await p.locator('[data-action=activate]').isDisabled(),true);
    assert.equal(await p.locator('[data-field=active]').isDisabled(),true);
    await p.locator('[data-action=save]').click();await p.waitForFunction(()=>!demoCard._busy);
    const save=await p.evaluate(()=>demoCalls.find(c=>c.operation==='save'));
    assert.equal(save.days.monday[1].time,'10:15');assert.equal(save.revision,'revision-1');
    assert.match(await p.locator('.success').innerText(),/verificato/);
  });
  await test('create and copy a day across the week',async p=>{
    await p.locator('[data-action=new]').click();
    await p.locator('[data-field=name]').fill('Nuova settimana');
    await p.locator('[data-action=add-slot]').click();await p.locator('[data-field=time][data-index="1"]').fill('10:00');
    await p.locator('[data-action=add-slot]').click();await p.locator('[data-field=preset][data-index="2"]').selectOption('PROTECTION');
    await p.locator('details.copy-options').evaluate(el=>el.open=true);await p.locator('[data-action=copy]').click();await p.locator('[data-action=save]').click();await p.waitForFunction(()=>!demoCard._busy);
    const save=await p.evaluate(()=>demoCalls.find(c=>c.operation==='save'));
    assert.equal(save.number,3);assert.equal(save.revision,null);assert.equal(save.days.sunday[1].time,'10:00');
  });
  await test('stale revision preserves unsaved draft',async p=>{
    await edit(p);await p.locator('[data-field=name]').fill('Modifica locale');await p.evaluate(()=>demoPrograms[2].sha256='external-change');
    await p.locator('[data-action=save]').click();await p.waitForFunction(()=>!demoCard._busy);
    assert.match(await p.locator('.error').innerText(),/cambiato/);assert.equal(await p.locator('[data-field=name]').inputValue(),'Modifica locale');
  });
  await test('selection activates a program without saving',async p=>{
    await p.locator('[data-field=active]').selectOption('1');await p.waitForFunction(()=>!demoCard._busy);
    assert.equal(await p.evaluate(()=>demoActive),1);assert.equal(await p.evaluate(()=>demoCalls.filter(c=>c.operation==='save').length),0);
  });
  await test('active program cannot be deleted',async p=>{
    assert.equal(await p.locator('[data-action=delete]').isDisabled(),true);
  });
  await test('delete inactive program requires confirmation',async p=>{
    p.on('dialog',d=>d.accept());await p.locator('[data-action=open][data-number="1"]').click();await p.waitForFunction(()=>!demoCard._busy);
    await more(p);await p.locator('[data-action=delete]').click();await p.waitForFunction(()=>!demoCard._busy);
    assert.equal(await p.evaluate(()=>Boolean(demoPrograms[1])),false);
  });
  await test('non-admin can read but cannot edit',async p=>{
    assert.equal(await p.locator('[data-action=new]').isDisabled(),true);assert.equal(await p.locator('[data-action=edit-day]').isDisabled(),true);
    assert.equal(await p.locator('[data-field=active]').isDisabled(),true);
  },'?readonly=1');
  await test('failed initial connection does not become a polling loop',async p=>{
    await p.evaluate(()=>{for(let i=0;i<10;i++)demoCard.hass=demoHass});await p.waitForTimeout(60);
    assert.equal(await p.evaluate(()=>demoCalls.filter(c=>c.operation==='list').length),1);
  },'?fail=1');
  await test('program names are escaped as text',async p=>{
    await p.locator('[data-action=new]').click();await p.locator('[data-field=name]').fill('<img src=x onerror=window.hacked=1>');
    await p.locator('[data-action=save]').click();await p.waitForFunction(()=>!demoCard._busy);
    assert.equal(await p.locator('bticino-programs-card img').count(),0);assert.equal(await p.evaluate(()=>window.hacked),undefined);
  });
  await test('mobile dark layout has no horizontal document overflow',async p=>{
    await p.setViewportSize({width:390,height:1800});
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await p.locator('bticino-programs-card').screenshot({path:path.join(out,'bticino-programs-mobile-dark.png')});
  },'?dark=1');
  await test('english labels render',async p=>{assert.match(await p.locator('h2').innerText(),/Weekly/);},'?lang=en');
  await test('switching thermostat ignores a pending response for the previous entity',async p=>{
    await p.evaluate(()=>{
      const original=demoHass.callWS;
      demoHass.callWS=async function(msg){if(msg.entity_id==='climate.atrio'&&msg.operation==='list')await new Promise(r=>setTimeout(r,80));return original.call(this,msg)};
      demoCard._load(true);
      demoHass.states['climate.other']={state:'auto',attributes:{friendly_name:'Other',program_number:2,program_mode:'AUTOMATIC',current_function:'HEATING'}};
      demoCard.setConfig({entity:'climate.other'});
    });
    await p.waitForFunction(()=>!demoCard._busy&&demoCard._catalog&&demoCalls.at(-1).entity_id==='climate.other');
    assert.equal(await p.locator('.subtitle').innerText(),'Other');assert.equal(await p.locator('.error').count(),0);
  });
  await test('export downloads the editable weekly program',async p=>{
    await more(p);const pending=p.waitForEvent('download');await p.locator('[data-action=export]').click();const download=await pending;
    const data=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
    assert.equal(data.format,'bticino-weekly-program-v1');assert.equal(data.days.monday[1].time,'07:30');
  });
  await test('import creates a new draft without writing',async p=>{
    const data=await p.evaluate(()=>({format:'bticino-weekly-program-v1',...demoPrograms[1]}));
    await p.locator('input[type=file]').setInputFiles({name:'program.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});
    await p.waitForFunction(()=>demoCard._draft.number===3);
    assert.equal(await p.evaluate(()=>demoCalls.filter(c=>c.operation==='save').length),0);
    await edit(p);assert.equal(await p.locator('[data-field=time][data-index="1"]').inputValue(),'10:00');
  });
  await test('invalid import keeps the current program',async p=>{
    await p.locator('input[type=file]').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{bad')});
    await p.locator('.error').waitFor();assert.equal(await p.evaluate(()=>demoCard._draft.number),2);
  });
  await test('visual card editor localizes labels and emits entity changes',async p=>{
    const result=await p.evaluate(()=>{const editor=document.createElement('bticino-programs-card-editor');editor.setConfig({entity:'climate.atrio'});editor.hass=demoHass;document.body.append(editor);let changed;editor.addEventListener('config-changed',e=>changed=e.detail.config);editor.querySelector('ha-entity-picker').dispatchEvent(new CustomEvent('value-changed',{detail:{value:'climate.other'}}));return{label:editor.querySelector('label span').textContent,entity:changed.entity}});
    assert.match(result.label,/Titolo/);assert.equal(result.entity,'climate.other');
  });
  await test('consultation is readable and secondary tools are collapsed',async p=>{
    assert.equal(await p.locator('[data-field=time]').count(),0);
    assert.match(await p.locator('.periods').innerText(),/07:30.*13:00/);
    assert.equal(await p.locator('[data-action=delete]').isVisible(),false);
    await edit(p);assert.equal(await p.locator('[data-field=time]').count(),7);
    assert.equal(await p.locator('.slot-end').nth(1).innerText(),'13:00');
  });
  await test('today shows current and next scheduled period with actual target',async p=>{
    assert.match(await p.locator('.today-heading').innerText(),/Lunedì/i);
    assert.match(await p.locator('.current-period').innerText(),/Giorno.*18[\s\S]*13:00/);
    assert.match(await p.locator('.next-period').innerText(),/Protezione.*7[\s\S]*13:00/);
    assert.match(await p.locator('.actual-target').innerText(),/18/);
    assert.equal(await p.locator('.period.current').count(),1);
    assert.equal(await p.locator('[data-action=save]').count(),0);
    await p.locator('bticino-today-card').screenshot({path:path.join(out,'bticino-today-desktop.png')});
  },'?today=1');
  await test('today uses the saved active program rather than the unsaved editor draft',async p=>{
    await p.locator('[data-action=open][data-number="1"]').click();await p.waitForFunction(()=>!demoCard._busy);
    await edit(p);await p.locator('[data-field=name]').fill('Bozza non salvata');
    await p.locator('[data-field=preset][data-index="1"]').selectOption('NIGHT');
    await p.locator('[data-action=view][data-view=today]').click();
    assert.match(await p.locator('.today-heading').innerText(),/Programma Atrio/);
    assert.match(await p.locator('.current-period').innerText(),/Giorno/);
    await p.locator('[data-action=view][data-view=programs]').click();
    assert.equal(await p.locator('[data-field=name]').inputValue(),'Bozza non salvata');
    assert.equal(await p.evaluate(()=>demoCalls.filter(c=>['save','activate','delete'].includes(c.operation)).length),0);
  });
  await test('manual override with unchanged program number is never highlighted as running',async p=>{
    await p.evaluate(()=>{demoHass.states['climate.atrio'].attributes.program_mode='MANUAL';demoCard.hass=demoHass});
    assert.equal(await p.locator('.period.current').count(),0);
    assert.equal(await p.locator('.next-period').count(),0);
    assert.match(await p.locator('.today-panel .notice').innerText(),/sospeso/);
    assert.match(await p.locator('.current-period').innerText(),/Obiettivo attuale/i);
  },'?today=1');
  await test('unavailable thermostat displays stale schedule without an active period',async p=>{
    await p.evaluate(()=>{demoHass.states['climate.atrio'].state='unavailable';demoCard.hass=demoHass});
    assert.equal(await p.locator('.period.current').count(),0);
    assert.match(await p.locator('.today-panel .notice').innerText(),/non collegato/);
  },'?today=1');
  await test('today uses cooling preset values',async p=>{
    await p.evaluate(()=>{demoHass.states['climate.atrio'].attributes.current_function='COOLING';demoCard.hass=demoHass});
    assert.match(await p.locator('.current-period').innerText(),/30/);
  },'?today=1');
  await test('today follows HA timezone rather than the browser timezone',async p=>{
    await p.evaluate(()=>{demoHass.config.time_zone='Pacific/Honolulu';demoCard.hass=demoHass});
    assert.match(await p.locator('.today-heading').innerText(),/Domenica/i);
    assert.match(await p.locator('.today-heading time').innerText(),/23:30/);
    assert.match(await p.locator('.next-period').innerText(),/Domani 00:00/);
  },'?today=1');
  await test('display clock crosses a schedule boundary without device commands',async p=>{
    const count=await p.evaluate(()=>demoCalls.length);
    await p.clock.setSystemTime(new Date('2026-10-26T12:00:00Z'));await p.clock.runFor(30000);
    assert.match(await p.locator('.current-period').innerText(),/Protezione[\s\S]*15:00/);
    assert.equal(await p.evaluate(()=>demoCalls.length),count);
  },'?today=1');
  await test('display clock changes weekday at midnight',async p=>{
    await p.clock.setSystemTime(new Date('2026-10-26T23:01:00Z'));await p.clock.runFor(30000);
    assert.match(await p.locator('.today-heading').innerText(),/Martedì/i);
    assert.equal(await p.locator('.period').count(),3);
  },'?today=1');
  await test('native program changes fetch the new active profile without editing',async p=>{
    await p.evaluate(()=>{demoActive=1;demoHass.states['climate.atrio'].attributes.program_number=1;demoCard.hass=demoHass});
    await p.waitForFunction(()=>!demoCard._busy&&demoCard._profiles[1]);
    assert.match(await p.locator('.today-heading').innerText(),/HA Lun-Sab/);
    assert.equal(await p.locator('.period').count(),3);
    assert.equal(await p.evaluate(()=>demoCalls.filter(c=>c.operation==='save').length),0);
  },'?today=1');
  await test('today is available to non-admins without mutation controls',async p=>{
    assert.equal(await p.locator('.period').count(),7);
    assert.equal(await p.locator('[data-field=active]').count(),0);
    assert.equal(await p.locator('[data-action=edit-day]').count(),0);
  },'?today=1&readonly=1');
  await test('today mobile dark card fits within its own width',async p=>{
    await p.setViewportSize({width:390,height:1200});
    assert.equal(await p.locator('bticino-today-card').evaluate(el=>el.shadowRoot.querySelector('ha-card').scrollWidth<=el.clientWidth),true);
    await p.locator('bticino-today-card').screenshot({path:path.join(out,'bticino-today-mobile-dark.png')});
  },'?today=1&dark=1');
  await test('removing today card releases its display timer',async p=>{
    assert.equal(await p.evaluate(()=>Boolean(demoCard._clockTimer)),true);
    await p.evaluate(()=>demoCard.remove());
    assert.equal(await p.evaluate(()=>demoCard._clockTimer),null);
  },'?today=1');
  await test('unsaved edits to the active program do not alter today',async p=>{
    await edit(p);await p.locator('[data-field=preset][data-index="1"]').selectOption('NIGHT');
    await p.locator('[data-action=view][data-view=today]').click();
    assert.match(await p.locator('.current-period').innerText(),/Giorno/);
    assert.equal(await p.evaluate(()=>demoCalls.filter(c=>c.operation==='save').length),0);
  });
  await test('refresh updates today after an external schedule edit',async p=>{
    await p.evaluate(()=>demoPrograms[2].days.monday[1].preset='NIGHT');
    await p.locator('[data-action=refresh]').click();await p.waitForFunction(()=>!demoCard._busy);
    assert.match(await p.locator('.current-period').innerText(),/Notte/);
  },'?today=1');
  await test('today handles a missing program without inventing an active period',async p=>{
    await p.evaluate(()=>{const a=demoHass.states['climate.atrio'].attributes;a.program_number=null;a.program_mode='MANUAL';demoCard.hass=demoHass});
    assert.match(await p.locator('.today-heading').innerText(),/Nessun programma/);
    assert.equal(await p.locator('.period.current').count(),0);
    assert.equal(await p.locator('.next-period').count(),0);
  },'?today=1');
  await test('today card supports English and its visual editor',async p=>{
    assert.match(await p.locator('h2').innerText(),/today/i);
    assert.match(await p.locator('.today-heading').innerText(),/Monday/i);
    assert.equal(await p.evaluate(()=>customElements.get('bticino-today-card').getConfigElement().tagName),'BTICINO-PROGRAMS-CARD-EDITOR');
  },'?today=1&lang=en');
  await test('mobile editing fits the card and preserves field focus',async p=>{
    await p.setViewportSize({width:390,height:1500});await edit(p);
    await p.locator('[data-field=name]').fill('Settimana aggiornata');
    assert.equal(await p.locator('[data-field=name]').evaluate(el=>el.getRootNode().activeElement===el),true);
    assert.equal(await p.locator('bticino-programs-card').evaluate(el=>el.shadowRoot.querySelector('ha-card').scrollWidth<=el.clientWidth),true);
    await p.locator('bticino-programs-card').screenshot({path:path.join(out,'bticino-programs-editor-mobile.png')});
  });
  await test('today timeline has proportional segments and a current-time cursor',async p=>{
    const widths=await p.locator('.day-segment').evaluateAll(els=>els.map(el=>parseFloat(el.style.width)));
    assert.equal(widths.length,7);assert.ok(Math.abs(widths.reduce((a,b)=>a+b,0)-100)<0.001);
    assert.equal(widths[0],31.25);
    assert.equal(await p.locator('.time-cursor').evaluate(el=>parseFloat(el.style.left)),43.75);
    assert.equal(await p.locator('.period-list').evaluate(el=>el.open),false);
    assert.equal(await p.locator('.day-segment.current').getAttribute('data-index'),'1');
  },'?today=1');
  await test('touching a timeline segment shows its range without any device request',async p=>{
    const count=await p.evaluate(()=>demoCalls.length);await p.locator('.day-segment').nth(6).click();
    assert.match(await p.locator('.timeline-detail').innerText(),/22:00.*24:00[\s\S]*Protezione/);
    assert.equal(await p.locator('.day-segment[aria-pressed=true]').getAttribute('data-index'),'6');
    assert.equal(await p.evaluate(()=>demoCalls.length),count);
    await p.locator('.day-segment').nth(1).focus();await p.keyboard.press('Enter');
    assert.equal(await p.locator('.day-segment').nth(1).evaluate(el=>el.getRootNode().activeElement===el),true);
  },'?today=1');
  await test('manual mode retains timeline but suppresses the running cursor',async p=>{
    await p.evaluate(()=>{demoHass.states['climate.atrio'].attributes.program_mode='MANUAL';demoCard.hass=demoHass});
    assert.equal(await p.locator('.day-segment').count(),7);
    assert.equal(await p.locator('.time-cursor').count(),0);
    assert.equal(await p.locator('.day-segment.current').count(),0);
  },'?today=1');
  await test('timeline inspection resets to current period when weekday changes',async p=>{
    await p.locator('.day-segment').nth(6).click();
    await p.clock.setSystemTime(new Date('2026-10-26T23:01:00Z'));await p.clock.runFor(30000);
    assert.equal(await p.locator('.day-segment').count(),3);
    assert.match(await p.locator('.timeline-detail').innerText(),/00:00.*20:00/);
    assert.equal(await p.locator('.day-segment[aria-pressed=true]').getAttribute('data-index'),'0');
  },'?today=1');
  await test('standalone today defaults to only the timeline and hour axis',async p=>{
    assert.equal(await p.locator('.day-segment').count(),7);
    assert.equal(await p.locator('header,h2,.today-summary,.legend,.timeline-detail,footer,.period-list').count(),0);
    assert.equal(await p.locator('.time-cursor').count(),1);
    assert.match(await p.locator('.day-axis').innerText(),/00:00[\s\S]*24:00/);
    assert.ok(await p.locator('bticino-today-card').evaluate(el=>el.clientHeight)<120);
    await p.locator('bticino-today-card').screenshot({path:path.join(out,'bticino-today-strip-desktop.png')});
  },'?today=1&compact=1');
  await test('dashboard strip fits mobile and inspecting it sends no commands',async p=>{
    await p.setViewportSize({width:390,height:300});
    const count=await p.evaluate(()=>demoCalls.length);await p.locator('.day-segment').nth(6).click();
    assert.match(await p.locator('.day-segment').nth(6).getAttribute('aria-label'),/22:00.*24:00/);
    assert.equal(await p.evaluate(()=>demoCalls.length),count);
    assert.equal(await p.locator('bticino-today-card').evaluate(el=>el.shadowRoot.querySelector('ha-card').scrollWidth<=el.clientWidth),true);
    await p.locator('bticino-today-card').screenshot({path:path.join(out,'bticino-today-strip-mobile.png')});
  },'?today=1&compact=1&dark=1');
  await test('dashboard strip signals a manual override without extra panels',async p=>{
    await p.evaluate(()=>{demoHass.states['climate.atrio'].attributes.program_mode='MANUAL';demoCard.hass=demoHass});
    assert.equal(await p.locator('.time-cursor,.day-segment.current').count(),0);
    assert.match(await p.locator('.strip-status').getAttribute('aria-label'),/sospeso/);
    assert.equal(await p.locator('.today-summary').count(),0);
  },'?today=1&compact=1');
  await browser.close();server.close();
  fs.writeFileSync(path.join(out,'bticino-programs-ui-test-results.json'),JSON.stringify(tests,null,2));
  console.log(JSON.stringify(tests,null,2));if(tests.some(t=>!t.passed))process.exitCode=1;
})().catch(e=>{console.error(e);server.close();process.exitCode=1});
