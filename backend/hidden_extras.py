"""One-tap extras a photo can't show: cooking fat, milk, sweeteners, sauces, cheese and cream.

Each extra uses your saved usual product for that category when there is one,
otherwise a plain UK CoFID record. Spoon and splash measures are converted to
the record's own basis (g or ml); cheese is offered in plain grams.
"""

# (group, key, label, usual-product category, CoFID fallback, density g/ml or None for gram measures, [(measure, ml or g)])
# shortcut: densities are rounded typical values, fine for a spoon-sized estimate; a product with an ml label skips them.
EXTRAS=[
    ('Cooking fat','oil','Cooking oil','cooking oil','Oil, vegetable, average',0.92,[('1 tsp',5),('1 tbsp',15),('2 tbsp',30)]),
    ('Cooking fat','butter','Butter','butter','Butter, salted',0.91,[('1 tsp',5),('1 tbsp',15)]),
    ('Milk and sweeteners','milk','Milk','milk','Milk, semi-skimmed, pasteurised, average',1.03,[('A splash',30),('100 ml',100)]),
    ('Milk and sweeteners','sugar','Sugar','sugar','Sugar, white',0.85,[('1 tsp',5),('2 tsp',10)]),
    ('Milk and sweeteners','honey','Honey','honey','Honey',1.42,[('1 tsp',5),('1 tbsp',15)]),
    ('Sauces and dressings','mayonnaise','Mayonnaise','mayonnaise','Mayonnaise, standard, retail',0.92,[('1 tsp',5),('1 tbsp',15)]),
    ('Sauces and dressings','ketchup','Ketchup','ketchup','Tomato ketchup',1.15,[('1 tbsp',15),('2 tbsp',30)]),
    ('Sauces and dressings','bbq','BBQ sauce','bbq sauce','Barbecue sauce',1.1,[('1 tbsp',15),('2 tbsp',30)]),
    ('Sauces and dressings','salad cream','Salad cream','salad cream','Salad cream',1.0,[('1 tbsp',15),('2 tbsp',30)]),
    ('Sauces and dressings','dressing','Salad dressing','salad dressing','Dressing, French',0.95,[('1 tbsp',15),('2 tbsp',30)]),
    ('Sauces and dressings','gravy','Gravy','gravy','Gravy instant granules, made up with water',1.0,[('50 ml',50),('100 ml',100)]),
    ('Sauces and dressings','curry sauce','Curry sauce','curry sauce','Sauce, curry, sweet, UK type, homemade',1.05,[('50 ml',50),('100 ml',100)]),
    ('Cheese and cream','cheese','Grated cheese','cheese','Cheese, Cheddar, English',None,[('15 g',15),('30 g',30)]),
    ('Cheese and cream','single cream','Single cream','single cream','Cream, fresh, single',1.0,[('1 tbsp',15),('A splash',30)]),
    ('Cheese and cream','double cream','Double cream','double cream','Cream, fresh, double, including Jersey cream',0.95,[('1 tbsp',15),('2 tbsp',30)]),
    ('Cheese and cream','creme fraiche','Crème fraîche','creme fraiche','Creme fraiche, full fat',1.0,[('1 tbsp',15),('2 tbsp',30)]),
]


def hidden_extras(usuals,cofid):
    usual={entry['category']:entry['food'] for entry in usuals}
    by_name={food['name']:food for food in cofid}
    result=[]
    for group,key,label,category,fallback,density,measures in EXTRAS:
        food=usual.get(category)
        if not food or food.get('nutritionBasis')=='serving':food=by_name.get(fallback)
        if not food:continue
        # Gram measures stay grams; a product labelled per 100 ml takes the ml amount as it is.
        per_unit=1 if density is None or food.get('nutritionBasis')=='ml' else density
        result.append({'group':group,'key':key,'label':label,'food':food,'options':[{'label':measure,'amount':round(amount*per_unit,1)} for measure,amount in measures]})
    return result
