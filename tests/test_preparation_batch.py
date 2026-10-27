import pytest
from backend import estimation

@pytest.mark.parametrize('name,description',[
 ('Laila Basmati rice','Cooked basmati rice'),
 ('Chicken, whole, raw, meat and skin, weighed with bone','Chicken on the bone, skin removed'),
 ('Chickpeas, canned, whole contents','Canned chickpeas drained'),
])
def test_incompatible_preparation_rejected(name,description):
 assert not estimation.preparation_matches({'name':name},description)

def test_skinless_and_cooked_sources_remain_allowed():
 assert estimation.preparation_matches({'name':'Chicken, without skin, weighed with bone'},'Chicken skin removed on bone')
 assert estimation.preparation_matches({'name':'Rice, white, basmati, boiled in unsalted water'},'Cooked basmati rice')

def test_drained_tins_and_batch_division():
 c={'label':'Canned chickpeas drained','query':'chickpeas drained','quantity':2,'unit':'tin','estimatedGrams':800,'basis':'user','amountScope':'batch','batchServings':3}
 assert estimation.component_grams(c,{'name':'Chickpeas canned drained','portions':[]}) == 160

def test_explicit_drained_pack_weight():
 c={'label':'Canned chickpeas drained','query':'chickpeas drained','quantity':2,'unit':'tin','estimatedGrams':800,'basis':'user','amountScope':'batch','batchServings':3}
 assert estimation.component_grams(c,{'name':'Chickpeas canned drained','drainedGrams':210,'portions':[]}) == 140

def test_bowl_amount_not_divided_by_batch_yield():
 c={'label':'Onion','quantity':50,'unit':'g','basis':'assumed','amountScope':'serving','batchServings':3}
 assert estimation.component_grams(c,{'name':'Onion'})==50

def test_batch_amount_survives_preserve():
 c={'label':'Oil','quantity':5,'unit':'g','basis':'assumed','amountScope':'batch','batchServings':3,'previousItemId':'oil'}
 estimation.preserve_amounts([c],[{'id':'oil','grams':5,'food':{'id':'o'}}])
 assert estimation.component_grams(c,{'name':'Oil'})==pytest.approx(1.6667)

def test_cooked_rice_correction_applied_even_if_model_only_acknowledges(tmp_path,monkeypatch):
 from backend.main import create_app
 from backend import vision
 from fastapi.testclient import TestClient
 with TestClient(create_app(tmp_path/'test.sqlite')) as client:
  store=client.app.state.store
  raw=next(f for f in store.foods() if 'Rice, white, basmati, raw'==f['name'])
  cooked=next(f for f in store.foods() if f['name']=='Rice, white, basmati, boiled in unsalted water')
  monkeypatch.setattr(vision,'refine',lambda *a:{'replace':False,'components':[],'message':'Thanks','question':'How much rice?'})
  monkeypatch.setattr(vision,'select_sources',lambda entries:{i:cooked for i in range(len(entries))})
  r=client.post('/api/refine',json={'message':'The rice on my plate is cooked basmati, not dry rice.','items':[{'id':'rice','food':raw,'label':'Basmati rice','grams':180}]}).json()
  assert r['items'] and r['items'][0]['food']['id']==cooked['id']
  assert r['items'][0]['grams']==180
  assert r['totals']['calories']==pytest.approx(210.6)
