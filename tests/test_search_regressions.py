from backend.search import search_foods
from backend import uk_products


def food(name,brand='',retailer=''):
 return {'id':name,'name':name,'brand':brand,'retailer':retailer,'source':'Open Food Facts — UK products' if brand else 'UK CoFID 2021'}


def test_chickpeas_and_yoghurt_synonyms():
 assert search_foods([food('Beans, chick peas, canned, drained'),food('Ackee, canned')],'canned chickpeas')['foods'][0]['name'].startswith('Beans, chick peas')
 assert search_foods([food('Asda · Fat Free Greek Style Yogurt','Asda')],'ASDA fat free greek yoghurt')['matchType']=='matched'


def test_preparation_never_becomes_food_identity():
 for query in ['chickpeas canned','canned chickpeas']:
  assert search_foods([food('Ackee, canned'),food('Corned beef, canned')],query)['foods']==[]
 assert search_foods([food('Lamb, breast, raw'),food('Chicken, breast, grilled')],'chicken breast raw')['foods']==[food('Chicken, breast, grilled')]


def test_plain_ingredients_before_composite_foods():
 for query,plain,other in [('cucumber','Cucumber, raw, flesh and skin','Relish, corn/cucumber/onion'),('carrot','Carrots, old, raw','Cake, carrot, iced')]:
  assert search_foods([food(other),food(plain)],query)['foods'][0]['name']==plain


def test_brand_and_food_type_are_not_silently_substituted():
 records=[food('Tesco · Fajita chicken wrap','Tesco'),food('Rowan Hill · High Protein Tortilla Wraps','Rowan Hill','Lidl'),food('Wraps, wheat')]
 result=search_foods(records,'Lidl protein tortilla wrap')
 assert result['matchType']=='matched'
 assert result['foods']==[records[1]]
 assert not search_foods([records[0]],'Lidl protein wrap')['foods']


def test_external_search_filters_unrelated_hits_and_uses_plain_query(monkeypatch):
 uk_products._cache.clear();uk_products._calls.clear()
 def product(name,brand):
  return {'code':'5063089020357','product_name':name,'brands':brand,'quantity':'500g','countries_tags':['en:united-kingdom'],'nutriments':{'energy-kcal_100g':66,'proteins_100g':7,'carbohydrates_100g':8,'fat_100g':.5}}
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'hits':[product('Fat Free Greek Style Yoghurt','Asda'),product('Fat Free Cottage Cheese','Asda'),product('Fat Free Greek Style Yoghurt','Tesco')]}
 def get(url,**kwargs):
  assert ' AND ' not in kwargs['params']['q']
  return Response()
 monkeypatch.setattr(uk_products.httpx,'get',get)
 fs,_=uk_products.search_products('ASDA fat free greek yogurt')
 assert len(fs)==1 and fs[0]['brand']=='Asda'


def test_actual_uk_catalog_api_ranks_ingredients_and_keeps_identity(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 monkeypatch.setattr(uk_products,'search_products',lambda q:([food('Tesco · Chicken carrot wrap','Tesco')],None))
 with TestClient(create_app(tmp_path/'foods.sqlite')) as client:
  for query,expected in [('carrot','Carrots,'),('cucumber','Cucumber,'),('canned chickpeas','Beans, chick peas, canned')]:
   found=client.get('/api/foods',params={'q':query,'uk':True}).json()['foods']
   assert found[0]['name'].startswith(expected)
   assert all(not f['source'].startswith('USDA') for f in found)


def test_external_search_keeps_singular_product_for_plural_query(monkeypatch):
 uk_products._cache.clear();uk_products._calls.clear()
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'hits':[{'code':'12345678','product_name':'Chicken Breast','brands':'Tesco','quantity':'500g','countries_tags':['en:united-kingdom'],'nutriments':{'energy-kcal_100g':106,'proteins_100g':24,'carbohydrates_100g':0,'fat_100g':1.1}}]}
 monkeypatch.setattr(uk_products.httpx,'get',lambda *args,**kwargs:Response())
 fs,_=uk_products.search_products('Tesco chicken breasts')
 assert len(fs)==1 and 'Chicken Breast' in fs[0]['name']


def test_tortilla_chips_are_not_a_wrap_substitute():
 records=[food('Tortilla chips fried in sunflower oil'),food('Tortilla, wheat, soft')]
 assert search_foods(records,'Lidl protein wrap')['foods']==[records[1]]
