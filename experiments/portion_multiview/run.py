"""Local paired-view research pilot; never imported by Caltra's production app."""
import csv,hashlib,io,json,os,subprocess,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import httpx,numpy as np
from PIL import Image,ImageDraw
from experiments.portion_weight.core import load_records,food_priors,metrics,capture_day,feature_signature
from experiments.portion_multiview.core import crop_region,heldout_ids,paired_improvement

ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'portion_weight'
DATA=ROOT/'data';OUT=ROOT/'results';MODELS=ROOT/'models'
DETECTOR={'model':'google/owlvit-base-patch32','revision':'cbc355fb364588351c5d51c7f74465e8e7ec6f72'}
SOURCE='https://storage.googleapis.com/nutrition5k_dataset/nutrition5k_dataset/'
VARIANTS=['food_only','overhead','paired_whole','paired_localized']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    for path in [DATA,OUT,MODELS]:path.mkdir(exist_ok=True)
    prior=json.loads((OLD/'results/manifest.json').read_text());records,excluded=load_records(OLD/'data')
    available=set(json.loads((OLD/'data/available-rgb-ids.json').read_text()))
    official=set((OLD/'data/depth_test_ids.txt').read_text().splitlines())
    splits={'train':prior['splits']['train'],'validation':prior['splits']['validation'],'test':heldout_ids(official&available&records.keys(),prior['splits']['test'],160)}
    assert len(set(sum(splits.values(),[])))==880
    assert not {capture_day(i) for i in splits['train']}&{capture_day(i) for i in splits['validation']}
    manifest={'source':prior['source'],'license':prior['license'],'splits':splits,'records':{i:records[i] for group in splits.values() for i in group},'previous_test_excluded':prior['splits']['test'],'protocol_sha256':sha(ROOT/'PROTOCOL.md'),'detector':DETECTOR,'encoder':json.loads((OLD/'data/encoder-source.json').read_text()),'excluded_metadata_count':len(excluded),'missing_side':[]}
    lock=threading.Lock();transferred=0
    def get(url,cap,range_request=False):
        nonlocal transferred
        with httpx.stream('GET',url,headers={'Range':f'bytes=0-{cap-1}'} if range_request else {},timeout=45,follow_redirects=True) as response:
            response.raise_for_status()
            if range_request and response.status_code!=206:raise ValueError('Server ignored bounded video range')
            content=bytearray()
            for chunk in response.iter_bytes():
                with lock:
                    transferred+=len(chunk)
                    if transferred>800_000_000:raise ValueError('Public-image download budget exceeded')
                content.extend(chunk)
                if len(content)>cap:raise ValueError('Public object exceeds request bound')
            return bytes(content)
    def fetch(ident):
        overhead=OLD/'data/images'/(ident+'.jpg')
        if not overhead.exists():
            raw=get(SOURCE+'imagery/realsense_overhead/'+ident+'/rgb.png',3_000_000)
            image=Image.open(io.BytesIO(raw)).convert('RGB');image.thumbnail((640,640));image.save(overhead,quality=95)
        side=DATA/(ident+'-side.jpg')
        if side.exists():
            with Image.open(side) as image:image.verify()
            return ident,None
        for cap in [524288,2097152]:
            try:raw=get(SOURCE+'imagery/side_angles/'+ident+'/camera_A.h264',cap,True)
            except httpx.HTTPStatusError as error:
                if error.response.status_code==404:return ident,'camera A unavailable'
                raise
            decoded=subprocess.run(['ffmpeg','-v','error','-f','h264','-i','pipe:0','-frames:v','1','-f','image2pipe','-vcodec','mjpeg','pipe:1'],input=raw,capture_output=True,timeout=30)
            try:
                image=Image.open(io.BytesIO(decoded.stdout)).convert('RGB');image.thumbnail((640,640));image.save(side,quality=95)
                return ident,None
            except OSError:pass
        return ident,'first frame could not be decoded within 2 MiB'
    ids=sum(splits.values(),[])
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(fetch,i) for i in ids]
        for n,future in enumerate(as_completed(futures),1):
            ident,reason=future.result()
            if reason:manifest['missing_side'].append({'id':ident,'reason':reason})
            if n%100==0 or n==len(ids):print(f'Paired images {n}/{len(ids)}; fetched {transferred/1e6:.1f} MB',flush=True)
    missing={r['id'] for r in manifest['missing_side']}
    manifest['splits']={g:[i for i in group if i not in missing] for g,group in splits.items()}
    manifest['image_hashes']={i:{'overhead':sha(OLD/'data/images'/(i+'.jpg')),'side':sha(DATA/(i+'-side.jpg'))} for i in ids if i not in missing}
    manifest['downloaded_bytes_this_run']=transferred
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def extract(manifest):
    import torch
    from transformers import OwlViTProcessor,OwlViTForObjectDetection,AutoImageProcessor,ResNetModel
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    ids=sum(manifest['splits'].values(),[])
    rows=[{'dish':i,'food':f['id'],'name':f['name'],'target':f['grams']} for i in ids for f in manifest['records'][i]['ingredients']]
    signature=feature_signature([manifest['encoder'],DETECTOR,sha(Path(__file__))],[(r['dish'],r['food'],r['name']) for r in rows],manifest['image_hashes'])
    cache=OUT/'features.npz';boxes_file=OUT/'boxes.json'
    if cache.exists() and boxes_file.exists():
        cached=np.load(cache,allow_pickle=False)
        if str(cached['signature'])==signature:return torch,rows,{key:cached[key] for key in ['overhead','side','crop_overhead','crop_side','geometry']}
    det=OwlViTForObjectDetection.from_pretrained(**{'pretrained_model_name_or_path':DETECTOR['model'],'revision':DETECTOR['revision']},cache_dir=str(OLD/'models/detector'),token=False,use_safetensors=True,local_files_only=True).eval().to(device)
    dp=OwlViTProcessor.from_pretrained(DETECTOR['model'],revision=DETECTOR['revision'],cache_dir=str(OLD/'models/detector'),token=False,use_fast=False,local_files_only=True)
    enc=ResNetModel.from_pretrained(manifest['encoder']['model'],revision=manifest['encoder']['revision'],cache_dir=str(OLD/'models/encoder'),token=False,use_safetensors=True,local_files_only=True).eval().to(device)
    ep=AutoImageProcessor.from_pretrained(manifest['encoder']['model'],revision=manifest['encoder']['revision'],cache_dir=str(OLD/'models/encoder'),token=False,use_fast=False,local_files_only=True)
    det.requires_grad_(False);enc.requires_grad_(False)
    arrays={key:[] for key in ['overhead','side','crop_overhead','crop_side','geometry']};boxes=[]
    def encode(photos):
        parts=[]
        for start in range(0,len(photos),16):
            inputs=ep(images=photos[start:start+16],return_tensors='pt').to(device)
            with torch.inference_mode():parts.append(enc(**inputs).pooler_output.flatten(1).cpu().numpy())
        return np.concatenate(parts)
    print(f'Extracting frozen detector/crop features on {device}',flush=True)
    for number,ident in enumerate(ids):
        foods=manifest['records'][ident]['ingredients'];n=len(foods)
        photos=[Image.open(OLD/'data/images'/(ident+'.jpg')).convert('RGB'),Image.open(DATA/(ident+'-side.jpg')).convert('RGB')]
        whole=encode(photos);geometry=[];food_boxes=[];crop_features=[]
        for view,image in enumerate(photos):
            inputs=dp(images=image,text=[['a photo of '+f['name'] for f in foods]],return_tensors='pt').to(device)
            with torch.inference_mode():output=det(**inputs)
            scores=output.logits.sigmoid()[0].cpu();pred_boxes=output.pred_boxes[0].cpu()
            crops=[];geom=[];view_boxes=[]
            for j,food in enumerate(foods):
                best=int(scores[:,j].argmax());score=float(scores[best,j]);box,accepted=crop_region(pred_boxes[best].tolist(),score,image.width,image.height)
                crops.append(image.crop(box));x1,y1,x2,y2=box
                geom.append([x1/image.width,y1/image.height,x2/image.width,y2/image.height,float(accepted)])
                view_boxes.append({'food':food['id'],'name':food['name'],'box':box,'accepted':accepted,'score':score})
            geometry.append(np.asarray(geom));food_boxes.append(view_boxes);crop_features.append(encode(crops))
        arrays['overhead'].extend([whole[0]]*n);arrays['side'].extend([whole[1]]*n)
        arrays['crop_overhead'].extend(crop_features[0]);arrays['crop_side'].extend(crop_features[1]);arrays['geometry'].extend(np.concatenate(geometry,axis=1))
        boxes.append({'dish':ident,'views':food_boxes})
        # Fixed training examples only; overlays are qualitative, not ground-truth masks.
        if number<6:
            for view,image in enumerate(photos):
                draw=ImageDraw.Draw(image)
                for b in food_boxes[view]:
                    if b['accepted']:draw.rectangle(b['box'],outline='red',width=2);draw.text(b['box'][:2],b['name'],fill='red')
                image.save(OUT/f'example-{number}-{view}.jpg')
        if (number+1)%40==0 or number+1==len(ids):
            print(f'Localized paired features {number+1}/{len(ids)}',flush=True)
    arrays={key:np.asarray(value,dtype=np.float32) for key,value in arrays.items()}
    np.savez_compressed(cache,signature=signature,**arrays);boxes_file.write_text(json.dumps(boxes,indent=2))
    return torch,rows,arrays


