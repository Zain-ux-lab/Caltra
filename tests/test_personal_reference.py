import pytest
from backend import estimation,vision
from backend.store import Store
from backend.nutrition import calculate


def reference():
 return {'id':'reference:test-wrap','name':'Lidl protein tortilla — provisional','brand':'Lidl','market':'UK','source':'Your product reference','personalReference':True,'referenceTerms':['lidl','protein','wrap'],'defaultPortionGrams':61,'nutritionBasis':'g','nutrients':{'calories':179/61*100,'protein':9.8/61*100,'carbs':29/61*100,'fat':2.3/61*100},'portions':[{'label':'1 wrap','grams':61,'unit':'g'}],'sourceWarning':'Provisional product reference; not confirmed against your pack.'}


def test_explicit_named_wrap_uses_persistent_reference_not_vision_weight(tmp_path,monkeypatch):
 s=Store(tmp_path/'f.sqlite');s.seed();s.cache_food(reference())
 assert Store(tmp_path/'f.sqlite').food(reference()['id'])
 monkeypatch.setattr(vision,'select_sources',lambda e:pytest.fail('Known reference should not be guessed again'))
 monkeypatch.setattr(vision,'estimate_nutrients',lambda e:pytest.fail('Known reference should not use AI macros'))
 r=estimation.resolve_observation({'foods':[{'label':'Lidl protein tortilla','query':'protein tortilla','brand':'Lidl','estimatedGrams':40,'visibleCount':1}],'description':'One wrap','question':'','notice':''},s,allow_ai=True)
 assert r['items'][0]['grams']==61
 assert r['totals']['calories']==pytest.approx(179)
 assert 'Assumed' in r['items'][0]['portionLabel']


def test_explicit_component_grams_override_reference_serving(tmp_path,monkeypatch):
 s=Store(tmp_path/'f.sqlite');s.cache_food(reference())
 items,missing=estimation.resolve_components([{'label':'Lidl protein tortilla','query':'protein wrap','brand':'Lidl','quantity':40,'unit':'g','basis':'user'}],s,allow_ai=True)
 assert not missing and items[0]['grams']==40


def test_generic_or_other_brand_does_not_get_personal_reference():
 from backend.estimation import personal_reference
 assert personal_reference({'label':'Tortilla','query':'wrap'},[reference()]) is None
 assert personal_reference({'label':'Tesco protein tortilla','query':'protein wrap','brand':'Tesco'},[reference()]) is None


def test_patty_components_are_one_estimated_food_but_salad_stays_separate(tmp_path,monkeypatch):
 s=Store(tmp_path/'f.sqlite');s.seed()
 def pick(entries):
  return {i:next(f for f in e['candidates'] if 'raw, extra lean' in f['name'].lower()) if 'Beef' in e['label'] else next(f for f in e['candidates'] if 'Lentils, red' in f['name'] and 'boiled' in f['name']) for i,e in enumerate(entries)}
 monkeypatch.setattr(vision,'select_sources',pick)
 r=estimation.resolve_observation({'foods':[{'label':'Homemade lean beef and lentil patty','query':'beef lentil patty','estimatedGrams':120,'components':[{'label':'Beef','query':'beef mince raw extra lean','quantity':80,'unit':'g','basis':'assumed'},{'label':'Lentils','query':'red lentils boiled','quantity':40,'unit':'g','basis':'assumed'}]}],'description':'Patty','notice':'','question':''},s)
 assert len(r['items'])==1 and r['items'][0]['food']['recipeItems']
 f=r['items'][0]['food'];assert 'estimated' in f['dataType'].lower()
 assert r['totals']['calories']==pytest.approx(calculate(f['recipeItems'])['calories'])
 assert s.food(f['id']) and not r['missing']


