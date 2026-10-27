import pytest
from fastapi.testclient import TestClient
from backend import estimation,vision
from backend.store import Store as _Store

def Store(*args,**kwargs):
    # Explicit legacy-catalog fixture for source-parser/migration regressions.
    return _Store(*args,uk_only=False,**kwargs)
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)



def estimate(entries):
    return {i:{'nutrients':{'calories':400,'protein':5,'carbs':50,'fat':20},'estimatedGrams':120,'assumptions':'Generic recipe; not the exact bakery product.'} for i,_ in enumerate(entries)}


def test_unmatched_cookie_gets_labelled_macros_and_does_not_enter_food_search(tmp_path,monkeypatch):
    store=Store(tmp_path/'food.sqlite');store.seed()
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i,_ in enumerate(entries)})
    monkeypatch.setattr(vision,'estimate_nutrients',estimate,raising=False)
    result=estimation.resolve_observation({'foods':[{'label':'Bakery cookie','query':'cookie','visibleCount':2,'estimatedGrams':240}],'description':'Two cookies','question':'','notice':''},store,allow_ai=True)
    assert not result['missing'] and len(result['items'])==1
    item=result['items'][0]
    assert item['grams']==120 and result['totals']['calories']==480
    assert item['food']['isAiEstimate'] and 'AI estimate' in item['food']['source']
    assert 'not' in item['food']['sourceWarning']
    assert store.food(item['food']['id'])==item['food']
    assert all(f['id']!=item['food']['id'] for f in store.foods())


def test_unmatched_component_keeps_explicit_grams(tmp_path,monkeypatch):
    store=Store(tmp_path/'food.sqlite')
    monkeypatch.setattr(vision,'estimate_nutrients',estimate,raising=False)
    items,missing=estimation.resolve_components([{'label':'Mystery topping','query':'mystery topping','quantity':30,'unit':'g','basis':'user'}],store,allow_ai=True)
    assert not missing and items[0]['grams']==30 and items[0]['food']['isAiEstimate']


def test_fallback_failure_does_not_hide_unmatched_food(tmp_path,monkeypatch):
    def fail(entries):raise vision.VisionError('Service unavailable')
    monkeypatch.setattr(vision,'estimate_nutrients',fail,raising=False)
    items,missing=estimation.resolve_components([{'label':'Unknown food','query':'zxqvw','quantity':100,'unit':'g'}],Store(tmp_path/'food.sqlite'),allow_ai=True)
    assert items==[] and missing==['Unknown food']


def test_ai_estimate_saves_and_server_rejects_client_macro_tampering(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'recognize',lambda data,note='':{'foods':[{'label':'Cookie','query':'cookie','visibleCount':1,'estimatedGrams':120}],'description':'Cookie','question':'','notice':''})
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i,_ in enumerate(entries)})
    monkeypatch.setattr(vision,'estimate_nutrients',estimate,raising=False)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        result=client.post('/api/recognize',files={'file':('cookie.jpg',b'mocked','image/jpeg')}).json()
        item=result['items'][0];item['food']['nutrients']['calories']=1
        saved=client.post('/api/meals',json={'id':'ai-meal','name':'Cookie','date':'2026-10-21','items':[item]})
        assert saved.status_code==200 and saved.json()['totals']['calories']==480
        assert saved.json()['items'][0]['food']['isAiEstimate']


def test_estimate_schema_rejects_impossible_macro_density():
    from backend.vision import NutritionGuess
    from pydantic import ValidationError
    with pytest.raises(ValidationError):NutritionGuess(index=0,estimatedGrams=100,nutrients={'calories':900,'protein':100,'carbs':100,'fat':100},assumptions='')


def test_repeated_cookie_unknown_weight_uses_one_item_guess(tmp_path,monkeypatch):
    def guess(entries):
        assert entries[0]['visibleCount']==2
        assert entries[0]['portionScope']=='one visible item'
        return estimate(entries)
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i,_ in enumerate(entries)})
    monkeypatch.setattr(vision,'estimate_nutrients',guess)
    result=estimation.resolve_observation({'foods':[{'label':'Cookie','query':'cookie','visibleCount':2,'estimatedGrams':None}],'description':'Two cookies','question':'','notice':''},Store(tmp_path/'f.sqlite'),allow_ai=True)
    assert result['items'][0]['grams']==120


def test_resolving_one_duplicate_label_does_not_hide_other_missing_food(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i,_ in enumerate(entries)})
    monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:{0:estimate(entries)[0]})
    result=estimation.resolve_observation({'foods':[{'label':'Cookie','query':'cookie','visibleCount':1,'estimatedGrams':120},{'label':'Cookie','query':'cookie','visibleCount':1,'estimatedGrams':120}],'description':'Different cookies','question':'','notice':''},Store(tmp_path/'f.sqlite'),allow_ai=True)
    assert len(result['items'])==1 and result['missing']==['Cookie']


def test_recipe_preserves_ai_provenance_and_catalog_separation(tmp_path):
    from backend.fallback import estimate_foods
    from backend.nutrition import make_recipe
    store=Store(tmp_path/'f.sqlite')
    ai={'id':'ai:test','name':'Cookie','isAiEstimate':True,'source':'AI estimate','nutrients':{'calories':400,'protein':5,'carbs':50,'fat':20},'portions':[],'url':''}
    store.cache_estimate(ai)
    result=make_recipe('Cookie dessert',[{'food':ai,'grams':100}],100,'recipe-test')
    assert result['isAiEstimate'] and 'AI' in result['sourceWarning']
