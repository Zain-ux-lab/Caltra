"""Leakage-conscious data and metrics for the experimental portion-weight pilot."""
import csv,hashlib,json,math
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np


def feature_signature(encoder,ids,image_hashes):
    return hashlib.sha256(json.dumps([encoder,ids,image_hashes],sort_keys=True).encode()).hexdigest()


def parse_row(row):
    if len(row)<13:raise ValueError('Incomplete dish row')
    mass=float(row[2])
    if not math.isfinite(mass) or mass<=0:raise ValueError('Invalid dish mass')
    start=6 if row[6].startswith('ingr_') else 7
    if (len(row)-start)%7:raise ValueError('Unexpected ingredient layout')
    ingredients={}
    for pos in range(start,len(row),7):
        ident,name,grams=row[pos:pos+3];grams=float(grams)
        if not ident.startswith('ingr_') or not math.isfinite(grams) or grams<0:raise ValueError('Invalid ingredient')
        if grams==0:continue
        previous=ingredients.get(ident,{'grams':0})
        ingredients[ident]={'id':ident,'name':name,'grams':previous['grams']+grams}
    if not ingredients or abs(sum(x['grams'] for x in ingredients.values())-mass)>max(.1,mass*.005):raise ValueError('Ingredient and dish masses disagree')
    return {'id':row[0],'mass':mass,'ingredients':list(ingredients.values())}


def load_records(root):
    records={};excluded=[]
    for filename in ['dish_metadata_cafe1.csv','dish_metadata_cafe2.csv']:
        for row in csv.reader((Path(root)/filename).open()):
            try:record=parse_row(row)
            except (ValueError,IndexError) as e:
                excluded.append({'id':row[0] if row else '', 'reason':str(e)});continue
            if record['id'] in records:raise ValueError('Duplicate dish ID')
            records[record['id']]=record
    return records,excluded


def capture_day(ident):
    return datetime.fromtimestamp(int(ident.split('_')[1]),timezone.utc).date().isoformat()


def choose_splits(records,train_ids,test_ids,counts=(600,120,160),seed=42):
    train_ids=set(train_ids);test_ids=set(test_ids)
    if train_ids&test_ids:raise ValueError('Official train/test overlap')
    order=lambda ident:hashlib.sha256(f'{seed}:{ident}'.encode()).hexdigest()
    days=sorted({capture_day(i) for i in train_ids&records.keys()},key=order)
    if len(days)<3:raise ValueError('Need separate capture days for validation')
    val_days=set(days[:max(1,len(days)//5)])
    pools=[sorted([i for i in train_ids&records.keys() if capture_day(i) not in val_days],key=order),sorted([i for i in train_ids&records.keys() if capture_day(i) in val_days],key=order),sorted(test_ids&records.keys(),key=order)]
    if any(len(pool)<n for pool,n in zip(pools,counts)):raise ValueError('Insufficient examples for requested split')
    splits={name:pool[:n] for name,pool,n in zip(['train','validation','test'],pools,counts)}
    assert not set(splits['train'])&set(splits['test'])
    assert not {capture_day(i) for i in splits['train']}&{capture_day(i) for i in splits['validation']}
    return splits


def metrics(truth,predictions):
    truth=np.asarray(truth,dtype=float);predictions=np.asarray(predictions,dtype=float)
    if truth.shape!=predictions.shape or truth.size==0 or np.any(truth<=0) or not np.isfinite(predictions).all():raise ValueError('Invalid metric inputs')
    error=predictions-truth;absolute=np.abs(error)
    large=truth>=10
    return {'count':int(truth.size),'mae_g':float(absolute.mean()),'rmse_g':float(np.sqrt((error**2).mean())),'bias_g':float(error.mean()),'wape_percent':float(100*absolute.sum()/truth.sum()),'median_ape_percent':float(np.median(100*absolute/truth)),'within_20_percent':float(100*(absolute/truth<=.2).mean()),'mae_at_least_10g':float(absolute[large].mean()) if large.any() else None,'count_at_least_10g':int(large.sum())}


def food_priors(records,ids):
    values=defaultdict(list)
    for ident in ids:
        for food in records[ident]['ingredients']:values[food['id']].append(food['grams'])
    fallback=float(np.median([x for portions in values.values() for x in portions]))
    return {ident:float(np.median(portions)) for ident,portions in values.items()},fallback
