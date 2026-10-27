import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend import estimation,vision

@pytest.fixture
def store(tmp_path):
 with TestClient(create_app(tmp_path/'test.sqlite')) as c:yield c.app.state.store

def test_correction_preserves_unchanged_amounts():
 current=[{'id':'y','food':{'id':'asda','nutritionBasis':'g'},'grams':100}]
 parts=[{'label':'Yogurt','query':'yogurt','sourceId':'asda','quantity':50,'unit':'g','basis':'assumed'}]
 estimation.preserve_amounts(parts,current)
 assert parts[0]['quantity']==100
 assert parts[0]['basis']=='assumed'

def test_explicit_amount_and_new_ingredient_survive():
 current=[{'id':'y','food':{'id':'asda'},'grams':100}]
 parts=[{'label':'Yogurt','query':'yogurt','sourceId':'asda','quantity':2,'unit':'tbsp','basis':'user'}, {'label':'Milk','query':'milk','quantity':100,'unit':'ml','basis':'assumed'}]
 estimation.preserve_amounts(parts,current)
 assert parts[0]['quantity']==2 and parts[0]['unit']=='tbsp'
 assert parts[1]['quantity']==100

def test_changed_source_preserves_amount_by_item_id():
 parts=[{'label':'Yogurt','query':'yogurt','previousItemId':'y','sourceId':None,'quantity':50,'unit':'g','basis':'assumed'}]
 estimation.preserve_amounts(parts,[{'id':'y','food':{'id':'old'},'grams':120}])
 assert parts[0]['quantity']==120

def test_ambiguous_reused_source_is_not_arbitrarily_selected():
 parts=[{'label':'Yogurt','query':'yogurt','sourceId':'same','quantity':50,'unit':'g','basis':'assumed'}]
 estimation.preserve_amounts(parts,[{'id':'a','food':{'id':'same'},'grams':100},{'id':'b','food':{'id':'same'},'grams':200}])
 assert parts[0]['quantity']==50

@pytest.mark.parametrize('berry',['blueberries','raspberries'])
def test_plain_branded_berry_uses_stable_uk_reference(store,monkeypatch,berry):
 def no_model(*a,**k):raise AssertionError('Plain berry needs no generated nutrition')
 monkeypatch.setattr(vision,'select_sources',no_model)
 monkeypatch.setattr(vision,'estimate_nutrients',no_model)
 items,missing=estimation.resolve_components([{'label':'Lidl frozen '+berry,'query':'frozen '+berry,'brand':'Lidl','quantity':30,'unit':'g','basis':'photo'}],store,allow_ai=True)
 assert not missing and len(items)==1
 assert items[0]['food']['source']=='UK CoFID 2021'
 assert 'generic' in items[0]['food']['sourceWarning'].lower()
 assert not items[0]['food'].get('brand')

@pytest.mark.parametrize('name',['blueberry yogurt','sweetened blueberries','blueberry smoothie','raspberry jam','mixed berries'])
def test_berry_fallback_does_not_replace_composite_products(store,name):
 assert estimation.generic_berry({'label':name,'query':name,'brand':'Lidl'},store.foods()) is None

def test_household_question_replaces_weight_request():
 assert 'spoon' in vision.household_question('Could you confirm the approximate weight of dry oats?').lower()
 assert vision.household_question('How many eggs?')=='How many eggs?'

def test_refine_endpoint_keeps_yogurt_when_adding_honey(tmp_path,monkeypatch):
 with TestClient(create_app(tmp_path/'api.sqlite')) as c:
  yogurt=c.post('/api/products',json={'name':'Fat free Greek style yogurt','brand':'ASDA','nutritionBasis':'g','nutrients':{'calories':66,'protein':7,'carbs':8,'fat':0.5}}).json()
  honey=next(f for f in c.app.state.store.foods() if f['name']=='Honey')
  monkeypatch.setattr(vision,'refine',lambda *a:{'replace':True,'components':[{'label':'Yogurt','query':'yogurt','sourceId':yogurt['id'],'quantity':50,'unit':'g','basis':'assumed'},{'label':'Honey','query':'honey','quantity':7,'unit':'g','basis':'assumed'}],'message':'Added honey','question':''})
  monkeypatch.setattr(vision,'select_sources',lambda entries:{0:honey})
  r=c.post('/api/refine',json={'message':'There was a drizzle of honey too','items':[{'id':'y','food':yogurt,'grams':100}]}).json()
  assert r['items'][0]['grams']==100
  assert len(r['items'])==2

def test_whole_berry_observation_uses_uk_proxy(store,monkeypatch):
 monkeypatch.setattr(vision,'estimate_nutrients',lambda *a: (_ for _ in ()).throw(AssertionError('Must use UK source')))
 r=estimation.resolve_observation({'foods':[{'label':'Lidl frozen blueberries','query':'frozen blueberries','brand':'Lidl','estimatedGrams':50,'visibleCount':1,'components':[]}],'question':''},store,allow_ai=True)
 assert r['items'][0]['food']['source']=='UK CoFID 2021'

def test_split_does_not_duplicate_old_amount():
 current=[{'id':'mix','food':{'id':'mixed'},'grams':100}]
 parts=[{'label':'Blueberries','query':'blueberries','previousItemId':'mix','quantity':60,'unit':'g','basis':'assumed'},{'label':'Raspberries','query':'raspberries','previousItemId':'mix','quantity':40,'unit':'g','basis':'assumed'}]
 estimation.preserve_amounts(parts,current)
 assert [p['quantity'] for p in parts]==[60,40]

def test_refinement_does_not_add_same_honey_twice():
 current=[{'id':'old','food':{'id':'honey'},'grams':15}]
 items=[{'food':{'id':'honey'},'grams':15,'quantityBasis':'assumed'},{'food':{'id':'honey'},'grams':10,'quantityBasis':'assumed'},{'food':{'id':'milk'},'grams':30,'quantityBasis':'assumed'}]
 assert estimation.remove_guessed_duplicates(items,current)==[items[0],items[2]]

def test_explicit_additional_portion_is_not_discarded():
 current=[{'id':'old','food':{'id':'honey'},'grams':15}]
 items=[{'food':{'id':'honey'},'grams':15,'quantityBasis':'assumed'},{'food':{'id':'honey'},'grams':7,'quantityBasis':'user'}]
 assert estimation.remove_guessed_duplicates(items,current)==items
