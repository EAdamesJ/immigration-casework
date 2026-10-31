#!/usr/bin/env python3
"""Offline visitor preparation and personalized bulletin date comparisons."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

TOPICS = {
 'purpose': ('¿Cuál es el propósito concreto de su visita?', 'What is the specific purpose of your visit?'),
 'duration': ('¿Cuánto tiempo planea quedarse y por qué?', 'How long will you stay, and why?'),
 'funding': ('¿Quién pagará y cómo se cubrirá el presupuesto?', 'Who will pay and how will the budget be covered?'),
 'return_plan': ('¿Qué planes y compromisos tiene al regresar?', 'What plans and commitments do you have upon returning?'),
 'occupation': ('¿A qué se dedica actualmente?', 'What do you currently do?'),
 'travel_history': ('¿Qué viajes y estancias anteriores debe declarar?', 'What previous trips and stays must you disclose?'),
 'us_contacts': ('¿A quién visitará o dónde se alojará?', 'Who will you visit or where will you stay?'),
 'prior_refusals': ('¿Ha tenido negativas y qué circunstancias han cambiado?', 'Have you had refusals, and what circumstances have changed?'),
 'immigrant_petitions': ('¿Existen peticiones migratorias y cuál es su situación?', 'Are there immigrant petitions, and what is their status?')
}
STATUS = {'document_verified','user_reported','unverified','contradicted'}

def read(path):
    def pairs(items):
        out = {}
        for k,v in items:
            if k in out: raise ValueError('Duplicate JSON key.')
            out[k]=v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs)

def profile_check(p):
    if not isinstance(p,dict) or p.get('visa') not in ('B1','B2','B1/B2') or not isinstance(p.get('topics'),dict):
        raise ValueError('Expected visa B1, B2 or B1/B2 and a topics object.')
    for key,row in p['topics'].items():
        if key not in TOPICS or not isinstance(row,dict) or row.get('status') not in STATUS or not isinstance(row.get('answer'),str) or not isinstance(row.get('evidence_ids',[]),list) or not all(isinstance(x,str) and x for x in row.get('evidence_ids',[])):
            raise ValueError('Invalid preparation topic.')
    return p

def readiness(p):
    profile_check(p)
    missing=[]; unverified=[]; conflicts=[]; documented=[]
    for key in TOPICS:
        row=p['topics'].get(key,{})
        if not row.get('answer','').strip(): missing.append(key)
        elif row['status']=='contradicted': conflicts.append(key)
        elif row['status']=='document_verified' and row.get('evidence_ids'): documented.append(key)
        else: unverified.append(key)
    state='review_required' if conflicts else ('incomplete' if missing else ('partial' if unverified else 'complete'))
    return {'preparation':state,'missing_topics':missing,'needs_evidence_review':unverified,'contradictions':conflicts,'documented_topics':documented,'approval_probability':None,'eligibility_decided':False,'note':'Preparation coverage only; linked evidence must be inspected. No income, marital-status or property score.'}

def interview(p,language='es'):
    r=readiness(p)
    order=r['contradictions']+r['missing_topics']+[k for k in TOPICS if k not in r['contradictions']+r['missing_topics']]
    return {'language':language,'mode':'practice_one_question_at_a_time','questions':[{'topic':k,'question':TOPICS[k][language=='en'],'follow_up':('¿Qué dato o documento le permitiría aclararlo?' if language=='es' else 'What fact or document would help clarify this?')} for k in order], 'evaluation_dimensions':['clarity','consistency_with_supplied_facts','acknowledged_uncertainty'],'not_evaluated':['approval_likelihood','accent','wealth','perceived_honesty'],'recording_enabled':False}

def day(s):
    import re
    if not isinstance(s,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',s): raise ValueError('Dates must use YYYY-MM-DD.')
    return date.fromisoformat(s)

def bulletin(snapshot,category,country,priority,as_of,process):
    pd=day(priority); now=day(as_of)
    if pd>now: raise ValueError('Priority date cannot be in the future.')
    if process not in ('consular','adjustment'): raise ValueError('Unknown process.')
    if not isinstance(snapshot,dict): raise ValueError('Expected bulletin snapshot object.')
    import re
    month=snapshot.get('month','')
    if not re.fullmatch(r'\d{4}-\d{2}',month): raise ValueError('Bulletin month must use YYYY-MM.')
    effective=day(month+'-01')
    source=snapshot.get('source',{})
    def checked(src,host):
        u=urlsplit(src.get('url',''))
        if u.scheme!='https' or u.hostname!=host or u.username or u.password or u.port not in (None,443) or day(src.get('checked_at',''))>now:
            raise ValueError('Snapshot requires dated official source metadata.')
    checked(source,'travel.state.gov')
    rows=snapshot.get('rows')
    if not isinstance(rows,list) or not all(isinstance(row,dict) for row in rows): raise ValueError('Missing or malformed bulletin rows.')
    if category in ('IR1','CR1','IR2','IR5'):
        return {'category':category,'result':'preference_bulletin_not_applicable','approval_or_filing_authorized':False}
    results={}
    for chart in ('final_action','filing'):
        matched=[r for r in rows if r.get('category')==category and r.get('country')==country and r.get('chart')==chart]
        if len(matched)>1: raise ValueError('Ambiguous duplicate bulletin row.')
        if not matched: results[chart]={'result':'unknown_missing_row'}; continue
        cut=matched[0].get('cutoff')
        if cut=='C': result='date_condition_met'
        elif cut=='U': result='unavailable'
        else: result='date_condition_met' if pd<day(cut) else 'waiting'
        results[chart]={'cutoff':cut,'result':result}
    selected=None
    if process=='adjustment':
        choice=snapshot.get('uscis_chart')
        if choice:
            checked(choice,'www.uscis.gov')
            family='family' if category in ('F1','F2A','F2B','F3','F4') else 'employment'
            if choice.get('month')!=month or choice.get('family')!=family or choice.get('chart') not in results:
                raise ValueError('USCIS chart must match month and preference family.')
            selected=choice['chart']
    return {'month':month,'effective_relative_to_analysis':'upcoming' if effective>now else ('current' if month==now.strftime('%Y-%m') else 'historical'), 'category':category,'chargeability':country,'priority_date':priority,'process':process,'charts':results,'uscis_selected_chart':selected,'source':source,'source_contents_verified_by_tool':False,'approval_or_filing_authorized':False,'note':'Date comparison only. Verify source extraction, chargeability, category, notices, current chart and all other requirements. No interview or approval forecast.'}

def main():
    p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest='cmd',required=True)
    for cmd in ('readiness','interview'):
        q=s.add_parser(cmd);q.add_argument('--profile',required=True)
        if cmd=='interview':q.add_argument('--language',choices=('es','en'),default='es')
    q=s.add_parser('bulletin');q.add_argument('--snapshot',required=True)
    for flag in ('category','country','priority','as-of'):q.add_argument('--'+flag,required=True)
    q.add_argument('--process',choices=('consular','adjustment'),required=True)
    args=p.parse_args()
    try:
        if args.cmd=='readiness': out=readiness(read(args.profile))
        elif args.cmd=='interview':out=interview(read(args.profile),args.language)
        else:out=bulletin(read(args.snapshot),args.category,args.country,args.priority,args.as_of,args.process)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except (ValueError,TypeError,KeyError,OSError):
        print('Invalid or incomplete input; verify the documented schema and official source metadata.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
