import pytest
from backend import estimation,vision
from backend.store import Store

def test_four_salmon_pieces_log_whole_plate_not_one_piece(tmp_path,monkeypatch):
 s=Store(tmp_path/'test.sqlite');s.seed()
 monkeypatch.setattr(vision,'select_sources',lambda entries:{i:None for i in range(len(entries))})
 monkeypatch.setattr(vision,'estimate_nutrients',lambda entries:{0:{'nutrients':{'calories':206,'protein':22.1,'carbs':0,'fat':12.3},'estimatedGrams':180,'assumptions':'Cooked salmon estimate'}})
 r=estimation.resolve_observation({'foods':[{'label':'Cooked salmon pieces','query':'cooked salmon','estimatedGrams':180,'visibleCount':4,'basis':'photo','visualEvidence':'Four cooked pieces on the plate.'}],'description':'Rice and four salmon pieces on one plate','question':'','notice':''},s,allow_ai=True)
 assert r['items'][0]['grams']==180
 assert r['totals']['calories']==pytest.approx(370.8)
 assert r['groups'][0]['visible']==r['groups'][0]['logged']==4

@pytest.mark.parametrize('components',[False,True])
def test_explicit_whole_group_scope_for_sources_and_components(tmp_path,monkeypatch,components):
 s=Store(tmp_path/'test.sqlite');s.seed()
 fish=next(f for f in s.foods() if f['name']=='Salmon, wild, steamed')
 monkeypatch.setattr(vision,'select_sources',lambda entries:{i:fish for i in range(len(entries))})
 f={'label':'Cooked salmon pieces','query':'cooked salmon','estimatedGrams':180,'visibleCount':4,'portionScope':'allVisible'}
 if components:f['components']=[{'label':'Cooked salmon','query':'cooked salmon','quantity':180,'unit':'g','estimatedGrams':180,'basis':'photo'}]
 r=estimation.resolve_observation({'foods':[f],'description':'Salmon on plate','question':'','notice':''},s)
 assert r['items'][0]['grams']==180
 assert r['groups'][0]['logged']==4
