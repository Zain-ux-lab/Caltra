from backend import vision
from backend.micronutrients import fill_missing, generic_name
from backend.nutrition import nutrient_coverage

YOGURT={'id':'cofid-yogurt','name':'Yogurt, Greek style, plain','source':'UK CoFID 2021','nutrients':{'calories':115,'protein':6,'carbs':2,'fat':9,'calcium':126,'vitaminB12':0.2,'iron':None}}
COFID=[YOGURT,{'id':'cofid-milk','name':'Milk, whole','source':'UK CoFID 2021','nutrients':{'calcium':120}}]


def product(**extra):
    return {'id':'off:1','name':'Milbona · Greek Yoghurt (500 g)','brand':'Milbona','source':'Open Food Facts','nutrients':{'calories':130,'protein':5,'carbs':4,'fat':10,'calcium':150},**extra}


def test_generic_name_drops_brand_and_pack():
    assert generic_name(product())=='greek yogurt'


def test_picked_reference_fills_only_missing_values_and_is_labelled(monkeypatch):
    seen=[]
    def pick(entries):
        seen.extend(entries)
        return {0:YOGURT}
    monkeypatch.setattr(vision,'select_generic_references',pick)
    food=product()
    assert fill_missing([food],COFID,{})=={'off:1':'cofid-yogurt'}
    assert seen[0]['candidates'][0]['id']=='cofid-yogurt'
    assert food['nutrients']['calcium']==150  # the label's own value wins
    assert food['nutrients']['vitaminB12']==0.2
    assert food['nutrients'].get('iron') is None  # CoFID has no value either
    assert food['micronutrientEstimate']=={'fromId':'cofid-yogurt','from':'Yogurt, Greek style, plain','keys':['vitaminB12']}
    coverage=nutrient_coverage([{'grams':100,'food':food}])
    assert coverage['vitaminB12']['estimated']==1 and coverage['calcium']['estimated']==0


def test_earlier_decisions_are_reused_without_asking(monkeypatch):
    monkeypatch.setattr(vision,'select_generic_references',lambda entries:(_ for _ in ()).throw(AssertionError('asked again')))
    rejected,picked=product(),product(id='off:2')
    assert fill_missing([rejected,picked],COFID,{'off:1':None,'off:2':'cofid-yogurt'})=={}
    assert rejected['micronutrientEstimate']['keys']==[] and rejected['nutrients'].get('vitaminB12') is None
    assert picked['nutrients']['vitaminB12']==0.2


def test_provider_failure_leaves_values_unknown_and_undecided(monkeypatch):
    def fail(entries):raise vision.VisionError('no key')
    monkeypatch.setattr(vision,'select_generic_references',fail)
    food=product()
    assert fill_missing([food],COFID,{})=={}
    assert 'micronutrientEstimate' not in food and food['nutrients'].get('vitaminB12') is None


def test_serving_labels_and_cofid_foods_are_skipped(monkeypatch):
    monkeypatch.setattr(vision,'select_generic_references',lambda entries:(_ for _ in ()).throw(AssertionError('should not ask')))
    serving=product(nutritionBasis='serving')
    assert fill_missing([serving,dict(YOGURT,nutrients=dict(YOGURT['nutrients']))],COFID,{})=={}


def test_sodium_is_not_estimated_when_the_label_gives_salt(monkeypatch):
    monkeypatch.setattr(vision,'select_generic_references',lambda entries:{0:dict(YOGURT,nutrients={**YOGURT['nutrients'],'sodium':50})})
    food=product()
    food['nutrients']['salt']=0.3
    fill_missing([food],COFID,{})
    assert food['nutrients'].get('sodium') is None


