import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend import estimation,vision

@pytest.fixture
def client(tmp_path):
 with TestClient(create_app(tmp_path/'test.sqlite')) as c:yield c

def product(client,basis='g'):
 r=client.post('/api/products',json={'name':'Fat free Greek style yogurt','brand':'Tesco','retailer':'Tesco','nutritionBasis':basis,'nutrients':{'calories':55,'protein':5,'carbs':8,'fat':0,'sugars':6}})
 assert r.status_code==200,r.text
 return r.json()

def test_label_product_saved_default_and_daily_arithmetic(client):
 food=product(client)
 r=client.post('/api/usual-products',json={'category':'yogurt','foodId':food['id']})
 assert r.status_code==200,r.text
 assert client.get('/api/usual-products').json()[0]['food']['brand']=='Tesco'
 forged={**food,'nutrients':{'calories':1,'protein':1,'carbs':1,'fat':1}}
 r=client.post('/api/meals',json={'id':'breakfast','name':'Bowl','date':'2026-10-22','items':[{'id':'y','food':forged,'grams':200}]})
 assert r.json()['totals']['calories']==110
 assert r.json()['nutrientTotals']['sugars']['value']==12
 assert not r.json()['nutrientTotals']['fibre']['complete']
 client.delete('/api/usual-products/yogurt')
 assert client.get('/api/usual-products').json()==[]
 assert client.get('/api/meals').json()[0]['totals']['calories']==110

def test_ml_not_silently_treated_as_grams(client):
 food=product(client,'ml')
 assert estimation.component_grams({'quantity':2,'unit':'tbsp'},food)==30
 with pytest.raises(ValueError):estimation.component_grams({'quantity':30,'unit':'g','estimatedGrams':30},food)

def test_usual_product_requires_real_record_and_is_not_an_ai_estimate(client):
 assert client.post('/api/usual-products',json={'category':'milk','foodId':'fake'}).status_code==422
 assert client.post('/api/products',json={'name':'Bad','brand':'X','nutrients':{'calories':-1,'protein':2,'carbs':3,'fat':4}}).status_code==422

def test_defaults_override_generic_not_explicit_alternative(client,monkeypatch):
 food=product(client);client.post('/api/usual-products',json={'category':'yogurt','foodId':food['id']})
 usual=client.app.state.store.usual_products()
 from backend.usual_products import find_usual
 assert find_usual({'label':'Greek style yogurt','query':'fat free yogurt'},usual)['id']==food['id']
 assert find_usual({'label':'Full fat yogurt','query':'full fat yogurt'},usual) is None
 assert find_usual({'label':'Yogurt','query':'yogurt','brand':'Asda'},usual) is None
 assert find_usual({'label':'Yogurt bowl with berries','query':'yogurt bowl'},usual) is None
 monkeypatch.setattr(vision,'select_sources',lambda x: (_ for _ in ()).throw(AssertionError('Saved source needs no AI matching')))
 items,missing=estimation.resolve_components([{'label':'Yogurt','query':'yogurt','quantity':200,'unit':'g','basis':'user'}],client.app.state.store,usual_products=usual)
 assert not missing and items[0]['food']['id']==food['id'] and items[0]['usingUsualProduct']
 assert items[0]['food']['nutrients']['protein']==5

def test_partial_extra_nutrients_are_not_zero(client):
 food=product(client)
 other=client.post('/api/products',json={'name':'Rice without optional label fields','brand':'Test','nutrients':{'calories':130,'protein':3,'carbs':28,'fat':1}}).json()
 r=client.post('/api/meals',json={'id':'x','name':'Mix','date':'2026-10-22','items':[{'id':'a','food':food,'grams':100},{'id':'b','food':other,'grams':100}]})
 assert r.status_code==200
 assert r.json()['nutrientTotals']['sugars']['value']==6
 assert not r.json()['nutrientTotals']['sugars']['complete']

