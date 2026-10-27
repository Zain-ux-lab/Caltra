import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend import uk_products


def product():
 return {'code':'5011157996776','product_name':'Pure Basmati Rice','brands':['Tilda'],'quantity':'250g','countries_tags':['en:united-kingdom'],'nutriments':{'energy-kcal_100g':143,'proteins_100g':2.9,'carbohydrates_100g':28.2,'fat_100g':1.9}}


def test_brand_and_pack_are_preserved_but_not_called_verified():
 f=uk_products.normalize_product(product())
 assert f['brand']=='Tilda' and f['packGrams']==250
 assert f['nutrients']['calories']==143 and 'Community' in f['dataType']
 assert f['id']=='off:5011157996776'


@pytest.mark.parametrize('change',[{'quantity':'250 ml'},{'brands':[]},{'countries_tags':['en:france']},{'nutriments':{'energy-kcal_100g':438,'proteins_100g':3.8,'carbohydrates_100g':9.9,'fat_100g':5.1}}])
def test_wrong_market_unknown_brand_liquid_and_bad_energy_are_not_accepted(change):
 assert uk_products.normalize_product({**product(),**change}) is None


def test_uk_search_returns_named_product_and_source_validates_on_save(tmp_path,monkeypatch):
 f=uk_products.normalize_product(product())
 monkeypatch.setattr(uk_products,'search_products',lambda q:([f],'Check current pack label'))
 with TestClient(create_app(tmp_path/'test.sqlite')) as client:
  found=client.get('/api/foods',params={'q':'Tilda basmati','uk':True}).json()
  assert found['foods'][0]['id']==f['id']
  fake={**f,'nutrients':{'calories':1,'protein':1,'carbs':1,'fat':1}}
  saved=client.post('/api/meals',json={'id':'test','name':'Rice','date':'2026-10-20','items':[{'id':'rice','food':fake,'grams':125}]}).json()
  assert saved['totals']['calories']==178.75


def test_cofid_seed_has_cooked_basmati_and_generic_moussaka(tmp_path):
 with TestClient(create_app(tmp_path/'test.sqlite')) as client:
  rice=client.get('/api/foods?q=basmati%20boiled').json()['foods']
  assert any(f['source']=='UK CoFID 2021' and f['nutrients']['calories']==117 for f in rice)
  assert any(f['source']=='UK CoFID 2021' for f in client.get('/api/foods?q=moussaka').json()['foods'])


def test_branded_photo_does_not_accept_different_pack_variant(tmp_path,monkeypatch):
 from backend.store import Store
 from backend import estimation,vision
 store=Store(tmp_path/'store.sqlite');store.seed()
 f=uk_products.normalize_product(product());store.cache_food(f)
 def select(entries):
  raise AssertionError('A wrong pack size must not reach the selector')
 monkeypatch.setattr(vision,'select_sources',select)
 d=estimation.resolve_observation({'foods':[{'label':'Tilda rice','query':'basmati','brand':'Tilda','packGrams':500,'estimatedGrams':500,'visibleCount':1}],'question':'','description':'Pack'},store)
 assert not d['items'] and d['missing']==['Tilda rice']


def test_named_brand_correction_looks_up_and_uses_product(tmp_path,monkeypatch):
 from backend import vision
 f=uk_products.normalize_product(product())
 monkeypatch.setattr(uk_products,'search_products',lambda q:([f],None))
 monkeypatch.setattr(vision,'refine',lambda *args:{'replace':True,'components':[{'label':'Tilda Pure Basmati Rice','query':'pure basmati rice','brand':'Tilda','packGrams':250,'quantity':125,'unit':'g','basis':'user'}],'message':'Updated rice','question':''})
 def select(entries):
  assert any(x['id']==f['id'] for x in entries[0]['candidates'])
  return {0:f}
 monkeypatch.setattr(vision,'select_sources',select)
 with TestClient(create_app(tmp_path/'store.sqlite')) as client:
  r=client.post('/api/refine',json={'message':'125g of Tilda Pure Basmati Rice from a250g pouch','items':[]}).json()
  assert r['items'][0]['food']['brand']=='Tilda'
  assert r['totals']['calories']==178.75
