import io
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

from backend.assistant import validate_reply

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'test.sqlite')) as c:
        yield c


def test_cached_food_to_diary_and_recipe(client):
    results=client.get('/api/foods?q=rice%20white%20long-grain').json()['foods']
    food=next(f for f in results if f['id']=='168878')
    meal={'id':'test','name':'Lunch','date':'2026-10-18','items':[{'id':'one','food':food,'grams':150,'quantityKind':'measured'}]}
    saved=client.post('/api/meals',json=meal)
    assert saved.status_code==200
    assert saved.json()['totals']['calories']==195
    meal['items'][0]['grams']=200
    client.post('/api/meals',json=meal)
    assert len(client.get('/api/meals').json())==1
    assert client.get('/api/export').json()['meals'][0]['totals']['calories']==260
    recipe=client.post('/api/recipes',json={'name':'Family rice','items':meal['items'],'yieldGrams':400})
    assert recipe.status_code==200
    assert recipe.json()['nutrients']['calories']==65
    client.delete('/api/meals/test')
    assert client.get('/api/meals').json()==[]


def test_server_does_not_trust_client_nutrition(client):
    food=client.get('/api/foods?q=rice').json()['foods'][0]
    food['nutrients']['calories']=1
    r=client.post('/api/meals',json={'id':'test','name':'x','date':'2026-10-18','items':[{'id':'one','food':food,'grams':100}]})
    assert r.status_code==200
    assert r.json()['totals']['calories']!=1


def test_bad_image_and_foreign_origin_rejected(client):
    assert client.post('/api/recognize',files={'file':('x.png',b'not image','image/png')}).status_code==400
    assert client.post('/api/meals',json={},headers={'origin':'https://evil.example'}).status_code==403


def test_assistant_cannot_invent_nutrients_or_edit_unknown_item():
    items=[{'id':'one'}]
    assert validate_reply({'message':'Try this','actions':[{'type':'set_grams','itemId':'one','grams':100}]},items)['actions'][0]['grams']==100
    for action in [{'type':'set_grams','itemId':'unknown','grams':100},{'type':'set_grams','itemId':'one','grams':-1},{'type':'set_nutrients','calories':100}]:
        with pytest.raises(ValueError): validate_reply({'message':'x','actions':[action]},items)


def test_empty_or_incomplete_meal_cannot_save(client):
    assert client.post('/api/meals',json={'id':'x','name':'Lunch','date':'2026-10-18','items':[]}).status_code==422


def test_plural_classifier_label_finds_singular_database_food(client):
    found=client.get('/api/foods?q=beignets').json()['foods']
    assert any(f['name']=='Beignet' for f in found)


def test_specific_cookie_name_offers_labelled_alternatives(client):
    result=client.get('/api/foods?q=Sticky%20toffee%20pudding%20cookie').json()
    assert result['matchType']=='related'
    assert result['foods']
    assert all('cookie' in f['name'].lower() for f in result['foods'])
    assert 'not an exact match' in result['warning'].lower()


def test_search_recovers_typo_without_unrelated_results(client):
    result=client.get('/api/foods?q=choclate%20cookie').json()
    assert any('chocolate' in f['name'].lower() and 'cookie' in f['name'].lower() for f in result['foods'])
    assert client.get('/api/foods?q=zxqvw').json()['foods']==[]
