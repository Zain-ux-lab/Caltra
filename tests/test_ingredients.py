import pytest
from backend.store import Store as _Store

def Store(*args,**kwargs):
    # Explicit legacy-catalog fixture for source-parser/migration regressions.
    return _Store(*args,uk_only=False,**kwargs)
from backend.nutrition import calculate
from backend import estimation

@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path/'food.sqlite');store.seed();return store


def test_breakfast_components_use_database_quantities_and_arithmetic(store,monkeypatch):
    components=[
        {'label':'Whole eggs','query':'Egg whole raw fresh','quantity':2,'unit':'medium','estimatedGrams':88,'basis':'user'},
        {'label':'Egg whites','query':'Egg white raw fresh','quantity':30,'unit':'g','estimatedGrams':30,'basis':'user'},
        {'label':'Reduced fat cheddar','query':'Cheese cheddar reduced fat','quantity':25,'unit':'g','estimatedGrams':25,'basis':'user'},
        {'label':'Spinach','query':'Spinach raw','quantity':None,'unit':'g','estimatedGrams':30,'basis':'assumed'},
        {'label':'Tomato','query':'Tomatoes red ripe raw','quantity':None,'unit':'g','estimatedGrams':60,'basis':'assumed'},
        {'label':'Seeds','query':'Mixed seeds','quantity':None,'unit':'g','estimatedGrams':3,'basis':'assumed'},
    ]
    ids=['171287','172183','2705730','168462','170457','2707589']
    # Pick by exact source description so this exercises real cached records.
    names=['Egg, whole, raw, fresh','Egg, white, raw, fresh','Cheese, Cheddar, reduced fat','Spinach, raw','Tomatoes, red, ripe, raw, year round average','Mixed seeds']
    foods=[next(f for f in store.foods() if f['name']==name) for name in names]
    monkeypatch.setattr(estimation.vision,'select_sources',lambda entries:{i:foods[i] for i in range(len(entries))})
    items,missing=estimation.resolve_components(components,store)
    assert not missing
    assert len(items)==6
    assert items[0]['grams']==88
    assert items[0]['quantityKind']=='estimated'
    totals=calculate(items)
    assert 240<totals['calories']<280
    assert 20<totals['protein']<28
    assert 10<totals['fat']<20
    assert all(i['food']['source']=='USDA FoodData Central' for i in items)


def test_components_and_whole_dish_cannot_be_counted_together(store,monkeypatch):
    egg=next(f for f in store.foods() if f['name']=='Egg, whole, raw, fresh')
    monkeypatch.setattr(estimation.vision,'select_sources',lambda entries:{0:egg})
    result=estimation.resolve_observation({'foods':[{'label':'Omelette','query':'omelet','estimatedGrams':200,'visibleCount':1,'components':[{'label':'Egg','query':'Egg whole raw fresh','quantity':2,'unit':'medium','estimatedGrams':88,'basis':'photo'}]}],'description':'omelette','question':'How many eggs?','notice':'Estimate'},store)
    assert len(result['items'])==1
    assert result['items'][0]['food']['id']==egg['id']
    assert result['foods'][0]['matches']==[]


def test_unknown_household_unit_does_not_use_unrelated_serving():
    food={'portions':[{'label':'1 cup','grams':135}]}
    with pytest.raises(ValueError):estimation.component_grams({'quantity':2,'unit':'medium','estimatedGrams':None},food)


def test_null_weight_without_source_unit_remains_unmatched(store,monkeypatch):
    egg=next(f for f in store.foods() if f['name']=='Egg, whole, raw, fresh')
    monkeypatch.setattr(estimation.vision,'select_sources',lambda entries:{0:egg})
    items,missing=estimation.resolve_components([{'label':'egg','query':'Egg whole raw fresh','quantity':None,'unit':'g','estimatedGrams':None,'basis':'photo'}],store)
    assert items==[] and missing==['egg']


def test_provider_schema_is_flat_but_runtime_validation_remains_strict():
    from backend.vision import provider_schema,RefinementPlan
    from pydantic import ValidationError
    import json
    schema=provider_schema(RefinementPlan)
    text=json.dumps(schema)
    assert '$ref' not in text and '$defs' not in text and 'exclusiveMinimum' not in text
    with pytest.raises(ValidationError):
        RefinementPlan.model_validate({'replace':True,'message':'x','components':[{'label':'egg','query':'egg','quantity':-1}]})


