"""Download public, generic FNDDS dish records; never fabricate nutrient values."""
import json,time
from pathlib import Path
import httpx
queries=['biryani','curry','dal','naan','chapati','samosa','pakora','paneer','dosa','idli','kebab','paratha']
ids={2708985,2706538,2706490}
with httpx.Client(timeout=40) as client:
    for query in queries:
        r=client.get('https://api.nal.usda.gov/fdc/v1/foods/search',params={'api_key':'DEMO_KEY','query':query,'pageSize':30})
        r.raise_for_status()
        matches=[f for f in r.json()['foods'] if f['dataType']=='Survey (FNDDS)'][:5]
        for f in matches:
            ids.add(f['fdcId']);print(f['fdcId'],f['description'],flush=True)
    r=client.get('https://api.nal.usda.gov/fdc/v1/foods',params={'api_key':'DEMO_KEY','fdcIds':','.join(map(str,sorted(ids)))})
    r.raise_for_status()
    Path('data/usda-regional-raw.json').write_text(json.dumps(r.json(),indent=2))
