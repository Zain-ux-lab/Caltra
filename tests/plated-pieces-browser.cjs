const {chromium}=require('@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 const food={id:'test',name:'Rice',source:'UK test fixture',nutrients:{calories:117,protein:2.8,carbs:26.5,fat:.7},portions:[]};
 const items=[{id:'a',food,grams:180,label:'Cooked salmon pieces',quantityKind:'estimated',quantityBasis:'photo',portionEvidence:'Shallow mound; scale uncertain.',portionLabel:'Photo estimate'}, {id:'b',food:{...food,name:'Milk'},grams:20,label:'Milk',quantityKind:'estimated',quantityBasis:'assumed',portionLabel:'Assumed quantity: a splash'}];
 await page.route('**/api/recognize',r=>{
 assert.ok(r.request().postDataBuffer().includes(Buffer.from('name="angle"')));
 return r.fulfill({json:{foods:[],items,groups:[{id:'0',itemIds:['a'],visible:4,logged:4}],missing:[],usuals:[],description:'Test fixture',question:'',notice:''}});
 });
 await page.goto('http://127.0.0.1:8000');
 await page.getByRole('button',{name:'Log food',exact:true}).click();
 const upload={name:'test.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')};
 await page.getByLabel('Upload meal photo',{exact:true}).setInputFiles(upload);
 await page.getByLabel('Upload angled meal photo').setInputFiles(upload);
 await page.getByRole('button',{name:'Estimate macros',exact:true}).click();
 await page.getByLabel('Estimated macros').waitFor();
 assert.match(await page.locator('.ingredient').first().innerText(),/Visually estimated.*Shallow mound/);
 assert.match(await page.locator('.ingredient').nth(1).innerText(),/Assumed portion/);
 await page.getByRole('button',{name:'Log one',exact:true}).click();
 assert.equal(await page.getByLabel('Portion in grams',{exact:true}).inputValue(),'45');
 await page.getByRole('button',{name:'Log all 4',exact:true}).click();
 assert.equal(await page.getByLabel('Portion in grams',{exact:true}).inputValue(),'180');
 await page.getByLabel('Portion in grams',{exact:true}).fill('90');
 assert.match(await page.locator('.ingredient').first().innerText(),/Your input.*Amount entered by you/);
 assert.doesNotMatch(await page.locator('.ingredient').first().innerText(),/Shallow mound/);
 await page.locator('.ingredient').first().getByRole('button',{name:'Ate half'}).click();
 assert.match(await page.locator('.ingredient').first().innerText(),/You selected half/);
 assert.equal(await page.getByLabel('Portion in grams',{exact:true}).inputValue(),'45');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.deepEqual(errors,[]);
 console.log('PASS: plated group starts at 180g, log-one gives 45g, log-all restores 180g; manual edits and mobile layout pass');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
