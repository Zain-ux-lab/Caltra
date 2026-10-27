from backend import estimation

def test_photo_without_visual_evidence_is_assumed():
 item={}
 estimation.set_portion_evidence(item,{'basis':'photo','estimatedGrams':150})
 assert item['quantityBasis']=='assumed'
 assert not item['portionEvidence']

def test_visual_evidence_preserved():
 item={}
 estimation.set_portion_evidence(item,{'basis':'photo','estimatedGrams':80,'visualEvidence':'A shallow mound covering about a sixth of the plate; depth uncertain.'})
 assert item['quantityBasis']=='photo'
 assert 'shallow mound' in item['portionEvidence']

def test_user_input_not_called_visual():
 item={}
 estimation.set_portion_evidence(item,{'basis':'user','weightEvidence':'two spoonfuls'})
 assert item['quantityBasis']=='user'
 assert item['portionEvidence']=='two spoonfuls'

def test_source_correction_preserves_original_evidence():
 c={'basis':'assumed','previousItemId':'a','label':'Salmon'}
 estimation.preserve_amounts([c],[{'id':'a','grams':90,'food':{'id':'f'},'quantityBasis':'photo','portionEvidence':'Two small thin pieces.'}])
 assert c['basis']=='photo' and c['visualEvidence']=='Two small thin pieces.'

def test_evidence_survives_save_and_load(tmp_path):
 from backend.main import create_app
 from fastapi.testclient import TestClient
 with TestClient(create_app(tmp_path/'test.sqlite')) as c:
  food=c.app.state.store.food('cofid:11-858')
  item={'id':'rice','food':food,'grams':80,'quantityBasis':'photo','portionEvidence':'Small shallow mound; scale uncertain.'}
  r=c.post('/api/meals',json={'id':'evidence','name':'Rice','date':'2026-10-25','items':[item]})
  assert r.status_code==200,r.text
  assert c.get('/api/meals').json()[0]['items'][0]['portionEvidence']==item['portionEvidence']
