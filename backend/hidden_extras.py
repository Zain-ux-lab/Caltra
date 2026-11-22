"""One-tap extras a photo can't show: cooking fat, milk and sweeteners.

Each extra uses your saved usual product for that category when there is one,
otherwise a plain UK CoFID record. Amounts are household measures converted to
the record's own basis (g or ml).
"""

# (key, label, usual-product category, CoFID fallback, density g/ml, [(measure, ml)])
EXTRAS=[
    ('oil','Cooking oil','cooking oil','Oil, vegetable, average',0.92,[('1 tsp',5),('1 tbsp',15),('2 tbsp',30)]),
    ('butter','Butter','butter','Butter, salted',0.91,[('1 tsp',5),('1 tbsp',15)]),
    ('milk','Milk','milk','Milk, semi-skimmed, pasteurised, average',1.03,[('A splash',30),('100 ml',100)]),
    ('sugar','Sugar','sugar','Sugar, white',0.85,[('1 tsp',5),('2 tsp',10)]),
    ('honey','Honey','honey','Honey',1.42,[('1 tsp',5),('1 tbsp',15)]),
]


def hidden_extras(usuals,cofid):
    usual={entry['category']:entry['food'] for entry in usuals}
    by_name={food['name']:food for food in cofid}
    result=[]
    for key,label,category,fallback,density,measures in EXTRAS:
        food=usual.get(category)
        if not food or food.get('nutritionBasis')=='serving':food=by_name.get(fallback)
        if not food:continue
        per_ml=1 if food.get('nutritionBasis')=='ml' else density
        result.append({'key':key,'label':label,'food':food,'options':[{'label':measure,'amount':round(ml*per_ml,1)} for measure,ml in measures]})
    return result
