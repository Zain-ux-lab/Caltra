import math
import pytest
from backend.nutrition import normalize_food, calculate
from backend.store import Store as _Store

def Store(*args,**kwargs):
    # Explicit legacy-catalog fixture for source-parser/migration regressions.
    return _Store(*args,uk_only=False,**kwargs)


def record():
    return {'fdcId': 1, 'description': 'Rice, cooked', 'dataType': 'SR Legacy', 'foodNutrients': [
        {'nutrient': {'id': n, 'unitName': u}, 'amount': v}
        for n, u, v in [(1008,'kcal',130),(1003,'g',2.7),(1004,'g',0.3),(1005,'g',28.2)]]}


def test_weighted_totals_use_source_energy():
    food = normalize_food(record())
    assert calculate([{'food': food, 'grams': 150}]) == {'calories':195.0,'protein':4.05,'fat':0.45,'carbs':42.3}


def test_missing_is_not_zero_and_kj_converts():
    raw = record()
    raw['foodNutrients'][0] = {'nutrient': {'id':1062,'unitName':'kJ'}, 'amount':418.4}
    assert normalize_food(raw)['nutrients']['calories'] == pytest.approx(100)
    raw['foodNutrients'].pop()
    assert normalize_food(raw)['nutrients']['carbs'] is None
    with pytest.raises(ValueError):
        calculate([{'food':normalize_food(raw),'grams':100}])


@pytest.mark.parametrize('grams', [0,-1,float('nan'),float('inf'),100001])
def test_invalid_portions_rejected(grams):
    with pytest.raises(ValueError):
        calculate([{'food':normalize_food(record()),'grams':grams}])


def test_wrong_nutrient_unit_does_not_become_grams():
    raw = record()
    raw['foodNutrients'][1]['nutrient']['unitName'] = 'mg'
    assert normalize_food(raw)['nutrients']['protein'] is None


def test_diary_upsert_persists_and_deletes(tmp_path):
    path = tmp_path/'test.db'
    store = Store(path)
    meal = {'id':'one', 'name':'Lunch', 'date':'2026-10-18','items':[{'id':'i','food':normalize_food(record()),'grams':150,'quantityKind':'measured'}]}
    store.save_meal(meal)
    meal['items'][0]['grams'] = 200
    store.save_meal(meal)
    saved = Store(path).meals()
    assert len(saved) == 1
    assert saved[0]['totals']['calories'] == 260
    store.delete_meal('one')
    assert store.meals() == []


def test_home_recipe_uses_cooked_yield_not_raw_weight():
    from backend.nutrition import make_recipe
    food = normalize_food(record())
    recipe = make_recipe('Mum’s rice', [{'food':food,'grams':200}], 400, 'r1')
    assert recipe['nutrients']['calories'] == 65
    assert calculate([{'food':recipe,'grams':150}])['calories'] == 97.5
    with pytest.raises(ValueError):
        make_recipe('Rice', [{'food':food,'grams':200}], 0, 'r1')


def test_servings_do_not_duplicate_counts_or_offer_unspecified_quantity():
    raw=record()
    raw['foodPortions']=[{'amount':1,'portionDescription':'1 cup','gramWeight':196},{'amount':1,'portionDescription':'Quantity not specified','gramWeight':245}]
    assert normalize_food(raw)['portions']==[{'label':'1 cup','grams':196}]
