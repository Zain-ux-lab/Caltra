const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {mkdtempSync,rmSync}=require('node:fs');
const {tmpdir}=require('node:os');
const dir=mkdtempSync(tmpdir()+'/caltra-browser-');
const server=spawn('python',['-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8765'],{env:{...process.env,CALTRA_DB_PATH:dir+'/app.sqlite',GEMINI_API_KEY:''},stdio:'inherit'});
(async()=>{
 let browser;
 try{
  for(let n=0;n<80;n++){
   try{if((await fetch('http://127.0.0.1:8765/healthz')).ok)break;}catch{}
   await new Promise(r=>setTimeout(r,250));
  }
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:8765');
  await page.getByRole('button',{name:'Log food',exact:true}).click();
  await page.getByRole('button',{name:'Search foods',exact:true}).click();
  await page.getByLabel('Search UK foods',{exact:true}).fill('popeyes spicy chicken meal');
  await page.getByRole('button',{name:'Search',exact:true}).click();
  await page.getByRole('button',{name:/^Popeyes · Spicy Chicken Sandwich · Sandwiches/}).click();
  assert.equal(await page.getByLabel('Food amount',{exact:true}).inputValue(),'1');
  await page.getByLabel('Food amount',{exact:true}).fill('0.5');
  await page.getByRole('button',{name:'Add to meal',exact:true}).click();
  assert.equal(await page.getByLabel('Menu servings 1').inputValue(),'0.5');
  assert.match(await page.locator('.portion-summary').innerText(),/0.5 menu servings/);
  await page.getByRole('button',{name:'Save meal',exact:true}).click();
  await page.getByRole('heading',{name:'Your daily diary'}).waitFor();
  assert.match(await page.locator('.logged-meal').innerText(),/0.5 serving/);
  const meals=await (await fetch('http://127.0.0.1:8765/api/meals')).json();
  assert.equal(meals[0].items[0].grams,.5);
  assert.equal(meals[0].totals.calories,264.735);
  await page.getByRole('button',{name:'Nutrients',exact:true}).click();
  const fibre=page.locator('.nutrient-card').filter({has:page.getByText('Fibre',{exact:true})});
  await fibre.waitFor();
  assert.match(await fibre.innerText(),/1.48/);
  await page.reload();
  await page.getByRole('button',{name:'Nutrients',exact:true}).click();
  await fibre.waitFor();assert.match(await fibre.innerText(),/1.48/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  console.log('PASS: real catalogue search, half-serving save, fractional diary display, same-day nutrients and persistence.');
 }finally{if(browser)await browser.close();server.kill();rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
