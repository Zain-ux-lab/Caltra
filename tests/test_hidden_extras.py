from fastapi.testclient import TestClient
from backend.main import create_app
from backend.hidden_extras import hidden_extras

OIL={'id':'cofid-oil','name':'Oil, vegetable, average','source':'UK CoFID 2021','nutrients':{}}


def test_cofid_fallback_converts_spoons_to_grams():
    extras=hidden_extras([],[OIL])
    assert [e['key'] for e in extras]==['oil']  # records missing from the catalogue are left out
    assert extras[0]['options'][1]=={'label':'1 tbsp','amount':13.8}


def test_usual_product_wins_and_ml_labels_keep_ml():
    milk={'id':'mine','name':'My milk','nutritionBasis':'ml','nutrients':{}}
    extras=hidden_extras([{'category':'milk','food':milk}],[])
    assert extras[0]['food']['id']=='mine' and extras[0]['options'][0]=={'label':'A splash','amount':30}


def test_endpoint_lists_every_extra_from_the_real_catalogue(tmp_path):
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        extras=client.get('/api/hidden-extras').json()
    from backend.hidden_extras import EXTRAS
    assert [e['key'] for e in extras]==[key for _,key,*_ in EXTRAS]  # every CoFID fallback name resolves
    assert {e['group'] for e in extras}=={'Cooking fat','Milk and sweeteners','Sauces and dressings','Cheese and cream'}
    cheese=next(e for e in extras if e['key']=='cheese')
    assert cheese['options']==[{'label':'15 g','amount':15},{'label':'30 g','amount':30}]  # grams, never converted
