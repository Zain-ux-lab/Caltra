"""Personal label records and conservative ingredient defaults; never portion facts."""
import re,uuid
from datetime import datetime,timezone
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
from .search import tokens,DISH_WORDS

CATEGORIES={'yogurt':{'yogurt','yoghurt'},'milk':{'milk'},'protein powder':{'protein'},'oats':{'oats','oat'},'honey':{'honey'},'cooking oil':{'oil'},'cheese':{'cheese','cheddar','feta'},'mayonnaise':{'mayonnaise','mayo'},'rice':{'rice'}}

class LabelNutrients(BaseModel):
 model_config=ConfigDict(extra='forbid')
 calories:float=Field(ge=0,le=950,allow_inf_nan=False)
 protein:float=Field(ge=0,le=100,allow_inf_nan=False)
 carbs:float=Field(ge=0,le=100,allow_inf_nan=False)
 fat:float=Field(ge=0,le=100,allow_inf_nan=False)
 fibre:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)
 sugars:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)
 saturates:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)
 salt:float|None=Field(default=None,ge=0,le=100,allow_inf_nan=False)

class LabelProduct(BaseModel):
 model_config=ConfigDict(extra='forbid')
 name:str=Field(min_length=1,max_length=100)
 brand:str=Field(min_length=1,max_length=80)
 retailer:str=Field(default='',max_length=80)
 barcode:str=Field(default='',max_length=14,pattern=r'^\d{0,14}$')
 nutritionBasis:Literal['g','ml']='g'
 nutrients:LabelNutrients
 servingAmount:float|None=Field(default=None,gt=0,le=10000,allow_inf_nan=False)
 servingLabel:str=Field(default='',max_length=60)

class UsualProduct(BaseModel):
 category:str=Field(min_length=1,max_length=40)
 foodId:str=Field(min_length=1,max_length=100)

def label_food(body):
 if not body.name.strip() or not body.brand.strip():raise ValueError('Enter a product name and brand or shop.')
 n=body.nutrients.model_dump()
 if n['sugars'] is not None and n['sugars']>n['carbs']+.5:raise ValueError('Sugars cannot exceed total carbohydrate. Check the per-100 values.')
 if n['saturates'] is not None and n['saturates']>n['fat']+.5:raise ValueError('Saturates cannot exceed total fat.')
 return {'id':'label:'+str(uuid.uuid4()),'name':body.brand.strip()+' · '+body.name.strip(),'brand':body.brand.strip(),'retailer':body.retailer.strip(),'barcode':body.barcode,'market':'UK','nutritionBasis':body.nutritionBasis,'source':'Your product label','dataType':'Manually entered; check against the current UK label','sourceWarning':'Values entered from your label; not independently verified. Amounts remain estimated unless measured.','url':'','retrievedAt':datetime.now(timezone.utc).isoformat(),'nutrients':n,'portions':[{'label':body.servingLabel.strip() or '1 serving','grams':body.servingAmount,'unit':body.nutritionBasis}] if body.servingAmount else []}

def find_usual(component,usuals):
 text=(component['label']+' '+component['query']).lower().replace('yoghurt','yogurt')
 words=set(tokens(text))
 if words & (DISH_WORDS|{'bowl','pancakes','pancake','smoothie','porridge'}):return None
 brand=component.get('brand')
 for entry in usuals:
  if not words&CATEGORIES.get(entry['category'],set()):continue
  food=entry['food'];saved=food['name'].lower();saved_words=set(tokens(saved))
  if brand and not set(tokens(brand))<=set(tokens(food.get('brand',''))):continue
  if component.get('packGrams') is not None and abs(food.get('packGrams',0)-component['packGrams'])>=1:continue
  if entry['category']=='protein powder' and 'powder' not in words and 'whey' not in words:continue
  if entry['category']=='rice':continue # dry label weights are never cooked photo weights
  plants={'coconut','almond','soya','soy','oat'}
  if entry['category'] in {'milk','yogurt'} and (words&plants)!=(saved_words&plants):continue
  full=bool(re.search(r'full[ -]?fat|whole milk',text));saved_lean=bool(re.search(r'fat[ -]?free|non[ -]?fat|low[ -]?fat|reduced|semi[ -]?skimmed|skimmed',saved))
  if full and (saved_lean or not re.search(r'full[ -]?fat|whole milk',saved)):continue
  if re.search(r'low[ -]?fat|reduced[ -]?fat|half[ -]?fat',text) and not re.search(r'low[ -]?fat|reduced[ -]?fat|half[ -]?fat|fat[ -]?free|non[ -]?fat|0%',saved):continue
  if re.search(r'fat[ -]?free|non[ -]?fat',text) and not re.search(r'fat[ -]?free|non[ -]?fat|0%',saved):continue
  if entry['category']=='milk' and 'semi' in words and 'semi' not in saved_words:continue
  if entry['category']=='milk' and 'skimmed' in words and 'semi' not in words and ('skimmed' not in saved_words or 'semi' in saved_words):continue
  if entry['category']=='cheese':
   types={'feta','cheddar','mozzarella','parmesan','cottage','cream','halloumi'}
   if words&types and not (words&types)<=(saved_words&types):continue
  if entry['category']=='protein powder':
   flavours={'chocolate','vanilla','strawberry','banana','unflavoured'}
   if words&flavours and not (words&flavours)<=(saved_words&flavours):continue
  if entry['category']=='cooking oil' and words&{'olive','sunflower','rapeseed','coconut'} and not words&saved_words&{'olive','sunflower','rapeseed','coconut'}:continue
  return food
 return None

def applies(homemade,text):
 return bool(homemade) and not re.search(r'\b(restaurant|takeaway|takeout|cafe|caf[eé]|eating out|store.bought|shop.bought)\b',text.lower())

def context(usuals):
 return '\nSaved usual UK products for this homemade meal (defaults only for ingredients actually present; never add ingredients just because they are saved; explicit alternatives override defaults): '+str([{'ingredient':u['category'],'product':u['food']['name'],'basis':u['food'].get('nutritionBasis','g'),'servings':u['food'].get('portions',[])} for u in usuals])+'. Break homemade mixed foods into ingredient components when supported, including yogurt bowls and oat pancakes. For liquid products with per-100-ml labels, return quantity and unit ml, not a gram-to-ml conversion. Unknown household amounts remain assumed; ask one answerable question rather than requiring weights. Do not add unmentioned oil, eggs, sugar, butter or ghee to an explicit ingredient list.'
