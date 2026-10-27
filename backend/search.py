"""Rank source records and explicitly distinguish related-food fallbacks."""
import re
from difflib import get_close_matches

# Preparation and portion words must not replace a food's identity in fallbacks.
SEARCH_MODIFIERS=set('cooked raw baked grilled boiled steamed fried roasted poached smoked frozen fresh dry heat no without with in and the a added oil fat butter salt unsalted boneless skinless flesh only fillet fillets piece pieces medium large farmed wild'.split())
COOKED_PREPARATIONS={'baked','grilled','boiled','steamed','roasted','poached','broiled','microwaved'}
SEARCH_MODIFIERS|=COOKED_PREPARATIONS

# Known UK retailer relationships; labels remain attributed to their actual brand.
RETAILER_BRANDS={'lidl':{'lidl','freshona','milbona','crownfield','rowan hill','lighthouse bay','ocean sea'},'asda':{'asda','just essentials'},'tesco':{'tesco'},'aldi':{'aldi','brooklea'}}
SEARCH_MODIFIERS.update({'canned','tinned','drained','reheated','water','brine','spring','in'})


def tokens(text):
    text=re.sub(r'\bchick[ -]?peas?\b','chickpea',text.casefold())
    text=re.sub(r'\bfat[ -]?free\b','fat free',text)
    text=re.sub(r'\btortillas?\b(?!\s+chips\b)','wrap',text)
    words=re.findall(r'[a-z0-9]+',text)
    aliases={'eggs':'egg','tomatoes':'tomato','potatoes':'potato','yoghurt':'yogurt','yoghurts':'yogurt','yogurts':'yogurt','wraps':'wrap','carrots':'carrot','cucumbers':'cucumber','avocados':'avocado','kiwis':'kiwi','blueberries':'blueberry','raspberries':'raspberry','tinned':'canned'}
    return [aliases.get(word,word) for word in words]


def food_terms(food):
    text=food['name']+' '+' '.join(food.get('aliases',[]))+' '+food.get('brand','')
    retailer=food.get('retailer') or ''
    text+=' '+(' '.join(retailer) if isinstance(retailer,list) else retailer)
    terms=set(tokens(text))
    for retailer,brands in RETAILER_BRANDS.items():
        if any(brand in food.get('brand','').casefold() for brand in brands):terms.add(retailer)
    if terms&COOKED_PREPARATIONS:terms.add('cooked')
    return terms


def search_foods(foods,query,limit=40):
    words=tokens(query)
    if not words:return {'foods':foods[:limit],'matchType':'browse','matchedQuery':''}
    retailers=set(words)&RETAILER_BRANDS.keys()
    # A named shop must not offer another shop's branded food as a substitute.
    eligible=[f for f in foods if not retailers or not f.get('brand') or retailers<=food_terms(f)]
    indexed=[(food,food_terms(food)) for food in eligible]
    vocabulary=set().union(*(terms for _,terms in indexed)) if indexed else set()
    normalized=[]
    for word in words:
        if word in vocabulary:normalized.append(word)
        elif word.endswith('s') and word[:-1] in vocabulary:normalized.append(word[:-1])
        else:normalized.append(next(iter(get_close_matches(word,vocabulary,n=1,cutoff=.85)),word))
    requested=set(normalized)
    def rank(food):
        # Prefer the ingredient itself over a dish containing it (carrot vs carrot cake).
        head=set(tokens(food['name'].split('·')[-1].split(',')[0]))
        return (0 if head<=requested else 1 if head&requested else 2,len(food_terms(food)-requested),food['name'])
    exact=[food for food,terms in indexed if requested<=terms]
    if exact:
        exact.sort(key=rank)
        return {'foods':exact[:limit],'matchType':'matched','matchedQuery':' '.join(normalized)}
    identity=requested-SEARCH_MODIFIERS-retailers
    # If the requested ingredient is absent, preparation words cannot replace it.
    anchor=next((word for word in reversed(normalized) if word in identity),None)
    if not anchor:return {'foods':[],'matchType':'none','matchedQuery':query}
    # Keep animal identity when a requested cut/preparation is unavailable.
    species=identity&{'chicken','turkey','lamb','beef','pork','salmon','tuna','cod','haddock'}
    related=[(food,len(terms&requested)) for food,terms in indexed if anchor in terms and species<=terms]
    if not related:return {'foods':[],'matchType':'none','matchedQuery':query}
    related.sort(key=lambda pair:(-pair[1],rank(pair[0])))
    return {'foods':[food for food,_ in related[:limit]],'matchType':'related','matchedQuery':anchor}


def photo_matches(foods,query,label):
    """Use an explicit generic record when descriptive photo text has no full match."""
    ranked=search_foods(foods,query)
    query_words=set(tokens(query))
    query_words|={word[:-1] for word in query_words if word.endswith('s')}
    words=set(tokens(query+' '+label))
    words|={word[:-1] for word in words if word.endswith('s')}
    generic=[]
    for food in foods:
        name=tokens(food['name'])
        if name and name[-1]=='nfs':
            base=set(name[:-1])
            if base and base<=query_words and query_words<=base|{word+'s' for word in base}:
                return {'foods':[food],'matchType':'approximate','matchedQuery':food['name']}
            if base and base<=words and all(food.get('nutrients',{}).get(k) is not None for k in ('calories','protein','carbs','fat')):
                generic.append((base,food))
    if ranked['matchType']=='matched':return ranked
    # Prefer the most specific generic phrase; don't choose between unrelated foods.
    if generic:
        length=max(len(base) for base,_ in generic)
        best=[food for base,food in generic if len(base)==length]
        if len(best)==1:
            return {'foods':best,'matchType':'approximate','matchedQuery':best[0]['name']}
    return ranked


# Whole-dish anchors prevent an ingredient from standing in for a composite meal.
DISH_WORDS={'omelet','curry','soup','stew','salad','sandwich','pizza','biryani','lasagna','cookie','cake','pancake','waffle','burger','burrito','taco','quiche','risotto','porridge'}

def dish_tokens(text):
    return [word[:-1] if word.endswith('s') and word[:-1] in DISH_WORDS else word for word in tokens(text.lower().replace('omelette','omelet').replace('cheesy','cheese'))]


def photo_candidates(foods,query,label):
    label_words=set(dish_tokens(label))
    anchors=label_words&DISH_WORDS
    eligible=[f for f in foods if 'as ingredient' not in f['name'].lower()]
    if len(anchors)==1:
        anchor=next(iter(anchors))
        eligible=[f for f in eligible if anchor in dish_tokens(f['name'])]
        # The observation's dish identity takes precedence over a bad search query.
        query=' '.join(dish_tokens(label))
    else:
        result=photo_matches(eligible,query,label)
        if result['matchType']=='approximate' and len(result['foods'])==1:return result['foods']
    requested=set(dish_tokens(query+' '+label))-{'with','and','or','a','the','on','toppings','topping'}
    ranked=[]
    for food in eligible:
        terms=set(dish_tokens(food['name']))
        overlap=len(terms&requested)
        if overlap:
            ranked.append((food,overlap))
    ranked.sort(key=lambda pair:(-pair[1],len(dish_tokens(pair[0]['name'])),pair[0]['name']))
    # Keep a true generic record alongside specific preparations for semantic selection.
    chosen=[f for f,_ in ranked[:35]]
    for food,_ in ranked:
        if food['name'].lower().endswith(', nfs') and food not in chosen:
            chosen.append(food)
        if len(chosen)>=40:break
    return chosen
