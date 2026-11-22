import {useRef,useState} from 'react';
import {ScanBarcode} from 'lucide-react';

async function readBarcode(file:File):Promise<string>{
 let values:string[];
 try{
  // Loaded on first scan: Safari has no native BarcodeDetector, so this ships a WebAssembly reader.
  const {BarcodeDetector}=await import('barcode-detector/ponyfill');
  const bitmap=await createImageBitmap(file);
  try{values=(await new BarcodeDetector({formats:['ean_13','ean_8','upc_a','upc_e']}).detect(bitmap)).map(b=>b.rawValue)}
  finally{bitmap.close()}
 }catch{throw new Error('Barcode reading isn’t available right now. Type the number under the barcode instead.')}
 const code=values.find(v=>/^\d{8,14}$/.test(v));
 if(!code)throw new Error('No product barcode found. Try a closer, well-lit photo of just the barcode.');
 return code;
}

export function BarcodeScanButton({onCode,onError,disabled}:{onCode:(code:string)=>void;onError:(message:string)=>void;disabled?:boolean}){
 const input=useRef<HTMLInputElement>(null),[reading,setReading]=useState(false);
 return <>
  <button type="button" className="secondary scan-button" disabled={disabled||reading} onClick={()=>input.current?.click()}><ScanBarcode size={16}/>{reading?'Reading…':'Scan barcode'}</button>
  <input ref={input} hidden type="file" accept="image/*" capture="environment" aria-label="Photograph a product barcode" onChange={async e=>{
   const file=e.target.files?.[0];e.target.value='';
   if(!file)return;
   setReading(true);
   try{onCode(await readBarcode(file))}catch(err){onError((err as Error).message)}finally{setReading(false)}
  }}/>
 </>;
}
