import {useState} from 'react';
import {Food,api,json} from './api';

export type Chain={brand:string;url:string};
type Props={query:string;chain:Chain|null;onSaved:(food:Food)=>void};
const fields=[['calories','Calories (kcal)'],['protein','Protein (g)'],['carbs','Carbohydrate (g)'],['fat','Fat (g)'],['sugars','Sugars (g)'],['saturates','Saturates (g)'],['fibre','Fibre (g)'],['salt','Salt (g)']] as const;

// The query minus the chain's own words, e.g. "Bills pancakes" -> "pancakes".
function itemWords(query:string,chain:Chain|null){
 const brand=new Set((chain?.brand||'').toLowerCase().replace(/['’]/g,'').split(/\s+/));
 return query.split(/\s+/).filter(word=>!brand.has(word.toLowerCase().replace(/['’]/g,''))).join(' ');
}

export default function FindItYourself({query,chain,onSaved}:Props){
 const item=itemWords(query,chain);
 const [open,setOpen]=useState(false),[name,setName]=useState(item),[brand,setBrand]=useState(chain?.brand||''),[values,setValues]=useState<Record<string,string>>({}),[busy,setBusy]=useState(false),[error,setError]=useState('');
 // A text fragment scrolls an HTML page to the item's first mention; PDFs and other pages ignore it.
 const officialUrl=chain&&(item?`${chain.url}#:~:text=${encodeURIComponent(item)}`:chain.url);
 const googleUrl='https://www.google.com/search?q='+encodeURIComponent(`${query} nutrition calories protein UK`);
 async function save(){
  setBusy(true);setError('');
  try{
   const nutrients=Object.fromEntries(fields.map(([key])=>[key,values[key]?.trim()?Number(values[key]):null]));
   onSaved(await api<Food>('/products',json({name,brand,nutritionBasis:'serving',nutrients})));
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <div className="find-yourself"><h3>Not on Caltra?</h3><p className="muted">Look up the published values, then add them here. Caltra remembers your entry for next time.</p>
  <div className="find-links">{chain&&officialUrl&&<a className="secondary" href={officialUrl} target="_blank" rel="noreferrer">{chain.brand} nutrition ↗</a>}<a className="secondary" href={googleUrl} target="_blank" rel="noreferrer">Search Google ↗</a><button className="text-button" onClick={()=>setOpen(!open)}>{open?'Close':'Enter it yourself'}</button></div>
  {open&&<form className="label-form" onSubmit={e=>{e.preventDefault();void save()}}><p className="muted">Copy the values for one menu serving. Leave the optional ones blank if they aren't listed.</p><label>Item name<input aria-label="Menu item name" value={name} maxLength={100} required onChange={e=>setName(e.target.value)}/></label><label>Restaurant or brand<input aria-label="Restaurant or brand" value={brand} maxLength={80} required onChange={e=>setBrand(e.target.value)}/></label><div className="label-nutrients">{fields.map(([key,label],index)=><label key={key}>{label}{index>3?' (optional)':''}<input aria-label={'Menu '+key} type="number" min="0" max={key==='calories'?5000:500} step="any" required={index<4} value={values[key]||''} onChange={e=>setValues({...values,[key]:e.target.value})}/></label>)}</div>{error&&<p className="error" role="alert">{error}</p>}<button className="primary wide" disabled={busy}>{busy?'Saving…':'Save and add to meal'}</button></form>}
 </div>
}
