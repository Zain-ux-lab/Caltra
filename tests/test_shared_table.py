import pytest
from backend import estimation


@pytest.mark.parametrize('source',['Cauliflower cheese, retail','Macaroni cheese','Broccoli with cheese sauce'])
def test_plain_baked_cheese_rejects_different_major_ingredients(source):
 assert not estimation.preparation_matches({'name':source},'Baked cheese dish baked cheese in oil')


def test_explicit_cheese_vegetable_dish_still_matches():
 assert estimation.preparation_matches({'name':'Cauliflower cheese, retail'},'Cauliflower cheese')
 assert estimation.preparation_matches({'name':'Cheese, Feta'},'Baked feta cheese')


def test_uncertain_pastry_and_cheese_get_identity_questions():
 assert 'filling' in estimation.clarification('Börek and flatbread slices').lower()
 assert 'cheese' in estimation.clarification('Baked cheese dish').lower()
 assert estimation.clarification('Baked feta cheese')==''


def test_wrong_cheese_candidate_cannot_be_selected(tmp_path,monkeypatch):
 from backend.store import Store
 from backend import vision
 store=Store(tmp_path/'table.sqlite');store.seed()
 seen=[]
 def select(entries):
  for e in entries:
   seen.extend(f['name'] for f in e['candidates'])
   assert all('cauliflower' not in f['name'].lower() for f in e['candidates'])
  return {}
 monkeypatch.setattr(vision,'select_sources',select)
 r=estimation.resolve_observation({'foods':[{'label':'Baked cheese dish','query':'baked cheese','estimatedGrams':120,'visibleCount':1,'components':[]}],'description':'Cheese in a small ceramic dish','question':''},store)
 assert not r['items']


def test_scope_is_sent_to_provider_and_cache_separated(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 from backend import vision
 from PIL import Image
 import io,json,httpx
 monkeypatch.setenv('GEMINI_API_KEY','test-key')
 calls=[]
 def provider(url,**kwargs):
  calls.append(kwargs['json'])
  result={'foods':[],'question':'Did you eat any shared bread or spreads?','description':'Two plates','scopeSummary':'Nearest plate only','unconfirmedExtras':['Butter','Jam','Honey','Shared bread']}
  return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
 monkeypatch.setattr(vision.httpx,'post',provider)
 data=io.BytesIO();Image.new('RGB',(10,10),'red').save(data,format='JPEG')
 with TestClient(create_app(tmp_path/'table.sqlite')) as c:
  for scope in ('myPlate','allVisible'):
   r=c.post('/api/recognize',data={'scope':scope},files={'file':('fixture.jpg',data.getvalue(),'image/jpeg')})
   assert r.status_code==200,r.text
   assert 'Butter' in r.json()['unconfirmedExtras']
  assert c.post('/api/recognize',data={'scope':'invalid'},files={'file':('fixture.jpg',data.getvalue(),'image/jpeg')}).status_code==422
 assert 'nearest' in calls[0]['contents'][0]['parts'][0]['text'].lower()
 assert 'all plates' in calls[1]['contents'][0]['parts'][0]['text'].lower()
 guidance=calls[0]['systemInstruction']['parts'][0]['text'].lower()
 assert 'coffee' in guidance and 'visible butter' in guidance


def test_same_photo_with_a_different_plate_scope_does_not_reuse_cache(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 from backend import vision
 from PIL import Image
 import io
 calls=[]
 def recognize(data,note='',angle=None):
  calls.append(note)
  return {'foods':[{'label':'Cooked basmati rice','query':'cooked basmati rice','estimatedGrams':100,'visibleCount':1,'components':[]}],'question':'','description':'Synthetic rice','notice':''}
 monkeypatch.setattr(vision,'recognize',recognize)
 monkeypatch.setattr(vision,'select_sources',lambda entries:{i:e['candidates'][0] for i,e in enumerate(entries)})
 data=io.BytesIO();Image.new('RGB',(10,10),'red').save(data,format='JPEG')
 with TestClient(create_app(tmp_path/'cache.sqlite')) as c:
  for scope in ('myPlate','myPlate','allVisible'):
   r=c.post('/api/recognize',data={'scope':scope},files={'file':('fixture.jpg',data.getvalue(),'image/jpeg')})
   assert r.status_code==200,r.text
   assert r.json()['items']
 assert len(calls)==2
 assert 'nearest' in calls[0] and 'all plates' in calls[1]
