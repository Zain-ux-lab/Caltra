import json
import tempfile
import unittest
from pathlib import Path
from backend.nutrition import calculate, nutrient_coverage
from backend.estimation import component_grams
from backend.search import search_foods
from backend.store import Store, uk_source
from scripts.import_restaurants import build


class RestaurantCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.foods = build()

    def find(self, name):
        return next(f for f in self.foods if f['name'] == name)

    def test_snapshot_is_reproducible_and_sources_are_explicit(self):
        self.assertEqual(self.foods, json.loads(Path('data/uk-restaurants.json').read_text()))
        self.assertGreater(len(self.foods),700)
        self.assertEqual(len(self.foods),len({f['id'] for f in self.foods}))
        for food in self.foods:
            self.assertTrue(uk_source(food))
            self.assertEqual(food['nutritionBasis'],'serving')
            self.assertTrue(food['url'].startswith('https://'))
            self.assertFalse(food.get('isAiEstimate'))
            self.assertNotIn('vitaminC',food['nutrients'])

    def test_serving_scaling_and_mixed_gram_meal(self):
        food=self.find('Greggs · All Butter Croissant')
        half={'food':food,'grams':.5}
        self.assertEqual(calculate([half])['calories'],146)
        self.assertEqual(nutrient_coverage([half])['fibre']['value'],1.05)
        self.assertIsNone(nutrient_coverage([half])['vitaminC']['value'])
        gram={'food':{'nutrients':{'calories':100,'protein':10,'carbs':10,'fat':2}},'grams':50}
        self.assertEqual(calculate([half,gram])['calories'],196)

    def test_serving_unit_cannot_be_inferred_from_photo_weight(self):
        food=self.foods[0]
        self.assertEqual(component_grams({'quantity':.5,'unit':'serving'},food),.5)
        for unit in ['g','ml','slice']:
            with self.assertRaises(ValueError):
                component_grams({'quantity':100,'unit':unit,'estimatedGrams':100},food)

    def test_search_brand_and_variants(self):
        result=search_foods(self.foods,'Pizza Express Padana')
        self.assertEqual(result['matchType'],'matched')
        names=[f['name'] for f in result['foods']]
        self.assertTrue(any('Classic' in n for n in names))
        self.assertTrue(any('Romana' in n for n in names))
        self.assertTrue(all(f['brand']=='PizzaExpress' for f in result['foods']))
        self.assertEqual(search_foods(self.foods,'Greggs Padana')['foods'],[])

    def test_menu_meal_query_returns_components_not_a_fake_combo(self):
        result=search_foods(self.foods,'Greggs chicken bake meal')
        self.assertEqual(result['matchType'],'related')
        self.assertIn('separately',result['matchedQuery'])
        self.assertTrue(all('Chicken Bake' in f['name'] for f in result['foods']))

    def test_popeyes_spicy_chicken_queries_and_exact_serving(self):
        for query in ['popeyes spicy chicken', 'popeyes spicy chicken meal']:
            result=search_foods(self.foods,query)
            self.assertTrue(result['foods'])
            self.assertTrue(all(f['brand']=='Popeyes' for f in result['foods']))
            self.assertTrue(any(f['name']=='Popeyes · Spicy Chicken Sandwich · Sandwiches' for f in result['foods']))
        food=self.find('Popeyes · Spicy Chicken Sandwich · Sandwiches')
        self.assertEqual(calculate([{'food':food,'grams':1}])['calories'],529.47)
        self.assertFalse(any('Ireland Only' in f['name'] for f in self.foods))

    def test_nandos_milligrams_and_portion_exclusions(self):
        food=self.find("Nando's · 1/2 Chicken · Pe Ri Pe Ri Chicken")
        self.assertEqual(food['nutrients']['protein'],78.7)
        self.assertIn('Excludes chosen spice',food['sourceWarning'])
        self.assertTrue(any('Full Platter (chicken only)' in f['name'] for f in self.foods))

    def test_kfc_published_serving_and_unpublished_fibre(self):
        result=search_foods(self.foods,'kfc zinger')
        self.assertTrue(result['foods'])
        self.assertTrue(all(f['brand']=='KFC' for f in result['foods']))
        food=self.find('KFC · Zinger Burger · Burgers')
        self.assertEqual(calculate([{'food':food,'grams':1}]),{'calories':468,'protein':23,'carbs':43,'fat':22})
        self.assertIsNone(nutrient_coverage([{'food':food,'grams':1}])['fibre']['value'])
        self.assertEqual(nutrient_coverage([{'food':food,'grams':1}])['salt']['value'],2)
        self.assertFalse(any('ROI' in f['name'] for f in self.foods if f['brand']=='KFC'))

    def test_mcdonalds_published_serving_nicknames_and_bad_rows(self):
        for query in ["mcdonald's big mac", 'maccies big mac']:
            result=search_foods(self.foods,query)
            self.assertTrue(result['foods'])
            self.assertTrue(all(f['brand']=="McDonald's" for f in result['foods']))
        food=self.find("McDonald's · Big Mac · Burgers")
        self.assertEqual(calculate([{'food':food,'grams':1}]),{'calories':509,'protein':27,'carbs':41,'fat':25})
        self.assertEqual(food['nutrients']['fibre'],3.4)
        self.assertFalse(any('Cappuccino' in f['name'] for f in self.foods if f['brand']=="McDonald's"))  # published 34 g salt

    def test_pret_per_serving_values_and_default_drink_build(self):
        for query in ['pret porridge', 'pret a manger latte']:
            result=search_foods(self.foods,query)
            self.assertTrue(result['foods'])
            self.assertTrue(all(f['brand']=='Pret' for f in result['foods']))
        food=self.find("Pret · Pret's Proper Porridge · Breakfast")
        self.assertEqual(calculate([{'food':food,'grams':1}]),{'calories':216,'protein':8.7,'carbs':23.7,'fat':8.7})
        self.assertEqual(food['nutrients']['fibre'],4.2)
        self.assertIn('default published recipe',self.find('Pret · Latte · Hot Drinks')['sourceWarning'])

    def test_subway_six_inch_build_and_excluded_source_errors(self):
        result=search_foods(self.foods,'subway chicken tikka')
        self.assertTrue(result['foods'])
        self.assertTrue(all(f['brand']=='Subway' for f in result['foods']))
        food=self.find('Subway · Chicken Tikka · 6-inch Subs')
        self.assertEqual(calculate([{'food':food,'grams':2}]),{'calories':690,'protein':56,'carbs':86,'fat':14.2})  # a footlong
        self.assertIn('add cheese, sauce and extras separately',food['sourceWarning'])
        names={f['name'] for f in self.foods if f['brand']=='Subway'}
        self.assertNotIn('Subway · Ultimate Festive · Spuds',names)  # published 3.1 g protein for 628 kcal
        self.assertFalse(any('(ROI)' in n for n in names))

    def test_caffe_nero_milk_and_size_variants(self):
        for query in ['nero latte', 'caffe nero latte']:
            result=search_foods(self.foods,query)
            self.assertTrue(result['foods'])
            self.assertTrue(all(f['brand']=='Caffè Nero' for f in result['foods']))
        food=self.find('Caffè Nero · Latte (Semi Skimmed Milk, Regular) · Coffee')
        self.assertEqual(calculate([{'food':food,'grams':1}]),{'calories':123,'protein':9.1,'carbs':12.5,'fat':4.4})
        self.assertEqual(self.find('Caffè Nero · Latte (Semi Skimmed Milk, Grande) · Coffee')['nutrients']['calories'],183)
        self.assertFalse(any(f['name'].endswith('(NI)') or '(NI) ·' in f['name'] for f in self.foods if f['brand']=='Caffè Nero'))

    def test_seed_upgrades_existing_database_without_changing_meals(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'app.db')
            store.seed()
            food=store.food(self.foods[0]['id'])
            self.assertIsNotNone(food)
            retired={**food,'id':'uk-restaurant:retired'}
            store.cache_food(retired)
            store.seed()
            self.assertIsNone(store.food(retired['id']))
            self.assertEqual(store.food(food['id']),food)

if __name__=='__main__':
    unittest.main()


def test_a_word_from_a_multi_word_chain_does_not_restrict_search():
    chain={'id':'x','name':'Burger King · Whopper','brand':'Burger King','source':'Official UK restaurant nutrition','nutrients':{}}
    generic={'id':'y','name':'Burger, beef, grilled','source':'UK CoFID 2021','nutrients':{}}
    assert 'y' in [f['id'] for f in search_foods([chain,generic],'burger')['foods']]  # CoFID burger isn't filtered out
    assert [f['id'] for f in search_foods([chain,generic],'burger king whopper')['foods']]==['x']


def test_an_unnamed_chains_brand_word_is_not_a_related_match():
    nero={'id':'n','name':'Caffè Nero · Honey · Breakfast','brand':'Caffè Nero','source':'Official UK restaurant nutrition','nutrients':{}}
    kale={'id':'k','name':'Cavolo nero, raw','source':'Open Food Facts','nutrients':{}}
    assert search_foods([nero],'cavolo nero')['matchType']=='none'  # "nero" is only the chain's name
    assert [f['id'] for f in search_foods([nero,kale],'cavolo nero')['foods']]==['k']
    assert search_foods([nero],'caffe nero honey')['foods']==[nero]
