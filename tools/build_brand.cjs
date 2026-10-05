/* Export our native SVG artwork with Chromium; no image editing dependency. */
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require(require.resolve('playwright',{paths:[process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES||process.cwd()]}));
const root=path.resolve(__dirname,'..'),out=path.join(root,'brand');
fs.mkdirSync(out,{recursive:true});
const icon=fs.readFileSync(path.join(root,'custom_components/home_scheduler/frontend/icon.svg'),'utf8');
fs.writeFileSync(path.join(out,'icon.svg'),icon);
for(const [name,color] of [['logo','#243445'],['logo-dark','#ffffff']]) {
 const house=icon.replace('width="256" height="256"','x="16" y="16" width="128" height="128"');
 fs.writeFileSync(path.join(out,name+'.svg'),`<svg xmlns="http://www.w3.org/2000/svg" width="640" height="160" viewBox="0 0 640 160">${house}<g fill="${color}" font-family="Arial, sans-serif"><text x="168" y="76" font-size="44" font-weight="600">Home Scheduler</text><text x="169" y="115" font-size="28">&amp; Simulator</text></g></svg>\n`);
}
(async()=>{
 const browser=await chromium.launch({headless:true,
  ...(process.env.HOME_SCHEDULER_BROWSER?{executablePath:process.env.HOME_SCHEDULER_BROWSER}:{}),
  args:['--no-sandbox','--disable-dev-shm-usage'],
  ...(process.env.FLOOR3DX_RUNTIME_LIBRARY_DIR?{env:{...process.env,LD_LIBRARY_PATH:process.env.FLOOR3DX_RUNTIME_LIBRARY_DIR}}:{})});
 try {
  for(const name of ['icon','logo','logo-dark'])for(const scale of [1,2]){
   const context=await browser.newContext({deviceScaleFactor:scale,viewport:{width:700,height:300}}),page=await context.newPage();
   await page.setContent('<!doctype html><meta charset="utf-8"><style>body{margin:0;background:transparent}svg{display:block}</style>'+fs.readFileSync(path.join(out,name+'.svg'),'utf8'));
   await page.locator('body > svg').screenshot({path:path.join(out,name+(scale===2?'@2x':'')+'.png'),omitBackground:true});
   await context.close();
  }
  console.log('Exported selected cyan house icon and transparent light/dark wordmarks.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
