"""Small supervised portion experiment. Never imported by the production app."""
import argparse,csv,hashlib,io,json,os,time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import httpx,numpy as np
from PIL import Image
from experiments.portion_weight.core import load_records,choose_splits,food_priors,metrics,feature_signature

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data';OUTPUT=ROOT/'results';MODELS=ROOT/'models'
SOURCE='https://storage.googleapis.com/nutrition5k_dataset/nutrition5k_dataset/'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(counts):
    DATA.mkdir(exist_ok=True)
    for filename,remote in {
        'dish_metadata_cafe1.csv':'metadata/dish_metadata_cafe1.csv',
        'dish_metadata_cafe2.csv':'metadata/dish_metadata_cafe2.csv',
        'depth_train_ids.txt':'dish_ids/splits/depth_train_ids.txt',
        'depth_test_ids.txt':'dish_ids/splits/depth_test_ids.txt',
    }.items():
        path=DATA/filename
        if not path.exists():
            response=httpx.get(SOURCE+remote,timeout=60);response.raise_for_status()
            path.write_bytes(response.content)
    encoder_source=DATA/'encoder-source.json'
    if not encoder_source.exists():
        encoder_source.write_text(json.dumps({'model':'microsoft/resnet-18','revision':'65a5785d9156231087c481e0c7dd33a5ff6f7e3e','source':'https://huggingface.co/microsoft/resnet-18'},indent=2))
    records,excluded=load_records(DATA)
    inventory=DATA/'available-rgb-ids.json'
    if not inventory.exists():
        available=[];page=None
        while True:
            params={'prefix':'nutrition5k_dataset/imagery/realsense_overhead/','maxResults':1000,'fields':'items(name),nextPageToken'}
            if page:params['pageToken']=page
            response=httpx.get('https://storage.googleapis.com/storage/v1/b/nutrition5k_dataset/o',params=params,timeout=60)
            response.raise_for_status();listing=response.json()
            available.extend(item['name'].split('/')[-2] for item in listing.get('items',[]) if item['name'].endswith('/rgb.png'))
            page=listing.get('nextPageToken')
            if not page:break
        inventory.write_text(json.dumps(sorted(set(available))))
    available=set(json.loads(inventory.read_text()))
    unavailable=sorted(records.keys()-available)
    records={ident:record for ident,record in records.items() if ident in available}
    train_ids=(DATA/'depth_train_ids.txt').read_text().splitlines();test_ids=(DATA/'depth_test_ids.txt').read_text().splitlines()
    splits=choose_splits(records,train_ids,test_ids,counts)
    manifest={'dataset':'Nutrition5k','source':'https://github.com/google-research-datasets/Nutrition5k','license':'CC BY 4.0','seed':42,'splits':splits,'records':{i:records[i] for ids in splits.values() for i in ids},'excluded_metadata':excluded,'unavailable_rgb_ids':unavailable,'files':{p.name:digest(p) for p in DATA.glob('*.csv')}}
    OUTPUT.mkdir(exist_ok=True);MODELS.mkdir(exist_ok=True);(OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    images=DATA/'images';images.mkdir(exist_ok=True)
    ids=[i for group in splits.values() for i in group]
    transferred=0;completed=0
    def fetch(ident):
        path=images/(ident+'.jpg')
        if path.exists():
            with Image.open(path) as image:image.verify()
            return 0
        url=SOURCE+'imagery/realsense_overhead/'+ident+'/rgb.png'
        for attempt in range(3):
            try:
                r=httpx.get(url,timeout=30);r.raise_for_status()
                if len(r.content)>3_000_000:raise ValueError('Unexpected image size')
                image=Image.open(io.BytesIO(r.content)).convert('RGB')
                image.thumbnail((640,640));tmp=path.with_suffix('.part');image.save(tmp,format='JPEG',quality=95);tmp.replace(path)
                return len(r.content)
            except (httpx.HTTPError,OSError):
                if attempt==2:raise
        raise RuntimeError('Download failed')
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(fetch,ident):ident for ident in ids}
        for future in as_completed(futures):
            transferred+=future.result();completed+=1
            if transferred>600_000_000:raise RuntimeError('Pilot download budget exceeded')
            if completed%100==0 or completed==len(ids):print(f'Images {completed}/{len(ids)}; downloaded {transferred/1e6:.1f} MB',flush=True)
    manifest['downloaded_bytes_this_run']=transferred
    manifest['image_sha256']={ident:digest(images/(ident+'.jpg')) for ident in ids}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest


