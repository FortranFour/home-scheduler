/* Actual scheduler backend + actual floor3dx 1.4 renderer. HA form widgets
 * and service/storage APIs use doubles. See README for test prerequisites. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||process.cwd()]}));
const root=path.resolve(__dirname,'..'),assets=path.join(root,'custom_components/home_scheduler/frontend');
const imported=JSON.parse(fs.readFileSync(path.join(assets,'demo-home.json'),'utf8'));
imported.name='Imported house';imported.camera_position={x:10,y:14,z:11};
const originalEntries=imported.entities;
const binding=(index,entity)=>({...structuredClone(originalEntries[index]),entity});
imported.entities=[binding(0,'light.fixture_living'),binding(1,'light.fixture_living'),
 binding(2,'switch.fixture_wall'),binding(3,'switch.fixture_alias'),
 binding(12,'fan.fixture_ceiling'),binding(17,'cover.fixture_blind'),
 binding(16,'binary_sensor.fixture_door'),binding(7,'climate.fixture_room')];
imported.entities[1].color_entity='light.fixture_living';
const personal={renderer:imported,legacy_domain:'lighting_scheduler',aliases:{'switch.fixture_alias':'switch.fixture_wall'}};
if(!process.env.FLOOR3DX_BUNDLE) throw new Error('Set FLOOR3DX_BUNDLE to floor3dx-card 1.4.0 dist/floor3dx-card.js.');
const html=`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;padding:12px;font:14px Arial;background:#edf1f5;--primary-text-color:#233443;--secondary-text-color:#657787;--primary-color:#009bcc;--rgb-primary-color:0,155,204;--card-background-color:#fff;--divider-color:#dce4ea;--error-color:#b00020;--secondary-background-color:#f0f5f8}ha-card{display:block;background:white}</style><home-assistant></home-assistant><home-scheduler-card></home-scheduler-card>`;
const server=spawn(process.env.PYTHON||'python3',['-u',path.join(__dirname,'fixture_server.py')],{stdio:['ignore','pipe','inherit']});
const address=new Promise((resolve,reject)=>{let buffer='';server.stdout.on('data',chunk=>{buffer+=chunk;if(buffer.includes('\n'))resolve('http://127.0.0.1:'+JSON.parse(buffer.split('\n')[0]).port);});server.on('error',reject);server.on('exit',code=>{if(code)reject(new Error('Fixture server exited '+code));});});
(async()=>{
 const base=await address;
 const browser=await chromium.launch({headless:true,
  ...(process.env.HOME_SCHEDULER_BROWSER?{executablePath:process.env.HOME_SCHEDULER_BROWSER}:{}),
  args:['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'],
  ...(process.env.FLOOR3DX_RUNTIME_LIBRARY_DIR?{env:{...process.env,LD_LIBRARY_PATH:process.env.FLOOR3DX_RUNTIME_LIBRARY_DIR}}:{})});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1150}}),errors=[],logs=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',m=>{if(['error','warning'].includes(m.type()))logs.push(m.text().slice(0,500));});
  await page.route('http://scheduler.test/**',async route=>{
   const url=new URL(route.request().url());
   if(url.pathname.startsWith('/api/')) {
    const response=await fetch(base+url.pathname.slice(4),{method:route.request().method(),...(route.request().postData()?{body:route.request().postData()}:{}),headers:{'Content-Type':'application/json'}});
    return route.fulfill({status:response.status,contentType:'application/json',body:await response.text()});
   }
   if(url.pathname==='/floor3dx.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(process.env.FLOOR3DX_BUNDLE)});
   if(url.pathname==='/home_scheduler/models.json')return route.fulfill({contentType:'application/json',body:JSON.stringify({models:[{name:'My house',url:'/home_scheduler/my-house.json'}]})});
   if(url.pathname==='/home_scheduler/my-house.json')return route.fulfill({contentType:'application/json',body:JSON.stringify(personal)});
   if(url.pathname.startsWith('/home_scheduler/')){
    const filename=path.basename(url.pathname),types={'.js':'text/javascript','.json':'application/json','.svg':'image/svg+xml','.glb':'model/gltf-binary'};
    return route.fulfill({contentType:types[path.extname(filename)],body:fs.readFileSync(path.join(assets,filename))});
   }
   return route.fulfill({contentType:'text/html',body:html});
  });
  await page.goto('http://scheduler.test/');
  await page.addScriptTag({content:fs.readFileSync(path.join(__dirname,'ha_editor_stubs.js'),'utf8')});
  await page.addScriptTag({type:'module',url:'http://scheduler.test/floor3dx.js'});
  await page.evaluate(async imported=>{
   window.calls=[];window.deviceCalls=0;window.bubbledConfigs=0;window.pending=0;
   document.addEventListener('config-changed',()=>bubbledConfigs++);
   const value=await(await fetch('/api/state')).json();
   window.realHass={states:value.states,language:'en',locale:{language:'en'},resources:{en:{}},localize:()=>'',themes:{themes:{}},config:{latitude:0,longitude:0},user:{is_admin:true},
    callService:async(domain,service,data)=>{
     if(domain!=='home_scheduler'){deviceCalls++;throw new Error('Unexpected device service');}
     calls.push(structuredClone(data));
     pending++;
     try {
     const response=await fetch('/api/command',{method:'POST',body:JSON.stringify(data)}),result=await response.json();
     if(!response.ok)throw new Error(result.error);
     realHass.states=result.states;window.backendCalls=result.calls;card.hass={...realHass};
     } finally {pending--;}
    },callWS:async message=>{
      (window.wsQueries??=[]).push(message);
      if(message.type==='call_service'&&message.domain==='home_scheduler'&&message.service==='learning') {
        const response=await fetch('/api/learning',{method:'POST',body:JSON.stringify(message.service_data)}),result=await response.json();
        if(!response.ok)throw new Error(result.error);
        realHass.states=result.states;window.backendCalls=result.calls;card.hass={...realHass};
        return {response:result.response};
      }
      if(message.type==='lovelace/dashboards/list')return [{url_path:'dashboard-house',title:'House dashboard'}];
      if(message.type==='lovelace/config')return {views:[{cards:message.url_path==='dashboard-house'?[imported]:[]}]};
      return [];
    },connection:{sendMessagePromise:async()=>[],sendMessage:()=>null}};
   window.loadCardHelpers=async()=>({createCardElement:config=>{const el=document.createElement(config.type.slice(7));el.setConfig(config);return el;}});
  },imported);
  await page.addScriptTag({url:'http://scheduler.test/home_scheduler/home-scheduler-card.js'});
  await page.evaluate(()=>{window.card=document.querySelector('home-scheduler-card');card.setConfig({model_editor:false});card.hass=realHass;});
  try{await page.waitForFunction(()=>card.renderer?._modelready,null,{timeout:25000});}
  catch(error){console.error({errors,logs,state:await page.evaluate(()=>({modelText:card.shadowRoot.getElementById('model').textContent,ready:card.renderer?._modelready,webgl:!!document.createElement('canvas').getContext('webgl')}))});throw error;}
  const q=s=>page.locator('home-scheduler-card '+s);
  const command=data=>page.evaluate(data=>realHass.callService('home_scheduler','command',data),data);
  const waitFor=fn=>page.waitForFunction(fn,null,{timeout:10000});
  const visible=()=>page.evaluate(()=>card.visibleIndices().map(i=>card.plan.devices[i].kind));
  assert.equal(await q('input[data-row]').count(),16*96);
  assert.deepEqual(await visible(),Array(6).fill('light'));
  assert.equal(await page.evaluate(()=>card.renderer.preview),false);
  assert.equal(await q('#editor-pane').isVisible(),false);
  await q('[data-kind="fan"]').check();await waitFor(()=>card.plan.shown_types.includes('fan'));
  assert.deepEqual(await visible(),[...Array(6).fill('light'),'fan','fan']);
  await q('#device-manager > summary').click();
  await q('[data-visible="light.hs_demo_living"]').uncheck();await waitFor(()=>card.plan.hidden_devices.includes('light.hs_demo_living'));
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].rows['light.hs_demo_living'].use),true,'Hiding a row does not disable it');
  await q('#device-manager > summary').click();
  await q('#clear-all').click();await waitFor(()=>card.plan.profiles[0].rows['fan.hs_demo_ceiling'].days[0]==='0'.repeat(24));
  assert.notEqual(await page.evaluate(()=>card.plan.profiles[0].rows['light.hs_demo_living'].days[0]),'0'.repeat(24),'Hidden rows are not cleared');
  await command({op:'view',shown_types:['light'],hidden_devices:[]});
  await q('[data-fill-row="0"][data-value="false"]').click();await waitFor(()=>card.plan.profiles[0].rows['light.hs_demo_living'].days[0]==='0'.repeat(24));
  const first=q('[data-paint-row="0"][data-paint-slot="4"]'),last=q('[data-paint-row="0"][data-paint-slot="8"]');
  await first.scrollIntoViewIfNeeded();const a=await first.boundingBox(),b=await last.boundingBox();
  await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(b.x+b.width/2,b.y+b.height/2,{steps:8});await page.mouse.up();
  await waitFor(()=>calls.at(-1)?.op==='range'&&card.plan.profiles[0].rows['light.hs_demo_living'].days[0]!=='0'.repeat(24));
  assert.deepEqual(await page.evaluate(()=>Array.from(card.shadowRoot.querySelectorAll('[data-row="0"]')).filter(x=>x.checked).map(x=>Number(x.dataset.slot))),[4,5,6,7,8]);
  await page.mouse.move(b.x+b.width/2,b.y+b.height/2);await page.mouse.down();await page.mouse.move(a.x+a.width/2,a.y+a.height/2,{steps:8});await page.mouse.up();
  await waitFor(()=>calls.at(-1)?.op==='range'&&calls.at(-1)?.value===false);
  assert.equal(await q('[data-row="0"]:checked').count(),0,'Reverse drag clears the selected interval');
  await q('[data-row="0"][data-slot="10"]').focus();await page.keyboard.press('Space');await waitFor(()=>calls.at(-1)?.op==='cell'&&calls.at(-1)?.slot===10);
  await command({op:'view',shown_types:['scene'],hidden_devices:[]});
  const sceneBefore=await page.evaluate(()=>card.plan.profiles[0].rows['scene.hs_demo_evening'].days[0]);
  assert.equal(await q('#select-all').isDisabled(),true);
  assert.equal(await q('[data-fill-row="14"][data-value="true"]').isDisabled(),true);
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].rows['scene.hs_demo_evening'].days[0]),sceneBefore);
  await command({op:'view',shown_types:['light','fan','cover'],hidden_devices:[]});
  await q('[data-device-row="0"] .row-settings > summary').click();
  await q('[data-setting-row="0"][data-setting="brightness"]').fill('40');await q('[data-setting-row="0"][data-setting="brightness"]').dispatchEvent('change');
  await waitFor(()=>card.plan.profiles[0].rows['light.hs_demo_living'].on.brightness===40);
  await q('[data-setting-row="0"][data-setting="color"]').fill('#123456');await q('[data-setting-row="0"][data-setting="color"]').dispatchEvent('change');
  await waitFor(()=>card.plan.profiles[0].rows['light.hs_demo_living'].on.color==='#123456');
  await q('[data-device-row="8"] .row-settings > summary').click();
  await q('[data-setting-row="8"][data-setting="percentage"]').fill('80');await q('[data-setting-row="8"][data-setting="percentage"]').dispatchEvent('change');
  await waitFor(()=>card.plan.profiles[0].rows['fan.hs_demo_ceiling'].on.percentage===80);
  await q('[data-device-row="10"] .row-settings > summary').click();
  await q('[data-setting-row="10"][data-setting="position"]').fill('35');await q('[data-setting-row="10"][data-setting="position"]').dispatchEvent('change');
  await waitFor(()=>card.plan.profiles[0].rows['cover.hs_demo_blind'].on.position===35);
  await q('[data-off-position="10"]').fill('20');await q('[data-off-position="10"]').dispatchEvent('change');
  await waitFor(()=>card.plan.profiles[0].rows['cover.hs_demo_blind'].off_position===20);
  await q('[data-outside="10"]').selectOption('restore');await waitFor(()=>card.plan.profiles[0].rows['cover.hs_demo_blind'].outside==='restore');
  await page.evaluate(()=>card.shadowRoot.activeElement?.blur());await waitFor(()=>pending===0);
  await page.evaluate(async()=>{const value=await(await fetch('/api/reset',{method:'POST',body:'{}'})).json();realHass.states=value.states;card.hass={...realHass};});
  await page.evaluate(()=>card.shadowRoot.querySelectorAll('.row-settings').forEach(el=>el.open=false));
  // Native renderer animations follow the real backend's typed virtual states.
  await command({op:'settings',minute:480});
  await page.waitForTimeout(1500);
  const garageOpen=await page.evaluate(()=>card.renderer._scene.getObjectByName('GarageDoor').position.y);
  const closed=await page.evaluate(()=>({shade:card.renderer._scene.getObjectByName('BedroomCurtain').scale.y,fan:card.renderer._rotation_state.slice(),jet:card.renderer._scene.getObjectByName('FountainJet').visible}));
  assert.equal(closed.jet,false);
  assert.deepEqual(closed.fan,[0,0]);
  await command({op:'settings',minute:1080});
  await waitFor(()=>card.renderer._rotation_state[0]===.6&&card.renderer._scene.getObjectByName('FountainJet').visible);
  await page.waitForTimeout(1700);
  assert.ok(await page.evaluate(()=>card.renderer._scene.getObjectByName('GarageDoor').position.y)<garageOpen,'Garage door closes in the native renderer');
  assert.ok(await page.evaluate(()=>card.renderer._scene.getObjectByName('BedroomCurtain').scale.y)<=.0101,'Curtain stays retracted until 19:30');
  const angle=await page.evaluate(()=>card.renderer._scene.getObjectByName('LivingFanBlades').rotation.y);
  await page.waitForTimeout(150);
  assert.notEqual(await page.evaluate(()=>card.renderer._scene.getObjectByName('LivingFanBlades').rotation.y),angle,'Fan actually spins');
  await command({op:'settings',minute:1200});await page.waitForTimeout(1700);
  assert.equal(await page.evaluate(()=>card.renderer._scene.getObjectByName('BedroomCurtain').scale.y),1);
  await command({op:'settings',minute:720});await page.waitForTimeout(1700);
  assert.ok(await page.evaluate(()=>card.renderer._scene.getObjectByName('BedroomCurtain').scale.y)<=.0101,'Roman curtain visibly retracts');
  // Day and night output are review artifacts, not test baselines.
  fs.mkdirSync(path.join(root,'previews'),{recursive:true});
  await page.evaluate(()=>{window.scrollTo(0,0);card.shadowRoot.getElementById('grid').scrollTop=0;card.shadowRoot.getElementById('grid').scrollLeft=0;});
  await page.screenshot({path:path.join(root,'previews/demo-day.png'),fullPage:true});
  await command({op:'settings',minute:1230});await page.waitForTimeout(250);
  assert.equal(await page.evaluate(()=>card.frame.states['light.hs_demo_accent'].state),'on');
  assert.equal(await page.evaluate(()=>card.renderer._scene.getObjectByName('AccentLamp_light').color.getHexString()),'bb75ff','Scene sets the actual 3D light color');
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].rows['cover.hs_demo_blind'].outside),'off','Demo reset restores defaults');
  await page.screenshot({path:path.join(root,'previews/demo-night.png'),fullPage:true});
  await q('#model').screenshot({path:path.join(root,'previews/demo-home.png')});
  await q('#toggle-editor').click();await waitFor(()=>card.editor?._mode==='ready');
  assert.ok(await page.evaluate(()=>card.editor._modelObjects.includes('GarageDoor')&&card.editor._modelObjects.includes('StudyBlind')));
  const layout=await page.evaluate(()=>{const e=card.shadowRoot.getElementById('editor-pane').getBoundingClientRect(),m=card.shadowRoot.getElementById('model').getBoundingClientRect();return e.right<m.left&&Math.abs(e.top-m.top)<2;});
  assert.equal(layout,true,'Editor sits to the left on desktop');
  const editor=q('floor3dx-card-editor');
  await editor.getByRole('button',{name:'Edit',exact:true}).first().click();await waitFor(()=>card.renderer._highlightHelpers.length===1);
  const select=editor.locator('ha-form select[data-field="object_id"]');
  assert.ok(await select.locator('option').count()>70,'Editor lists actual demo meshes');
  await select.selectOption('KitchenLamp');await waitFor(()=>card.rendererDirty&&card.rendererDraft.entities[0].object_id==='KitchenLamp');
  await q('#discard-model').click();await waitFor(()=>card.renderer._modelready&&!card.rendererDirty&&card.rendererDraft.entities[0].object_id==='LivingLamp');
  await editor.getByRole('button',{name:'Back',exact:true}).click();
  await editor.getByRole('button',{name:'Camera and navigation',exact:true}).click();
  await editor.getByRole('button',{name:'Use the current view of the preview',exact:true}).click();await waitFor(()=>card.rendererDirty);
  await q('#save-model').click();await waitFor(()=>!card.rendererDirty&&!card.modelSaving&&card.plan.renderer_revision===1);
  assert.equal(await page.evaluate(()=>deviceCalls),0);
  assert.equal(await page.evaluate(()=>bubbledConfigs),0);
  assert.equal(await page.evaluate(()=>backendCalls.length),0);
  await page.screenshot({path:path.join(root,'previews/demo-editor.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth===innerWidth),true);
  assert.equal(await page.evaluate(()=>card.shadowRoot.getElementById('editor-pane').getBoundingClientRect().bottom<card.shadowRoot.getElementById('model').getBoundingClientRect().top),true);
  await page.screenshot({path:path.join(root,'previews/demo-phone.png'),fullPage:true});
  await q('#toggle-editor').click();
  // A device added while its category was hidden becomes visible immediately.
  await q('#device-manager > summary').click();
  await q('#new-kind').selectOption('switch');await q('#new-name').fill('Desk outlet');await q('#add-device').click();
  await waitFor(()=>card.plan.devices.length===17);assert.ok((await visible()).includes('switch'));
  await q('[data-remove-device]').last().click();await waitFor(()=>card.plan.devices.length===16);
  // Select an existing dashboard model: no manual device list or mesh binding.
  await page.setViewportSize({width:1440,height:1150});
  await waitFor(()=>card.modelChoices.some(x=>x.id==='dashboard-dashboard-house-0'));
  await command({op:'settings',physical:true});
  await q('#model-select').selectOption('dashboard-dashboard-house-0');
  await waitFor(()=>!card.modelImporting&&card.plan.devices.length===5&&card.renderer._modelready);
  assert.equal(await page.evaluate(()=>card.plan.physical),false,'Import disarms physical control');
  assert.deepEqual(await visible(),['light','light','light']); // No explicit alias metadata in a raw dashboard card.
  assert.deepEqual(await page.evaluate(()=>card.savedRenderer.camera_position),imported.camera_position);
  assert.equal(await page.evaluate(()=>card.plan.devices[0].target),'light.fixture_living');
  assert.equal(await page.evaluate(()=>card.savedRenderer.entities[0].entity),await page.evaluate(()=>card.savedRenderer.entities[1].entity),'Repeated light bindings share one row');
  assert.equal(await page.evaluate(()=>card.savedRenderer.entities[6].entity),'binary_sensor.fixture_door');
  assert.equal(await page.evaluate(()=>card.plan.last_import.thermostats),1);
  await q('[data-fill-row="0"][data-value="true"]').click();
  await waitFor(()=>card.frame.states[card.plan.devices[0].entity].state==='on'&&card.renderer._scene.getObjectByName('LivingLamp_light').intensity>0);
  assert.equal(await page.evaluate(()=>realHass.states['light.fixture_living'].state),'off','Imported simulation leaves the real device unchanged');
  // Reloading the card restores the imported catalog and model from HA storage.
  await page.evaluate(()=>{card.remove();card=document.createElement('home-scheduler-card');document.body.append(card);card.setConfig({model_editor:false});card.hass=realHass;});
  await waitFor(()=>card.renderer?._modelready&&card.plan.devices.length===5);
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].rows[card.plan.devices[0].entity].days[0]),'f'.repeat(24));
  // The personal preset supplies aliases and copies live legacy schedules automatically.
  const legacy={renderer:imported,lights:[{entity:'light.fixture_living',name:'Imported living lamp'},{entity:'switch.fixture_wall',name:'Imported kitchen lamps'}],
    profiles:[{id:'weekly',name:'My lighting schedule',rows:{'light.fixture_living':{use:true,days:['0'.repeat(18)+'f'.repeat(2)+'0'.repeat(4)].concat(Array(6).fill('0'.repeat(24)))},'switch.fixture_wall':{use:true,days:Array(7).fill('f'.repeat(24))}}}],
    watts:{'light.fixture_living':9,'switch.fixture_wall':18},random:{'light.fixture_living':false,'switch.fixture_wall':true},profile:'weekly',date:'2026-10-05',jitter:10,seed:12};
  await page.evaluate(async legacy=>{
    let result=await(await fetch('/api/reset',{method:'POST',body:'{}'})).json();
    result=await(await fetch('/api/legacy',{method:'POST',body:JSON.stringify(legacy)})).json();
    realHass.states=result.states;card.remove();card=document.createElement('home-scheduler-card');document.body.append(card);card.setConfig({model_editor:false});card.hass=realHass;
  },legacy);
  await waitFor(()=>card.renderer?._modelready&&card.modelChoices.some(x=>x.id==='preset-0'));
  await q('#model-select').selectOption('preset-0');
  await waitFor(()=>!card.modelImporting&&card.plan.devices.length===4&&card.renderer._modelready);
  assert.deepEqual(await visible(),['light','light']);
  assert.equal(await page.evaluate(()=>card.plan.last_import.schedule_rows_copied),2);
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].name),'My lighting schedule');
  assert.equal(await page.evaluate(()=>card.plan.watts[card.plan.devices[0].entity]),9);
  assert.equal(await page.evaluate(()=>card.savedRenderer.entities[2].entity),await page.evaluate(()=>card.savedRenderer.entities[3].entity),'Preset aliases share the physical target and one preview row');
  assert.equal(await q('#model-status').textContent().then(x=>x.includes('existing schedules copied')),true);
  await command({op:'settings',minute:1110});
  await waitFor(()=>card.renderer._scene.getObjectByName('LivingLamp_light').intensity>0);
  assert.equal(await page.evaluate(()=>realHass.states['light.fixture_living'].state),'off');
  await page.screenshot({path:path.join(root,'previews/model-import.png'),fullPage:true});
  // JSON and YAML file selection trigger the same import automatically.
  await q('#model-file').setInputFiles({name:'house.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(personal))});
  await waitFor(()=>!card.modelImporting&&calls.at(-1)?.op==='import_model');
  assert.equal(await page.evaluate(()=>card.plan.devices.length),4);
  const yaml='type: custom:floor3dx-card\nname: YAML house\npath: /home_scheduler/\nobjfile: demo-home.glb\nheader: no\ncamera_position: {x: 9, y: 13.5, z: 12.5}\ncamera_target: {x: 0, y: 0, z: 0.8}\nentities:\n  - entity: light.fixture_living\n    type3d: light\n    object_id: LivingLamp\n    light:\n      lumens: 650\n      follow_entity: yes\n';
  await q('#model-file').setInputFiles({name:'house.yaml',mimeType:'text/yaml',buffer:Buffer.from(yaml)});
  await waitFor(()=>!card.modelImporting&&card.plan.devices.length===1&&card.renderer._modelready);
  assert.equal(await page.evaluate(()=>card.savedRenderer.header),'no');
  await q('#model-file').setInputFiles({name:'bad.yaml',mimeType:'text/yaml',buffer:Buffer.from('renderer: !secret house')});
  await waitFor(()=>!card.modelImporting&&card.shadowRoot.getElementById('model-status').classList.contains('error'));
  assert.equal(await page.evaluate(()=>card.plan.devices.length),1,'Invalid imports retain the existing model and rows');
  await q('#model-select').selectOption('demo');await waitFor(()=>!card.modelImporting&&card.plan.devices.length===16&&card.renderer._modelready);
  assert.deepEqual(await visible(),Array(6).fill('light'));
  assert.equal(await page.evaluate(()=>card.plan.profiles[0].rows['light.hs_demo_living'].days[0]==='0'.repeat(24)),false,'Switching to demo restores its schedule');
  assert.ok(await page.evaluate(()=>wsQueries.every(x=>['lovelace/config','lovelace/dashboards/list','call_service'].includes(x.type))));
  assert.equal(await page.evaluate(()=>deviceCalls),0);
  assert.equal(await page.evaluate(()=>backendCalls.length),0);
  // Learn proposals have their own player, even while the physical runner is armed.
  await page.evaluate(async()=>{
    const value=await(await fetch('/api/learning-fixture',{method:'POST',body:JSON.stringify({arm:true})})).json();
    realHass.states=value.states;card.hass={...realHass};
    window.learningRunnerBefore={profile:card.plan.profile,frame:structuredClone(card.frame),physical:card.plan.physical,clock:card.plan.clock};
  });
  await q('#learn-open').click();
  assert.equal(await q('[data-learn-select]:checked').count(),6,'Linked lights default selected');
  assert.equal(await q('[data-learn-select="fan.hs_demo_ceiling"]').isChecked(),false);
  assert.equal(await q('#learn-include-history').isChecked(),false);
  await q('#learn-propose').click();await waitFor(()=>!!card.learningProposal);
  const cell=q('[data-learn-cell="0"][data-learn-slot="72"]');
  assert.ok((await cell.getAttribute('title')).includes('On on 5 of 6'));
  assert.equal(await cell.isChecked(),true);
  await q('#learn-preview').click();await waitFor(()=>card.learningFrame?.minute===1080&&card.renderer._scene.getObjectByName('LivingLamp_light').intensity>0);
  assert.equal(await page.evaluate(()=>card.plan.profile===learningRunnerBefore.profile&&card.plan.physical&&card.plan.clock),true);
  assert.equal(await page.evaluate(()=>JSON.stringify(card.frame)===JSON.stringify(learningRunnerBefore.frame)),true,'Preview does not publish or replace runner frame');
  assert.equal(await page.evaluate(()=>realHass.states['light.fixture_observed_0'].state),'off');
  assert.equal(await q('[data-learn-lamp="0"]').textContent(),'On');
  await q('#learn-play').click();await waitFor(()=>card.learningFrame.minute>=1110);
  await q('#learn-play').click();
  assert.equal(await page.evaluate(()=>card.learningPlaying),false);
  await q('#learn-scrubber').fill('120');await waitFor(()=>card.learningFrame.minute===120&&card.renderer._scene.getObjectByName('LivingLamp_light').intensity===0);
  assert.equal(await q('[data-learn-lamp="0"]').textContent(),'Off');
  await q('[data-learn-day="1"]').click();await waitFor(()=>card.learningDay===1);
  assert.ok((await q('[data-learn-cell="0"][data-learn-slot="72"]').getAttribute('title')).includes('Still learning: 2'));
  assert.equal(await q('[data-learn-cell="0"][data-learn-slot="72"]').isChecked(),true,'Unknown retains existing checked block');
  await q('[data-learn-day="0"]').click();
  await q('[data-learn-cell="0"][data-learn-slot="73"]').uncheck();
  await q('#learn-name').fill('Observed evening');
  if(!(await q('#editor-pane').isVisible())) {await q('#toggle-editor').click();await waitFor(()=>card.editor?._mode==='ready');}
  await q('#learn-scrubber').fill('1080');await waitFor(()=>card.learningFrame.minute===1080);
  await page.evaluate(()=>{window.scrollTo(0,0);card.shadowRoot.getElementById('learn-grid').scrollLeft=0;});
  await page.screenshot({path:path.join(root,'previews/learn-actual-use.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth===innerWidth),true,'Learning review stays within phone width');
  await page.setViewportSize({width:1440,height:1150});
  await q('#learn-save').click();await waitFor(()=>card.plan.profiles.some(p=>p.name==='Observed evening'));
  assert.equal(await page.evaluate(()=>card.plan.profile===learningRunnerBefore.profile&&card.plan.physical&&card.plan.clock),true);
  assert.equal(await page.evaluate(()=>card.plan.profiles.find(p=>p.name==='Observed evening').rows['light.hs_demo_living'].days[0][18]),'b','Edited proposal was saved');
  assert.equal(await q('#learn-review').isVisible(),false);
  assert.equal(await page.evaluate(()=>card.learningFrame),null);
  assert.equal(await page.evaluate(()=>backendCalls.length),0);
  await q('#learn-close').click();
  await page.evaluate(async()=>{const value=await(await fetch('/api/reset',{method:'POST',body:'{}'})).json();realHass.states=value.states;card.hass={...realHass};});
  // A grid-only installation works without floor3dx or HA card helpers.
  await page.evaluate(()=>{
    window.gridHelperCalls=0;
    window.loadCardHelpers=async()=>{gridHelperCalls++;throw new Error('Grid-only mode must not load renderer helpers');};
    card.remove();card=document.createElement('home-scheduler-card');document.body.append(card);
    card.setConfig({show_model:false});card.hass=realHass;
  });
  assert.equal(await q('#model-workspace').isVisible(),false);
  assert.equal(await q('#model-toolbar').isVisible(),false);
  assert.equal(await q('#grid').isVisible(),true);
  assert.equal(await q('floor3dx-card').count(),0);
  await command({op:'settings',minute:0});
  assert.equal(await q('[data-lamp="0"]').textContent(),'Off');
  await command({op:'settings',minute:1080});
  assert.equal(await q('[data-lamp="0"]').textContent(),'On');
  assert.equal(await page.evaluate(()=>gridHelperCalls),0);
  assert.equal(await page.evaluate(()=>backendCalls.length),0);
  await page.screenshot({path:path.join(root,'previews/grid-only.png'),fullPage:true});
  // Hiding the model while helpers load cancels the pending renderer mount.
  await page.evaluate(()=>{
    window.pendingMounts=0;
    window.loadCardHelpers=()=>new Promise(resolve=>{window.finishModelHelpers=resolve;});
    card.remove();card=document.createElement('home-scheduler-card');document.body.append(card);
    card.setConfig({model_editor:false});card.hass=realHass;
  });
  await waitFor(()=>typeof window.finishModelHelpers==='function');
  await page.evaluate(()=>{
    card.setConfig({show_model:false});
    finishModelHelpers({createCardElement:()=>{pendingMounts++;throw new Error('Canceled renderer mounted');}});
  });
  await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,0)));
  assert.equal(await page.evaluate(()=>pendingMounts),0);
  assert.equal(await q('#model-workspace').isVisible(),false);
  assert.deepEqual(errors,[]);
  assert.deepEqual(logs.filter(x=>x.includes('not found in Home Assistant')),[],'Model switching always supplies the outgoing and incoming preview entities');
  console.log('UI checks passed: real backend + floor3dx 1.4 GLB; grid editing, scenes, fan/cover motion, native editor, model imports, mobile layout; learned consensus/counts/unknown cells, isolated animated 3D and On/Off preview while runner armed, edited proposal saved without changing runner or real states; grid-only simulation and canceled renderer loading; no physical service calls.');
  console.log('Renderer diagnostics:',JSON.stringify(logs));
 } finally {await browser.close();server.kill();}
})().catch(error=>{server.kill();console.error(error);process.exitCode=1;});
