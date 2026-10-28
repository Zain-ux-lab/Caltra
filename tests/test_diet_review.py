from datetime import date,timedelta
from backend.nutrition import nutrient_coverage


def meal(day,values):
 return {'date':day,'items':[{'id':day,'grams':100,'food':{'name':'Synthetic meal','nutrients':{'calories':2000,'protein':100,'carbs':250,'fat':60,**values}}}]}


def test_missing_days_and_missing_nutrients_are_never_deficits():
 from backend.diet_review import review
 meals=[meal('2026-10-25',{}),meal('2026-10-27',{})]
 r=review(meals,date(2026,10,27),3,{'2026-10-25','2026-10-27'})
 fibre=next(n for n in r['nutrients'] if n['key']=='fibre')
 assert fibre['status']=='insufficient_data' and fibre['average'] is None
 assert r['loggedDays']==2 and r['completedDays']==2 and r['missingDays']==1


def test_consistent_low_fibre_needs_complete_days_and_complete_coverage():
 from backend.diet_review import review
 days=['2026-10-25','2026-10-26','2026-10-27'];meals=[meal(d,{'fibre':12,'vitaminC':60,'calcium':800,'potassium':3600}) for d in days]
 r=review(meals,date(2026,10,27),3,set(days))
 fibre=next(n for n in r['nutrients'] if n['key']=='fibre')
 assert fibre['status']=='below_reference' and fibre['average']==12 and fibre['daysBelow']==3
 assert 'deficient' not in fibre['message'].lower()
 assert fibre['suggestions'] and fibre['source'].startswith('https://www.nhs.uk/')
 r=review(meals,date(2026,10,27),3,set())
 assert next(n for n in r['nutrients'] if n['key']=='fibre')['status']=='insufficient_data'


def test_partial_nutrient_coverage_suppresses_low_intake_claims():
 from backend.diet_review import review
 days=['2026-10-25','2026-10-26','2026-10-27'];meals=[meal(d,{'fibre':12}) for d in days]
 for m in meals:m['items'].append({'id':'unknown','grams':100,'food':{'name':'AI macro-only meal','nutrients':{'calories':100,'protein':5,'carbs':10,'fat':5}}})
 r=review(meals,date(2026,10,27),3,set(days))
 assert next(n for n in r['nutrients'] if n['key']=='fibre')['status']=='insufficient_data'


def test_complete_day_status_persists_and_period_is_validated(tmp_path):
 from backend.main import create_app
 from fastapi.testclient import TestClient
 path=tmp_path/'review.sqlite'
 with TestClient(create_app(path)) as c:
  assert c.post('/api/days/2026-10-27/complete',json={'complete':True}).status_code==200
  assert c.get('/api/diet-review?end=2026-10-27&period=4').status_code==422
 with TestClient(create_app(path)) as c:
  assert c.get('/api/days/2026-10-27').json()['complete'] is True
  assert c.get('/api/diet-review?end=2026-10-27&period=7').status_code==200
