const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const food=(id,name,kcal)=>({id,name,nutrients:{calories:kcal,protein:10,carbs:20,fat:5},portions:[],url:'https://example.com',source:'Test'});
  const fish={id:'fish',label:'Pan-fried fish',clarification:'What type of fish is this — salmon, cod, or something else?',food:food('f','Fish, cooked',150),grams:120,quantityKind:'estimated',portionLabel:'Photo estimate'};
  const rice={id:'rice',label:'Cooked white rice',clarification:'What kind of rice is this — basmati, jasmine, or another type?',food:food('r','Rice, white, cooked',130),grams:150,quantityKind:'estimated',portionLabel:'Photo estimate'};
  let cake=false;
  await page.route('**/api/recognize',r=>r.fulfill({json:cake?{foods:[{label:'Baked oat cake',query:'oat cake',components:[],matchType:'none'}],items:[],groups:[],missing:['Baked oat cake'],usuals:[],description:'Whole baked oat tray',question:'What ingredients went into the oat cake?',notice:'No suitable source yet'}:{foods:[{label:'Fish and rice',query:'fish rice',matchType:'ingredients'}],items:[fish,rice],groups:[],missing:[],usuals:[],description:'Fish and rice',question:'Was any oil used?',notice:'Estimate'}}));
  await page.route('**/api/refine',r=>{
   const body=r.request().postDataJSON();
   if(!cake){assert.match(body.message,/Correct only item fish/);assert.match(body.message,/salmon/);return r.fulfill({json:{items:[{...fish,id:'salmon',label:'Salmon',clarification:'',food:food('salmon','Salmon, cooked, dry heat',206)},rice],missing:[],message:'Updated fish to salmon',question:rice.clarification,version:body.version}})}
   assert.deepEqual(body.unresolved,[]);assert.match(body.message,/1 cup rolled oats/);
   return r.fulfill({json:{items:[{...fish,id:'oats',label:'Rolled oats',clarification:'',food:food('o','Oats, dry',379),grams:81},{...fish,id:'banana',label:'Bananas',clarification:'',food:food('b','Bananas, raw',89),grams:236}],missing:['Baking powder'],message:'Partial estimate. Baking powder not included yet.',question:'How many portions?',version:body.version}});
  });
  await page.goto('http://127.0.0.1:8000');
  const upload={name:'test.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')};
  const take=async()=>{await page.getByLabel('Upload meal photo').setInputFiles(upload);await page.getByRole('button',{name:'Estimate macros',exact:true}).click()};
  await take();const cards=page.getByRole('region',{name:'Individual foods'});await cards.waitFor();assert.equal(await cards.locator('.ingredient').count(),2);
  await cards.getByText(fish.clarification,{exact:true}).waitFor();await cards.getByText(rice.clarification,{exact:true}).waitFor();
  await cards.locator('.ingredient').nth(1).getByRole('button',{name:'Change food',exact:true}).click();
  await page.locator('.search-results').waitFor();
  await cards.getByLabel('Correct food 1',{exact:true}).fill('salmon');await cards.locator('.ingredient').first().getByRole('button',{name:'Correct',exact:true}).click();
  await cards.locator('b').filter({hasText:/^Salmon$/}).waitFor();assert.equal(await cards.locator('.food-question').count(),1);assert.equal(await page.locator('.search-results').count(),0);
  const calories=await page.locator('.calories').first().innerText();await page.getByLabel('Portion in grams',{exact:true}).fill('60');assert.notEqual(await page.locator('.calories').first().innerText(),calories);
  cake=true;await take();await page.getByLabel('Refine meal',{exact:true}).fill('1 cup rolled oats, 2 bananas, baking powder');await page.getByRole('button',{name:'Update',exact:true}).click();
  await cards.locator('b').filter({hasText:/^Rolled oats$/}).waitFor();assert.equal(await cards.locator('.ingredient').count(),2);
  await page.getByRole('button',{name:'Baking powder · find match',exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Save meal',exact:true}).isEnabled(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'test-results/editable-foods-mobile.png',fullPage:true});
  console.log('PASS: visible per-food editing, fish/rice questions, source replacement, live macros, oat recipe expansion, partial warning/save guard, mobile. Model outputs simulated; no private photo uploads.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
