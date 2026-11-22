from fastapi.testclient import TestClient
from backend import vision
from backend.main import create_app
from backend.restaurant_links import chain_link

PANCAKES={'name':'Buttermilk pancakes','brand':"Bill's",'nutritionBasis':'serving','nutrients':{'calories':1120,'protein':24,'carbs':140,'fat':48,'sugars':60}}


def test_chain_link_needs_the_whole_chain_name():
    assert chain_link('Bills pancakes')['brand']=="Bill's"
    assert chain_link("Bill's pancakes")['brand']=="Bill's"
    assert chain_link('pizza hut margherita')['brand']=='Pizza Hut'
    assert chain_link('pizza') is None and chain_link('burger') is None


def test_a_menu_entry_is_saved_per_serving_and_found_next_time(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'select_generic_references',lambda entries:(_ for _ in ()).throw(AssertionError('serving foods get no vitamin estimate')))
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        first=client.get('/api/foods',params={'q':'Bills pancakes'}).json()
        assert first['chain']['brand']=="Bill's" and first['matchType']!='matched'
        food=client.post('/api/products',json=PANCAKES).json()
        assert food['nutritionBasis']=='serving' and food['source']=='Your menu entry'
        again=client.get('/api/foods',params={'q':"Bill's pancakes"}).json()
        assert again['foods'][0]['id']==food['id']
        meal=client.post('/api/meals',json={'id':'m','name':'Brunch','date':'2026-11-21','items':[{'id':'p','food':food,'grams':1,'quantityBasis':'user'}]}).json()
        assert meal['totals']=={'calories':1120,'protein':24,'carbs':140,'fat':48}


def test_per_100_labels_keep_their_tighter_limits(tmp_path):
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        response=client.post('/api/products',json={**PANCAKES,'nutritionBasis':'g'})
    assert response.status_code==422 and 'per-100' in response.json()['detail']
