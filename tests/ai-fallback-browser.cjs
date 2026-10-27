const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const food={id:'ai:test',name:'Bakery cookie',source:'AI estimate — not database verified',sourceWarning:'No suitable database match. Calories and macros are AI guesses, not verified product-label values.',isAiEstimate:true,nutrients:{calories:400,protein:5,carbs:50,fat:20},portions:[],url:''};
  await page.route('**/api/status',r=>r.fulfill({json:{visionConfigured:true,visionModel:'test',cachedFoods:16333}}));
  await page.route('**/api/meals',r=>r.fulfill({json:[]}));
  await page.route('**/api/recognize',r=>r.fulfill({json:{foods:[{label:'Bakery cookie',query:'cookie',matchType:'ai-estimated'}],items:[{id:'cookie',food,grams:120,quantityKind:'estimated',portionLabel:'AI-estimated portion'}],groups:[],missing:[],usuals:[],description:'Cookie',question:'',notice:'Estimate'}}));
  await page.goto('http://127.0.0.1:8000');
  await page.getByLabel('Upload meal photo').setInputFiles({name:'test.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
  await page.getByRole('button',{name:'Estimate macros',exact:true}).click();
  await page.getByText('Includes AI-estimated macros · unverified',{exact:true}).waitFor();
  assert.match(await page.getByLabel('Estimated macros').innerText(),/480/);
  await page.getByText(food.sourceWarning,{exact:true}).waitFor();
  assert(await page.getByRole('button',{name:'Save meal',exact:true}).isEnabled());
  await page.getByLabel('Portion in grams',{exact:true}).fill('60');
  assert.match(await page.getByLabel('Estimated macros').innerText(),/240/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  console.log('PASS: labelled AI macros, source warning, editable amounts and enabled save on mobile. Mocked responses only; no private uploads.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
