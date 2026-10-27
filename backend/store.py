import json
import sqlite3
from pathlib import Path
from .nutrition import calculate, normalize_food


def uk_source(food):
    source=food.get('source','')
    if source.startswith('USDA'):return False
    if food.get('recipeItems'):return all(uk_source(i['food']) for i in food['recipeItems'])
    if food.get('isAiEstimate'):return True # a labelled guess, never a database reference
    if source.startswith('UK CoFID'):return True
    if food.get('market')=='UK' and (source.startswith('Open Food Facts') or source in {'Your product label','Your product reference','Photo nutrition label'}):return True
    if source=='Your recipe':return bool(food.get('recipeItems')) and all(uk_source(i['food']) for i in food['recipeItems'])
    return False


class Store:
    def __init__(self, path,uk_only=True):
        # Mixed-catalog mode remains for historical migration/parser unit tests.
        # The application always creates a UK-only store by default.
        self.uk_only=uk_only
        self.path = str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS foods (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS estimates (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS meals (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS favorites (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS usual_products (category TEXT PRIMARY KEY, data TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def analysis(self, ident):
        with self.connect() as db:
            row=db.execute('SELECT data FROM analyses WHERE id=?',(ident,)).fetchone()
        value=json.loads(row[0]) if row else None
        if value and self.uk_only and any(not uk_source(i['food']) for i in value.get('items',[])):return None
        return value

    def cache_analysis(self, ident, result):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO analyses VALUES (?,?)',(ident,json.dumps(result)))
            db.execute('DELETE FROM analyses WHERE rowid NOT IN (SELECT rowid FROM analyses ORDER BY rowid DESC LIMIT 500)')

    def cache_food(self,food):
        with self.connect() as db:
            db.execute('INSERT INTO foods VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(food['id'],json.dumps(food)))

    def cache_estimate(self,food):
        with self.connect() as db:
            db.execute('INSERT INTO estimates VALUES (?,?)',(food['id'],json.dumps(food)))

    def food(self, ident):
        with self.connect() as db:
            row=db.execute('SELECT data FROM foods WHERE id=?',(str(ident),)).fetchone()
            if row is None:row=db.execute('SELECT data FROM estimates WHERE id=?',(str(ident),)).fetchone()
        food=json.loads(row[0]) if row else None
        return food if food and (not self.uk_only or uk_source(food)) else None

    def foods(self, query=''):
        words=query.casefold().split()
        with self.connect() as db:
            rows=db.execute('SELECT data FROM foods').fetchall()
        foods=[f for r in rows if (f:=json.loads(r[0])) and (not self.uk_only or uk_source(f))]
        return [f for f in foods if all(w in (f['name']+' '+ ' '.join(f.get('aliases',[]))).casefold() for w in words)]

    def meals(self):
        with self.connect() as db:
            rows=db.execute('SELECT data FROM meals ORDER BY rowid DESC').fetchall()
        meals=[json.loads(r[0]) for r in rows]
        # Enrich old snapshots with missing micronutrients only, from the exact UK record.
        # Historical calories and macros remain as logged.
        from .nutrition import EXTRA_KEYS, nutrient_coverage
        catalog={f['id']:f for f in self.foods() if f['source'].startswith('UK CoFID')}
        for meal in meals:
            for item in meal['items']:
                food=item['food']; reference=catalog.get(food['id'])
                if reference and food.get('source','').startswith('UK CoFID') and reference['name']==food['name'] and not food.get('isAiEstimate'):
                    for key in EXTRA_KEYS:
                        if food['nutrients'].get(key) is None:
                            food['nutrients'][key]=reference['nutrients'].get(key)
            meal['nutrientTotals']=nutrient_coverage(meal['items'])
        return meals

    def setting(self,key):
        with self.connect() as db:row=db.execute('SELECT data FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_setting(self,key,value):
        with self.connect() as db:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
        return value

    def save_meal(self, meal):
        from .nutrition import nutrient_coverage
        meal={**meal, 'totals':calculate(meal['items']),'nutrientTotals':nutrient_coverage(meal['items'])}
        with self.connect() as db:
            db.execute('INSERT INTO meals VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(meal['id'],json.dumps(meal)))
        return meal

    def delete_meal(self,ident):
        with self.connect() as db:
            db.execute('DELETE FROM meals WHERE id=?',(ident,))

    def seed(self):
        names=['cofid-normalized.json'] if self.uk_only else ['usda-survey-normalized.json','usda-generic-normalized.json','cofid-normalized.json']
        paths=[Path(__file__).resolve().parent.parent/'data'/name for name in names]
        for path in paths:
            if not path.exists():continue
            with self.connect() as db:
                db.executemany('INSERT INTO foods VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',[(f['id'],json.dumps(f)) for f in json.loads(path.read_text())])
        for path in ([] if self.uk_only else (Path(__file__).resolve().parent.parent/'data').glob('usda-*-raw.json')):
            raw=json.loads(path.read_text())
            for entry in raw:
                if 'fdcId' in entry: self.cache_food(normalize_food(entry))

        notes_path=Path(__file__).resolve().parent.parent/'data'/'source-preparation-notes.json'
        if notes_path.exists():
            for ident,notes in json.loads(notes_path.read_text()).items():
                food=self.food(ident)
                if food:self.cache_food({**food,**notes})

    def favorites(self):
        with self.connect() as db:
            entries=[json.loads(row[0]) for row in db.execute('SELECT data FROM favorites ORDER BY rowid DESC').fetchall()]
        return [f for f in entries if not self.uk_only or all(uk_source(i['food']) for i in f['items'])]

    def save_favorite(self, value):
        value={**value,'totals':calculate(value['items'])}
        with self.connect() as db:
            db.execute('INSERT INTO favorites VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(value['id'],json.dumps(value)))
        return value

    def delete_favorite(self, ident):
        with self.connect() as db:db.execute('DELETE FROM favorites WHERE id=?',(ident,))

    def usual_products(self):
        with self.connect() as db:
            entries=[json.loads(row[0]) for row in db.execute('SELECT data FROM usual_products ORDER BY category')]
        return [{**entry,'food':self.food(entry['foodId'])} for entry in entries if self.food(entry['foodId'])]

    def save_usual(self, category, food_id):
        entry={'category':category,'foodId':food_id}
        with self.connect() as db:db.execute('INSERT INTO usual_products VALUES (?,?) ON CONFLICT(category) DO UPDATE SET data=excluded.data',(category,json.dumps(entry)))
        return entry

    def delete_usual(self, category):
        with self.connect() as db:db.execute('DELETE FROM usual_products WHERE category=?',(category,))
