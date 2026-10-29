from backend.vision import IngredientEstimate, VisibleFood
from backend.estimation import set_portion_evidence

def test_uncertain_identity_keeps_amount_and_requests_confirmation():
    observation=IngredientEstimate(label='Filled pastry',query='pastry',estimatedGrams=90,identityUncertain=True,confirmationQuestion='Was the filling cheese, meat, or something else?').model_dump()
    item={'label':'Filled pastry','grams':90}
    set_portion_evidence(item,observation)
    assert item['grams']==90
    assert item['clarification']==observation['confirmationQuestion']

def test_missing_question_gets_confirmation_fallback():
    item={'label':'Fish','grams':140}
    set_portion_evidence(item,{'identityUncertain':True})
    assert item['clarification']=='Is this Fish, or something else?'

def test_old_observations_remain_compatible():
    food=VisibleFood(label='Salmon',query='salmon',estimatedGrams=140)
    assert not food.identityUncertain
