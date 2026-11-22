"""Start a food's portion from what you usually log once you've corrected it a few times.

Only amounts you entered yourself count, so an accepted suggestion never reinforces itself.
"""
from statistics import median
from .nutrition import calculate

MIN_CORRECTIONS=2  # one odd meal shouldn't change future estimates
RECENT=5


def usual_portions(meals):
    """Map food id to the median of your most recent amounts for it."""
    history={}
    for meal in sorted(meals,key=lambda m:m['date'],reverse=True):
        for item in meal['items']:
            # "Ate half" marks items as yours, but half of a guess isn't an amount you know.
            if item.get('quantityBasis')=='user' and not item.get('portionEvidence','').startswith('You selected half'):
                history.setdefault(item['food']['id'],[]).append(item['grams'])
    return {ident:median(amounts[:RECENT]) for ident,amounts in history.items() if len(amounts)>=MIN_CORRECTIONS}


def apply_usual_portions(result,meals):
    """Replace photo or assumed amounts with your usual portion; amounts you stated are left alone."""
    usual=usual_portions(meals)
    changed=False
    for item in result.get('items') or []:
        grams=usual.get(item['food']['id'])
        if grams is None or item.get('quantityBasis')=='user' or item.get('possibleShared'):continue
        unit=item['food'].get('nutritionBasis') or 'g'
        item.update(grams=grams,quantityBasis='assumed',portionLabel=f'Your usual portion ({grams:g} {unit})',portionEvidence='Median of the amounts you recently entered for this food')
        changed=True
    if changed:result['totals']=calculate(result['items'])
    return result
