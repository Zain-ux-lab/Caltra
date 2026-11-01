"""Offline regressions: python -m unittest discover -s tests -p test_diagnostic_export.py."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
from backend.models import Meal, Refine
from backend import diagnostics, estimation, vision
from backend.database import postgres_sql
from backend.search import search_foods
from backend.store import Store
from backend.main import create_app


def banana():
    return {'id':'cofid:test-banana','name':'Bananas, flesh only','source':'UK CoFID 2021',
            'nutrients':{'calories':90,'protein':1,'carbs':20,'fat':0.3,'potassium':350},'portions':[]}


class RouteClient:
    """Invoke endpoint functions directly; no ASGI/thread transport dependencies."""
    def __init__(self, app):self.app=app
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def request(self,method,path,payload=None):
        route=next(r for r in self.app.routes if r.path==path.split('?')[0] and method in r.methods)
        if method=='POST':result=route.endpoint((Meal if path=='/api/meals' else Refine).model_validate(payload))
        elif path.startswith('/api/export'):result=route.endpoint(diagnostics='diagnostics=true' in path)
        else:result=route.endpoint()
        from fastapi.responses import JSONResponse
        if not isinstance(result,JSONResponse):result=JSONResponse(result)
        result.json=lambda:json.loads(result.body)
        result.text=result.body.decode()
        return result
    def get(self,path):return self.request('GET',path)
    def post(self,path,json):return self.request('POST',path,json)
    def delete(self,path):return self.request('DELETE',path)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.directory.name)/'test.sqlite')
        self.store.cache_food(banana())

    def tearDown(self):
        self.directory.cleanup()

    def test_trace_snapshots_and_failures(self):
        value={'amount':10}
        def operation():
            diagnostics.record('before',value=value)
            value['amount']=20
            return value
        diagnostics.capture(self.store,'correction',value,operation)
        trace=self.store.diagnostics()[0]
        self.assertEqual(trace['input']['amount'],10)
        self.assertEqual(trace['steps'][0]['value']['amount'],10)
        self.assertEqual(trace['result']['amount'],20)
        with self.assertRaises(ValueError):
            diagnostics.capture(self.store,'failure',{},lambda:(_ for _ in ()).throw(ValueError('private provider response')))
        self.assertEqual(self.store.diagnostics()[0]['errorType'],'ValueError')
        self.assertNotIn('private provider response',str(self.store.diagnostics()))

    def test_trace_failure_does_not_fail_save(self):
        with patch.object(self.store,'save_diagnostic',side_effect=RuntimeError('disk unavailable')):
            self.assertEqual(diagnostics.capture(self.store,'save',{},lambda:42),42)

    def test_retention_and_delete(self):
        for n in range(205):self.store.save_diagnostic({'id':str(n)})
        self.assertEqual(len(self.store.diagnostics()),200)
        self.assertEqual(self.store.diagnostics()[-1]['id'],'5')
        self.store.clear_diagnostics()
        self.assertEqual(self.store.diagnostics(),[])

    def test_postgres_diagnostic_insert(self):
        self.assertEqual(postgres_sql('INSERT INTO diagnostics VALUES (?,?)'),
                         'INSERT INTO diagnostics (id,data) VALUES (%s,%s)')

    def test_export_and_saved_edits(self):
        with patch.object(Store,'seed'),RouteClient(create_app(Path(self.directory.name)/'api.sqlite')) as client:
            client.app.state.store.cache_food(banana())
            meal={'id':'meal','name':'Banana','date':'2026-10-31','items':[{'id':'item','food':banana(),'grams':100}]}
            self.assertEqual(client.post('/api/meals',json=meal).status_code,200)
            meal['items'][0]['grams']=120
            self.assertEqual(client.post('/api/meals',json=meal).status_code,200)
            response=client.get('/api/export?diagnostics=true')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertIn('caltra-diagnostics.json',response.headers['content-disposition'])
            data=response.json()
            self.assertEqual(data['meals'][0]['items'][0]['grams'],120)
            self.assertEqual(data['diagnostics'][0]['input']['previous']['items'][0]['grams'],100)
            self.assertEqual(data['diagnostics'][0]['result']['items'][0]['grams'],120)
            self.assertNotIn('diagnostics',client.get('/api/export').json())
            client.delete('/api/diary')
            self.assertEqual(client.get('/api/export?diagnostics=true').json()['diagnostics'],[])

    def test_photo_banana_uses_reference_when_selector_declines(self):
        observation={'foods':[{'label':'Banana','query':'banana','estimatedGrams':100,'visibleCount':1,'components':[]}],
                     'description':'One banana','question':'','notice':''}
        with patch.object(vision,'select_sources',return_value={}),patch.object(estimation,'estimate_foods',return_value={}) as guesses:
            result=estimation.resolve_observation(observation,self.store,allow_ai=True)
        self.assertEqual(result['items'][0]['food']['id'],banana()['id'])
        self.assertEqual(result['items'][0]['food']['nutrients']['potassium'],350)
        guesses.assert_not_called()

    def test_correction_replaces_previous_plain_ai_guess(self):
        previous={**banana(),'id':'ai:banana','source':'AI estimate','isAiEstimate':True,'name':'Banana'}
        self.store.cache_estimate(previous)
        items,missing=estimation.resolve_components([{'label':'Banana','query':'banana','sourceId':'ai:banana',
            'quantity':100,'unit':'g','basis':'user'}],self.store,known_ids=['ai:banana'],allow_ai=True)
        self.assertFalse(missing)
        self.assertEqual(items[0]['food']['id'],banana()['id'])

    def test_no_generic_substitution_for_branded_or_composite_food(self):
        for component in [{'label':'Banana','query':'banana','brand':'Example'},
                          {'label':'Banana bread','query':'banana bread'}]:
            self.assertIsNone(estimation.plain_uk_reference(component,[banana()]))

    def test_brand_apostrophes_match(self):
        product={'id':'test','name':'McVities Digestives Milk Chocolate Caramel Millionaire Slice','brand':'McVities'}
        for query in ["McVitie's Digestives",'McVitie’s Digestives']:
            self.assertEqual(search_foods([product],query)['matchType'],'matched')
            self.assertTrue(estimation.product_matches(product,query.split()[0]))

    def test_correction_keeps_lookup_warning_and_trace(self):
        plan={'replace':True,'components':[{'label':'Brand biscuit','query':'biscuit','brand':'Brand','quantity':25,'unit':'g','basis':'user'}],'message':'Updated','question':''}
        item={'id':'biscuit','food':banana(),'grams':25}
        with patch.object(Store,'seed'),RouteClient(create_app(Path(self.directory.name)/'warn.sqlite')) as client, \
             patch.object(vision,'refine',return_value=plan), \
             patch('backend.uk_products.search_product_page',return_value={'foods':[],'warning':'Lookup unavailable','hasMore':True}), \
             patch.object(estimation,'resolve_components',return_value=([item],[])):
            response=client.post('/api/refine',json={'message':'Use Brand','items':[]})
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('Lookup unavailable',response.json()['message'])
            trace=client.get('/api/export?diagnostics=true').json()['diagnostics'][0]
            self.assertEqual(trace['input']['message'],'Use Brand')
            search=next(s for s in trace['steps'] if s['stage']=='product_search')
            self.assertEqual(search['warning'],'Lookup unavailable')

if __name__=='__main__':unittest.main()
