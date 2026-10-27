import pytest
from backend import estimation, uk_products, vision
from backend.store import Store
from backend.main import create_app
from fastapi.testclient import TestClient


def raw_product(**changes):
    return dict(code='12345678', product_name='Greek Style Yogurt', brands='Asda', quantity='500g', countries_tags=['en:united-kingdom'], nutriments={'energy-kcal_100g':66,'proteins_100g':7,'carbohydrates_100g':8,'fat_100g':.5}, **changes)


def observation(label):
    return {'foods':[{'label':'Chef Select Moussaka','query':'moussaka','brand':'Chef Select','packGrams':380,'estimatedGrams':190,'visibleCount':1,'nutritionLabel':label}], 'description':'Half a pack','question':'','notice':''}


def test_pack_label_overrides_ai_guess_without_a_second_image_call(tmp_path, monkeypatch):
    store=Store(tmp_path/'test.sqlite');store.seed()
    monkeypatch.setattr(vision,'select_sources',lambda *a:pytest.fail('Readable pack label must take priority'))
    def guesses(entries):
        return {0:{'nutrients':{'calories':145,'protein':6,'carbs':11,'fat':8},'estimatedGrams':190,'assumptions':'Generic recipe'}}
    monkeypatch.setattr(vision,'estimate_nutrients',guesses)
    result=estimation.resolve_observation(observation({'nutritionBasis':'g','per100':{'calories':134},'perServing':{'calories':509,'fat':28.5},'servingAmount':380,'evidence':'One pack contains 509 kcal, fat 28.5g. Typical values per 100g 134 kcal.'}),store,allow_ai=True)
    item=result['items'][0]
    assert item['grams']==190
    assert result['totals']['calories']==254.6
    assert result['totals']['fat']==14.25
    assert item['food']['isAiEstimate']
    assert set(item['food']['labelNutrients'])=={'calories','fat'}
    assert 'protein' in item['food']['sourceWarning'].lower()


def test_complete_label_uses_no_nutrition_model_and_survives_save(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'estimate_nutrients',lambda *a:pytest.fail('Complete label needs no guesses'))
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        label={'nutritionBasis':'g','per100':{'calories':134,'protein':6,'carbs':11,'fat':7.5},'evidence':'Per 100g:134kcal, protein6g, carbs11g, fat7.5g'}
        result=estimation.resolve_observation(observation(label),client.app.state.store,allow_ai=True)
        food=result['items'][0]['food']
        assert not food.get('isAiEstimate')
        assert food['source']=='Photo nutrition label'
        saved=client.post('/api/meals',json={'id':'pack','name':'Moussaka','date':'2026-10-25','items':result['items']})
        assert saved.status_code==200,saved.text
        assert saved.json()['totals']['calories']==254.6


def test_unclear_or_volume_label_is_not_applied_to_gram_portion(tmp_path,monkeypatch):
    store=Store(tmp_path/'test.sqlite');store.seed()
    for label in [{'nutritionBasis':None,'per100':{'calories':134},'evidence':'134'}, {'nutritionBasis':'ml','per100':{'calories':134},'evidence':'per100ml134kcal'}, {'nutritionBasis':'g','per100':{'calories':134},'evidence':''}]:
        assert estimation.photo_label_food(observation(label)['foods'][0],store,False,'') is None


@pytest.mark.parametrize('quantity', ['', '500 g e', '6 x 61g', 'one pot'])
def test_uk_products_with_complete_macros_do_not_require_simple_pack_text(quantity):
    raw=raw_product();raw['quantity']=quantity
    food=uk_products.normalize_product(raw)
    assert food is not None
    assert food['nutrients']['calories']==66
    if quantity in {'','one pot'}:
        assert not food.get('packGrams') and food['portions']==[]
    if quantity=='6 x 61g':assert food['packGrams']==366


def test_search_limits_to_uk_before_pagination_and_returns_more_than_40(monkeypatch):
    uk_products._cache.clear();uk_products._calls.clear()
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):
            return {'hits':[{**raw_product(),'code':str(10000000+i)} for i in range(70)],'page_count':3,'count':230}
    def get(url,**kwargs):
        calls.append(kwargs['params'])
        return Response()
    monkeypatch.setattr(uk_products.httpx,'get',get)
    result=uk_products.search_product_page('yogurt',2)
    assert 'countries_tags:"en:united-kingdom"' in calls[0]['q']
    assert calls[0]['page']==2 and calls[0]['page_size']==100
    assert len(result['foods'])==70 and result['hasMore'] and result['page']==2


def test_product_endpoint_filters_generics_before_limiting_and_paginates(tmp_path,monkeypatch):
    records=[uk_products.normalize_product({**raw_product(),'code':str(10000000+i)}) for i in range(65)]
    calls=[]
    def page(q,p=1):
        calls.append((q,p));return {'foods':records if p==1 else [],'warning':'Check the label','hasMore':p==1,'page':p}
    monkeypatch.setattr(uk_products,'search_product_page',page)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        r=client.get('/api/products/search',params={'q':'yogurt'});assert r.status_code==200,r.text
        assert len(r.json()['foods'])==65 and all(f.get('brand') for f in r.json()['foods'])
        assert r.json()['hasMore']
        assert client.get('/api/products/search',params={'q':'yogurt','page':2}).json()['page']==2
        assert calls==[('yogurt',1),('yogurt',2)]


def test_recognition_requests_and_retains_label_transcription(monkeypatch):
    import io,json,httpx
    from PIL import Image
    image=io.BytesIO();Image.new('RGB',(32,32)).save(image,format='PNG')
    label={'nutritionBasis':'g','per100':{'calories':134},'perServing':{'fat':28.5},'servingAmount':380,'evidence':'Per100g134kcal;perpack380gfat28.5g'}
    def post(url,**kwargs):
        payload=kwargs['json']
        assert 'nutritionLabel' in payload['generationConfig']['responseJsonSchema']['properties']['foods']['items']['properties']
        assert 'copy printed values' in payload['systemInstruction']['parts'][0]['text']
        data=observation(label);data.pop('notice')
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(data)}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    monkeypatch.setattr(vision.httpx,'post',post)
    result=vision.recognize(image.getvalue())
    assert result['foods'][0]['nutritionLabel']['per100']['calories']==134


def test_no_fake_zero_for_unreadable_nutrients():
    label=vision.ObservedNutritionLabel(nutritionBasis='g',per100={'calories':134},evidence='134kcal per100g')
    assert label.per100.protein is None and label.per100.fat is None
    with pytest.raises(ValueError):vision.ObservedNutritionLabel(nutritionBasis='g',per100={'calories':float('nan')})


def test_large_pack_energy_is_normalised_from_its_explicit_serving_amount(tmp_path):
    store=Store(tmp_path/'pack.sqlite')
    food=observation({'nutritionBasis':'g','perServing':{'calories':1340,'protein':60,'carbs':110,'fat':75},'servingAmount':1000,'evidence':'Per1000gpack1340kcal60gprotein110gcarbs75gfat'})['foods'][0]
    source=estimation.photo_label_food(food,store,False,'')
    assert source['nutrients']['calories']==134
