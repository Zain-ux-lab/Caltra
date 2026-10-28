import io,json
from datetime import date
import httpx,pytest
from PIL import Image
from backend import vision,estimation


def picture():
 out=io.BytesIO();Image.new('RGB',(16,16),'red').save(out,format='JPEG');return out.getvalue()


def test_valid_photo_survives_overlong_descriptive_metadata(monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test')
 result={'foods':[{'label':'Omelette','query':'omelette','visibleCount':1.0,'estimatedGrams':150,'visualEvidence':'A'*550,'possibleShared':None,'components':None}],'question':'Q'*400,'description':'D'*1400,'unconfirmedExtras':None,'excludedFoods':None,'scopeSummary':None}
 monkeypatch.setattr(vision.httpx,'post',lambda url,**kw:httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url)))
 response=vision.recognize(picture())
 assert response['foods'][0]['visibleCount']==1
 assert len(response['foods'][0]['visualEvidence'])==400
 assert len(response['question'])==300


def test_cut_short_ai_reply_is_reported_without_retry(monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test');calls=[]
 def provider(url,**kw):
  calls.append(1)
  return httpx.Response(200,json={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{"foods":['}]}}]},request=httpx.Request('POST',url))
 monkeypatch.setattr(vision.httpx,'post',provider)
 with pytest.raises(vision.VisionError,match='incomplete'):vision.recognize(picture())
 assert len(calls)==1


def test_changed_ai_preparation_does_not_reuse_old_density(tmp_path,monkeypatch):
 from backend.main import create_app
 from fastapi.testclient import TestClient
 monkeypatch.setattr(vision,'select_sources',lambda entries:{})
 monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:{i:{'nutrients':{'calories':300,'protein':15,'carbs':5,'fat':24},'estimatedGrams':100,'assumptions':'Synthetic oil recipe'} for i,e in enumerate(entries)})
 with TestClient(create_app(tmp_path/'fix.sqlite')) as c:
  food={'id':'ai:cheese','name':'Baked cheese casserole','isAiEstimate':True,'source':'AI estimate — not database verified','nutrients':{'calories':88,'protein':4,'carbs':5,'fat':5},'portions':[]}
  c.app.state.store.cache_estimate(food)
  monkeypatch.setattr(vision,'refine',lambda *a:{'replace':True,'components':[{'label':'Baked cheese casserole in oil','query':'baked cheese in oil','quantity':100,'estimatedGrams':100,'unit':'g','basis':'assumed','previousItemId':'old','sourceId':food['id']}],'message':'Updated oil preparation','question':''})
  r=c.post('/api/refine',json={'message':'This is baked cheese in oil','items':[{'id':'old','food':food,'grams':100}]} )
  assert r.status_code==200,r.text
  assert r.json()['totals']['calories']==300
  assert r.json()['items'][0]['food']['id']!=food['id']


def test_plain_uk_ingredient_has_micros_without_source_selector(tmp_path,monkeypatch):
 from backend.store import Store
 store=Store(tmp_path/'micros.sqlite');store.seed()
 monkeypatch.setattr(vision,'select_sources',lambda entries:{})
 monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:(_ for _ in ()).throw(AssertionError('Plain exact UK ingredient should not need AI guessing')))
 items,missing=estimation.resolve_components([{'label':'Walnuts','query':'walnuts','quantity':15,'unit':'g','basis':'user'}],store,allow_ai=True)
 assert not missing
 assert items[0]['food']['source']=='UK CoFID 2021'
 assert items[0]['food']['nutrients']['magnesium'] is not None