def test_reference_does_not_hide_wrap_fillings_or_replace_known_exact_label(tmp_path,monkeypatch):
 s=Store(tmp_path/'f.sqlite');s.seed();s.cache_food(reference())
 exact={**reference(),'id':'label:actual','source':'Your product label','personalReference':False,'nutrients':{'calories':300,'protein':20,'carbs':40,'fat':5}}
 s.cache_food(exact)
 cheese=next(f for f in s.foods() if f['name'].lower().startswith('cheese, cheddar'))
 components=[{'label':'Lidl protein tortilla','query':'protein wrap','sourceId':exact['id'],'quantity':40,'unit':'g','basis':'user'},{'label':'Cheddar cheese','query':'cheddar cheese','sourceId':cheese['id'],'quantity':20,'unit':'g','basis':'user'}]
 items,missing=estimation.resolve_components(components,s,[exact['id'],cheese['id']])
 assert not missing and items[0]['food']['id']==exact['id']
 monkeypatch.setattr(vision,'select_sources',lambda e:{i:e[i]['candidates'][0] for i in range(len(e))})
 r=estimation.resolve_observation({'foods':[{'label':'Lidl protein wrap with cheese','query':'lidl protein wrap','estimatedGrams':81,'components':components}],'description':'Filled wrap','notice':'','question':''},s)
 assert len(r['items'])==2
 assert estimation.personal_reference({'label':'Lidl protein wrap with chicken','query':'protein wrap','brand':'Lidl'},[reference()]) is None


def test_reference_component_portion_respects_repeated_wrap_count(tmp_path):
 s=Store(tmp_path/'f.sqlite');s.cache_food(reference())
 r=estimation.resolve_observation({'foods':[{'label':'Two Lidl protein tortillas','query':'protein tortilla','estimatedGrams':122,'visibleCount':2,'components':[{'label':'Lidl protein tortilla','query':'protein tortilla','quantity':122,'unit':'g','basis':'photo'}]}],'description':'Two wraps','notice':'','question':''},s)
 assert r['items'][0]['grams']==61 and r['totals']['calories']==pytest.approx(179)


def test_recognition_cannot_call_guessed_wrap_weight_user_supplied(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 from backend import uk_products
 from PIL import Image
 import io
 with TestClient(create_app(tmp_path/'api.sqlite')) as client:
  client.app.state.store.cache_food(reference())
  monkeypatch.setattr(uk_products,'search_products',lambda *a:([],''))
  monkeypatch.setattr(vision,'recognize',lambda *a:{'foods':[{'label':'Protein tortilla','query':'tortilla wrap','brand':'Lidl','estimatedGrams':80,'basis':'user','visibleCount':1,'components':[]}],'description':'Lidl protein tortilla','question':'','notice':''})
  photo=io.BytesIO();Image.new('RGB',(32,32),'white').save(photo,format='PNG')
  r=client.post('/api/recognize',files={'file':('meal.png',photo.getvalue(),'image/png')},data={'note':'This is my Lidl protein tortilla','homemade':'true'})
  assert r.status_code==200,r.text
  result=r.json();assert result['items'][0]['grams']==61
  assert result['totals']['calories']==pytest.approx(179)
  assert 'Lidl' in result['items'][0]['label']
  assert 'Your quantity' not in result['items'][0]['portionLabel']


def test_explicit_consumed_wrap_weight_can_override_serving():
 result={'foods':[{'label':'Protein tortilla','query':'tortilla wrap','brand':'Lidl','estimatedGrams':80,'basis':'user','weightEvidence':'I ate 80g of the Lidl protein tortilla'}]}
 estimation.validate_photo_quantities(result,'I ate 80g of the Lidl protein tortilla')
 assert result['foods'][0]['basis']=='user'


def test_unquoted_or_pack_weight_cannot_be_consumed_weight():
 for note,evidence in [('Lidl protein tortilla','I ate 80g of the Lidl protein tortilla'),('The pack weighs 366g','The pack weighs 366g')]:
  result={'foods':[{'label':'Protein tortilla','query':'tortilla wrap','estimatedGrams':366 if '366' in note else 80,'basis':'user','weightEvidence':evidence}]}
  estimation.validate_photo_quantities(result,note)
  assert result['foods'][0]['basis']=='photo'