def test_unresolved_identity_requires_all_food_terms_in_one_source():
    from backend.estimation import remaining_unresolved
    items=[{'food':{'name':'Egg, whole, raw, fresh'},'portionLabel':'2 medium eggs'},{'food':{'name':'Oil, sunflower'},'portionLabel':'5g'}]
    assert remaining_unresolved(['Egg whites','Olive oil'],items)==['Egg whites','Olive oil']
    assert remaining_unresolved(['Reduced-fat cheddar'],[{'food':{'name':'Cheese, Cheddar, reduced fat'},'portionLabel':'25g'}])==[]


@pytest.mark.parametrize('query',['tomato raw','raw tomato','tomatoes raw'])
def test_singular_tomato_retrieves_raw_tomato(store,query):
    candidates=estimation.ingredient_candidates(store.foods(),query,'Tomato raw')
    assert candidates
    assert 'tomato' in candidates[0]['name'].lower()
    assert 'raw' in candidates[0]['name'].lower()


def test_generic_rice_and_fish_require_specificity_but_confirmed_types_do_not():
    assert 'fish' in estimation.clarification('Pan-fried fish').lower()
    assert 'rice' in estimation.clarification('Cooked white rice').lower()
    assert estimation.clarification('Grilled salmon')==''
    assert estimation.clarification('Cooked basmati rice')==''


def test_oat_cake_cannot_be_logged_as_snack_cake(store,monkeypatch):
    cake=next(f for f in store.foods() if f['name']=='Snack cake, chocolate')
    monkeypatch.setattr(estimation.vision,'select_sources',lambda entries:{0:cake})
    d=estimation.resolve_observation({'foods':[{'label':'Chocolate oat cake','query':'oat cake','estimatedGrams':800,'visibleCount':1,'components':[]}],'question':'','description':'Oat cake'},store)
    assert d['items']==[]
    assert d['missing']==['Chocolate oat cake']
    assert 'ingredient' in d['question'].lower()


def test_ingredient_retains_identified_name(store,monkeypatch):
    oats=store.food('173904')
    monkeypatch.setattr(estimation.vision,'select_sources',lambda entries:{0:oats})
    items,missing=estimation.resolve_components([{'label':'Rolled oats','query':'oats dry','quantity':1,'unit':'cup','estimatedGrams':80,'basis':'user'}],store)
    assert not missing
    assert items[0]['label']=='Rolled oats'
    assert items[0]['grams']==81


def test_cup_conversion_uses_source_tablespoon_weight_not_model_guess(store):
    cocoa=store.food('2705587')
    assert estimation.component_grams({'quantity':0.25,'unit':'cup','estimatedGrams':25},cocoa)==20


def test_baking_powder_seed_includes_teaspoon_amount(store):
    powder=store.food('172803')
    assert powder and powder['source']=='USDA FoodData Central'
    assert estimation.component_grams({'quantity':1,'unit':'teaspoon','estimatedGrams':4},powder)==4.6


def test_plain_salmon_candidates_exclude_known_added_fat_recipe(store):
    candidates=estimation.ingredient_candidates(store.foods(),'salmon cooked','Cooked salmon')
    assert candidates and all(f['id'] not in {'2706285','2706286','2706287'} for f in candidates)
    assert store.food('2706285')['includesAddedFat'] is True


def test_explicit_oil_preparation_can_use_added_fat_reference(store):
    candidates=estimation.ingredient_candidates(store.foods(),'salmon baked','Salmon baked with oil')
    assert any(f['id']=='2706286' for f in candidates)


def test_existing_salmon_source_cannot_bypass_preparation_filter(store,monkeypatch):
    bad=store.food('2706285')
    def select(entries):
        assert all(f['id'] not in {'2706285','2706286','2706287'} for f in entries[0]['candidates'])
        return {0:entries[0]['candidates'][0]}
    monkeypatch.setattr(estimation.vision,'select_sources',select)
    items,missing=estimation.resolve_components([{'label':'Cooked salmon, no oil','query':'salmon cooked','sourceId':bad['id'],'quantity':180,'unit':'g','basis':'user'}],store,{bad['id']})
    assert not missing and items[0]['grams']==180
    assert not items[0]['food'].get('includesAddedFat')
