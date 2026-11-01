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

    def test_seed_upgrades_existing_database_without_changing_meals(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'app.db')
            store.seed()
            food=store.food(self.foods[0]['id'])
            self.assertIsNotNone(food)
            store.seed()
            self.assertEqual(store.food(food['id']),food)

if __name__=='__main__':
    unittest.main()
