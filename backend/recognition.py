"""Local specialist classifiers; dish suggestions only, never nutrient or mass predictions."""
import io
import threading
import time
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError

ROOT=Path(__file__).resolve().parent.parent
MODEL_INFO={
    'indian':{'name':'Indian food · 20 categories','repo':'Subhash5/indian-food-classifier','revision':'fac307381c6f2025ebbb79ee1fb1650f89a4c80c'},
    'food':{'name':'General food · 101 categories','repo':'nateraw/food','revision':'8991abd49ea01ebf502aeda51d4f12a59c603e01'},
}
_lock=threading.Lock()
_current=None
_model=None
_processor=None
_last_error=None
Image.MAX_IMAGE_PIXELS=25_000_000


def decode_image(data):
    if len(data)>10*1024*1024: raise ValueError('Image must be under 10 MB.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'JPEG','MPO','PNG','WEBP'}: raise ValueError('Use a JPEG, PNG or WebP image.')
            # Phone multi-picture JPEGs carry auxiliary frames; use the main photo.
            image.seek(0)
            image.load()
            result=ImageOps.exif_transpose(image).convert('RGB')
            result.thumbnail((1600,1600))
            result.info.clear()
            return result
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise ValueError('This image could not be read. Use a JPEG, PNG or WebP under 10 MB.')


def status():
    return {key:{**info,'downloaded':(ROOT/'models'/key/'config.json').exists() and any((ROOT/'models'/key/f).exists() for f in ['model.safetensors','pytorch_model.bin']), 'loaded':_current==key} for key,info in MODEL_INFO.items()}


def recognize(data, kind='indian'):
    global _current,_model,_processor,_last_error
    image=decode_image(data)
    if kind not in MODEL_INFO: raise ValueError('Unknown model.')
    path=ROOT/'models'/kind
    if not status()[kind]['downloaded']: raise RuntimeError('This food model is not installed. Run the model setup script or use food search.')
    started=time.monotonic()
    with _lock:
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification
        torch.set_num_threads(4)
        if _current!=kind:
            _model=None
            _processor=None
            _current=None
            import gc
            gc.collect()
            _processor=AutoImageProcessor.from_pretrained(str(path),local_files_only=True,use_fast=False,trust_remote_code=False)
            _model=AutoModelForImageClassification.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,weights_only=True)
            _model.eval()
            _current=kind
        with torch.inference_mode():
            logits=_model(**_processor(images=image,return_tensors='pt')).logits
            scores,labels=logits.softmax(-1)[0].topk(3)
        candidates=[{'label':_model.config.id2label[int(label)].replace('_',' '),'score':round(float(score),4)} for score,label in zip(scores,labels)]
        category=broad_category(image) if kind=='food' and (ROOT/'models'/'category'/'pytorch_model.bin').exists() else None
        result=reconcile_predictions(candidates,category) if category else {'candidates':candidates,'categoryOnly':False,'notice':'Dish suggestions only; exact identity and portion are unverified.'}
    return {**result,'category':category,'model':MODEL_INFO[kind]['name'],'seconds':round(time.monotonic()-started,2)}


DESSERT_LABELS={'apple pie','baklava','beignets','bread pudding','cannoli','carrot cake','cheesecake','chocolate cake','chocolate mousse','churros','creme brulee','cup cakes','donuts','frozen yogurt','ice cream','macarons','pancakes','panna cotta','red velvet cake','strawberry shortcake','tiramisu','waffles'}
_category_model=None
_category_processor=None


def reconcile_predictions(candidates,category):
    top=candidates[0]['label']
    # This is disagreement between two classifiers, not calibrated out-of-domain
    # detection. Withhold the specific guess instead of presenting either as certain.
    conflict=(category['label']=='dessert' and top not in DESSERT_LABELS) or (top in DESSERT_LABELS and category['label'] in {'seafood','meat','noodles','rice','soup','vegetable','egg'})
    if conflict:
        return {'candidates':[category],'categoryOnly':True,'notice':'The recognition models disagree about the dish. Only a broad category is suggested. Enter the food name to find a source record; the exact product is not identified.'}
    return {'candidates':candidates,'categoryOnly':False,'notice':'Dish suggestions only. This model does not measure portions or detect hidden oil. None of these may be correct.'}


def broad_category(image):
    global _category_model,_category_processor
    import torch
    from transformers import AutoImageProcessor,AutoModelForImageClassification
    path=ROOT/'models'/'category'
    if _category_model is None:
        _category_processor=AutoImageProcessor.from_pretrained(str(path),local_files_only=True,use_fast=False,trust_remote_code=False)
        _category_model=AutoModelForImageClassification.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,weights_only=True).eval()
    with torch.inference_mode():
        probabilities=_category_model(**_category_processor(images=image,return_tensors='pt')).logits.softmax(-1)[0]
        index=int(probabilities.argmax())
    return {'label':_category_model.config.id2label[index].lower(),'score':round(float(probabilities[index]),4)}
