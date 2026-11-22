"""Official nutrition pages for UK chains Caltra doesn't hold, so you can copy the values yourself.

Links were checked by hand on 21 November 2026 (data/restaurant-links.json); sites move pages,
so a link is a starting point, never a source of nutrient values.
"""
import json
from functools import cache
from pathlib import Path
from .search import tokens


@cache
def links():
    return json.loads((Path(__file__).resolve().parent.parent/'data'/'restaurant-links.json').read_text())


def chain_link(query):
    """The chain a search names, matched on whole names so 'pizza' alone never means Pizza Hut."""
    words=set(tokens(query))
    for chain in links():
        if any(set(tokens(name))<=words for name in chain['names']):
            return {'brand':chain['brand'],'url':chain['url']}
    return None
