from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Item(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1,max_length=100)
    label:str=Field(default='',max_length=100)
    clarification:str=Field(default='',max_length=300)
    food: dict
    grams: float = Field(gt=0,le=100000,allow_inf_nan=False)
    quantityKind: Literal['measured','estimated'] = 'estimated'
    quantityBasis: Literal['photo','user','assumed'] = 'assumed'
    portionEvidence:str=Field(default='',max_length=400)
    portionLabel: str = Field(default='',max_length=200)
    usingUsualProduct:bool=False


class Meal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1,max_length=100)
    name: str = Field(min_length=1,max_length=100)
    date: date
    items: list[Item] = Field(min_length=1,max_length=40)
    notes: str = Field(default='',max_length=2000)
    homemade:bool=False
    mealType:Literal['breakfast','lunch','dinner','snacks','unassigned']='unassigned'


class Chat(BaseModel):
    message: str = Field(min_length=1,max_length=2000)
    items: list[Item] = Field(max_length=40)
    history: list[dict] = Field(default_factory=list,max_length=12)
    version: int = 0


class Recipe(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    items: list[Item] = Field(min_length=1,max_length=40)
    yieldGrams: float = Field(gt=0,le=100000,allow_inf_nan=False)


class Refine(Chat):
    homemade:bool=False
    pendingQuestion:str=Field(default='',max_length=300)
    unresolved:list[str]=Field(default_factory=list,max_length=40)
    observation:str=Field(default='',max_length=2000)


class Favorite(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    items:list[Item]=Field(min_length=1,max_length=40)
    observation:str=Field(default='',max_length=2000)
    id:str|None=Field(default=None,max_length=100)
