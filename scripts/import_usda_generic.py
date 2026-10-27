"""Import complete usable USDA generic-food releases; no API key or branded inference."""
import hashlib,io,json,math,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from backend.nutrition import normalize_food

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 'Foundation':'https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_json_2026-04-30.zip',
 'SR Legacy':'https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip',
}


def main():
    foods={};provenance=[]
    for kind,url in SOURCES.items():
        downloaded=bytearray()
        with httpx.stream('GET',url,follow_redirects=True,timeout=90) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                downloaded.extend(chunk)
                if len(downloaded)>20_000_000:raise ValueError('Unexpected archive size')
        with zipfile.ZipFile(io.BytesIO(downloaded)) as archive:
            files=[info for info in archive.infolist() if info.filename.endswith('.json')]
            if len(files)!=1 or files[0].file_size>300_000_000:raise ValueError('Unexpected release contents')
            raw=archive.read(files[0]);release=json.loads(raw)
        entries=next(value for value in release.values() if isinstance(value,list))
        accepted=0
        for entry in entries:
            if not isinstance(entry,dict):continue
            food=normalize_food(entry)
            if not all(isinstance(v,(float,int)) and math.isfinite(v) and v>=0 for v in food['nutrients'].values()):continue
            food['releaseSourceUrl']=url;foods[food['id']]=food;accepted+=1
        provenance.append({'dataType':kind,'url':url,'archive_sha256':hashlib.sha256(downloaded).hexdigest(),'json_sha256':hashlib.sha256(raw).hexdigest(),'release_records':len(entries),'usable_complete_macros':accepted,'excluded_unusable_records':len(entries)-accepted})
        print(kind,len(entries),'records;',accepted,'with complete macros',flush=True)
    (ROOT/'data/usda-generic-normalized.json').write_text(json.dumps(list(foods.values()),ensure_ascii=False))
    (ROOT/'data/usda-generic-provenance.json').write_text(json.dumps(provenance,indent=2))
    print('Saved',len(foods),'generic records',flush=True)


if __name__=='__main__':main()