def fit_and_evaluate(manifest,torch,rows,features):
    from safetensors.torch import save_file,load_file
    torch.set_num_threads(4)
    train_ids=manifest['splits']['train'];priors,fallback=food_priors(manifest['records'],train_ids)
    vocab={food:n+1 for n,food in enumerate(sorted(priors))};groups={g:np.array([j for j,r in enumerate(rows) if r['dish'] in set(ids)]) for g,ids in manifest['splits'].items()}
    true=np.array([r['target'] for r in rows]);baseline=np.array([priors.get(r['food'],fallback) for r in rows])
    food=torch.tensor([vocab.get(r['food'],0) for r in rows]);base=torch.tensor(np.log1p(baseline),dtype=torch.float32);target=torch.tensor(true,dtype=torch.float32)
    class Head(torch.nn.Module):
        def __init__(self,width):
            super().__init__();self.food=torch.nn.Embedding(len(vocab)+1,16,padding_idx=0)
            self.net=torch.nn.Sequential(torch.nn.Linear(width+16,64),torch.nn.ReLU(),torch.nn.Dropout(.2),torch.nn.Linear(64,1))
            torch.nn.init.zeros_(self.net[-1].weight);torch.nn.init.zeros_(self.net[-1].bias)
        def forward(self,x,food,base):
            delta=self.net(torch.cat([x,self.food(food)],1)).flatten().clamp(-2.5,2.5)*(food!=0)
            return torch.expm1(base+delta).clamp_min(.01)
    values={};histories={};checkpoints={}
    for variant in VARIANTS:
        torch.manual_seed(42);rng=np.random.default_rng(42)
        if variant=='food_only':x=np.zeros((len(rows),1034),dtype=np.float32)
        elif variant=='overhead':x=np.concatenate([features['overhead'],np.zeros((len(rows),522),dtype=np.float32)],axis=1)
        elif variant=='paired_whole':x=np.concatenate([features['overhead'],features['side'],np.zeros((len(rows),10),dtype=np.float32)],axis=1)
        else:x=np.concatenate([features['crop_overhead'],features['crop_side'],features['geometry']],axis=1)
        mean=x[groups['train']].mean(0);std=np.maximum(x[groups['train']].std(0),.01);x=torch.tensor((x-mean)/std,dtype=torch.float32)
        model=Head(x.shape[1]);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
        best=metrics(true[groups['validation']],baseline[groups['validation']])['mae_g'];epoch_best=0;state={k:v.detach().clone() for k,v in model.state_dict().items()};history=[]
        def predict(indices):
            model.eval()
            with torch.inference_mode():return model(x[indices],food[indices],base[indices]).numpy()
        for epoch in range(1,201):
            model.train()
            for selected in np.array_split(rng.permutation(groups['train']),max(1,int(np.ceil(len(groups['train'])/128)))):
                optimizer.zero_grad();p=model(x[selected],food[selected],base[selected]);loss=torch.nn.functional.smooth_l1_loss(p/50,target[selected]/50,beta=.2);loss.backward();optimizer.step()
            score=metrics(true[groups['validation']],predict(groups['validation']))['mae_g'];history.append({'epoch':epoch,'validation_mae_g':score})
            if score<best-1e-5:best=score;epoch_best=epoch;state={k:v.detach().clone() for k,v in model.state_dict().items()}
            if epoch==1 or epoch%20==0:print(f'{variant}: epoch {epoch}, validation MAE {score:.2f} g, best {best:.2f} at {epoch_best}',flush=True)
            if epoch-epoch_best>=30:break
        model.load_state_dict(state);save_file(model.state_dict(),str(MODELS/(variant+'.safetensors')))
        metadata={'variant':variant,'input_width':x.shape[1],'food_vocabulary':vocab,'priors':priors,'fallback':fallback,'mean':mean.tolist(),'std':std.tolist(),'selected_epoch':epoch_best,'validation_mae_g':best,'dropout':.2,'experimental_only':True,'protocol_sha256':manifest['protocol_sha256']}
        (MODELS/(variant+'.json')).write_text(json.dumps(metadata,indent=2))
        checkpoints[variant]={'metadata':metadata,'features':x};histories[variant]=history
    print('All four validation-selected checkpoints saved. Evaluating new test split now.',flush=True)
    # Reload saved checkpoints before evaluating; verify artifact inference rather than transient training state.
    for variant,item in checkpoints.items():
        model=Head(item['metadata']['input_width']);model.load_state_dict(load_file(str(MODELS/(variant+'.safetensors'))));model.eval()
        with torch.inference_mode():values[variant]=model(item['features'],food,base).numpy()
    values['median_baseline']=baseline
    # Frozen first experiment on identical new test examples, for context rather than matched ablation.
    old_meta=json.loads((OLD/'models/portion-model.json').read_text());old_vocab=old_meta['food_vocabulary']
    old_food=torch.tensor([old_vocab.get(r['food'],0) for r in rows]);old_base=torch.tensor([np.log1p(old_meta['training_median_grams'].get(r['food'],old_meta['unknown_food_fallback_grams'])) for r in rows],dtype=torch.float32)
    class OldHead(torch.nn.Module):
        def __init__(self):
            super().__init__();self.food=torch.nn.Embedding(len(old_vocab)+1,16,padding_idx=0);self.net=torch.nn.Sequential(torch.nn.Linear(528,64),torch.nn.ReLU(),torch.nn.Dropout(.1),torch.nn.Linear(64,1))
        def forward(self,image):return torch.expm1(old_base+self.net(torch.cat([image,self.food(old_food)],1)).flatten().clamp(-2.5,2.5)*(old_food!=0)).clamp_min(.01)
    old=OldHead();old.load_state_dict(load_file(str(OLD/'models/portion-head.safetensors')));old.eval()
    x=torch.tensor((features['overhead']-np.asarray(old_meta['feature_mean']))/np.asarray(old_meta['feature_std']),dtype=torch.float32)
    with torch.inference_mode():values['previous_model']=old(x).numpy()
    results={'protocol_sha256':manifest['protocol_sha256'],'uses_ground_truth_food_identities':True,'production_integration':False,'seed':42,'counts':{g:{'dishes':len(manifest['splits'][g]),'ingredients':len(indices)} for g,indices in groups.items()},'history':histories,'selected_checkpoints':{v:{'epoch':c['metadata']['selected_epoch'],'validation_mae_g':c['metadata']['validation_mae_g']} for v,c in checkpoints.items()},'metrics':{}}
    for group,indices in groups.items():
        results['metrics'][group]={}
        for name,predictions in values.items():
            dish_rows=[{'dish':i,'truth':manifest['records'][i]['mass'],'predicted':float(predictions[[j for j in indices if rows[j]['dish']==i]].sum())} for i in manifest['splits'][group]]
            results['metrics'][group][name]={'ingredient':metrics(true[indices],predictions[indices]),'meal':metrics([r['truth'] for r in dish_rows],[r['predicted'] for r in dish_rows])}
            if group=='test':(OUT/(name+'-test-meals.json')).write_text(json.dumps(dish_rows,indent=2))
    test=groups['test'];clusters=[capture_day(rows[j]['dish']) for j in test]
    results['paired_comparisons']={}
    for candidate,reference in [('overhead','food_only'),('paired_whole','overhead'),('paired_localized','paired_whole'),('paired_localized','median_baseline')]:
        results['paired_comparisons'][candidate+'_vs_'+reference]=paired_improvement(true[test],values[reference][test],values[candidate][test],clusters)
    results['localization']={g:{'overhead_accepted_percent':float(100*features['geometry'][ix,4].mean()),'side_accepted_percent':float(100*features['geometry'][ix,9].mean()),'unseen_food_portions':int((food[ix]==0).sum())} for g,ix in groups.items()}
    with (OUT/'test-predictions.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['dish','food','name','target',*values.keys()]);writer.writeheader()
        writer.writerows({**rows[j],**{name:float(p[j]) for name,p in values.items()}} for j in test)
    (OUT/'metrics.json').write_text(json.dumps(results,indent=2));print('FINAL',json.dumps({'test':results['metrics']['test'],'paired_comparisons':results['paired_comparisons'],'localization':results['localization']['test']}),flush=True)
    return results


if __name__=='__main__':
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1';os.environ['HF_HUB_DISABLE_XET']='1';start=time.time()
    manifest=prepare();torch,rows,features=extract(manifest);fit_and_evaluate(manifest,torch,rows,features)
    print(f'Completed in {time.time()-start:.1f} seconds',flush=True)
