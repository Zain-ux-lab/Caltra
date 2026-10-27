import json
import httpx
import pytest
from backend import vision
from backend.search import photo_candidates
from backend.store import Store as _Store

def Store(*args,**kwargs):
    # Explicit legacy-catalog fixture for source-parser/migration regressions.
    return _Store(*args,uk_only=False,**kwargs)

@pytest.fixture
def foods(tmp_path):
    store=Store(tmp_path/'food.sqlite');store.seed();return store.foods()


def test_omelette_cannot_turn_into_cheese_or_omelette_ingredient(foods):
    candidates=photo_candidates(foods,'cheese','Cheesy omelette with seeds')
    assert candidates
    assert all('omelet' in f['name'].lower() for f in candidates)
    assert all('as ingredient' not in f['name'].lower() for f in candidates)
    assert any('with cheese' in f['name'].lower() for f in candidates)


def test_source_picker_accepts_only_candidate_ids(monkeypatch,foods):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    candidates=photo_candidates(foods,'cheese','Cheesy omelette with seeds')
    def respond(url,**kwargs):
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps({'selections':[{'index':0,'sourceId':'2705704'}]})}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',respond)
    with pytest.raises(vision.VisionError):vision.select_sources([{'label':'Cheesy omelette with seeds','candidates':candidates}])


def test_omelette_matching_uses_only_selected_whole_dish(tmp_path,monkeypatch):
    from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

    from fastapi.testclient import TestClient
    monkeypatch.setattr(vision,'recognize',lambda data:{'foods':[{'label':'Cheesy omelette with seeds','query':'cheese','estimatedGrams':200,'visibleCount':1}],'description':'omelette','question':'','notice':'Estimate'})
    monkeypatch.setattr(vision,'select_sources',lambda entries:{0:next(f for f in entries[0]['candidates'] if f['id']=='2707212')})
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        response=client.post('/api/recognize',files={'file':('meal.jpg',b'mocked','image/jpeg')})
        assert response.status_code==200
        result=response.json()['foods'][0]
        assert result['matches'][0]['id']=='2707212'
        assert result['matches'][0]['nutrients']['calories']*2==342
        assert result['matchType']=='approximate'


def test_source_picker_failure_does_not_choose_first_record(tmp_path,monkeypatch):
    from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

    from fastapi.testclient import TestClient
    monkeypatch.setattr(vision,'recognize',lambda data:{'foods':[{'label':'Cheesy omelette','query':'cheese','estimatedGrams':200}],'description':'omelette','question':'','notice':'Estimate'})
    def fail(entries):raise vision.VisionError('Nutrition matching unavailable. Retry.')
    monkeypatch.setattr(vision,'select_sources',fail)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        response=client.post('/api/recognize',files={'file':('meal.jpg',b'mocked','image/jpeg')})
        result=response.json()
        assert response.status_code==200
        assert result['foods'][0]['label']=='Cheesy omelette'
        assert result['foods'][0]['matches']==[]
        assert 'unavailable' in result['notice']
