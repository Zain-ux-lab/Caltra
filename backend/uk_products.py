"""UK-market branded labels from Open Food Facts; community data, not verified labels."""
import math,re,time,threading
from collections import deque
from datetime import datetime,timezone
import httpx
from .search import search_foods

_cache={};_calls=deque();_lock=threading.Lock()


def normalize_product(product):
    if 'en:united-kingdom' not in (product.get('countries_tags') or []):return None
    brand=product.get('brands') or ''
    if isinstance(brand,list):brand=', '.join(str(x) for x in brand)
    name=product.get('product_name') or ''
    code=str(product.get('code') or '')
    quantity=product.get('quantity') or ''
    if not isinstance(name,str) or not isinstance(brand,str) or not isinstance(quantity,str):return None
    counted=re.fullmatch(r'\s*([1-9]\d{0,2})\s+(wraps|tortillas|fillets|slices|pieces)\s+(\d+(?:\.\d+)?)\s*(kg|g)\s*',quantity,re.I)
    mass=f'{counted[3]}{counted[4]}' if counted else quantity
    multipack=re.fullmatch(r'\s*([1-9]\d{0,2})\s*[x×]\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\s*',mass,re.I)
    if multipack:mass=f'{int(multipack[1])*float(multipack[2]):g}{multipack[3]}'
    pack=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l|litre|litres)\s*[e℮]?\s*',mass,re.I)
    # Pack size is optional; liquid records still require an explicit per-100-ml basis.
    if not name or not brand or not re.fullmatch(r'\d{8,14}',code):return None
    unit=pack[2].lower() if pack else str(product.get('product_quantity_unit') or '').lower()
    basis='ml' if unit in {'ml','l','litre','litres'} or product.get('nutrition_data_per')=='100ml' else 'g'
    if basis=='ml' and product.get('nutrition_data_per')!='100ml':return None
    grams=float(pack[1])*(1000 if unit in {'kg','l','litre','litres'} else 1) if pack else None
    n=product.get('nutriments') or {}
    values={k:n.get(key+'_100g') for k,key in [('calories','energy-kcal'),('protein','proteins'),('carbs','carbohydrates'),('fat','fat')]}
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in values.values()):return None
    if (grams is not None and not 0<grams<=100000) or any(values[k]>100 for k in ['protein','carbs','fat']):return None
    energy=4*(values['protein']+values['carbs'])+9*values['fat']
    # Reject obvious transcription/unit errors; this is not label verification.
    if energy and not .55*energy<=values['calories']<=1.6*energy:return None
    for key,off_key in [('fibre','fiber'),('sugars','sugars'),('saturates','saturated-fat'),('salt','salt')]:
        v=n.get(off_key+'_100g');values[key]=v if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0<=v<=100 else None
    portions=[{'label':'1 pack','grams':grams,'unit':basis}] if grams else []
    if counted and grams:portions.append({'label':'1 '+counted[2].lower().rstrip('s'),'grams':grams/int(counted[1]),'unit':basis})
    aliases=['high protein'] if 'en:high-proteins' in (product.get('labels_tags') or []) else []
    return {'id':'off:'+code,'name':f'{brand} · {name}'+(f' ({quantity})' if quantity else ''),'brand':brand,'barcode':code,**({('packGrams' if basis=='g' else 'packMl'):grams} if grams else {}),'nutritionBasis':basis,'retailer':product.get('stores') or '', 'market':'UK','source':'Open Food Facts — UK products','dataType':'Community product label; as sold, confirm preparation','url':'https://world.openfoodfacts.org/product/'+code,'retrievedAt':datetime.now(timezone.utc).isoformat(),'nutrients':values,'portions':portions,'aliases':aliases,'sourceWarning':'Community record: check brand, pack size, nutrition basis and current label; this is not a confirmed photo match.','lastModified':product.get('last_modified_t')}

def lookup_barcode(barcode):
    try:
        r=httpx.get('https://world.openfoodfacts.org/api/v2/product/'+barcode+'.json',headers={'User-Agent':'Caltra/0.1 (personal UK nutrition tracker)'},timeout=12)
        r.raise_for_status();p=r.json().get('product',{})
        food=normalize_product(p)
        return food,None if food else 'No complete UK label found for this barcode. Enter the current label, including whether values are per 100 g or 100 ml.'
    except (httpx.HTTPError,ValueError,TypeError):return None,'Barcode lookup is unavailable. You can enter the label instead.'


def search_products(query):
    result=search_product_page(query)
    return result['foods'],result['warning']


def search_product_page(query,page=1):
    words=re.findall(r'[a-z0-9]+',query.lower())[:16]
    key=(' '.join(words),page)
    empty={'foods':[],'warning':None,'hasMore':False,'page':page}
    if len(key[0])<3:return empty
    with _lock:
        now=time.monotonic()
        if key in _cache and now-_cache[key][0]<_cache[key][1]:return _cache[key][2]
        while _calls and now-_calls[0]>60:_calls.popleft()
        if len(_calls)>=9:return {**empty,'warning':'UK product lookup is busy; retry in a minute. Cached foods remain available.','hasMore':True}
        _calls.append(now)
        try:
            # Country filtering happens upstream, before the worldwide results are paginated.
            response=httpx.get('https://search.openfoodfacts.org/search',params={'q':key[0]+' countries_tags:"en:united-kingdom"','page_size':100,'page':page},headers={'User-Agent':'Caltra-local-prototype/0.1 (UK nutrition lookup)'},timeout=20)
            response.raise_for_status()
            data=response.json();hits=data.get('hits',[])
            products=[f for p in hits if (f:=normalize_product(p))]
            matched=search_foods(products,query,limit=100)
            products=list({f['id']:f for f in matched['foods']}.values()) if matched['matchType']=='matched' else []
            more=page<data.get('page_count',page) or (len(hits)==100 and 'page_count' not in data)
            warning='UK branded results are community label records. Confirm the exact product, pack size and raw/cooked state.' if products else 'No complete UK product matched on this page. Try more results, a barcode or the current label.'
            value=(now,3600,{'foods':products,'warning':warning,'hasMore':more,'page':page})
        except (httpx.HTTPError,ValueError,TypeError):
            value=(now,30,{**empty,'warning':'UK product lookup is unavailable. Showing cached foods; no exact UK match is confirmed.','hasMore':True})
        if len(_cache)>=64:_cache.pop(next(iter(_cache)))
        _cache[key]=value
        return value[2]
