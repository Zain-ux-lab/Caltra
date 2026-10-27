"""Download pinned public food models; no paid service or remote Python code."""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent.parent
MODELS={
 'category':('Kaludi/food-category-classification-v2.0','66bc2994c1c707f23cae3ed32eacfbae5e571b08','pytorch_model.bin'),
 'food':('nateraw/food','8991abd49ea01ebf502aeda51d4f12a59c603e01','pytorch_model.bin'),
 'indian':('Subhash5/indian-food-classifier','fac307381c6f2025ebbb79ee1fb1650f89a4c80c','model.safetensors'),
}
parser=argparse.ArgumentParser();parser.add_argument('model',choices=MODELS,default='food',nargs='?');args=parser.parse_args()
repo,rev,weights=MODELS[args.model];directory=ROOT/'models'/args.model;directory.mkdir(parents=True,exist_ok=True)
for filename in ['config.json','preprocessor_config.json',weights]:
    target=directory/filename
    if target.exists():print('Already downloaded:',filename);continue
    print('Downloading',filename,flush=True)
    temporary=target.with_suffix(target.suffix+'.partial')
    with urlopen(f'https://huggingface.co/{repo}/resolve/{rev}/{filename}',timeout=60) as source,temporary.open('wb') as output:
        while chunk:=source.read(1024*1024):output.write(chunk)
    temporary.replace(target)
print('Ready:',args.model)
