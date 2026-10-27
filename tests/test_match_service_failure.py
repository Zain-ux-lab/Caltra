from backend import estimation,vision
from backend.store import Store


def fail(entries):raise vision.VisionError('Matching service unavailable')


def guesses(entries):
 return {i:{'nutrients':{'calories':150,'protein':10,'carbs':5,'fat':10},'estimatedGrams':100,'assumptions':'Unverified generic estimate.'} for i,_ in enumerate(entries)}


def test_source_service_failure_still_runs_labelled_fallback(tmp_path,monkeypatch):
 store=Store(tmp_path/'f.sqlite');store.seed()
 monkeypatch.setattr(vision,'select_sources',fail)
 monkeypatch.setattr(vision,'estimate_nutrients',guesses)
 result=estimation.resolve_observation({'foods':[{'label':'Hard boiled egg','query':'egg boiled','estimatedGrams':50,'visibleCount':1},{'label':'Chapati','query':'chapati','estimatedGrams':80,'visibleCount':1}],'description':'Egg and chapati','question':'','notice':''},store,allow_ai=True)
 assert len(result['items'])==2 and not result['missing']
 assert all(i['food']['isAiEstimate'] for i in result['items'])
 assert result['totals']['calories']==195


def test_component_failure_preserves_known_food_and_estimates_rest(tmp_path,monkeypatch):
 store=Store(tmp_path/'f.sqlite');store.seed()
 known=next(f for f in store.foods() if f['name']=='Cucumber, raw, flesh and skin')
 monkeypatch.setattr(vision,'select_sources',fail)
 monkeypatch.setattr(vision,'estimate_nutrients',guesses)
 items,missing=estimation.resolve_components([{'label':'Cucumber','query':'cucumber','sourceId':known['id'],'quantity':50,'unit':'g'},{'label':'Egg','query':'egg boiled','quantity':50,'unit':'g'}],store,[known['id']],allow_ai=True)
 assert not missing and len(items)==2
 assert items[0]['food']['id']==known['id'] and items[1]['food']['isAiEstimate']


def test_both_services_fail_without_inventing_macros(tmp_path,monkeypatch):
 store=Store(tmp_path/'f.sqlite');store.seed()
 monkeypatch.setattr(vision,'select_sources',fail)
 monkeypatch.setattr(vision,'estimate_nutrients',fail)
 r=estimation.resolve_observation({'foods':[{'label':'Egg','query':'egg boiled','estimatedGrams':50}],'description':'Egg','question':'','notice':''},store,allow_ai=True)
 assert r['items']==[] and r['missing']==['Egg'] and r['totals'] is None


def test_boiled_egg_candidate_is_egg_not_egg_noodles(tmp_path):
 from backend.search import photo_candidates
 store=Store(tmp_path/'f.sqlite');store.seed()
 candidates=photo_candidates(store.foods(),'egg boiled','hard boiled egg')
 assert candidates and candidates[0]['name'].lower().startswith('eggs,')
 assert 'boiled' in candidates[0]['name'].lower()


def test_recognize_route_does_not_clear_meal_on_match_failure(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.main import create_app
 monkeypatch.setattr(vision,'recognize',lambda data:{'foods':[{'label':'Hard boiled egg','query':'egg boiled','estimatedGrams':50,'visibleCount':1}],'description':'Egg','question':'','notice':''})
 monkeypatch.setattr(vision,'select_sources',fail)
 monkeypatch.setattr(vision,'estimate_nutrients',guesses)
 with TestClient(create_app(tmp_path/'api.sqlite')) as c:
  r=c.post('/api/recognize',files={'file':('test.jpg',b'mocked','image/jpeg')})
  assert r.status_code==200
  assert r.json()['items'][0]['food']['isAiEstimate']
  assert r.json()['totals']['calories']==75 and not r.json()['missing']
