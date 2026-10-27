import io
import json
import pytest
import httpx
from PIL import Image
from backend import vision
from backend.main import create_app as _create_app

def create_app(*args,**kwargs):
    return _create_app(*args,uk_only=False,**kwargs)

from fastapi.testclient import TestClient


def photo():
    out=io.BytesIO()
    Image.new('RGB',(20,20),'brown').save(out,format='JPEG')
    return out.getvalue()


def test_missing_key_is_actionable(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    with pytest.raises(vision.VisionError,match='Settings'):
        vision.recognize(photo())


def test_image_is_sent_and_nutrition_is_not_model_generated(monkeypatch,tmp_path):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    def respond(url,**kwargs):
        payload=kwargs['json']
        if len(payload['contents'][0]['parts'])==1:
            result={'selections':[{'index':0,'sourceId':'2707899'}]}
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
        assert payload['contents'][0]['parts'][1]['inlineData']['mimeType']=='image/jpeg'
        assert kwargs['headers']['x-goog-api-key']=='test-key'
        result={'foods':[{'label':'Iced cookie','query':'cookie','estimatedGrams':110}], 'question':'Where did you buy this cookie?', 'description':'One large iced cookie'}
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',respond)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        response=client.post('/api/recognize',files={'file':('cookie.jpg',photo(),'image/jpeg')})
        assert response.status_code==200
        result=response.json()
        assert result['foods'][0]['label']=='Iced cookie'
        assert result['foods'][0]['matches']
        assert result['foods'][0]['matches'][0]['source']=='USDA FoodData Central'
        assert result['foods'][0]['estimatedGrams']==110
        assert 'calories' not in result['foods'][0]


def test_quota_error_does_not_fallback_to_old_classifier(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    def respond(url,**kwargs):
        return httpx.Response(429,request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',respond)
    with pytest.raises(vision.VisionError,match='quota'):
        vision.recognize(photo())


def test_unreliable_output_is_rejected(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    def respond(url,**kwargs):
        result={'foods':[{'label':'cookie','query':'cookie','estimatedGrams':-1,'calories':500}], 'question':'', 'description':'cookie'}
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',respond)
    with pytest.raises(vision.VisionError):vision.recognize(photo())


def test_settings_saves_private_key_without_returning_it(monkeypatch,tmp_path):
    import backend.main as main
    app=create_app(tmp_path/'test.sqlite')
    monkeypatch.setattr(main,'ROOT',tmp_path)
    monkeypatch.setattr(main,'ENV_PATH',tmp_path/'.env')
    monkeypatch.setenv('GEMINI_API_KEY','')
    with TestClient(app) as client:
        key='test-private-key-123'
        response=client.post('/api/settings/gemini',json={'apiKey':key})
        assert response.status_code==200
        assert key not in response.text
        status=client.get('/api/status')
        assert status.json()['visionConfigured'] is True
        assert key not in status.text
        assert (tmp_path/'.env').stat().st_mode & 0o777==0o600
        assert client.post('/api/settings/gemini',json={'apiKey':key},headers={'origin':'https://evil.example'}).status_code==403


def test_descriptive_cookie_gets_generic_macros_without_animal_cookie(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'select_sources',lambda entries:{index:next(f for f in entry['candidates'] if f['name']=='Cookie, NFS') for index,entry in enumerate(entries)})
    monkeypatch.setattr(vision,'recognize',lambda data:{'foods':[{'label':'Iced cookie with toppings','query':'iced cookie with toppings','estimatedGrams':120}],'description':'cookie','question':'','notice':'Estimate'})
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        result=client.post('/api/recognize',files={'file':('cookie.jpg',photo(),'image/jpeg')}).json()['foods'][0]
        assert result['matchType']=='approximate'
        assert result['matches'][0]['name']=='Cookie, NFS'
        assert all(result['matches'][0]['nutrients'][k] is not None for k in ['calories','protein','carbs','fat'])


def test_unrecognised_food_has_no_automatic_generic_match():
    from backend.search import photo_matches
    assert photo_matches([{'name':'Cookie, NFS','aliases':[]}],'zxqvw','zxqvw')['matchType']=='none'


def test_visible_count_is_validated():
    from pydantic import ValidationError
    food=vision.VisibleFood(label='Cookie',query='cookie',estimatedGrams=240,visibleCount=2)
    assert food.visibleCount==2
    with pytest.raises(ValidationError):
        vision.VisibleFood(label='Cookie',query='cookie',estimatedGrams=240,visibleCount=0)


def test_broad_cookie_query_uses_generic_record_not_alphabetical_subtype(tmp_path):
    from backend.search import photo_matches
    from backend.store import Store
    store=Store(tmp_path/'foods.sqlite',uk_only=False)
    store.seed()
    result=photo_matches(store.foods(),'cookie','Cookie with toppings')
    assert result['foods'][0]['name']=='Cookie, NFS'


def test_user_note_is_sent_with_photo_and_overrides_guesses(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    def respond(url,**kwargs):
        payload=kwargs['json']
        assert 'Salmon, basmati rice, no added oil' in payload['contents'][0]['parts'][0]['text']
        assert 'override visual guesses' in payload['systemInstruction']['parts'][0]['text']
        assert 'Do not add a separate oil' in payload['systemInstruction']['parts'][0]['text']
        result={'foods':[{'label':'Salmon with basmati rice','query':'salmon rice','estimatedGrams':200}],'question':'','description':'User-confirmed salmon and rice, no added oil'}
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',respond)
    assert vision.recognize(photo(),'Salmon, basmati rice, no added oil')['foods'][0]['label']=='Salmon with basmati rice'
