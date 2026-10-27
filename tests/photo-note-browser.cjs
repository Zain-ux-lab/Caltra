const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.addInitScript(()=>{window.SpeechRecognition=class{start(){this.onresult({results:[[{transcript:'no added oil'}]]});this.onend()}stop(){this.onend?.()}}});
  const food={id:'test',name:'Salmon, cooked, dry heat',nutrients:{calories:200,protein:22,carbs:0,fat:12},portions:[],url:'https://example.com',source:'Test'};
  let calls=0;
  await page.route('**/api/recognize',async route=>{calls++;const body=route.request().postData();assert.match(body,/Salmon, basmati rice/);assert.match(body,/no added oil/);await route.fulfill({json:{foods:[{label:'Salmon with basmati rice',query:'salmon',matchType:'ingredients'}],items:[{id:'salmon',food,grams:120,quantityKind:'estimated',portionLabel:'Photo estimate'}],groups:[],missing:[],usuals:[],description:'Salmon and rice',question:'',notice:'Estimate'}})});
  await page.goto('http://127.0.0.1:8000');
  await page.getByLabel('Upload meal photo').setInputFiles({name:'test.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
  await page.getByRole('button',{name:'Estimate macros',exact:true}).waitFor();
  assert.equal(calls,0);assert.equal(await page.getByLabel('Estimated macros',{exact:true}).count(),0);
  await page.locator('#meal-note').fill('Salmon, basmati rice');
  await page.getByRole('button',{name:'Add a voice note',exact:true}).click();
  await page.getByRole('button',{name:'Estimate macros',exact:true}).click();
  await page.getByLabel('Estimated macros',{exact:true}).waitFor();assert.equal(calls,1);
  await page.getByText('Foods & portions identified',{exact:true}).click();
  await page.getByText('Salmon, cooked, dry heat',{exact:true}).first().waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  console.log('PASS: preview waits, text and simulated voice note submitted together, exact source visible, mobile layout. No image sent to AI.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
