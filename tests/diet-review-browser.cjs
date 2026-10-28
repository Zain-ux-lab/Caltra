const {chromium}=require('@playwright/test');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});try{
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const day='2026-10-27';let complete=false,periods=[];
 await page.route('**/api/meals',r=>r.fulfill({json:[{id:'synthetic',name:'Synthetic food',date:day,items:[{id:'i',grams:100,food:{id:'f',name:'Macro-only food',source:'AI estimate',nutrients:{calories:100,protein:10,carbs:10,fat:2}}}]}]}));
 await page.route('**/api/days/*/complete',r=>{complete=r.request().postDataJSON().complete;assert.equal(r.request().headers()['content-type'],'application/json');return r.fulfill({json:{complete}})});
 await page.route('**/api/diet-review?*',r=>{const period=new URL(r.request().url()).searchParams.get('period');periods.push(period);return r.fulfill({json:{start:day,end:day,loggedDays:1,completedDays:complete?1:0,missingDays:6,notice:'Unknown values are never zero.',days:[{date:day,logged:true,complete}],nutrients:[{key:'fibre',label:'Fibre',unit:'g',average:null,coveredDays:0,status:'insufficient_data',message:'Not enough coverage.',reference:30,suggestions:[],source:null}]}})});
 await page.goto('http://127.0.0.1:8000');
 await page.getByRole('button',{name:'Nutrients',exact:true}).click();
 await page.getByRole('heading',{name:'Your diet over time'}).waitFor();
 await page.getByText(/Not enough nutrient data for a personalised pattern yet/).waitFor();
 await page.getByLabel('Review period').selectOption('3');await page.waitForResponse(r=>r.url().includes('diet-review')&&r.url().includes('period=3'));
 await page.getByText('Mark days you’ve finished logging',{exact:true}).click();await page.getByRole('checkbox').check();
 await page.getByText(/1 days logged · 1 marked complete/).waitFor();
 assert.deepEqual(periods.slice(0,2),['7','3']);assert.equal(complete,true);
 await page.screenshot({path:'/private/tmp/caltra-review-mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
 console.log('PASS: mobile review, insufficient-data explanation, period switch, JSON day completion, no overflow. All diary writes mocked.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