def test_saving_a_meal_fills_and_remembers_the_product_estimate(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.store import Store
    calls=[]
    def pick(entries):
        calls.append(entries)
        return {0:entries[0]['candidates'][0]}
    monkeypatch.setattr(vision,'select_generic_references',pick)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        food=client.post('/api/products',json={'name':'Greek style yogurt','brand':'Tesco','retailer':'Tesco','nutritionBasis':'g','nutrients':{'calories':130,'protein':5,'carbs':4,'fat':10}}).json()
        meal={'id':'b','name':'Bowl','date':'2026-11-20','items':[{'id':'y','food':food,'grams':100}]}
        saved=client.post('/api/meals',json=meal).json()
        assert saved['nutrientTotals']['calcium']['estimated']==1
        assert saved['items'][0]['food']['micronutrientEstimate']['from'].startswith('Yogurt')
        Store(tmp_path/'test.sqlite').cache_food(food)  # a later product search re-caches the plain record
        again=client.post('/api/meals',json={**meal,'id':'c'}).json()
        assert again['items'][0]['food']['micronutrientEstimate']['from'].startswith('Yogurt')
    assert len(calls)==1  # the decision is remembered per product


def test_backfill_fills_old_meals_once_per_product_and_keeps_macros(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.store import Store
    calls=[]
    def pick(entries):
        calls.append(len(entries))
        return {i:e['candidates'][0] for i,e in enumerate(entries)}
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        food=client.post('/api/products',json={'name':'Greek style yogurt','brand':'Tesco','retailer':'Tesco','nutritionBasis':'g','nutrients':{'calories':130,'protein':5,'carbs':4,'fat':10}}).json()
        store=Store(tmp_path/'test.sqlite')
        for day in ('2026-11-01','2026-11-02'):  # logged before estimates existed
            store.save_meal({'id':day,'name':'Bowl','date':day,'items':[{'id':'y','food':food,'grams':150}],'notes':'','mealType':'breakfast'})
        monkeypatch.setattr(vision,'select_generic_references',pick)
        assert client.post('/api/meals/fill-vitamins').json()=={'updatedMeals':2,'undecidedFoods':0}
        meals=client.get('/api/meals').json()
        assert all(m['nutrientTotals']['calcium']['estimated']==1 for m in meals)
        assert all(m['totals']['calories']==195 for m in meals)
        assert client.post('/api/meals/fill-vitamins').json()=={'updatedMeals':0,'undecidedFoods':0}
    assert calls==[1]


def test_backfill_reports_foods_left_undecided_when_the_provider_fails(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.store import Store
    def fail(entries):raise vision.VisionError('no key')
    monkeypatch.setattr(vision,'select_generic_references',fail)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        food=client.post('/api/products',json={'name':'Greek style yogurt','brand':'Tesco','retailer':'Tesco','nutritionBasis':'g','nutrients':{'calories':130,'protein':5,'carbs':4,'fat':10}}).json()
        Store(tmp_path/'test.sqlite').save_meal({'id':'a','name':'Bowl','date':'2026-11-01','items':[{'id':'y','food':food,'grams':150}],'notes':'','mealType':'breakfast'})
        assert client.post('/api/meals/fill-vitamins').json()=={'updatedMeals':0,'undecidedFoods':1}


def test_more_than_one_batch_of_products_is_split(monkeypatch):
    sizes=[]
    def pick(entries):
        sizes.append(len(entries))
        return {}
    monkeypatch.setattr(vision,'select_generic_references',pick)
    foods=[product(id=f'off:{n}') for n in range(45)]
    assert len(fill_missing(foods,COFID,{}))==45 and sizes==[40,5]


def test_shortlist_falls_back_to_word_pairs_and_skips_loose_fragments():
    import json,pathlib
    from backend.micronutrients import shortlist
    cofid=json.loads((pathlib.Path(__file__).parent.parent/'data'/'cofid-normalized.json').read_text())
    names=[food['name'] for food in shortlist(cofid,'white bread slices in basket')]
    assert 'Bread, white, average' in names
    assert not any('Chicken' in name for name in names)  # 'slices' alone shouldn't pull in meat
    assert shortlist(cofid,'zzz qqq')==[]
