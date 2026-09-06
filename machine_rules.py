"""Fail closed for unverified pen-and-blade machine models."""
import json
from pathlib import Path
import re
RULES=json.loads((Path(__file__).parent/'machine-rules.json').read_text())
def classify(row):
    title=row.get('title','')
    machine=bool(re.search(RULES['machine_pattern'],title+' '+row.get('matched_query',''),re.I)) or 'primary-plotter' in row.get('watch_ids',[])
    if not machine: return {'is_machine':False,'eligible':True}
    if re.search(RULES['accessory_pattern'],title,re.I):
        return {'is_machine':True,'eligible':False,'reason':'Accessory, incomplete, or nonworking listing'}
    models=[m for m in RULES['models'] if re.search(m['pattern'],title,re.I)]
    if len(models)!=1: return {'is_machine':True,'eligible':False,'reason':'Exact pen-and-blade configuration unverified or single-tool machine'}
    # Conflicting model numbers are not an exact-model identification.
    if re.search(r'\bcameo\s*[124]\b',title,re.I): return {'is_machine':True,'eligible':False,'reason':'Ambiguous model'}
    return {'is_machine':True,'eligible':True,'model':models[0]}
def eligible(row): return classify(row)['eligible']
def annotate(row):
    row['machine_fit']=classify(row)
    return row
