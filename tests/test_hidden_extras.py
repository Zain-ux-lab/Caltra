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
        assert [e['key'] for e in client.get('/api/hidden-extras').json()]==['oil','butter','milk','sugar','honey']
