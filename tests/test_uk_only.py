import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.store import Store

def test_uk_only_catalog_never_loads_usda_and_filters_old_cache(tmp_path):
 store=Store(tmp_path/'x.sqlite',uk_only=True)
 store.cache_food({'id':'old-us','name':'Old rice','source':'USDA FoodData Central','nutrients':{'calories':100,'protein':1,'carbs':20,'fat':0}})
 store.seed()
 assert store.foods() and all(f['source'].startswith('UK CoFID') for f in store.foods())
 assert store.food('old-us') is None
 assert store.food('168878') is None

def test_no_usda_network_even_with_configured_key(tmp_path,monkeypatch):
 monkeypatch.setenv('USDA_API_KEY','dummy-do-not-send')
 from backend import main
 monkeypatch.setattr(main.httpx,'get',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No USDA network allowed')))
 with TestClient(create_app(tmp_path/'x.sqlite')) as client:
  r=client.get('/api/foods?q=rice')
  assert r.status_code==200
  assert all(f['source'].startswith('UK CoFID') for f in r.json()['foods'])
  assert client.get('/api/status').json()['nutritionRegion']=='UK'

def test_old_us_source_cannot_be_saved_as_new_meal_or_used_in_recipe(tmp_path):
 with TestClient(create_app(tmp_path/'x.sqlite')) as client:
  store=client.app.state.store
  f={'id':'old-us','name':'Rice','source':'USDA FoodData Central','nutrients':{'calories':130,'protein':2,'carbs':28,'fat':0}}
  store.cache_food(f)
  r=client.post('/api/meals',json={'id':'m','name':'Rice','date':'2026-10-24','items':[{'id':'i','food':f,'grams':100}]})
  assert r.status_code==422

def test_us_derived_recipe_and_cached_analysis_are_excluded(tmp_path):
 store=Store(tmp_path/'x.sqlite',uk_only=True)
 f={'id':'recipe:old','name':'Old recipe','source':'Your recipe','recipeItems':[{'food':{'source':'USDA FoodData Central'}}]}
 store.cache_food(f)
 assert store.food(f['id']) is None
 store.cache_analysis('old',{'items':[{'food':{'source':'USDA FoodData Central'}}]})
 assert store.analysis('old') is None

def test_uk_seed_never_opens_us_database_files(tmp_path,monkeypatch):
 from pathlib import Path
 read=Path.read_text
 def guarded(path,*args,**kwargs):
  assert not path.name.startswith('usda-'),'UK mode opened a US data file'
  return read(path,*args,**kwargs)
 monkeypatch.setattr(Path,'read_text',guarded)
 store=Store(tmp_path/'x.sqlite')
 store.seed()
 assert store.uk_only and len(store.foods())>1000

def test_ai_recipe_flag_cannot_hide_us_ingredients(tmp_path):
 store=Store(tmp_path/'x.sqlite')
 food={'id':'recipe:ai-old','name':'Old mixed recipe','source':'Your recipe','isAiEstimate':True,'recipeItems':[{'food':{'source':'USDA FoodData Central'}}]}
 store.cache_food(food)
 assert store.food(food['id']) is None
