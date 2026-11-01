"""Build the shared catalogue from reviewed, numeric-only official source rows.

Run: python scripts/import_restaurants.py
Source snapshots are factual nutrition rows, not copied guides or menu descriptions.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ['calories', 'protein', 'carbs', 'fat', 'saturates', 'sugars', 'fibre', 'salt']


def build():
    records = []
    sources = json.loads((ROOT/'data/restaurant-sources.json').read_text())
    for source in sources:
        with (ROOT/'data/restaurant-rows'/source['file']).open() as f:
            for row in csv.DictReader(f):
                name, section = row['name'], row['section']
                identity = source['brand']+'|'+section+'|'+name
                nutrients = {k: float(row[k]) if row[k] else None for k in KEYS}
                assert all(nutrients[k] is not None and nutrients[k] >= 0 for k in KEYS[:4]), identity
                records.append({
                    'id': 'uk-restaurant:'+hashlib.sha256(identity.encode()).hexdigest()[:20],
                    'name': source['brand']+' · '+name+(' · '+section if section else ''),
                    'brand': source['brand'], 'aliases': source.get('aliases', []),
                    'source': 'Official UK restaurant nutrition', 'market': 'UK',
                    'dataType': 'Published restaurant serving', 'nutritionBasis': 'serving',
                    'url': source['url'], 'retrievedAt': source['retrievedAt'],
                    'sourceVersion': source['version'], 'sourcePage': row['page'],
                    'nutrients': nutrients, 'portions': [{'label': '1 menu serving', 'grams': 1, 'unit': 'serving'}],
                    'sourceWarning': source['scope']+' Published values are per menu serving. Choose the exact size and variant; log sides and drinks separately unless named in this item. Actual preparation may vary.',
                })
    assert len({r['id'] for r in records}) == len(records), 'Duplicate item identities'
    return records


if __name__ == '__main__':
    records = build()
    (ROOT/'data/uk-restaurants.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    print(f'Wrote {len(records)} official UK restaurant records')
