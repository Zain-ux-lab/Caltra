import numpy as np
import pytest
from experiments.portion_multiview.core import crop_region,heldout_ids,paired_improvement


def test_crop_clamps_boxes_and_marks_unreliable_detections():
    box,accepted=crop_region([.05,.5,.4,.4],.8,100,80)
    assert accepted and box==(0,24,25,56)
    assert crop_region([.5,.5,.4,.4],.01,100,80)==((0,0,100,80),False)
    assert crop_region([float('nan'),.5,.4,.4],.8,100,80)==((0,0,100,80),False)


def test_new_test_set_excludes_previously_inspected_dishes_and_is_deterministic():
    pool=[f'dish_{i}' for i in range(10)]
    a=heldout_ids(pool,{'dish_0','dish_1'},4)
    assert a==heldout_ids(reversed(pool),{'dish_0','dish_1'},4)
    assert len(a)==4 and not set(a)&{'dish_0','dish_1'}
    with pytest.raises(ValueError):heldout_ids(pool,set(pool),1)


def test_paired_error_comparison_resamples_capture_days_not_rows():
    result=paired_improvement([100,100,100,100],[130]*4,[110]*4,['day1','day1','day2','day2'])
    assert result['mae_reduction_g']==20
    assert result['capture_day_clusters']==2
    assert np.allclose(result['cluster_bootstrap_95_interval_g'],[20,20])
