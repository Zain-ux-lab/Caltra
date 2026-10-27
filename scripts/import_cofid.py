"""Import official CoFID 2021 macros, vitamins and minerals in their native units."""
import json,sys,zipfile,xml.etree.ElementTree as E
from pathlib import Path
from datetime import datetime,timezone
URL='https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid'
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def convert(path):
    with zipfile.ZipFile(path) as z:
        strings=[''.join(n.itertext()) for n in E.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        rows=E.fromstring(z.read('xl/worksheets/sheet4.xml')).findall('s:sheetData/s:row',ns)
        foods=[]
        for row in rows[3:]:
            values={}
            for cell in row:
                value=cell.findtext('s:v','',ns)
                values[''.join(c for c in cell.attrib['r'] if c.isalpha())]=strings[int(value)] if cell.attrib.get('t')=='s' and value else value
            def number(col):
                value=values.get(col,'')
                if value=='Tr':return 0.0
                try:return float(value)
                except ValueError:return None
            nutrients={k:number(col) for k,col in [('calories','M'),('protein','J'),('fat','K'),('carbs','L')]}
            # Alcoholic beverages use 100 ml in CoFID; do not interpret as 100 g.
            if not values.get('A') or any(v is None for v in nutrients.values()) or (number('X') or 0)>0:continue
            foods.append({'id':'cofid:'+values['A'],'name':values['B'],'source':'UK CoFID 2021','dataType':'UK generic food; per 100 g','url':URL,'retrievedAt':datetime.now(timezone.utc).isoformat(),'nutrients':nutrients,'portions':[], 'sourceNotes':values.get('C',''),'traceNutrients':[k for k,col in [('protein','J'),('fat','K'),('carbs','L')] if values.get(col)=='Tr']})
        enrich(z,strings,foods)
        return foods

def enrich(z,strings,foods):
    # Column mappings verified against the 2021 workbook's labelled header rows.
    columns={
        4:{'Q':'sugars','Z':'fibre','AB':'saturates'},
        5:{'H':'sodium','I':'potassium','J':'calcium','K':'magnesium','L':'phosphorus','M':'iron','N':'copper','O':'zinc','P':'chloride','Q':'manganese','R':'selenium','S':'iodine'},
        6:{'J':'vitaminA','K':'vitaminD','L':'vitaminE','M':'vitaminK1','N':'thiamin','O':'riboflavin','R':'niacin','S':'vitaminB6','T':'vitaminB12','U':'folate','V':'pantothenate','W':'biotin','X':'vitaminC'}
    }
    by_id={f['id']:f for f in foods}
    for sheet,mapping in columns.items():
        for row in E.fromstring(z.read(f'xl/worksheets/sheet{sheet}.xml')).findall('s:sheetData/s:row',ns)[3:]:
            values={}
            for cell in row:
                raw=cell.findtext('s:v','',ns)
                values[''.join(c for c in cell.attrib['r'] if c.isalpha())]=strings[int(raw)] if cell.attrib.get('t')=='s' and raw else raw
            food=by_id.get('cofid:'+values.get('A',''))
            if not food:continue
            for col,key in mapping.items():
                raw=values.get(col,'')
                try:value=0.0 if raw=='Tr' else float(raw)
                except ValueError:value=None
                food['nutrients'][key]=value
                if raw=='Tr' and key not in food['traceNutrients']:food['traceNutrients'].append(key)
    for food in foods:
        sodium=food['nutrients'].get('sodium')
        food['nutrients']['salt']=sodium*2.5/1000 if sodium is not None else None

if __name__=='__main__':
    foods=convert(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(foods,ensure_ascii=False,indent=2));print('Imported',len(foods),'complete non-alcoholic UK food records.')
