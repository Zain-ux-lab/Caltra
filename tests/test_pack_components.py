import pytest
from backend.uk_products import normalize_product
from backend import estimation,vision
from backend.store import Store


def product(quantity):
 return {'code':'12345678','product_name':'Tortilla Wraps','brands':'Rowan Hill Bakery','quantity':quantity,'labels_tags':['en:high-proteins'],'countries_tags':['en:united-kingdom'],'nutriments':{'energy-kcal_100g':293,'proteins_100g':16,'carbohydrates_100g':47.6,'fat_100g':3.8}}


def test_counted_wrap_pack_uses_total_mass_and_individual_portion():
 f=normalize_product(product('6 wraps 366g'))
 assert f and f['packGrams']==366
 assert f['portions'][1]=={'label':'1 wrap','grams':61,'unit':'g'}
 assert 'protein' in ' '.join(f.get('aliases',[]))


@pytest.mark.parametrize('quantity',['6 wraps','6 wraps approx','0 wraps 366g'])
def test_ambiguous_pack_size_not_guessed(quantity):
 f=normalize_product(product(quantity))
 assert f is not None and not f.get('packGrams') and f['portions']==[]
 assert f['nutrients']['calories']==293


def test_separate_salad_components_resolve_to_distinct_uk_sources(tmp_path,monkeypatch):
 s=Store(tmp_path/'f.sqlite');s.seed()
 def select(entries):
  return {i:next(f for f in e['candidates'] if ('chick peas, canned' in f['name'].lower() if 'chickpea' in e['label'].lower() else 'red kidney, canned' in f['name'].lower())) for i,e in enumerate(entries)}
 monkeypatch.setattr(vision,'select_sources',select)
 r=estimation.resolve_observation({'foods':[{'label':'Bean salad','query':'bean salad','estimatedGrams':100,'components':[{'label':'Canned kidney beans','query':'red kidney beans canned','quantity':50,'unit':'g','basis':'photo'},{'label':'Canned chickpeas','query':'chickpeas canned','quantity':50,'unit':'g','basis':'photo'}]}],'description':'Salad','question':'','notice':''},s,allow_ai=False)
 assert len(r['items'])==2 and not r['missing']
 assert all(i['food']['source']=='UK CoFID 2021' for i in r['items'])
 assert r['items'][0]['food']['id']!=r['items'][1]['food']['id']
