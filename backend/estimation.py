"""Resolve ingredient/whole-dish estimates to source records and deterministic amounts."""
import math
import re
import uuid
from datetime import datetime,timezone
from . import vision
from .fallback import estimate_foods
from .nutrition import calculate, make_recipe
from .search import search_foods, photo_candidates, tokens


def source_picks(entries,allow_ai):
    try:return vision.select_sources(entries)
    except vision.VisionError:
        if not allow_ai:raise
        # Failed source selection is unresolved, not a reason to skip the fallback
        # or discard independently resolved products from the same meal.
        return {}


def validate_photo_quantities(result,note):
    """A model's 'user' flag is not evidence that the user gave a consumed weight."""
    normalized=' '.join(note.casefold().split())
    for food in result['foods']:
        for entry in [food]+food.get('components',[]):
            if entry.get('basis')!='user':continue
            if entry is not food and entry.get('unit','g') not in {'g','gram','grams'}:continue
            quote=' '.join((entry.get('weightEvidence') or '').casefold().split())
            grams=entry.get('quantity') if entry is not food else entry.get('estimatedGrams')
            identity=set(tokens(entry['label']+' '+entry['query']))-{'g','gram','grams','protein','lidl','asda','tesco'}
            values=[float(n)*(1000 if unit=='kg' else 1) for n,unit in re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(kg|grams?|g)\b',quote)]
            valid=quote and quote in normalized and not re.search(r'\b(?:pack|packet|package|net|per|100g)\b',quote) and bool(identity&set(tokens(quote))) and grams is not None and any(abs(v-grams)<.01 for v in values)
            if not valid:entry['basis']='photo' if entry is food else 'assumed'


def preserve_amounts(components,current):
    """Keep existing portions unless the correction explicitly supplies an amount."""
    for component in components:
        if component.get('basis')=='user' or component.get('amountScope')=='batch':continue
        previous=component.get('previousItemId')
        if previous and sum(c.get('previousItemId')==previous for c in components)!=1:continue
        if not previous and sum(c.get('sourceId')==component.get('sourceId') for c in components)!=1:continue
        matches=[i for i in current if i['id']==previous] if previous else [i for i in current if i['food']['id']==component.get('sourceId')]
        if len(matches)!=1:continue
        item=matches[0]
        component.update(quantity=item['grams'],unit=item['food'].get('nutritionBasis','g'),estimatedGrams=item['grams'],basis=item.get('quantityBasis','assumed'))
        component['visualEvidence']=item.get('portionEvidence','') if component['basis']=='photo' else None
        component['weightEvidence']=item.get('portionEvidence','') if component['basis']=='user' else None


def remove_guessed_duplicates(items,current):
    """A more specific name must not add a second guessed serving of an old food."""
    keep=list(items)
    for old in current:
        ident=old['food']['id']
        if sum(i['food']['id']==ident for i in current)!=1:continue
        matches=[i for i in keep if i['food']['id']==ident]
        retained=next((i for i in matches if i['grams']==old['grams']),None)
        if retained is not None:
            keep=[i for i in keep if i is retained or i['food']['id']!=ident or i.get('quantityBasis')=='user']
    return keep


def generic_berry(component,records):
    """Plain berries may use a disclosed generic UK proxy, never a branded guess."""
    words=set(tokens(component['label']+' '+component['query']))
    fruits=words&{'blueberry','raspberry'}
    allowed={'blueberry','raspberry','frozen','fresh','raw','plain','unsweetened','lidl','asda','tesco','aldi'}
    if len(fruits)!=1 or words-allowed:return None
    name={'blueberry':'Blueberries','raspberry':'Raspberries, raw'}[next(iter(fruits))]
    source=next((f for f in records if f.get('source')=='UK CoFID 2021' and f['name']==name),None)
    if not source:return None
    return {**source,'sourceWarning':'Generic UK plain-berry nutrition used as a proxy; this is not an exact supermarket product label. Frozen preparation may differ.'}


def personal_reference(component,records):
    words=set(tokens(component['label']+' '+component['query']+' '+(component.get('brand') or '')))
    if words&{'with','filled','chicken','salad','beef','lentil','kebab','patty','tuna'}:return None
    matches=[]
    for food in records:
        if not food.get('personalReference') or not food.get('referenceTerms'):continue
        if not set(food['referenceTerms'])<=words:continue
        if component.get('brand') and not set(tokens(component['brand']))<=set(tokens(food.get('brand',''))):continue
        if component.get('packGrams') is not None and component['packGrams']!=food.get('packGrams'):continue
        matches.append(food)
    return matches[0] if len(matches)==1 else None


def product_matches(food,brand,pack=None):
    return bool(food.get('brand')) and set(tokens(brand))<=set(tokens(food['brand'])) and (pack is None or abs(food.get('packGrams',0)-pack)<1)


def preparation_matches(food,description):
    text=description.lower()
    name=food.get('name','').lower()
    requested=set(tokens(description))
    source_words=set(tokens(name))
    # A shared ingredient name cannot justify a materially different complete dish.
    if 'cheese' in requested:
        major={'cauliflower','broccoli','macaroni','pasta','potato','chicken','beef','lamb','fish','rice','lentil','chickpea','spinach'}
        if (source_words & major)-requested:return False
    cooked=r'\b(?:cooked|boiled|steamed|microwave|ready to eat)\b'
    # As-sold rice labels cannot be applied to cooked mass, even for a usual brand.
    if 'rice' in text and re.search(cooked,text) and not re.search(cooked,name):return False
    if re.search(r'\b(?:skinless|skin removed|without skin)\b',text):
        if re.search(r'\b(?:and skin|with skin|skin.on)\b',name):return False
    if 'drained' in text and re.search(r'whole contents|undrained',name):return False
    if re.search(r'boneless|meat only',text) and 'weighed with bone' in name:return False
    if not food.get('includesAddedFat'):return True
    if re.search(r'\b(?:no|without)\s+(?:(?:added|olive|cooking)\s+)?(?:oil|fat|butter|ghee)\b',text):return False
    return bool(re.search(r'\b(?:with|in)\s+(?:(?:olive|vegetable|cooking|sunflower)\s+)?(?:oil|butter|ghee)\b',text))


def ingredient_candidates(records,query,label,brand=None,pack=None):
    query=query.lower().replace('half fat','reduced fat').replace('low fat','reduced fat')
    # A cooked fish portion is not a raw recipe ingredient, even if the model
    # accidentally asks for a raw database entry during a species correction.
    species={'salmon','cod','haddock','tuna','trout','mackerel','tilapia','seabass'}
    cooked={'cooked','fried','grilled','baked','steamed','poached','roasted'}
    if set(tokens(label))&species and set(tokens(label))&cooked:
        query=re.sub(r'\braw\b','cooked',query)
        records=[f for f in records if set(tokens(f['name']))&cooked and 'raw' not in tokens(f['name'])]
    records=[f for f in records if preparation_matches(f,label+' '+query)]
    records=[f for f in records if product_matches(f,brand,pack)] if brand else [f for f in records if not f.get('brand')]
    ranked=search_foods(records,query)
    if ranked['matchType']=='matched':return [f for f in ranked['foods'] if all(f['nutrients'].get(k) is not None for k in ('calories','protein','carbs','fat'))][:30]
    if ranked['foods']:records=ranked['foods']
    requested=set(tokens(query+' '+label))-{'with','and','the','a','g','grams'}
    scored=[(f,len(set(tokens(f['name']))&requested)) for f in records if all(f['nutrients'].get(k) is not None for k in ('calories','protein','carbs','fat'))]
    scored=[(f,score) for f,score in scored if score>0]
    scored.sort(key=lambda pair:(-pair[1],len(tokens(pair[0]['name'])),pair[0]['name']))
    return [f for f,_ in scored[:30]]


def batch_divisor(component):
    if component.get('amountScope')!='batch':return 1
    servings=component.get('batchServings')
    if isinstance(servings,bool) or not isinstance(servings,(int,float)) or not math.isfinite(servings) or servings<=0:
        raise ValueError('How many portions did the batch make?')
    return servings


def component_grams(component,food):
    quantity=component.get('quantity')
    unit=component.get('unit','g').strip().lower()
    if food.get('nutritionBasis')=='ml':
        # Legacy amount field is named grams; for ml-labelled foods it holds ml.
        factors={'ml':1,'millilitre':1,'millilitres':1,'l':1000,'litre':1000,'tsp':5,'teaspoon':5,'teaspoons':5,'tbsp':15,'tablespoon':15,'tablespoons':15}
        if quantity is None or unit not in factors or isinstance(quantity,bool) or not isinstance(quantity,(int,float)) or not math.isfinite(quantity) or not 0<quantity*factors[unit]<=10000:raise ValueError('Enter a volume in ml for this product; grams cannot be silently converted.')
        return round(quantity*factors[unit]/batch_divisor(component),4)
    volume={'cup':48,'cups':48,'tablespoon':3,'tablespoons':3,'tbsp':3,'teaspoon':1,'teaspoons':1,'tsp':1}
    if quantity is not None and (isinstance(quantity,bool) or not math.isfinite(quantity) or quantity<=0):raise ValueError('Invalid amount.')
    if quantity is not None and unit in {'tin','tins','can','cans'} and 'drained' in (component['label']+' '+component.get('query','')).lower() and re.search(r'chickpea|kidney|bean|lentil',component['label'],re.I):
        grams=quantity*food.get('drainedGrams',240)
    elif component.get('basis') in {'photo','assumed'} and component.get('estimatedGrams') is not None and (component.get('basis')=='photo' or unit in volume) and unit not in {'g','gram','grams'}:
        # A visual 'cup/fillet' description must not replace the actual visual
        # mass estimate with a database's average reference portion.
        grams=component['estimatedGrams']
    elif quantity is not None and unit in {'g','gram','grams'}:grams=quantity
    elif quantity is not None:
        grams=None
        for portion in food.get('portions',[]):
            match=re.fullmatch(r'([0-9.]+)\s+(.+)',portion['label'].strip().lower())
            if match and float(match[1])>0:
                source_unit=match[2]
                if source_unit==unit:
                    grams=quantity*portion['grams']/float(match[1]);break
                if unit in volume and source_unit in volume:
                    grams=quantity*volume[unit]/volume[source_unit]*portion['grams']/float(match[1]);break
        if grams is None:grams=component.get('estimatedGrams')
    else:grams=component.get('estimatedGrams')
    if isinstance(grams,bool) or not isinstance(grams,(float,int)) or not math.isfinite(grams) or not 0<grams<=10000:raise ValueError('No usable amount.')
    return round(grams/batch_divisor(component),4)


def clarification(label):
    words=set(tokens(label))
    if re.search(r'\b(?:b[oö]rek|pastry|pie|flatbread)\b',label,re.I) and not words&{'cheese','beef','chicken','meat','spinach','apple','lentil','potato'}:
        return 'Was this plain bread or a filled pie/pastry, and what was the filling if you know?'
    if 'cheese' in words and words&{'baked','grilled','dish'} and not words&{'feta','halloumi','cheddar','mozzarella','cottage','ricotta','cauliflower','broccoli','macaroni','pasta','pie','omelette'}:
        return 'What type of cheese was this, and was it baked in oil or served in a sauce?'
    if words&{'fish','fillet','fillets'} and not words&{'salmon','cod','haddock','tuna','tilapia','trout','mackerel','sardine','seabass','halibut'}:
        return 'What type of fish is this — salmon, cod, or something else?'
    if 'rice' in words and not words&{'basmati','jasmine','arborio','sushi','wild'}:
        return 'What kind of rice is this — basmati, jasmine, or another type?'
    return ''


def set_portion_evidence(item,observation):
    basis=observation.get('basis','assumed')
    evidence=(observation.get('visualEvidence') or '').strip()
    if basis=='photo' and (not evidence or not observation.get('estimatedGrams')):basis='assumed'
    item['quantityBasis']=basis
    if basis=='assumed' and item.get('portionLabel','').startswith('Photo estimate'):
        item['portionLabel']=item['portionLabel'].replace('Photo estimate','Assumed portion',1)
    item['portionEvidence']=evidence if basis=='photo' else (observation.get('weightEvidence') or '') if basis=='user' else ''


def observation_portion_label(food):
    if food.get('basis')=='user':return 'Your quantity'
    if not food.get('estimatedGrams'):return 'Assumed reference serving; no usable photo weight'
    return 'Photo estimate' if food.get('basis')=='photo' and food.get('visualEvidence') else 'Assumed portion'


def item_for(food,grams,label,identified=''):
    item={'id':str(uuid.uuid4()),'food':food,'grams':grams,'quantityKind':'estimated','portionLabel':label,'label':identified or food['name'],'clarification':clarification(identified or food['name'])}
    calculate([item])
    return item


def resolve_components(components,store,known_ids=(),allow_ai=False,usual_products=(),group_count=1):
    records=store.foods()
    entries=[]
    selected={}
    reference_defaults=set()
    missing=[]
    for index,component in enumerate(components):
        from .usual_products import find_usual
        usual=find_usual(component,usual_products)
        ident=component.get('sourceId')
        reference=personal_reference(component,records)
        if ident and ident in known_ids and store.food(ident) and preparation_matches(store.food(ident),component['label']+' '+component['query']) and (not component.get('brand') or product_matches(store.food(ident),component['brand'],component.get('packGrams'))):selected[index]=store.food(ident)
        elif usual and preparation_matches(usual,component['label']+' '+component['query']):selected[index]=usual
        elif reference:
            selected[index]=reference
            reference_defaults.add(index)
        else:
            candidates=ingredient_candidates(records,component['query'],component['label'],component.get('brand'),component.get('packGrams'))
            # Cooking changes rice hydration; a dry branded label is not a match.
            # Use a clearly named generic cooked reference instead of inventing label values.
            if not candidates and component.get('brand') and 'rice' in component['query'].lower() and re.search(r'\b(?:cooked|boiled|steamed)\b',component['label']+' '+component['query'],re.I):
                candidates=ingredient_candidates(records,component['query'],component['label'])
            if candidates:entries.append((index,{'label':component['label']+'; search '+component['query'],'ingredient':True,'candidates':candidates}))
            else:missing.append(component['label'])
    if entries:
        picks=source_picks([entry for _,entry in entries],allow_ai)
        for index,food in picks.items():
            allowed={f['id']:f for f in entries[index][1]['candidates']}
            if food and food['id'] not in allowed:raise vision.VisionError('Ingredient source was not in the candidate list.')
            selected[entries[index][0]]=allowed.get(food['id']) if food else None
    for index,component in enumerate(components):
        if not selected.get(index):
            generic=generic_berry(component,records)
            if generic:selected[index]=generic
    if allow_ai:
        unresolved=[i for i in range(len(components)) if not selected.get(i)]
        guesses=estimate_foods([components[i] for i in unresolved],store) if unresolved else {}
        for j,(food,grams) in guesses.items():
            i=unresolved[j];selected[i]=food
            if not components[i].get('estimatedGrams') and grams:components[i]={**components[i],'estimatedGrams':grams}

    missing=[]
    items=[]
    for index,component in enumerate(components):
        food=selected.get(index)
        if not food:
            if component['label'] not in missing:missing.append(component['label'])
            continue
        try:
            if index in reference_defaults and component.get('basis')!='user' and component.get('unit','g') in {'g','gram','grams'}:
                component={**component,'quantity':food['defaultPortionGrams']*group_count,'unit':'g','estimatedGrams':food['defaultPortionGrams']*group_count,'basis':'assumed'}
            grams=component_grams(component,food)
            basis={'user':'Your quantity','photo':'Photo estimate','assumed':'Assumed quantity'}.get(component.get('basis'),'Assumed quantity')
            quantity=component.get('quantity')
            unit=component.get('unit','g')
            detail=f'{quantity:g} {unit}' if quantity is not None and component.get('basis')=='user' else f'≈ {grams:g} g'
            identified=food['name'].split('—')[0].strip() if food.get('personalReference') else component['label']
            item=item_for(food,grams,f'{basis}: {detail}',identified)
            set_portion_evidence(item,component)
            if component.get('amountScope')=='batch':item['portionLabel']+=f" · batch divided into {component['batchServings']:g} servings"
            if unit.lower() in {'tin','tins','can','cans'} and 'drained' in (component['label']+' '+component['query']).lower() and re.search(r'chickpea|kidney|bean|lentil',component['label'],re.I):
                item['portionLabel']+=f" · {'label' if food.get('drainedGrams') else 'assumed'} {food.get('drainedGrams',240):g} g drained per tin"
                item['quantityBasis']='assumed'
            if any(u['food']['id']==food['id'] for u in usual_products):
                item['usingUsualProduct']=True
                item['portionLabel']+=' · using your usual product'
            items.append(item)
        except ValueError:missing.append(component['label'])
    return items,missing


def photo_label_food(food,store,allow_ai,description):
    raw=food.get('nutritionLabel')
    if not raw:return None
    try:label=vision.ObservedNutritionLabel.model_validate(raw)
    except ValueError:return None
    # Whole-food portions currently use edible grams, so volume labels cannot be applied here.
    if label.nutritionBasis!='g' or not label.evidence.strip():return None
    values={}
    if label.perServing and label.servingAmount:
        values={k:v*100/label.servingAmount for k,v in label.perServing.model_dump().items() if v is not None}
    if label.per100:values.update({k:v for k,v in label.per100.model_dump().items() if v is not None})
    if not values or any(v>(950 if k=='calories' else 100) for k,v in values.items()):return None
    missing=[k for k in ('calories','protein','carbs','fat') if k not in values]
    nutrients={k:None for k in vision.LabelValues.model_fields}
    source=None
    if missing:
        if not allow_ai:return None
        guesses=estimate_foods([{'label':food['label'],'query':food['query'],'description':description+' Readable label values per100g: '+str(values),'estimatedGrams':food.get('estimatedGrams'),'portionScope':'one visible item'}],store)
        if 0 not in guesses:return None
        source=guesses[0][0]
        nutrients.update(source['nutrients'])
    nutrients.update(values)
    source={**(source or {}),'id':'photo-label:'+str(uuid.uuid4()),'name':food['label'],'brand':food.get('brand') or '', 'market':'UK','nutritionBasis':'g','source':'Photo nutrition label + AI estimates' if missing else 'Photo nutrition label','dataType':'AI-transcribed package label; review against pack','url':'','retrievedAt':datetime.now(timezone.utc).isoformat(),'nutrients':nutrients,'portions':[],'labelNutrients':list(values),'labelEvidence':label.evidence,'sourceWarning':'Read from the photo: '+', '.join(values)+'. Check the transcription against the pack.'+(' AI-estimated because absent from the readable label: '+', '.join(missing)+'.' if missing else ''),'isAiEstimate':bool(missing)}
    if food.get('packGrams'):source['packGrams']=food['packGrams']
    if missing:store.cache_estimate(source)
    else:store.cache_food(source)
    return source


def portion_divisor(food):
    """Separate a whole plated portion from one independent item in a group."""
    count=food.get('visibleCount',1)
    if food.get('portionScope')=='allVisible':return 1
    if food.get('portionScope')=='oneItem':return count
    # Older/cached observations have no scope. Plated fish pieces belong together.
    if set(tokens(food['label']))&{'fish','salmon','cod','haddock','trout','mackerel','tilapia','seabass'}:return 1
    return count


def include_shared_extras(result):
    """Keep already detected extras in the reviewable estimate, not a second queue."""
    foods=result['foods']
    existing={f['label'].casefold().strip() for f in foods}
    excluded={name.casefold().strip() for name in result.get('excludedFoods',[])}
    pending=[];added=False
    for label in result.get('unconfirmedExtras',[]):
        key=label.casefold().strip()
        if key in existing or key in excluded:continue
        if len(foods)>=12:
            pending.append(label);continue
        foods.append({'label':label,'query':label,'estimatedGrams':None,'visibleCount':1,'portionScope':'allVisible','basis':'assumed','visualEvidence':None,'components':[],'possibleShared':True})
        existing.add(key);added=True
    result['unconfirmedExtras']=pending
    if added:result['scopeSummary']='Detected table foods included; possible shared foods have assumed quantities. Reduce or remove anything you did not eat.'


def resolve_observation(result,store,allow_ai=False,usual_products=()):
    items=[];groups=[];missing=[];component_missing=[]
    if sum(len(f.get('components',[])) or 1 for f in result['foods'])>40:raise vision.VisionError('Too many ingredients were returned. Try one plate at a time.')
    whole=[]
    for index,food in enumerate(result['foods']):
        food['matches']=[];food['matchType']='none'
        label_source=photo_label_food(food,store,allow_ai,result.get('description',''))
        if label_source and food.get('estimatedGrams'):
            count=portion_divisor(food)
            item=item_for(label_source,food['estimatedGrams']/count,observation_portion_label(food),food['label'])
            items.append(item);groups.append({'id':str(index),'itemIds':[item['id']],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
            food['matches']=[label_source];food['matchType']='photo-label'
            continue
        components=food.get('components',[])
        from .usual_products import find_usual
        if not components and find_usual(food,usual_products):
            components=[{**food,'basis':'photo'}]
            food['components']=components
        count=portion_divisor(food)
        reference=personal_reference(food,store.foods())
        if reference and not components:
            grams=food.get('estimatedGrams')/count if food.get('basis')=='user' and food.get('estimatedGrams') else reference['defaultPortionGrams']*food.get('visibleCount',1)/count
            item=item_for(reference,grams,'Your quantity' if food.get('basis')=='user' else f"Assumed: {reference['portions'][0]['label']} ({grams:g} g), provisional product serving",reference['name'].split('—')[0].strip())
            items.append(item);groups.append({'id':str(index),'itemIds':[item['id']],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
            food['matches']=[reference];food['matchType']='product-reference'
            continue
        if components:
            resolved,unmatched=resolve_components(components,store,allow_ai=allow_ai,usual_products=usual_products,group_count=food.get('visibleCount',1))
            for item in resolved:
                item['grams']/=count
                if count>1:item['portionLabel']=f"1 of {count} visible items; ≈ {item['grams']:g} g of this ingredient"
            if resolved and not unmatched and set(tokens(food['label']))&{'patty','patties','kebab','kebabs'}:
                weight=sum(item['grams'] for item in resolved)
                recipe=make_recipe(food['label'],resolved,weight,'recipe-estimate:'+str(uuid.uuid4()))
                recipe.update(dataType='Estimated homemade dish; ingredient proportions unverified',sourceWarning='Ingredients and proportions are estimated, not a measured recipe. '+recipe.get('sourceWarning',''))
                store.cache_estimate(recipe)
                resolved=[item_for(recipe,weight,'Estimated homemade dish; ingredient proportions assumed',food['label'])]
            items.extend(resolved);component_missing.extend(unmatched);missing.extend(unmatched)
            groups.append({'id':str(index),'itemIds':[i['id'] for i in resolved],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
            food['matchType']='ingredients' if not unmatched else 'partial'
        else:
            records=[f for f in store.foods() if f.get('nutritionBasis','g')=='g']
            if food.get('brand'):
                records=[f for f in records if product_matches(f,food['brand'],food.get('packGrams'))]
            else:records=[f for f in records if not f.get('brand')]
            records=[f for f in records if preparation_matches(f,food['label']+' '+food['query'])]
            candidates=photo_candidates(records,food['query'],food['label'])
            if candidates:whole.append((index,{'label':food['label'],'candidates':candidates}))
            else:missing.append(food['label'])
    if whole:
        picks=source_picks([entry for _,entry in whole],allow_ai)
        for pick,source in picks.items():
            index=whole[pick][0];food=result['foods'][index]
            if source and set(tokens(food['label']))&{'oat','oats','oatmeal'} and not set(tokens(source['name']))&{'oat','oats','oatmeal'}:
                source=None
                result['question']='What ingredients went into the oat cake? Add what you know so I can list and calculate each one.'
            if source:
                allowed={f['id']:f for f in whole[pick][1]['candidates']}
                if source['id'] not in allowed:raise vision.VisionError('Whole-food source was not in the candidate list.')
                source=allowed[source['id']]
                count=portion_divisor(food)
                grams=food.get('estimatedGrams')
                if grams:grams/=count
                else:grams=source.get('portions',[{}])[0].get('grams') if source.get('portions') else None
                if grams:
                    item=item_for(source,grams,observation_portion_label(food),food['label'])
                    items.append(item);groups.append({'id':str(index),'itemIds':[item['id']],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
                    food['matches']=[source];food['matchType']='approximate'
                else:missing.append(food['label'])
            else:missing.append(food['label'])
    for index,food in enumerate(result['foods']):
        if food.get('components') or food['matches']:continue
        generic=generic_berry(food,store.foods())
        if generic and food.get('estimatedGrams'):
            count=portion_divisor(food)
            item=item_for(generic,food['estimatedGrams']/count,observation_portion_label(food),food['label'])
            items.append(item);groups.append({'id':str(index),'itemIds':[item['id']],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
            food['matches']=[generic];food['matchType']='approximate'
    if allow_ai:
        unresolved=[(i,f) for i,f in enumerate(result['foods']) if not f.get('components') and not f['matches']]
        guesses=estimate_foods([{'label':f['label'],'query':f['query'],'estimatedGrams':f.get('estimatedGrams')/portion_divisor(f) if f.get('estimatedGrams') else None,'visibleCount':f.get('visibleCount',1),'portionScope':'one visible item' if portion_divisor(f)>1 else 'all visible pieces in the plated portion','description':result.get('description','')} for _,f in unresolved],store) if unresolved else {}
        for j,(source,guessed_grams) in guesses.items():
            index,food=unresolved[j];count=portion_divisor(food);grams=food.get('estimatedGrams')/count if food.get('estimatedGrams') else guessed_grams
            if not grams:continue
            item=item_for(source,grams,observation_portion_label(food),food['label'])
            items.append(item);groups.append({'id':str(index),'itemIds':[item['id']],'visible':food.get('visibleCount',1),'logged':food.get('visibleCount',1)//count})
            food['matches']=[source];food['matchType']='ai-estimated'
            missing=[label for label in missing if label!=food['label']]
    for group in groups:
        observed=result['foods'][int(group['id'])]
        for item in items:
            if item['id'] in group['itemIds']:item['possibleShared']=bool(observed.get('possibleShared'))
        if observed.get('components'):continue
        for item in items:
            if item['id'] in group['itemIds']:
                if item['food'].get('personalReference') and observed.get('basis')!='user':
                    set_portion_evidence(item,{'basis':'assumed'})
                else:set_portion_evidence(item,observed)
    missing=list(dict.fromkeys(component_missing+[f['label'] for f in result['foods'] if not f.get('components') and not f['matches']]))
    result['question']=next((i['clarification'] for i in items if i.get('clarification')),result.get('question',''))
    result.update(items=items,groups=groups,missing=missing,totals=calculate(items) if items else None)
    return result


def remaining_unresolved(unresolved,items):
    # Conservative identity matching: a related ingredient cannot satisfy the warning.
    from .search import dish_tokens
    ignored={'with','and','the','a','of','ingredient'}
    def words(text):
        text=text.lower().replace('half-fat','reduced fat').replace('half fat','reduced fat')
        special={'tomatoes':'tomato','potatoes':'potato','leaves':'leaf'}
        return {special.get(word,word[:-3]+'y' if word.endswith('ies') else word[:-1] if word.endswith('s') and len(word)>3 else word) for word in dish_tokens(text)}-ignored
    sizes={'medium','large','small','extra','jumbo'}
    sources=[words(i['food']['name'])|(words(i.get('portionLabel',''))&sizes) for i in items]
    return [label for label in unresolved if not words(label) or not any(words(label)<=source for source in sources)]


def apply_explicit_preparation(plan,message,current):
    """Do not let a conversational acknowledgement discard an unambiguous state correction."""
    text=message.lower()
    if not re.search(r'\bcooked\s+(?:white\s+|basmati\s+|jasmine\s+)?rice\b|\brice\b[^.!?]{0,50}\bis cooked\b',text):return plan
    if re.search(r'\b(?:not|isn.t|uncooked)\s+cooked\b|\bif\b|\?',text):return plan
    targets=[i for i in current if 'rice' in tokens(i.get('label') or i['food']['name']) and not set(tokens(i.get('label') or i['food']['name']))&{'biryani','pudding','curry'}]
    if len(targets)!=1:return plan
    target=targets[0]
    if plan['replace']:
        components=[dict(c) for c in plan['components']]
        matches=[c for c in components if c.get('previousItemId')==target['id']]
        if len(matches)!=1:return plan
        component=matches[0]
    else:
        components=[{'label':i.get('label') or i['food']['name'],'query':i.get('label') or i['food']['name'],'quantity':i['grams'],'estimatedGrams':i['grams'],'unit':i['food'].get('nutritionBasis','g'),'basis':'assumed','previousItemId':i['id'],'sourceId':i['food']['id']} for i in current]
        component=next(c for c in components if c['previousItemId']==target['id'])
    label=re.sub(r'\b(?:raw|dry|cooked)\b','',component['label'],flags=re.I).strip()
    component.update(label='Cooked '+label,query='cooked '+label,sourceId=None,brand=None,packGrams=None)
    return {**plan,'replace':True,'components':components,'message':'Updated the cooked-rice nutrition source; existing portion amounts are retained unless changed.','question':plan.get('question','')}
