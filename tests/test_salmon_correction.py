import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend import vision
from backend.main import create_app


def test_unsupported_new_source_is_rematched_not_rejected(monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test-key')
 old={'id':'fish-row','food':{'id':'ai:whitefish','name':'Pan-fried fish pieces'},'grams':140}
 plan={'replace':True,'components':[{'label':'Salmon','query':'salmon cooked','sourceId':'cofid:invented','previousItemId':'fish-row','quantity':140,'unit':'g','basis':'photo'}],'message':'Updated fish','question':''}
 monkeypatch.setattr(vision.httpx,'post',lambda url,**kw:httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(plan)}]}}]},request=httpx.Request('POST',url)))
 result=vision.refine('It is salmon',[old],[],'Cooked fish')
 assert result['components'][0]['sourceId'] is None
 assert result['components'][0]['previousItemId']=='fish-row'


def test_salmon_correction_recalculates_only_fish(tmp_path,monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test-key')
 with TestClient(create_app(tmp_path/'test.sqlite')) as c:
  s=c.app.state.store
  fish={'id':'ai:whitefish','name':'Pan-fried fish pieces','source':'AI estimate — not database verified','isAiEstimate':True,'nutrients':{'calories':105,'protein':20,'carbs':0,'fat':3},'portions':[]}
  s.cache_estimate(fish)
  rice=s.food('cofid:11-858');salmon=s.food('cofid:16-359')
  plan={'replace':True,'components':[{'label':'Salmon','query':'salmon baked','sourceId':'cofid:invented','previousItemId':'fish-row','quantity':190,'unit':'g','basis':'photo'},{'label':'Basmati rice','query':'basmati rice boiled','sourceId':rice['id'],'previousItemId':'rice-row','quantity':200,'unit':'g','basis':'photo'}],'message':'Updated fish to salmon','question':''}
  monkeypatch.setattr(vision.httpx,'post',lambda url,**kw:httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(plan)}]}}]},request=httpx.Request('POST',url)))
  def select(entries):
   assert salmon['id'] in {f['id'] for f in entries[0]['candidates']}
   return {0:salmon}
  monkeypatch.setattr(vision,'select_sources',select)
  r=c.post('/api/refine',json={'message':'It is salmon','items':[{'id':'fish-row','food':fish,'grams':140},{'id':'rice-row','food':rice,'grams':150}]} )
  assert r.status_code==200,r.text
  items=r.json()['items'];assert len(items)==2
  assert items[0]['food']['id']==salmon['id'] and items[0]['grams']==140
  assert items[1]['food']['id']==rice['id'] and items[1]['grams']==150
  assert items[0]['food']['nutrients']['calories']*1.4==pytest.approx(324.8)
  assert r.json()['totals']['calories']>147


def test_cooked_fish_correction_cannot_select_raw_salmon(tmp_path):
 from backend.estimation import ingredient_candidates
 with TestClient(create_app(tmp_path/'prep.sqlite')) as c:
  candidates=ingredient_candidates(c.app.state.store.foods(),'Salmon, farmed, raw','Pan-fried salmon pieces')
  assert candidates
  assert all('raw' not in f['name'].lower() for f in candidates)
  assert any('baked' in f['name'].lower() or 'grilled' in f['name'].lower() for f in candidates)


def test_raw_recipe_fish_is_still_available(tmp_path):
 from backend.estimation import ingredient_candidates
 with TestClient(create_app(tmp_path/'raw.sqlite')) as c:
  candidates=ingredient_candidates(c.app.state.store.foods(),'salmon farmed raw','Raw salmon ingredient')
  assert any(f['id']=='cofid:16-356' for f in candidates)


def test_missing_unit_with_existing_gram_estimate_is_usable():
 c=vision.IngredientEstimate(label='Salmon',query='salmon cooked',unit='',quantity=None,estimatedGrams=140)
 assert c.unit=='g' and c.estimatedGrams==140


def test_missing_unit_for_unknown_quantity_is_not_invented():
 from pydantic import ValidationError
 with pytest.raises(ValidationError):vision.IngredientEstimate(label='Milk',query='milk',unit='',quantity=2)
