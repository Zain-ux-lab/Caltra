from backend.portion_memory import apply_usual_portions, usual_portions

RICE={'id':'rice','name':'Rice, white, boiled','nutrients':{'calories':130,'protein':2.7,'carbs':28,'fat':0.3}}


def meal(day,grams,basis='user'):
    return {'date':day,'items':[{'food':RICE,'grams':grams,'quantityBasis':basis}]}


def test_needs_two_of_your_own_amounts_and_uses_the_recent_median():
    assert usual_portions([meal('2026-11-01',180)])=={}
    assert usual_portions([meal('2026-11-01',180),meal('2026-11-02',250,'assumed')])=={}
    history=[meal(f'2026-11-{day:02d}',grams) for day,grams in [(1,400),(2,170),(3,180),(4,190),(5,160),(6,200)]]
    assert usual_portions(history)=={'rice':180}  # the oldest 400 g is outside the recent five


def test_replaces_estimates_but_keeps_stated_and_shared_amounts():
    history=[meal('2026-11-01',180),meal('2026-11-02',180)]
    result={'items':[
        {'id':'a','food':RICE,'grams':300,'quantityBasis':'photo'},
        {'id':'b','food':RICE,'grams':90,'quantityBasis':'user'},
        {'id':'c','food':RICE,'grams':500,'quantityBasis':'assumed','possibleShared':True}]}
    apply_usual_portions(result,history)
    assert [i['grams'] for i in result['items']]==[180,90,500]
    assert result['items'][0]['quantityBasis']=='assumed'  # accepting it won't count as a new correction
    assert result['items'][0]['portionLabel']=='Your usual portion (180 g)'
    assert result['totals']['calories']==130*(180+90+500)/100


def test_no_history_leaves_the_result_untouched():
    result={'items':[{'id':'a','food':RICE,'grams':300,'quantityBasis':'photo'}],'totals':{'calories':390}}
    assert apply_usual_portions(result,[])['totals']=={'calories':390}


def test_halving_a_guess_does_not_count_as_your_amount():
    halved=[{'date':'2026-11-0'+str(day),'items':[{'food':RICE,'grams':150,'quantityBasis':'user','portionEvidence':'You selected half of the meal estimate'}]} for day in (1,2)]
    assert usual_portions(halved)=={}


def test_photo_route_starts_from_your_usual_portion(tmp_path,monkeypatch):
    import io
    from PIL import Image
    from fastapi.testclient import TestClient
    from backend import vision
    from backend.main import create_app
    rice_id='cofid:11-858'
    monkeypatch.setattr(vision,'select_sources',lambda entries:{i:next(f for f in e['candidates'] if f['id']==rice_id) for i,e in enumerate(entries)})
    monkeypatch.setattr(vision,'recognize',lambda data,note='':{'foods':[{'label':'Boiled basmati rice','query':'basmati rice boiled','estimatedGrams':300,'basis':'photo','visualEvidence':'fills half the plate'}],'description':'rice','question':'','notice':''})
    photo=io.BytesIO();Image.new('RGB',(20,20),'white').save(photo,format='JPEG')
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        rice=client.get('/api/foods?q=basmati rice').json()['foods']
        rice=next(f for f in rice if f['id']==rice_id)
        for day,grams in [('2026-11-01',180),('2026-11-02',200)]:
            client.post('/api/meals',json={'id':day,'name':'Rice','date':day,'items':[{'id':'r','food':rice,'grams':grams,'quantityBasis':'user'}]})
        item=client.post('/api/recognize',files={'file':('rice.jpg',photo.getvalue(),'image/jpeg')}).json()['items'][0]
    assert item['food']['id']==rice_id and item['grams']==190
    assert item['portionLabel']=='Your usual portion (190 g)'