def encode(manifest):
    import torch
    from transformers import AutoImageProcessor,ResNetModel
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    info=json.loads((DATA/'encoder-source.json').read_text())
    ids=[ident for group in manifest['splits'].values() for ident in group]
    signature=feature_signature(info,ids,manifest['image_sha256'])
    cached=OUTPUT/'image-features.npz'
    if cached.exists():
        data=np.load(cached,allow_pickle=False)
        if str(data['signature'])==signature and np.array_equal(data['ids'],ids):return torch,data['features'],ids,info
    model=ResNetModel.from_pretrained(info['model'],revision=info['revision'],cache_dir=str(MODELS/'encoder'),token=False,use_safetensors=True)
    processor=AutoImageProcessor.from_pretrained(info['model'],revision=info['revision'],cache_dir=str(MODELS/'encoder'),token=False,use_fast=False)
    model.eval();model.requires_grad_(False)
    features=[]
    with torch.inference_mode():
        for start in range(0,len(ids),16):
            photos=[]
            for ident in ids[start:start+16]:
                with Image.open(DATA/'images'/(ident+'.jpg')) as photo:photos.append(photo.convert('RGB'))
            inputs=processor(images=photos,return_tensors='pt')
            features.append(model(**inputs).pooler_output.flatten(1).cpu().numpy())
            if (start//16)%5==0 or start+16>=len(ids):print(f'Frozen image features {min(start+16,len(ids))}/{len(ids)}',flush=True)
    features=np.concatenate(features)
    np.savez_compressed(cached,features=features,signature=signature,ids=np.asarray(ids))
    return torch,features,ids,info


def train(manifest,features,ids,torch,info):
    seed=42;torch.manual_seed(seed);rng=np.random.default_rng(seed)
    records=manifest['records'];splits=manifest['splits']
    priors,fallback=food_priors(records,splits['train'])
    vocabulary={ident:index+1 for index,ident in enumerate(sorted(priors))}
    image_index={ident:index for index,ident in enumerate(ids)}
    train_features=features[[image_index[i] for i in splits['train']]]
    mean=train_features.mean(0);std=train_features.std(0);std=np.maximum(std,.01)
    normalized=torch.tensor((features-mean)/std,dtype=torch.float32)
    def examples(group):
        rows=[]
        for ident in splits[group]:
            for food in records[ident]['ingredients']:
                rows.append({'dish':ident,'image_index':image_index[ident],'food':food['id'],'name':food['name'],'target':food['grams'],'food_index':vocabulary.get(food['id'],0),'baseline':priors.get(food['id'],fallback)})
        return rows
    datasets={group:examples(group) for group in splits}
    def tensors(rows):
        return (torch.tensor([r['image_index'] for r in rows]),torch.tensor([r['food_index'] for r in rows]),torch.tensor([np.log1p(r['baseline']) for r in rows],dtype=torch.float32),torch.tensor([np.log1p(r['target']) for r in rows],dtype=torch.float32))
    tensors_by_split={group:tensors(rows) for group,rows in datasets.items()}
    class PortionHead(torch.nn.Module):
        def __init__(self):
            super().__init__();self.food=torch.nn.Embedding(len(vocabulary)+1,16,padding_idx=0)
            self.net=torch.nn.Sequential(torch.nn.Linear(features.shape[1]+16,64),torch.nn.ReLU(),torch.nn.Dropout(.1),torch.nn.Linear(64,1))
            torch.nn.init.zeros_(self.net[-1].weight);torch.nn.init.zeros_(self.net[-1].bias)
        def forward(self,image,food,baseline):
            correction=self.net(torch.cat([image,self.food(food)],1)).flatten().clamp(-2.5,2.5)
            correction=correction*(food!=0)
            return baseline+correction
    model=PortionHead();optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    loss_fn=torch.nn.SmoothL1Loss()
    def predict(group):
        model.eval();ix,food,baseline,target=tensors_by_split[group]
        with torch.inference_mode():return torch.expm1(model(normalized[ix],food,baseline)).clamp_min(.01).numpy()
    validation_target=np.array([r['target'] for r in datasets['validation']])
    baseline_score=metrics(validation_target,[r['baseline'] for r in datasets['validation']])['mae_g']
    best=baseline_score;best_epoch=0;best_state={k:v.detach().clone() for k,v in model.state_dict().items()};history=[]
    train_ix,train_food,train_base,train_target=tensors_by_split['train']
    for epoch in range(1,201):
        model.train();loss_sum=0
        order=torch.tensor(rng.permutation(len(train_ix)))
        for selected in order.split(128):
            optimizer.zero_grad();prediction=model(normalized[train_ix[selected]],train_food[selected],train_base[selected]);loss=loss_fn(prediction,train_target[selected]);loss.backward();optimizer.step();loss_sum+=float(loss.detach())*len(selected)
        val=metrics(validation_target,predict('validation'))['mae_g']
        history.append({'epoch':epoch,'train_log_huber':loss_sum/len(train_ix),'validation_mae_g':val})
        if val<best-1e-5:
            best=val;best_epoch=epoch;best_state={k:v.detach().clone() for k,v in model.state_dict().items()}
        if epoch==1 or epoch%10==0:print(f'Epoch {epoch}; validation MAE {val:.2f} g; best {best:.2f} g at {best_epoch}',flush=True)
        if epoch-best_epoch>=30:break
    model.load_state_dict(best_state)
    from safetensors.torch import save_file
    save_file(model.state_dict(),str(MODELS/'portion-head.safetensors'))
    (MODELS/'portion-model.json').write_text(json.dumps({'architecture':'frozen ResNet18 + ingredient embedding16 + MLP64 residual log-mass head','encoder':info,'food_vocabulary':vocabulary,'training_median_grams':priors,'unknown_food_fallback_grams':fallback,'feature_mean':mean.tolist(),'feature_std':std.tolist(),'best_epoch':best_epoch,'experimental_only':True,'requires_known_ingredient_identity':True},indent=2))
    results={'encoder':info,'seed':seed,'counts':{g:{'dishes':len(splits[g]),'ingredients':len(rows)} for g,rows in datasets.items()},'selected_epoch':best_epoch,'epochs_run':len(history),'validation_selection':'minimum ingredient MAE in grams; untouched official test IDs evaluated after selection','uses_ground_truth_ingredient_identities':True,'uses_depth':False,'uses_side_views':False,'production_integration':False,'metrics':{}}
    for group in ['train','validation','test']:
        rows=datasets[group];truth=np.array([r['target'] for r in rows]);baseline=np.array([r['baseline'] for r in rows]);predictions=predict(group)
        dish_rows=[]
        for ident in splits[group]:
            indices=[i for i,r in enumerate(rows) if r['dish']==ident]
            dish_rows.append({'dish':ident,'truth':records[ident]['mass'],'baseline':float(baseline[indices].sum()),'predicted':float(predictions[indices].sum())})
        results['metrics'][group]={'baseline':metrics(truth,baseline),'trained':metrics(truth,predictions),'meal_sum_baseline':metrics([r['truth'] for r in dish_rows],[r['baseline'] for r in dish_rows]),'meal_sum_trained':metrics([r['truth'] for r in dish_rows],[r['predicted'] for r in dish_rows]),'unseen_ingredients':sum(r['food_index']==0 for r in rows)}
        with (OUTPUT/(group+'-predictions.csv')).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['dish','food','name','target','baseline','prediction','known_food'])
            writer.writeheader();writer.writerows({'dish':r['dish'],'food':r['food'],'name':r['name'],'target':r['target'],'baseline':r['baseline'],'prediction':float(p),'known_food':r['food_index']>0} for r,p in zip(rows,predictions))
        (OUTPUT/(group+'-dish-predictions.json')).write_text(json.dumps(dish_rows,indent=2))
    results['history']=history
    (OUTPUT/'metrics.json').write_text(json.dumps(results,indent=2))
    print('FINAL HELD-OUT TEST',json.dumps(results['metrics']['test']),flush=True)
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--train',type=int,default=600);parser.add_argument('--validation',type=int,default=120);parser.add_argument('--test',type=int,default=160);args=parser.parse_args()
    start=time.time();os.environ['HF_HUB_DISABLE_TELEMETRY']='1';os.environ['HF_HUB_DISABLE_XET']='1'
    manifest=prepare((args.train,args.validation,args.test));torch,features,ids,info=encode(manifest);results=train(manifest,features,ids,torch,info)
    print(f'Completed in {time.time()-start:.1f} seconds',flush=True)
