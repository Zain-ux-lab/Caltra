const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const product={id:'off:5011157996776',name:'Tilda · Pure Basmati Rice (250g)',brand:'Tilda',packGrams:250,barcode:'5011157996776',nutrients:{calories:143,protein:2.9,carbs:28.2,fat:1.9},portions:[{label:'1 pack',grams:250}],source:'Open Food Facts — UK products',sourceWarning:'Community record: check brand and current label.',url:'https://world.openfoodfacts.org/product/5011157996776'};
  let calls=0;
  await page.route('**/api/recognize',r=>{const body=r.request().postData();calls++;assert.match(body,/name="file"/);assert.equal(/name="angle"/.test(body),calls===1);return r.fulfill({json:{foods:[{label:'Basmati rice',query:'basmati',matchType:'ingredients'}],items:[{id:'rice',label:'Basmati rice',food:{...product,id:'generic',name:'Rice, white, basmati, boiled',source:'UK CoFID 2021',sourceWarning:undefined},grams:125,quantityKind:'estimated',portionLabel:'Photo estimate'}],groups:[],missing:[],usuals:[],description:'Rice',question:'',notice:'Estimate'}})});
  await page.route('**/api/foods?**',r=>{assert.match(r.request().url(),/uk=true/);return r.fulfill({json:{foods:[product],matchType:'matched',warning:'Confirm current product label'}})});
  await page.goto('http://127.0.0.1:8000');
  const pic={name:'main.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')};
  await page.getByLabel('Upload meal photo',{exact:true}).setInputFiles(pic);
  await page.getByLabel('Upload angled meal photo',{exact:true}).setInputFiles({...pic,name:'side.png'});
  await page.getByAltText('Second angle of the same meal').waitFor();
  await page.getByRole('button',{name:'Estimate macros',exact:true}).click();
  await page.getByRole('region',{name:'Individual foods'}).waitFor();
  await page.getByRole('button',{name:'Change food',exact:true}).click();
  await page.locator('.food-result').filter({hasText:'Tilda · Pure Basmati Rice (250g)'}).click();
  await page.getByText(product.sourceWarning,{exact:true}).waitFor();
  assert.match(await page.locator('.ingredient a').innerText(),/Open Food Facts/);
  assert.match(await page.locator('.ingredient b').innerText(),/Tilda/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.getByLabel('Upload meal photo',{exact:true}).setInputFiles(pic);
  assert.equal(await page.getByAltText('Second angle of the same meal').count(),0);
  await page.getByRole('button',{name:'Estimate macros',exact:true}).click();await page.getByRole('region',{name:'Individual foods'}).waitFor();
  assert.equal(calls,2);
  console.log('PASS: dual-photo submission, optional single-photo fallback, second-photo reset, UK lookup, named product/source warnings and mobile layout. No AI uploads.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
