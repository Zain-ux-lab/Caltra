import io
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

from backend import vision


def photo():
    out=io.BytesIO();Image.new('RGB',(20,20),'yellow').save(out,format='PNG');return out.getvalue()


def test_repeated_photo_reuses_successful_result_across_restart(tmp_path,monkeypatch):
    calls=[]
    def identify(data):
        calls.append(1)
        return {'foods':[{'label':'Cheese omelette','query':'omelet','estimatedGrams':200+len(calls)*20,'visibleCount':1}],'description':'omelet','question':'','notice':'Estimate'}
    monkeypatch.setattr(vision,'recognize',identify)
    monkeypatch.setattr(vision,'select_sources',lambda entries:{0:next(f for f in entries[0]['candidates'] if f['id']=='2707212')})
    path=tmp_path/'test.sqlite'
    with TestClient(create_app(path)) as client:
        first=client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')}).json()
        second=client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')}).json()
        assert first['foods']==second['foods']
    with TestClient(create_app(path)) as client:
        third=client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')}).json()
        assert first['foods']==third['foods']
    assert len(calls)==1


def test_failed_match_is_not_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:{})
    calls=[]
    def identify(data):
        calls.append(1)
        return {'foods':[{'label':'Cheese omelette','query':'omelet','estimatedGrams':220}],'description':'omelet','question':'','notice':'Estimate'}
    monkeypatch.setattr(vision,'recognize',identify)
    monkeypatch.setattr(vision,'select_sources',lambda entries:{0:None})
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        for _ in range(2):client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')})
    assert len(calls)==2


def test_photo_note_reaches_model_and_changes_cache_key(tmp_path,monkeypatch):
    calls=[]
    def identify(data,note=''):
        calls.append(note)
        return {'foods':[{'label':'Rice','query':'cooked white rice','estimatedGrams':100,'visibleCount':1}],'description':note,'question':'','notice':'Estimate'}
    monkeypatch.setattr(vision,'recognize',identify)
    monkeypatch.setattr(vision,'select_sources',lambda entries:{0:entries[0]['candidates'][0]})
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        for note in ['basmati rice, no oil','basmati rice, no oil','salmon and rice']:
            response=client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')},data={'note':note})
            assert response.status_code==200
            assert response.json()['description']==note
        response=client.post('/api/recognize',files={'file':('meal.png',photo(),'image/png')},data={'note':'x'*2001})
        assert response.status_code==422
    assert calls==['basmati rice, no oil','salmon and rice']
