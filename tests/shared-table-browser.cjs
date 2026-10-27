const {chromium}=require('@playwright/test');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const food={id:'fixture',name:'Omelette',source:'Test fixture',nutrients:{calories:150,protein:12,carbs:2,fat:10},portions:[]};const item={id:'meal',food,label:'Omelette',grams:100,quantityKind:'estimated'};
 await page.route('**/api/recognize',r=>{assert.ok(r.request().postDataBuffer().includes(Buffer.from('name="scope"\r\n\r\nautomatic')));return r.fulfill({json:{foods:[],items:[item],groups:[],missing:[],usuals:[],description:'Two plates on a shared table',notice:'',question:'Did you have any butter or honey?',scopeSummary:'Nearest plate only; shared spreads not included',unconfirmedExtras:['Butter','Honey']}})});
 await page.route('**/api/refine',r=>r.fulfill({json:{items:[item,{...item,id:'butter',label:'Butter',food:{...food,name:'Butter'},grams:10}],message:'Added your butter',question:'Did you eat any honey?',missing:[]}}));
 await page.goto('http://127.0.0.1:8000');await page.getByRole('button',{name:'Log food',exact:true}).click();
 await page.getByLabel('Upload meal photo',{exact:true}).setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
 assert.equal(await page.getByLabel('Photo logging scope').count(),0);
 await page.getByRole('button',{name:'Estimate macros',exact:true}).click();await page.getByText('Nearest plate only; shared spreads not included',{exact:true}).waitFor();
 assert.match(await page.locator('.food-question').first().innerText(),/Butter, Honey/);
 await page.getByLabel('Refine meal',{exact:true}).fill('I had a little butter');await page.getByRole('button',{name:'Update',exact:true}).click();
 await page.getByText('Could not estimate these extras yet: Honey. Tell Caltra what you ate in Refine estimate.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Undo last correction'}).click();assert.match(await page.locator('.food-question').first().innerText(),/Butter, Honey/);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);console.log('PASS: automatic scope submitted without a selector, shared extras visible, correction clears confirmed extras, Undo restores, mobile layout works. No photos sent to AI.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
