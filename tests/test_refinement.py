import pytest
from fastapi.testclient import TestClient
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

from backend import vision

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'food.sqlite')) as client:yield client


def test_correction_replaces_generic_dish_and_favorite_reuses_it(client,monkeypatch):
    omelet=next(f for f in client.get('/api/foods?q=omelet%20cheese').json()['foods'] if f['id']=='2707212')
    current={'id':'old','food':omelet,'grams':200,'quantityKind':'estimated'}
    plan={'replace':True,'components':[{'label':'Whole eggs','query':'Egg whole raw fresh','quantity':2,'unit':'medium','estimatedGrams':88,'basis':'user'},{'label':'Egg whites','query':'Egg white raw fresh','quantity':30,'unit':'g','estimatedGrams':30,'basis':'user'}],'message':'Updated to eggs and egg whites.','question':'Any cheese?'}
    monkeypatch.setattr(vision,'refine',lambda *args:plan)
    store=client.app.state.store
    eggs=next(f for f in store.foods() if f['name']=='Egg, whole, raw, fresh')
    whites=next(f for f in store.foods() if f['name']=='Egg, white, raw, fresh')
    monkeypatch.setattr(vision,'select_sources',lambda entries:{0:eggs,1:whites})
    result=client.post('/api/refine',json={'message':'2 medium eggs plus 30g whites, nothing else','items':[current],'version':4}).json()
    assert result['version']==4
    assert len(result['items'])==2
    assert [i['grams'] for i in result['items']]==[88,30]
    assert result['totals']['calories']==pytest.approx(141.44)
    assert all(i['food']['id']!=omelet['id'] for i in result['items'])
    # Client nutrient edits cannot alter remembered meals or the diary.
    result['items'][0]['food']['nutrients']['calories']=1
    favorite=client.post('/api/favorites',json={'name':'My omelette','items':result['items'],'observation':'Egg omelette with whites'}).json()
    assert favorite['totals']['calories']==pytest.approx(141.44)
    assert client.get('/api/favorites').json()[0]['id']==favorite['id']
    saved=client.post('/api/meals',json={'id':'today','name':favorite['name'],'date':'2026-10-19','items':favorite['items']}).json()
    assert saved['totals']==favorite['totals']
    client.delete('/api/favorites/'+favorite['id'])
    assert client.get('/api/favorites').json()==[]
    assert len(client.get('/api/meals').json())==1


def test_unresolved_correction_does_not_partially_replace_meal(client,monkeypatch):
    monkeypatch.setattr(vision,'refine',lambda *args:{'replace':True,'components':[{'label':'unknown thing','query':'zxqvw','quantity':10,'unit':'g','estimatedGrams':10,'basis':'user'}],'message':'','question':'What is it?'})
    response=client.post('/api/refine',json={'message':'unknown thing','items':[]}).json()
    assert response['items'] is None
    assert 'unchanged' in response['message']


def test_question_only_keeps_current_items(client,monkeypatch):
    monkeypatch.setattr(vision,'refine',lambda *args:{'replace':False,'components':[],'message':'Do you know the egg count?','question':'How many eggs?'})
    result=client.post('/api/refine',json={'message':'I do not know the recipe','items':[]}).json()
    assert result['items'] is None and result['question']=='How many eggs?'


def test_partial_meal_correction_cannot_discard_unresolved_cheese(client,monkeypatch):
    store=client.app.state.store
    eggs=next(f for f in store.foods() if f['name']=='Egg, whole, raw, fresh')
    def refine(message,items,history,observation,unresolved):
        assert unresolved==['Cheddar cheese']
        return {'replace':True,'components':[{'label':'Eggs','query':'Egg whole raw fresh','sourceId':eggs['id'],'quantity':2,'unit':'medium','estimatedGrams':88,'basis':'user'}],'message':'Updated egg count','question':''}
    monkeypatch.setattr(vision,'refine',refine)
    result=client.post('/api/refine',json={'message':'2 eggs','items':[{'id':'egg','food':eggs,'grams':100}],'unresolved':['Cheddar cheese']}).json()
    assert result['items'] is None
    assert 'Cheddar cheese' in result['message']


def test_followup_question_reaches_refinement_with_short_answer(client,monkeypatch):
    def refine(message,items,history,observation,unresolved):
        assert message=='2 eggs and 30g egg white'
        assert history[-1]=={'role':'assistant','message':'How many eggs were used?'}
        return {'replace':False,'components':[],'message':'Need cheese quantity','question':'How much cheese?'}
    monkeypatch.setattr(vision,'refine',refine)
    response=client.post('/api/refine',json={'message':'2 eggs and 30g egg white','items':[],'pendingQuestion':'How many eggs were used?'} )
    assert response.status_code==200


def test_recipe_keeps_resolved_ingredients_visible_when_baking_powder_missing(client,monkeypatch):
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i in range(len(entries))})
    oats=client.app.state.store.food('173904')
    monkeypatch.setattr(vision,'refine',lambda *args:{'replace':True,'components':[{'label':'Rolled oats','query':'oats dry','sourceId':oats['id'],'quantity':1,'unit':'cup','estimatedGrams':80,'basis':'user'},{'label':'Baking powder','query':'zxqvw','quantity':4,'unit':'g','basis':'user'}],'message':'Recipe ingredients','question':'How many portions?'})
    r=client.post('/api/refine',json={'message':'recipe','items':[{'id':'o','food':oats,'grams':80}]}).json()
    assert r['items'] and r['items'][0]['label']=='Rolled oats'
    assert r['missing']==['Baking powder']
    assert 'partial' in r['message'].lower()


def test_partial_recipe_can_update_oats_while_preserving_missing_powder(client,monkeypatch):
    oats=client.app.state.store.food('173904')
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i in range(len(entries))})
    monkeypatch.setattr(vision,'refine',lambda *args:{'replace':True,'components':[{'label':'Rolled oats','query':'oats dry','sourceId':oats['id'],'quantity':100,'unit':'g','basis':'user'},{'label':'Baking powder','query':'zxqvw','quantity':4,'unit':'g','basis':'user'}],'message':'Updated oats','question':''})
    r=client.post('/api/refine',json={'message':'oats 100g','items':[{'id':'o','food':oats,'grams':81}],'unresolved':['Baking powder']}).json()
    assert r['items'][0]['grams']==100
    assert r['missing']==['Baking powder']


def test_correction_label_cannot_hide_wrong_resolved_source(client,monkeypatch):
    egg=next(f for f in client.app.state.store.foods() if f['name']=='Egg, whole, raw, fresh')
    monkeypatch.setattr(vision,'refine',lambda *args:{'replace':True,'components':[{'label':'Egg whites','query':'Egg white raw','sourceId':egg['id'],'quantity':30,'unit':'g','basis':'user'}],'message':'Updated','question':''})
    r=client.post('/api/refine',json={'message':'30g whites','items':[{'id':'e','food':egg,'grams':50}],'unresolved':['Egg whites']}).json()
    assert r['items'] is None
    assert 'Egg whites' in r['message']
