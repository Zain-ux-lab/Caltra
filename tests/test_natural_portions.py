from backend import vision,estimation

def test_carrot_spoon_question_becomes_natural():
 q=vision.household_question('How many tablespoons of carrot were added?')
 assert 'tablespoon' not in q.lower() and 'carrot' in q.lower()

def test_fish_weight_question_uses_pieces():
 q=vision.household_question('What is the weight of the fish?')
 assert 'piece' in q.lower() and 'spoon' not in q.lower()

def test_explicit_yogurt_spoon_question_remains():
 q='How many spoonfuls of yogurt did you add?'
 assert vision.household_question(q)==q

def test_assumed_spoons_do_not_use_database_reference_serving():
 food={'name':'Carrots raw','portions':[{'label':'1 tablespoon','grams':15}]}
 c={'label':'Carrot','quantity':2,'unit':'tablespoon','estimatedGrams':18,'basis':'assumed'}
 assert estimation.component_grams(c,food)==18

def test_user_spoon_amount_still_uses_conversion():
 food={'name':'Carrots raw','portions':[{'label':'1 tablespoon','grams':15}]}
 c={'label':'Carrot','quantity':2,'unit':'tablespoon','estimatedGrams':18,'basis':'user'}
 assert estimation.component_grams(c,food)==30

def test_assumed_carrot_displays_grams_not_invented_spoons(tmp_path):
 from backend.store import Store
 store=Store(tmp_path/'test.sqlite');store.seed()
 carrot=next(f for f in store.foods() if f['name']=='Carrots, old, raw')
 c={'label':'Carrot','query':'carrot raw','sourceId':carrot['id'],'quantity':2,'unit':'tablespoon','estimatedGrams':18,'basis':'assumed'}
 items,missing=estimation.resolve_components([c],store,{carrot['id']})
 assert not missing and items[0]['grams']==18
 assert '18 g' in items[0]['portionLabel']
 assert 'tablespoon' not in items[0]['portionLabel']
