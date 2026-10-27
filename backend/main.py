import json
import hashlib
import threading
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv, set_key
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from .store import Store
from . import targets
from .nutrients import NUTRIENTS
from .config import env_file
from .search import search_foods, photo_candidates
from .models import Meal, Chat, Recipe, Refine, Favorite
from .nutrition import calculate, make_recipe
from . import assistant, vision, estimation, uk_products, usual_products
from pydantic import BaseModel, Field, SecretStr

ROOT=Path(__file__).resolve().parent.parent
ENV_PATH=env_file(ROOT,Path.home())
load_dotenv(ENV_PATH)
ALIASES={'daal':'dal','roti':'chapati','gobi':'cauliflower','chana':'chickpeas','bhindi':'okra','palak':'spinach','aloo':'potato','qeema':'keema','pakode':'pakora','butter naan':'naan','kadai paneer':'paneer','dal makhani':'dal','chole bhature':'chickpeas'}


def create_app(db_path=None,*,uk_only=True):
    app=FastAPI(title='Caltra',docs_url=None,redoc_url=None)
    store=Store(db_path or ROOT/'data'/'caltra.sqlite',uk_only=uk_only)
    store.seed()
    app.state.store=store
    analysis_lock=threading.Lock()
    analysis_version='uk-plated-portions-v20'

    @app.middleware('http')
    async def local_only(request:Request,call_next):
        host=request.url.hostname
        if host not in {'127.0.0.1','localhost','testserver'}:
            return JSONResponse({'detail':'This prototype is local only.'},status_code=403)
        origin=request.headers.get('origin')
        if request.method not in {'GET','HEAD','OPTIONS'} and origin:
            allowed={f'http://{host}:8000',f'http://{host}:5173',f'http://{host}:8765'}
            if origin not in allowed:return JSONResponse({'detail':'Foreign origin rejected.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    def resolve_items(items):
        resolved=[]
        for item in items:
            data=item.model_dump() if hasattr(item,'model_dump') else dict(item)
            food=store.food(data['food'].get('id',''))
            if not food:raise HTTPException(422,'Choose a food from database search before saving.')
            resolved.append({**data,'food':food})
        try:calculate(resolved)
        except ValueError as e:raise HTTPException(422,str(e))
        return resolved

    @app.get('/api/targets')
    def get_targets():return store.setting('targets')

    @app.post('/api/targets')
    def save_targets(body:targets.Targets):return store.save_setting('targets',body.model_dump())

    @app.post('/api/targets/suggest')
    def suggest_targets(body:targets.Profile):
        try:return targets.suggest(body)
        except ValueError as e:raise HTTPException(422,str(e))

    @app.get('/api/nutrients')
    def nutrient_definitions():return [{'key':k,'label':label,'unit':unit,'group':group} for k,label,unit,group in NUTRIENTS]

    @app.get('/api/status')
    def status():
        return {'visionConfigured':bool(os.getenv('GEMINI_API_KEY','').strip()),'visionModel':vision.model_name(),'usdaConfigured':False,'nutritionRegion':'UK' if uk_only else 'legacy test catalog','chatConfigured':bool(os.getenv('GEMINI_API_KEY')),'cachedFoods':len(store.foods()),'chatModel':os.getenv('GEMINI_MODEL',vision.DEFAULT_MODEL)}

    @app.get('/api/foods')
    def foods(q:str=Query(default='',max_length=100),uk:bool=False):
        query=ALIASES.get(q.strip().lower(),q.strip())
        products,warning=uk_products.search_products(query) if uk and len(query)>=3 else ([],None)
        for food in products:store.cache_food(food)
        ranked=search_foods(store.foods(),query)
        if ranked['matchType']=='related':
            fallback=f"Not an exact match for ‘{q}’. These are related {ranked['matchedQuery']} records; their nutrition may differ."
            warning=f'{warning} {fallback}' if warning else fallback
        return {**ranked,'mode':'UK products and CoFID' if uk else 'UK CoFID and saved labels','warning':warning}

    @app.get('/api/products/search')
    def product_search(q:str=Query(min_length=3,max_length=100),page:int=Query(default=1,ge=1,le=100)):
        result=uk_products.search_product_page(q.strip(),page)
        for food in result['foods']:store.cache_food(food)
        # Generic CoFID foods must not consume the branded-product result limit.
        records=[f for f in store.foods() if f.get('brand') and not f.get('isAiEstimate')] if page==1 else result['foods']
        ranked=search_foods(records,q.strip(),limit=100)
        return {**result,**ranked,'mode':'UK branded products'}

    @app.post('/api/products')
    def create_product(body:usual_products.LabelProduct):
        try:food=usual_products.label_food(body)
        except ValueError as e:raise HTTPException(422,str(e))
        store.cache_food(food)
        return food

    @app.post('/api/products/label')
    async def read_label(file:UploadFile=File(...)):
        data=await file.read(10*1024*1024+1);await file.close()
        try:return {**await run_in_threadpool(vision.read_product_label,data),'reviewRequired':True}
        except ValueError as e:raise HTTPException(400,str(e))
        except vision.VisionError as e:raise HTTPException(503,str(e))

    @app.get('/api/products/barcode/{barcode}')
    def barcode_product(barcode:str):
        if not barcode.isdigit() or not 8<=len(barcode)<=14:raise HTTPException(422,'Enter an 8–14 digit barcode.')
        cached=store.food('off:'+barcode)
        if cached:return cached
        food,warning=uk_products.lookup_barcode(barcode)
        if not food:raise HTTPException(404,warning or 'Product not found. You can enter its UK label instead.')
        store.cache_food(food)
        return food

    @app.get('/api/usual-products')
    def get_usual_products():return store.usual_products()

    @app.post('/api/usual-products')
    def save_usual_product(body:usual_products.UsualProduct):
        if body.category not in usual_products.CATEGORIES:raise HTTPException(422,'Choose a supported ingredient category.')
        food=store.food(body.foodId)
        if not food or food.get('isAiEstimate') or not food.get('brand'):raise HTTPException(422,'Choose a branded product or enter its label first.')
        if any(food['nutrients'].get(k) is None for k in ('calories','protein','carbs','fat')):raise HTTPException(422,'This label is missing macros.')
        store.save_usual(body.category,body.foodId)
        return store.usual_products()

    @app.delete('/api/usual-products/{category}')
    def delete_usual_product(category:str):
        store.delete_usual(category)
        return {'ok':True}

    @app.get('/api/meals')
    def meals():return store.meals()

    @app.post('/api/meals')
    def save(meal:Meal):
        payload=meal.model_dump(mode='json')
        payload['items']=resolve_items(meal.items)
        return store.save_meal(payload)

    @app.delete('/api/meals/{ident}')
    def delete(ident:str):
        store.delete_meal(ident)
        return {'ok':True}

    @app.delete('/api/diary')
    def clear():
        for meal in store.meals():store.delete_meal(meal['id'])
        return {'ok':True}

    @app.get('/api/export')
    def export():return JSONResponse({'version':1,'meals':store.meals()},headers={'Content-Disposition':'attachment; filename="caltra-diary.json"'})

    class Connection(BaseModel):
        apiKey:SecretStr=Field(min_length=10,max_length=300)

    @app.post('/api/settings/gemini')
    def connect(body:Connection):
        key=body.apiKey.get_secret_value().strip()
        if not key or any(c.isspace() for c in key):raise HTTPException(422,'Enter a valid API key.')
        env_path=ENV_PATH
        env_path.touch(mode=0o600,exist_ok=True)
        env_path.chmod(0o600)
        set_key(str(env_path),'GEMINI_API_KEY',key)
        os.environ['GEMINI_API_KEY']=key
        return {'ok':True}

    def analyze(data,note,angle=None,homemade=False):
        # Serialised locally so simultaneous identical uploads cannot start two model calls.
        with analysis_lock:
            usuals=store.usual_products() if usual_products.applies(homemade,note) else []
            def cache_key():
                signature=json.dumps([{'id':f['id'],'name':f['name'],'nutrients':f['nutrients'],'includesAddedFat':f.get('includesAddedFat'),'portions':f.get('portions'),'personalReference':f.get('personalReference'),'defaultPortionGrams':f.get('defaultPortionGrams')} for f in sorted(store.foods(),key=lambda f:f['id'])],sort_keys=True)
                return hashlib.sha256(hashlib.sha256(data).digest()+hashlib.sha256(angle or b'').digest()+json.dumps([note,vision.model_name(),analysis_version,signature,[(u['category'],u['food']['id']) for u in usuals]]).encode()).hexdigest()
            key=cache_key()
            cached=store.analysis(key)
            if cached:return cached
            model_note=note+usual_products.context(usuals) if usuals else note
            result=vision.recognize(data,model_note,angle) if angle else vision.recognize(data,model_note) if model_note else vision.recognize(data)
            estimation.validate_photo_quantities(result,note)
            try:
                for food in result['foods']:
                    if food.get('brand'):
                        products,warning=uk_products.search_products(food['brand']+' '+food['query'])
                        for product in products:store.cache_food(product)
                        if warning:result['notice']+=' '+warning
                result=estimation.resolve_observation(result,store,allow_ai=True,usual_products=usuals) if usuals else estimation.resolve_observation(result,store,allow_ai=True)
            except vision.VisionError as e:
                result.update(items=[],groups=[],missing=[f['label'] for f in result['foods']],totals=None,notice=str(e))
                for food in result['foods']:food.update(matches=[],matchType='none')
            if result['items'] and not result['missing']:
                store.cache_analysis(cache_key(),result)
            return result
    @app.post('/api/recognize')
    async def recognize(file:UploadFile=File(...),note:str=Form(default='',max_length=2000),angle:UploadFile|None=File(default=None),homemade:bool=Form(default=False)):
        data=await file.read(10*1024*1024+1)
        await file.close()
        side=await angle.read(10*1024*1024+1) if angle else None
        if angle:await angle.close()
        if angle and not side:raise HTTPException(400,'Side photo is empty. Choose a valid image.')
        try:
            result=await run_in_threadpool(analyze,data,note.strip(),side,homemade)
            from .search import dish_tokens
            words=set(dish_tokens(' '.join(food['label'] for food in result['foods'])))
            favorites=store.favorites()
            favorites.sort(key=lambda f:-len(words&set(dish_tokens(f['name']+' '+f.get('observation','')))))
            result['usuals']=[f for f in favorites if len(words&set(dish_tokens(f['name']+' '+f.get('observation',''))))>=2][:3]
            return result
        except ValueError as e:raise HTTPException(400,str(e))
        except vision.VisionError as e:raise HTTPException(503,str(e))

    @app.post('/api/refine')
    def refine(body:Refine):
        current=resolve_items(body.items) if body.items else []
        usuals=store.usual_products() if usual_products.applies(body.homemade,body.observation+' '+body.message) else []
        try:
            history=list(body.history)
            if body.pendingQuestion:
                history.append({'role':'assistant','message':body.pendingQuestion})
            observation=body.observation+(usual_products.context(usuals) if usuals else '')
            plan=vision.refine(body.message,current,history,observation,body.unresolved)
            plan=estimation.apply_explicit_preparation(plan,body.message,current)
            if not plan['replace']:
                return {'items':None,'totals':None,'message':plan['message'],'question':plan['question'],'version':body.version}
            estimation.preserve_amounts(plan['components'],current)
            for component in plan['components']:
                if component.get('brand'):
                    products,_=uk_products.search_products(component['brand']+' '+component['query'])
                    for product in products:store.cache_food(product)
            items,missing=estimation.resolve_components(plan['components'],store,{i['food']['id'] for i in current},allow_ai=True,usual_products=usuals) if usuals else estimation.resolve_components(plan['components'],store,{i['food']['id'] for i in current},allow_ai=True)
            items=estimation.remove_guessed_duplicates(items,current)
            coverage=items+[{'food':{'name':label}} for label in missing]
            unpreserved=estimation.remaining_unresolved(body.unresolved,coverage)
            missing=list(dict.fromkeys(missing))
            if unpreserved or not items:
                missing=list(dict.fromkeys(missing+unpreserved))
                return {'items':None,'totals':None,'message':'Your meal is unchanged. Could not resolve: '+', '.join(missing),'question':plan['question'],'version':body.version}
            return {'items':items,'totals':calculate(items),'missing':missing,'message':('Partial estimate. Not included yet: '+', '.join(missing)+'. ' if missing else '')+plan['message'],'question':plan['question'],'version':body.version}
        except vision.VisionError as e:raise HTTPException(503,str(e))

    @app.get('/api/favorites')
    def favorites():return store.favorites()

    @app.post('/api/favorites')
    def remember(body:Favorite):
        payload=body.model_dump()
        payload['name']=payload['name'].strip()
        if not payload['name']:raise HTTPException(422,'Enter a meal name.')
        payload['id']=payload['id'] or str(uuid.uuid4())
        payload['items']=resolve_items(body.items)
        return store.save_favorite(payload)

    @app.delete('/api/favorites/{ident}')
    def forget(ident:str):
        store.delete_favorite(ident)
        return {'ok':True}

    @app.post('/api/chat')
    def chat(body:Chat):
        items=resolve_items(body.items)
        return {**assistant.chat(body.message,items,body.history),'version':body.version}

    @app.post('/api/recipes')
    def recipe(body:Recipe):
        result=make_recipe(body.name,resolve_items(body.items),body.yieldGrams,'recipe-'+str(uuid.uuid4()))
        if result.get('isAiEstimate'):store.cache_estimate(result)
        else:store.cache_food(result)
        return result

    if (ROOT/'dist').exists():app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='ui')
    return app

app=create_app()
