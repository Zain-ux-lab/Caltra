from backend.recognition import reconcile_predictions


def test_dessert_category_rejects_conflicting_savoury_guess():
    result=reconcile_predictions([{'label':'crab cakes','score':.71},{'label':'carrot cake','score':.07}],{'label':'dessert','score':.98})
    assert result['candidates']==[{'label':'dessert','score':.98}]
    assert result['categoryOnly'] is True
    assert 'disagree' in result['notice'].lower()


def test_agreeing_models_keep_specific_suggestions():
    guesses=[{'label':'chocolate cake','score':.8}]
    result=reconcile_predictions(guesses,{'label':'dessert','score':.9})
    assert result['candidates']==guesses
    assert not result['categoryOnly']
