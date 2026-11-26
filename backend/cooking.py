"""Swap a CoFID food for the same food cooked another way (raw, boiled, fried in oil and so on).

CoFID lists each cooking method as its own record, and a fried record already includes the fat
the food absorbed, so swapping the record is more accurate than adding oil on top.
"""
METHODS=('raw','boiled','steamed','poached','stewed','casseroled','microwaved','baked','roasted','grilled','barbecued','fried','stir-fried','deep-fried')


def cooking_key(name):
    """Split a CoFID name into (the food, how it was cooked), or None when it can't be split safely.

    'Mushrooms, white, fried in corn oil' -> ('mushrooms, white', 'fried in corn oil')
    """
    if 'weighed with' in name:return None  # the weight includes bone or skin, so it isn't the same food as eaten
    parts=name.split(', ')
    methods=[part for part in parts if part.split()[0].lower() in METHODS]
    # Two cooking steps (e.g. 'baked, ... fried') could pair the wrong records, so leave those alone.
    if len(methods)!=1:return None
    return ', '.join(part for part in parts if part!=methods[0]).lower(),methods[0]


def cooking_variants(food,cofid):
    """Other CoFID records for the same food that differ only in how it was cooked."""
    if not food.get('source','').startswith('UK CoFID') or not (key:=cooking_key(food['name'])):
        return []
    return [other for other in cofid if other['id']!=food['id'] and (match:=cooking_key(other['name'])) and match[0]==key[0]]
