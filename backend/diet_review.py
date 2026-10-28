"""Coverage-aware dietary patterns, not clinical deficiency assessments."""
from datetime import timedelta
from .nutrition import nutrient_coverage
from .nutrients import NUTRIENTS

REFERENCES={
 'fibre':(30,'Try oats, wholegrain bread or extra chickpeas/lentils in a curry or salad.','https://www.nhs.uk/live-well/eat-well/digestive-health/how-to-get-more-fibre-into-your-diet/'),
 'calcium':(700,'Consider milk, yogurt, cheese or a calcium-fortified alternative.','https://www.nhs.uk/conditions/vitamins-and-minerals/calcium/'),
 'vitaminC':(40,'Try peppers, citrus fruit, strawberries or broccoli alongside your usual meals.','https://www.nhs.uk/conditions/vitamins-and-minerals/vitamin-c/'),
}


def review(meals,end,period,completed_dates):
    if period not in (3,7):raise ValueError('Choose 3 or 7 days.')
    dates=[(end-timedelta(days=n)).isoformat() for n in reversed(range(period))]
    days=[]
    for day in dates:
        items=[i for m in meals if m['date']==day for i in m.get('items',[])]
        days.append({'date':day,'logged':bool(items),'complete':day in completed_dates,'coverage':nutrient_coverage(items)})
    nutrients=[]
    for key,label,unit,_ in NUTRIENTS:
        usable=[d['coverage'][key]['value'] for d in days if d['logged'] and d['complete'] and d['coverage'][key]['complete']]
        reference=REFERENCES.get(key)
        enough=len(usable)>=3
        average=sum(usable)/len(usable) if usable else None
        below=sum(v<reference[0] for v in usable) if reference else None
        recurring=bool(enough and reference and below>=max(3,(len(usable)+1)//2) and average<reference[0])
        status='insufficient_data' if not enough else 'below_reference' if recurring else 'within_reference' if reference else 'recorded_average'
        message=(f'At least 3 complete days with full {label.lower()} coverage are needed; {len(usable)} available.' if not enough else
                 f'Recorded intake was below the general adult reference on {below} of {len(usable)} covered days.' if recurring else
                 'No recurring low-intake pattern against this general adult reference.' if reference else
                 'Recorded average only; needs vary by age, sex and individual circumstances.')
        nutrients.append({'key':key,'label':label,'unit':unit,'average':average,'coveredDays':len(usable),'daysBelow':below,'status':status,'message':message,'reference':reference[0] if reference else None,'suggestions':[reference[1]] if recurring else [],'source':reference[2] if reference else None})
    return {'start':dates[0],'end':dates[-1],'period':period,'loggedDays':sum(d['logged'] for d in days),'completedDays':sum(d['logged'] and d['complete'] for d in days),'missingDays':sum(not d['logged'] for d in days),'days':[{k:v for k,v in d.items() if k!='coverage'} for d in days],'nutrients':nutrients,'notice':'For generally healthy adults. These are patterns in your recorded diet, not a diagnosis. Missing days and unknown nutrient values are never treated as zero. Portions remain estimates.'}
