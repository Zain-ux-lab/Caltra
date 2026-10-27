import pytest
from backend.estimation import component_grams

RICE={'name':'Cooked rice','nutrients':{'calories':130,'protein':3,'carbs':28,'fat':0.3},'portions':[{'label':'1 cup','grams':195}]}


def test_photo_estimate_is_not_replaced_by_reference_cup():
 component={'label':'Rice mound','query':'rice cooked','quantity':1,'unit':'cup','estimatedGrams':137,'basis':'photo'}
 assert component_grams(component,RICE)==137


def test_photo_estimate_is_not_replaced_by_average_fillet():
 fish={'name':'Salmon','portions':[{'label':'1 medium fillet','grams':150}]}
 assert component_grams({'quantity':1,'unit':'medium fillet','estimatedGrams':112,'basis':'photo'},fish)==112


def test_user_household_measure_still_uses_source_conversion():
 assert component_grams({'quantity':1,'unit':'cup','estimatedGrams':137,'basis':'user'},RICE)==195


def test_invalid_visual_weight_is_rejected():
 with pytest.raises(ValueError):component_grams({'quantity':1,'unit':'cup','estimatedGrams':-1,'basis':'photo'},RICE)


def test_photo_grams_never_override_explicit_liquid_basis():
 milk={'name':'Milk','nutritionBasis':'ml','portions':[]}
 with pytest.raises(ValueError):component_grams({'quantity':100,'unit':'g','estimatedGrams':100,'basis':'photo'},milk)


def test_assumed_serving_is_not_labelled_as_photo_estimate(tmp_path,monkeypatch):
 from backend.store import Store
 from backend import estimation,vision
 s=Store(tmp_path/'f.sqlite');s.seed()
 rice=s.food('cofid:11-858')
 monkeypatch.setattr(vision,'select_sources',lambda entries:{0:rice})
 result=estimation.resolve_observation({'foods':[{'label':'Cooked basmati rice','query':'basmati rice cooked','estimatedGrams':150,'basis':'assumed'}],'description':'','question':''},s)
 assert 'Assumed' in result['items'][0]['portionLabel']
 assert 'Photo' not in result['items'][0]['portionLabel']
