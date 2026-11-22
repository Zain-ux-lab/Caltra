"""Labelled vitamin and mineral estimates for foods whose record leaves them blank.

CoFID search proposes generic candidates, Gemini picks one or none, and the values
are copied from that CoFID record: the model never writes a nutrient value.
"""
import re
from . import vision
from .nutrients import NUTRIENTS
from .search import search_foods, tokens

MICRO_KEYS=tuple(key for key,_,_,group in NUTRIENTS if group in ('Vitamins','Minerals'))


def missing_keys(food):
    """Vitamin/mineral keys worth estimating; empty for a food that already carries an estimate."""
    # Per-serving labels can't take per-100 g values, and recipes inherit from their ingredients.
    if 'micronutrientEstimate' in food or food.get('recipeItems') or food.get('nutritionBasis')=='serving' or food.get('source','').startswith('UK CoFID'):
        return []
    nutrients=food['nutrients']
    # Sodium is derived from a label's salt, so a generic value would contradict it.
    return [key for key in MICRO_KEYS if nutrients.get(key) is None and not (key=='sodium' and nutrients.get('salt') is not None)]


def generic_name(food):
    """'Milbona · Greek Yoghurt (500 g)' -> 'greek yogurt'."""
    name=re.sub(r'\([^)]*\)','',food['name'].split('·')[-1])
    brand=set(tokens(food.get('brand','')))
    return ' '.join(word for word in tokens(name) if word not in brand)


def apply_reference(food,keys,reference):
    # shortcut: CoFID is per 100 g, so ml-based labels get a density-1 approximation; fine for a labelled estimate.
    filled=[key for key in keys if reference and reference['nutrients'].get(key) is not None]
    for key in filled:food['nutrients'][key]=reference['nutrients'][key]
    food['micronutrientEstimate']={'fromId':reference['id'],'from':reference['name'],'keys':filled} if filled else {'fromId':None,'from':None,'keys':[]}


def shortlist(cofid,query):
    """CoFID candidates for a generic name.

    Photo labels carry extra words ('white bread slices in basket'), so when the full name finds
    nothing, merge exact matches for each word pair, then each word. Loose 'related' hits from a
    fragment ('slices' -> chicken slices) are dropped; Gemini can still reject what remains.
    """
    result=search_foods(cofid,query,limit=8)
    if result['foods']:return result['foods']
    words=query.split()
    for size in (2,1):
        found={}
        for start in range(len(words)-size+1):
            part=search_foods(cofid,' '.join(words[start:start+size]),limit=8)
            if part['matchType']=='matched':found.update((food['id'],food) for food in part['foods'])
        if found:return list(found.values())[:8]
    return []


BATCH=40  # the selection schema accepts at most 40 entries per request


def fill_missing(foods,cofid,decisions):
    """Fill missing vitamins and minerals in place; return the new decisions (food id -> CoFID id or None).

    Copies of the same food (one per logged meal) share one decision, and earlier decisions are
    reused without asking. No key, a timeout or a provider error leaves that batch unknown and
    undecided, so a later save or backfill retries it.
    """
    by_id={food['id']:food for food in cofid}
    pending={}
    for food in foods:
        if keys:=missing_keys(food):pending.setdefault(food['id'],[]).append((food,keys))
    def settle(ident,reference):
        for food,keys in pending[ident]:apply_reference(food,keys,reference)
    new={};entries=[]
    for ident,copies in pending.items():
        if ident in decisions:
            settle(ident,by_id.get(decisions[ident]));continue
        query=generic_name(copies[0][0])
        candidates=shortlist(cofid,query) if query else []
        if not candidates:
            settle(ident,None);new[ident]=None
        else:entries.append((ident,{'label':copies[0][0]['name'],'candidates':candidates}))
    for start in range(0,len(entries),BATCH):
        batch=entries[start:start+BATCH]
        try:picks=vision.select_generic_references([entry for _,entry in batch])
        except vision.VisionError:continue
        for index,(ident,_) in enumerate(batch):
            reference=picks.get(index)
            settle(ident,reference);new[ident]=reference['id'] if reference else None
    return new
