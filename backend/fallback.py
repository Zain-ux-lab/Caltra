"""Retain model guesses separately from the nutrition reference catalog."""
import uuid
from datetime import datetime,timezone
from . import vision


def estimate_foods(entries,store):
    try:guesses=vision.estimate_nutrients(entries)
    except vision.VisionError:return {}
    result={}
    for index,guess in guesses.items():
        if not 0<=index<len(entries):continue
        checked=vision.NutritionGuess(index=index,**guess)
        if checked.nutrients is None:continue
        food={'id':'ai:'+str(uuid.uuid4()),'name':entries[index]['label'],'source':'AI estimate — not database verified','dataType':'Model-generated nutrition guess','url':'','retrievedAt':datetime.now(timezone.utc).isoformat(),'isAiEstimate':True,'nutrients':checked.nutrients.model_dump(),'portions':[],'sourceWarning':'No suitable database match. Calories and macros are AI guesses, not verified product-label values. '+checked.assumptions}
        store.cache_estimate(food)
        result[index]=(food,checked.estimatedGrams)
    return result
