"""Synthetic multi-picture JPEGs; no personal image fixtures."""
import io
from PIL import Image
from backend.recognition import decode_image


def mpo_photo():
    primary=Image.new('RGB',(30,20),'red')
    secondary=Image.new('RGB',(30,20),'blue')
    exif=Image.Exif();exif[274]=6;exif[315]='Private camera metadata'
    output=io.BytesIO()
    primary.save(output,format='MPO',save_all=True,append_images=[secondary],exif=exif)
    return output.getvalue()


def test_multi_picture_jpeg_uses_primary_frame_and_honours_orientation():
    data=mpo_photo()
    with Image.open(io.BytesIO(data)) as original:
        assert original.format=='MPO'
        assert original.n_frames==2
    photo=decode_image(data)
    assert photo.mode=='RGB'
    assert photo.size==(20,30)
    r,g,b=photo.getpixel((10,10))
    assert r>200 and b<40
    assert not photo.info
    out=io.BytesIO();photo.save(out,format='JPEG')
    with Image.open(io.BytesIO(out.getvalue())) as encoded:
        assert encoded.format=='JPEG'
        assert not encoded.getexif()


def test_mpo_reaches_photo_analysis_without_network(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend import vision
    import httpx,json
    monkeypatch.setenv('GEMINI_API_KEY','test-key')
    calls=[]
    def response(url,**kwargs):
        calls.append(kwargs['json'])
        result={'foods':[],'description':'Synthetic fixture','question':''}
        return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':json.dumps(result)}]}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(vision.httpx,'post',response)
    with TestClient(create_app(tmp_path/'test.sqlite')) as client:
        r=client.post('/api/recognize',files={'file':('phone.jpeg',mpo_photo(),'image/jpeg')})
        assert r.status_code==200,r.text
    assert calls
    assert calls[0]['contents'][0]['parts'][1]['inlineData']['mimeType']=='image/jpeg'
