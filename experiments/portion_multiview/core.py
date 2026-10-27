"""Evaluation and crop handling for the isolated multi-view portion experiment."""
import hashlib
import numpy as np


def crop_region(box,score,width,height,threshold=.1):
    fallback=((0,0,width,height),False)
    if not np.isfinite([*box,score]).all() or score<threshold:return fallback
    cx,cy,w,h=box
    if w<=0 or h<=0:return fallback
    x1,y1=max(0,round((cx-w/2)*width)),max(0,round((cy-h/2)*height))
    x2,y2=min(width,round((cx+w/2)*width)),min(height,round((cy+h/2)*height))
    if x2-x1<max(3,.03*width) or y2-y1<max(3,.03*height):return fallback
    return (x1,y1,x2,y2),True


def heldout_ids(pool,previous,n):
    eligible=sorted(set(pool)-set(previous),key=lambda x:hashlib.sha256(f'42:{x}'.encode()).hexdigest())
    if len(eligible)<n:raise ValueError('Insufficient unused test examples')
    return eligible[:n]


def paired_improvement(truth,baseline,prediction,clusters,draws=2000):
    truth,baseline,prediction=map(lambda x:np.asarray(x,dtype=float),(truth,baseline,prediction))
    clusters=np.asarray(clusters);days=np.unique(clusters)
    difference=np.abs(baseline-truth)-np.abs(prediction-truth)
    totals=np.array([difference[clusters==day].sum() for day in days]);counts=np.array([(clusters==day).sum() for day in days])
    rng=np.random.default_rng(42);sample=rng.integers(0,len(days),size=(draws,len(days)))
    distribution=totals[sample].sum(1)/counts[sample].sum(1)
    return {'mae_reduction_g':float(difference.mean()),'capture_day_clusters':len(days),'cluster_bootstrap_95_interval_g':np.quantile(distribution,[.025,.975]).tolist(),'interpretation':'Positive reduction favors the candidate; capture-day bootstrap interval is exploratory.'}
