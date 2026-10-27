import io,json,httpx
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

from backend import vision


def picture(color):
 out=io.BytesIO();Image.new('RGB',(20,20),color).save(out,format='PNG');return out.getvalue()


def test_second_angle_sent_in_same_model_request(monkeypatch):
 monkeypatch.setenv('GEMINI_API_KEY','test-key')
 def respond(url,**kwargs):
  parts=kwargs['json']['contents'][0]['parts']
  assert len([p for p in parts if 'inlineData' in p])==2
  assert 'same meal' in parts[0]['text'] and 'once' in parts[0]['text']
  result={'foods':[],'question':'','description':'Two angles'}
  return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
 monkeypatch.setattr(vision.httpx,'post',respond)
 assert vision.recognize(picture('red'),'',picture('blue'))['description']=='Two angles'


def test_second_angle_changes_analysis_cache_key(tmp_path,monkeypatch):
 calls=[]
 def identify(data,note='',angle=None):
  calls.append(angle)
  return {'foods':[{'label':'Cookie','query':'cookie','visibleCount':1,'estimatedGrams':100}],'question':'','description':'Cookie','notice':'Estimate'}
 monkeypatch.setattr(vision,'recognize',identify)
 monkeypatch.setattr(vision,'select_sources',lambda entries:{0:next(f for f in entries[0]['candidates'] if f['name']=='Cookie, NFS')})
 with TestClient(create_app(tmp_path/'test.sqlite')) as client:
  for angle in [None,picture('blue'),picture('blue'),picture('green')]:
   files={'file':('main.png',picture('red'),'image/png')}
   if angle:files['angle']=('side.png',angle,'image/png')
   assert client.post('/api/recognize',files=files).status_code==200
 assert len(calls)==3
 assert calls[0] is None


def test_empty_side_photo_is_rejected(tmp_path):
 with TestClient(create_app(tmp_path/'store.sqlite')) as client:
  r=client.post('/api/recognize',files={'file':('main.png',picture('red'),'image/png'),'angle':('empty.png',b'','image/png')})
  assert r.status_code==400
