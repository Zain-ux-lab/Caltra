const {chromium}=require(process.cwd()+'/node_modules/@playwright/test');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],requests=[];
 page.on('pageerror',e=>errors.push(String(e)));
 const food=i=>({id:'off:'+i,name:'Asda · UK yogurt '+i,brand:'Asda',nutritionBasis:'g',source:'Open Food Facts — UK products',nutrients:{calories:66,protein:7,carbs:8,fat:.5},portions:[]});
 await page.route('**/api/products/search?*',route=>{
  const url=new URL(route.request().url()),p=Number(url.searchParams.get('page'));requests.push({q:url.searchParams.get('q'),page:p});
  return route.fulfill({json:{foods:p===1?Array.from({length:65},(_,i)=>food(i)):[food(64),food(65)],page:p,hasMore:p===1,warning:'Check current label'}});
 });
 await page.goto('http://127.0.0.1:8765');await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:/My usual products/}).click();
 await page.getByLabel('Search UK products or barcode').fill('yogurt');await page.getByRole('button',{name:'Search',exact:true}).click();
 await page.getByText('65 UK products shown',{exact:true}).waitFor();assert.equal(await page.locator('.product-results article').count(),65);
 await page.getByLabel('Search UK products or barcode').fill('milk');await page.getByRole('button',{name:'Show more UK products',exact:true}).click();
 await page.getByText('66 UK products shown',{exact:true}).waitFor();assert.deepEqual(requests,[{q:'yogurt',page:1},{q:'yogurt',page:2}]);
 assert.equal(await page.getByRole('button',{name:'Show more UK products',exact:true}).count(),0);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 assert.deepEqual(errors,[]);
 await page.screenshot({path:'/private/tmp/caltra-expanded-products.png'});await browser.close();console.log('PASS: 65 results, next-page loading, deduplication, original search retained, mobile layout, no browser errors');
})().catch(e=>{console.error(e);process.exit(1)});
