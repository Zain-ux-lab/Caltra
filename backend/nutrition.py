"""Deterministic arithmetic over reference nutrients or explicitly labelled AI guesses."""
import math
from datetime import datetime, timezone

KEYS = ('calories', 'protein', 'carbs', 'fat')
from .nutrients import NUTRIENTS
EXTRA_KEYS=tuple(n[0] for n in NUTRIENTS)

def nutrient_coverage(items):
    result={}
    for key in EXTRA_KEYS:
        known=[i for i in items if isinstance(i['food']['nutrients'].get(key),(float,int)) and not isinstance(i['food']['nutrients'].get(key),bool) and math.isfinite(i['food']['nutrients'][key]) and i['food']['nutrients'][key]>=0]
        result[key]={'value':round(sum(i['food']['nutrients'][key]*i['grams']/100 for i in known),8) if known else None,'complete':bool(items) and len(known)==len(items),'missing':len(items)-len(known)}
    return result


def normalize_food(raw):
    values = {}
    for entry in raw.get('foodNutrients', []):
        nutrient = entry.get('nutrient', entry)
        ident = nutrient.get('id', nutrient.get('nutrientId'))
        unit = nutrient.get('unitName', '').lower()
        amount = entry.get('amount', entry.get('value'))
        if isinstance(amount, (int, float)) and math.isfinite(amount) and amount >= 0:
            values[ident] = (amount, unit)
    def get(ident, unit):
        pair = values.get(ident)
        return pair[0] if pair and pair[1] == unit else None
    calories = get(1008, 'kcal')
    if calories is None:
        calories = get(2048, 'kcal') or get(2047, 'kcal')
    if calories is None and get(1062, 'kj') is not None:
        calories = get(1062, 'kj') / 4.184
    portions=[]
    for portion in raw.get('foodPortions', []):
        grams = portion.get('gramWeight')
        if isinstance(grams, (int,float)) and grams > 0:
            label = portion.get('portionDescription') or portion.get('modifier') or portion.get('measureUnit',{}).get('name', 'serving')
            if any(word in str(label).lower() for word in ['not specified', 'unknown', 'quantity not']):
                continue
            amount=portion.get('amount',1)
            if portion.get('portionDescription'):
                display=str(label)
            else:
                display=f'{amount:g} {label}' if isinstance(amount,(int,float)) else str(label)
            portions.append({'label':display, 'grams':grams})
    return {'id':str(raw['fdcId']), 'name':raw['description'], 'source':'USDA FoodData Central',
            'dataType':raw.get('dataType',''), 'retrievedAt':datetime.now(timezone.utc).isoformat(),
            'url':f"https://fdc.nal.usda.gov/food-details/{raw['fdcId']}/nutrients",
            'nutrients':{'calories':calories, 'protein':get(1003,'g'), 'carbs':get(1005,'g'), 'fat':get(1004,'g')},
            'portions':portions}


def calculate(items):
    totals = dict.fromkeys(KEYS, 0.0)
    for item in items:
        grams = item['grams']
        if isinstance(grams, bool) or not isinstance(grams,(int,float)) or not math.isfinite(grams) or not 0 < grams <= 100000:
            raise ValueError('Enter a portion greater than zero and no more than 100,000 g.')
        for key in KEYS:
            value=item['food']['nutrients'].get(key)
            if value is None or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0:
                raise ValueError('This food is missing complete nutrition data. Choose another source record.')
            totals[key] += value * grams / 100
    return {k:round(v,8) for k,v in totals.items()}


def make_recipe(name, items, yield_grams, ident):
    if not isinstance(yield_grams,(int,float)) or not math.isfinite(yield_grams) or yield_grams<=0:
        raise ValueError('Cooked yield must be positive.')
    totals=calculate(items)
    result={'id':ident,'name':name,'source':'Your recipe','dataType':'Measured recipe','url':'',
            'retrievedAt':datetime.now(timezone.utc).isoformat(), 'nutrients':{k:v*100/yield_grams for k,v in totals.items()},
            'portions':[], 'recipeItems':items, 'yieldGrams':yield_grams}
    result['nutrients'].update({k:v['value']*100/yield_grams if v['complete'] else None for k,v in nutrient_coverage(items).items()})
    if any(i['food'].get('isAiEstimate') for i in items):
        result.update(isAiEstimate=True,dataType='Recipe including AI-estimated nutrition',sourceWarning='This recipe includes AI-estimated nutrition; its totals are not fully database verified.')
    return result
