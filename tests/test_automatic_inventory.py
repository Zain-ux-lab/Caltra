import pytest
from backend import estimation,vision


def test_detected_shared_extras_become_estimated_food_entries():
 result={'foods':[{'label':'Cheese pastry slice','query':'cheese pastry','estimatedGrams':100}], 'unconfirmedExtras':['Bread from basket','Coca-Cola can','Bread from basket'],'excludedFoods':[]}
 estimation.include_shared_extras(result)
 assert [f['label'] for f in result['foods']]==['Cheese pastry slice','Bread from basket','Coca-Cola can']
 assert all(f['possibleShared'] and f['basis']=='assumed' and f['estimatedGrams'] is None for f in result['foods'][1:])
 assert result['unconfirmedExtras']==[]


def test_explicitly_excluded_foods_are_not_added_back():
 result={'foods':[], 'unconfirmedExtras':['Other plate','Bread'], 'excludedFoods':['Other plate']}
 estimation.include_shared_extras(result)
 assert [f['label'] for f in result['foods']]==['Bread']


def test_different_pastries_remain_separate_and_shared_flag_survives_save(tmp_path,monkeypatch):
 from backend.store import Store
 from backend.models import Item
 store=Store(tmp_path/'inventory.sqlite');store.seed()
 monkeypatch.setattr(vision,'select_sources',lambda entries:{})
 monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:{i:{'nutrients':{'calories':250,'protein':7,'carbs':30,'fat':12},'estimatedGrams':80,'assumptions':'Synthetic fixture'} for i,e in enumerate(entries)})
 observation={'foods':[{'label':'Triangular cheese pie','query':'cheese pie','estimatedGrams':100,'components':[],'possibleShared':True,'portionScope':'allVisible'},{'label':'Long pastry strip, filling uncertain','query':'pastry','estimatedGrams':60,'components':[],'possibleShared':False,'portionScope':'allVisible'}],'description':'Two different pastries on one plate','question':''}
 result=estimation.resolve_observation(observation,store,allow_ai=True)
 assert len(result['items'])==2
 assert {i['label'] for i in result['items']}=={'Triangular cheese pie','Long pastry strip, filling uncertain'}
 assert sorted(i['grams'] for i in result['items'])==[60,100]
 item=next(i for i in result['items'] if i['possibleShared'])
 assert Item.model_validate(item).possibleShared
 saved=store.save_meal({'id':'test','date':'2026-10-27','name':'Two pastries','items':result['items']})
 assert saved['items'][0]['possibleShared']


def test_default_request_estimates_whole_photo_without_a_scope_step(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 from PIL import Image
 import io
 seen=[]
 def recognize(data,note='',angle=None):
  seen.append(note)
  return {'foods':[],'description':'Synthetic empty photo','question':'','notice':''}
 monkeypatch.setattr(vision,'recognize',recognize)
 data=io.BytesIO();Image.new('RGB',(10,10),'red').save(data,format='JPEG')
 with TestClient(create_app(tmp_path/'automatic.sqlite')) as client:
  r=client.post('/api/recognize',files={'file':('fixture.jpg',data.getvalue(),'image/jpeg')})
  assert r.status_code==200,r.text
 assert 'all plates' in seen[0]
 assert 'shared' in seen[0].lower()


def test_visual_schema_and_guidance_support_shared_and_distinct_foods():
 assert vision.VisibleFood.model_fields['possibleShared'].default is False
 assert 'different foods on the same plate' in vision.TABLE_GUIDANCE.lower()
 assert 'do not combine' in vision.TABLE_GUIDANCE.lower()