def test_home_defaults_are_not_used_for_eating_out_or_cached_across_scope(client,monkeypatch):
 from PIL import Image
 import io
 food=product(client);client.post('/api/usual-products',json={'category':'yogurt','foodId':food['id']})
 calls=[]
 def recognize(data,note=''):
  calls.append(note)
  return {'foods':[{'label':'Yogurt','query':'yogurt','estimatedGrams':100,'visibleCount':1,'components':[{'label':'Yogurt','query':'yogurt','quantity':100,'unit':'g','estimatedGrams':100,'basis':'photo'}]}],'description':'Yogurt','question':'','notice':''}
 monkeypatch.setattr(vision,'recognize',recognize)
 generic=next(f for f in client.app.state.store.foods() if 'yogurt' in f['name'].lower() and not f.get('brand'))
 monkeypatch.setattr(vision,'select_sources',lambda entries:{0:generic})
 b=io.BytesIO();Image.new('RGB',(32,32),'white').save(b,format='PNG')
 home=client.post('/api/recognize',data={'homemade':'true'},files={'file':('x.png',b.getvalue(),'image/png')})
 assert home.status_code==200,home.text
 assert home.json()['items'][0]['food']['id']==food['id']
 assert 'Saved usual UK products' in calls[0]
 out=client.post('/api/recognize',data={'homemade':'false'},files={'file':('x.png',b.getvalue(),'image/png')})
 assert out.json()['items'][0]['food']['id']!=food['id']
 assert len(calls)==2 and 'Saved usual UK products' not in calls[1]

def test_label_photo_is_review_only(client,monkeypatch):
 monkeypatch.setattr(vision,'read_product_label',lambda data:{'name':'Milk','brand':'Asda','nutritionBasis':'ml','nutrients':{'calories':47,'protein':3.5,'carbs':4.8,'fat':1.7}})
 r=client.post('/api/products/label',files={'file':('label.png',b'label','image/png')})
 assert r.status_code==200 and r.json()['reviewRequired']
 assert client.get('/api/usual-products').json()==[]

def test_volume_off_records_need_explicit_ml_basis():
 from backend.uk_products import normalize_product
 raw={'code':'1234567890123','product_name':'Semi skimmed milk','brands':'Asda','quantity':'1 l','countries_tags':['en:united-kingdom'],'nutriments':{'energy-kcal_100g':47,'proteins_100g':3.5,'carbohydrates_100g':4.8,'fat_100g':1.7}}
 assert normalize_product(raw) is None
 f=normalize_product({**raw,'nutrition_data_per':'100ml'})
 assert f['nutritionBasis']=='ml' and f['packMl']==1000

@pytest.mark.parametrize('category,saved,query',[('cheese','Tesco Mature cheddar','Feta cheese'),('yogurt','Tesco Full fat Greek yogurt','Low fat yogurt'),('milk','Tesco Whole milk','Skimmed milk'),('milk','Tesco Semi skimmed milk','Skimmed milk'),('yogurt','Tesco Fat free Greek yogurt','Coconut yogurt'),('rice','Tesco dry basmati rice','Cooked Tesco basmati rice')])
def test_explicit_subtypes_never_receive_incompatible_defaults(category,saved,query):
 from backend.usual_products import find_usual
 assert find_usual({'label':query,'query':query,'brand':'Tesco'},[{'category':category,'food':{'id':'test','name':saved,'brand':'Tesco'}}]) is None

def test_restaurant_scope_survives_refinement(client,monkeypatch):
 food=product(client);client.post('/api/usual-products',json={'category':'yogurt','foodId':food['id']})
 def refine(message,items,history,observation,unresolved):
  assert 'Saved usual UK products' not in observation
  return {'replace':False,'components':[],'question':'','message':'No change'}
 monkeypatch.setattr(vision,'refine',refine)
 r=client.post('/api/refine',json={'message':'I ate half','items':[],'observation':'Restaurant breakfast yogurt','homemade':True})
 assert r.status_code==200
