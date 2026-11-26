import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.cooking import cooking_key, cooking_variants
from backend.main import create_app

COFID=json.loads((Path(__file__).parent.parent/'data'/'cofid-normalized.json').read_text())


def test_cooking_key_splits_food_from_method():
    assert cooking_key('Mushrooms, white, fried in corn oil')==('mushrooms, white','fried in corn oil')
    assert cooking_key('Mushrooms, white, raw')==('mushrooms, white','raw')
    # Words after the method still describe the food, so they stay in its key.
    assert cooking_key('Potatoes, old, boiled in salted water, flesh only')==('potatoes, old, flesh only','boiled in salted water')


def test_cooking_key_refuses_names_it_cannot_split_safely():
    assert cooking_key('Bread, white, sliced') is None  # no cooking step named
    assert cooking_key('Potatoes, old, baked, flesh only, weighed with skin') is None  # weight includes inedible parts


def test_variants_are_the_same_food_cooked_differently():
    raw=next(f for f in COFID if f['name']=='Mushrooms, white, raw')
    names={f['name'] for f in cooking_variants(raw,COFID)}
    assert {'Mushrooms, white, fried in corn oil','Mushrooms, white, fried in salted butter','Mushrooms, white, stewed in unsalted water'}<=names
    assert raw['name'] not in names and not any('weighed with' in n for n in names)
    assert cooking_variants({'id':'off:1','name':'Tesco mushrooms','source':'Open Food Facts'},COFID)==[]


def test_endpoint_returns_variants_for_each_requested_food(tmp_path):
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        raw=next(f for f in COFID if f['name']=='Mushrooms, white, raw')
        result=client.post('/api/cooking-variants',json={'ids':[raw['id'],'off:unknown']}).json()
    assert any(f['name']=='Mushrooms, white, fried in corn oil' for f in result[raw['id']])
    assert result['off:unknown']==[]
