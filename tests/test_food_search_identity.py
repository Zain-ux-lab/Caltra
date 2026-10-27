import pytest
from backend.search import search_foods
from backend.estimation import ingredient_candidates
from backend.store import Store as _Store

def Store(*args,**kwargs):
    # Explicit legacy-catalog fixture for source-parser/migration regressions.
    return _Store(*args,uk_only=False,**kwargs)


@pytest.fixture
def records(tmp_path):
    store=Store(tmp_path/'foods.sqlite');store.seed();return store.foods()


@pytest.mark.parametrize('query',['salmon cooked','cooked salmon no oil','salmon fillet','salmon microwaved'])
def test_preparation_and_portion_words_cannot_replace_salmon_identity(records,query):
    found=search_foods(records,query)
    assert found['foods']
    assert all('salmon' in food['name'].lower() for food in found['foods'])
    candidates=ingredient_candidates(records,query,'Cooked salmon, no added oil')
    assert candidates and all('salmon' in food['name'].lower() for food in candidates)
    assert any(food['source']=='UK CoFID 2021' and 'baked' in food['name'].lower() for food in candidates)
    assert all(not food.get('includesAddedFat') for food in candidates)


def test_single_word_ingredient_queries_still_find_salt_and_oil(records):
    for query in ['salt','oil']:
        found=search_foods(records,query)
        assert found['matchType']=='matched' and found['foods']


def test_unknown_food_does_not_match_preparation_alone(records):
    assert search_foods(records,'zxqvw cooked')['foods']==[]


def test_full_usda_generic_catalog_is_seeded_alongside_uk_records(records):
    assert any(f.get('dataType')=='SR Legacy' and 'salmon' in f['name'].lower() and 'cooked, dry heat' in f['name'].lower() for f in records)
    assert any(f.get('dataType')=='Foundation' for f in records)
    assert any(f['source']=='UK CoFID 2021' for f in records)
