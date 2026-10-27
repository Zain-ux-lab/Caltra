import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.nutrition import nutrient_coverage, make_recipe


def test_micronutrients_missing_are_not_zero():
 items=[{'grams':50,'food':{'nutrients':{'iron':4,'vitaminC':20}}},{'grams':100,'food':{'nutrients':{}}}]
 values=nutrient_coverage(items)
 assert values['iron']=={'value':2,'complete':False,'missing':1}
 assert values['vitaminD']=={'value':None,'complete':False,'missing':2}


def test_targets_persist_and_reject_invalid_values(tmp_path):
 path=tmp_path/'diary.sqlite'
 with TestClient(create_app(path)) as c:
  assert c.get('/api/targets').json() is None
  target={'calories':2200,'protein':140,'carbs':230,'fat':80}
  assert c.post('/api/targets',json=target).status_code==200
  assert c.post('/api/targets',json={**target,'fat':-2}).status_code==422
 with TestClient(create_app(path)) as c:
  assert c.get('/api/targets').json()==target


def test_calculator_and_ai_fallback(monkeypatch,tmp_path):
 monkeypatch.setenv('GEMINI_API_KEY','')
 with TestClient(create_app(tmp_path/'diary.sqlite')) as c:
  profile={'age':25,'weight':70,'height':175,'sex':'male','activity':'light','goal':'maintain','proteinStyle':'higher','message':'I prefer high protein UK meals','useAI':True}
  r=c.post('/api/targets/suggest',json=profile)
  assert r.status_code==200,r.text
  result=r.json();t=result['targets']
  assert result['restingCalories']==1674
  assert 2200<t['calories']<2400
  assert abs(t['calories']-(4*t['protein']+4*t['carbs']+9*t['fat']))<=5
  assert result['mode']=='calculator'
  assert c.get('/api/targets').json() is None # proposal only
  assert c.post('/api/targets/suggest',json={**profile,'age':15}).status_code==422
  assert c.post('/api/targets/suggest',json={**profile,'pregnantOrBreastfeeding':True}).status_code==422


def test_meal_group_survives_reload_and_old_meals_still_save(tmp_path):
 with TestClient(create_app(tmp_path/'diary.sqlite')) as c:
  food=next(f for f in c.app.state.store.foods() if f['nutrients']['calories'] is not None)
  meal={'id':'breakfast','name':'Breakfast food','date':'2026-10-26','mealType':'breakfast','items':[{'id':'one','food':food,'grams':50}]}
  r=c.post('/api/meals',json=meal)
  assert r.status_code==200,r.text
  assert c.get('/api/meals').json()[0]['mealType']=='breakfast'
  del meal['mealType'];meal['id']='legacy'
  assert c.post('/api/meals',json=meal).status_code==200


def test_recipe_micronutrients_require_complete_inputs():
 nutrients={'calories':100,'protein':10,'carbs':10,'fat':2,'iron':4,'vitaminC':20}
 items=[{'grams':100,'food':{'nutrients':nutrients}},{'grams':100,'food':{'nutrients':{**nutrients,'vitaminC':None}}}]
 r=make_recipe('test',items,100,'recipe')
 assert r['nutrients']['iron']==8
 assert r['nutrients']['vitaminC'] is None


def test_ai_explanation_cannot_replace_targets(monkeypatch):
 from backend import targets
 class Response:
  def raise_for_status(self):pass
  def json(self):return {'candidates':[{'content':{'parts':[{'text':'{"message":"Try spreading protein across meals.","targets":{"calories":900}}'}]}}]}
 monkeypatch.setenv('GEMINI_API_KEY','test-key')
 monkeypatch.setattr(targets.httpx,'post',lambda *a,**kw:Response())
 p=targets.Profile(age=25,weight=70,height=175,sex='male',activity='light',goal='maintain',useAI=True)
 result=targets.suggest(p)
 assert result['mode']=='ai'
 assert result['targets']['calories']>2000
 assert result['aiMessage']=='Try spreading protein across meals.'


def test_uk_micronutrients_and_historical_macro_preservation(tmp_path):
 from backend.store import Store
 import json
 store=Store(tmp_path/'diary.sqlite');store.seed()
 food=next(f for f in store.foods() if f['name']=='Rice, white, basmati, boiled in unsalted water')
 assert food['nutrients']['potassium'] is not None
 assert food['nutrients']['salt']==pytest.approx(food['nutrients']['sodium']*.0025)
 snapshot={**food,'nutrients':{'calories':119,'protein':3,'carbs':26,'fat':1}}
 meal={'id':'old','name':'Old rice','date':'2026-10-20','items':[{'id':'one','food':snapshot,'grams':100}], 'totals':{'calories':119,'protein':3,'carbs':26,'fat':1}}
 with store.connect() as db:db.execute('INSERT INTO meals VALUES (?,?)',('old',json.dumps(meal)))
 enriched=store.meals()[0]
 assert enriched['items'][0]['food']['nutrients']['calories']==119
 assert enriched['totals']['calories']==119
 assert enriched['nutrientTotals']['potassium']['value']==food['nutrients']['potassium']
 with store.connect() as db:
  original=json.loads(db.execute('SELECT data FROM meals').fetchone()[0])
  assert 'potassium' not in original['items'][0]['food']['nutrients']
