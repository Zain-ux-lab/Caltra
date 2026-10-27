export type Nutrients={calories:number|null;protein:number|null;carbs:number|null;fat:number|null;[key:string]:number|null|undefined};
export type Food={personalReference?:boolean;nutritionBasis?:'g'|'ml';retailer?:string;isAiEstimate?:boolean;brand?:string;barcode?:string;packGrams?:number;sourceWarning?:string;id:string;name:string;source:string;dataType:string;url:string;retrievedAt:string;nutrients:Nutrients;portions:{label:string;grams:number;unit?:string}[]};
export type Item={quantityBasis?:'photo'|'user'|'assumed';portionEvidence?:string;usingUsualProduct?:boolean;label?:string;clarification?:string;id:string;food:Food;grams:number;quantityKind:'estimated'|'measured';portionLabel:string};
export type Meal={mealType?:'breakfast'|'lunch'|'dinner'|'snacks'|'unassigned';homemade?:boolean;id:string;name:string;date:string;items:Item[];notes:string;totals:Record<string,number>};
export type Status={visionConfigured:boolean;visionModel:string;usdaConfigured:boolean;chatConfigured:boolean;cachedFoods:number};
export async function api<T>(url:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api'+url,options);
 const data=await response.json();
 if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'Please check your entries and try again.');
 return data;
}
export const json=(value:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export function totals(items:Item[]){return items.reduce((sum,item)=>{for(const key of ['calories','protein','carbs','fat'] as const)sum[key]+=(item.food.nutrients[key]??0)*item.grams/100;return sum;},{calories:0,protein:0,carbs:0,fat:0});}
export function today(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
export type Favorite={id:string;name:string;items:Item[];totals:Record<string,number>;observation:string};
