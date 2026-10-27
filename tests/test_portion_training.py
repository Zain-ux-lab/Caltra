import pytest
from experiments.portion_weight.core import parse_row,choose_splits,metrics,food_priors,feature_signature


def row(ident='dish_1561662216',mass='30'):
    return [ident,'100',mass,'2','3','4','ingr_0000000001','rice','10','1','2','3','4','ingr_0000000001','rice','20','1','2','3','4']


def test_actual_csv_layout_and_duplicate_food_aggregation():
    d=parse_row(row());assert len(d['ingredients'])==1
    assert d['ingredients'][0]['grams']==30
    with pytest.raises(ValueError):parse_row(row(mass='99'))


def test_different_dishes_and_capture_days_are_kept_apart():
    ids=[f'dish_{1561662216+day*86400}' for day in range(12)]
    records={i:parse_row(row(i)) for i in ids}
    split=choose_splits(records,ids[:10],ids[10:],counts=(3,1,2))
    assert not set(split['train'])&set(split['validation'])
    assert set(split['test'])==set(ids[10:])
    with pytest.raises(ValueError):choose_splits(records,ids[:10],ids[9:],counts=(3,1,2))


def test_baseline_statistics_use_training_rows_only():
    records={'train':{'ingredients':[{'id':'rice','grams':50}]},'test':{'ingredients':[{'id':'rice','grams':200}]}}
    priors,fallback=food_priors(records,['train']);assert priors['rice']==50 and fallback==50
    result=metrics([100,200],[110,180]);assert result['mae_g']==15
    assert result['bias_g']==-5 and result['wape_percent']==10


def test_feature_cache_preserves_image_row_order():
    encoder={'revision':'pinned'};hashes={'a':'hash-a','b':'hash-b'}
    assert feature_signature(encoder,['a','b'],hashes)!=feature_signature(encoder,['b','a'],hashes)
    assert feature_signature(encoder,['a','b'],hashes)==feature_signature(encoder,['a','b'],dict(reversed(list(hashes.items()))))
