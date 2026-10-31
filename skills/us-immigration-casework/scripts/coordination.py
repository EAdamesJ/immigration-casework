#!/usr/bin/env python3
"""Local case collaboration and authorization-bound host dispatch ledger."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

from agenda import instant, text, utc
from connectors import PROVIDERS, bridge_request, build, digest
from preparation import identifier, load, private_dir, write

ROLES={'owner','preparer','reviewer','observer'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def sha(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Expected lowercase SHA-256.')
    return value


def initialize(out,owner,now):
    identifier(owner);utc(now)
    root=private_dir(out);path=root/'coordination.sqlite3'
    connection=sqlite3.connect(path)
    try:
        connection.executescript('CREATE TABLE snapshot(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, body TEXT NOT NULL); CREATE TABLE audit(seq INTEGER PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL);')
        state={'schema_version':'coordination-2.0','owner':owner,'cases':{},'connectors':{}}
        record={'revision':0,'at':utc(now),'actor':owner,'operation':'init','input_hash':digest({'owner':owner}),
                'previous_hash':'0'*64,'state_hash':digest(state)}
        connection.execute('INSERT INTO snapshot VALUES(1,0,?)',(canonical(state),))
        connection.execute('INSERT INTO audit VALUES(0,?,?)',(canonical(record),digest(record)));connection.commit()
        if os.name=='posix':path.chmod(0o600)
    finally:connection.close()
    return {'revision':0,'status':'initialized','network_used':False}


class Store:
    def __init__(self,path):
        path=Path(path).expanduser().absolute()
        if not path.is_file() or any(p.is_symlink() for p in (path,*path.parents)):
            raise ValueError('Existing regular private ledger required.')
        if any((p/'.git').exists() for p in path.parents):raise ValueError('Ledger must be outside Git workspaces.')
        self.db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10)
        self.db.execute('PRAGMA trusted_schema=OFF')

    def close(self):self.db.close()

    def snapshot(self):
        row=self.db.execute('SELECT revision,body FROM snapshot WHERE id=1').fetchone()
        if not row:raise ValueError('Missing snapshot.')
        revision,state=row[0],json.loads(row[1]);previous='0'*64;last=None
        rows=self.db.execute('SELECT seq,body,hash FROM audit ORDER BY seq').fetchall()
        for expected,(seq,body,hashed) in enumerate(rows):
            record=json.loads(body)
            if seq!=expected or record['revision']!=seq or record['previous_hash']!=previous or digest(record)!=hashed:
                raise ValueError('Audit chain mismatch.')
            previous=hashed;last=record
        if last is None or last['revision']!=revision or last['state_hash']!=digest(state) or state.get('schema_version')!='coordination-2.0':
            raise ValueError('Snapshot does not match audit chain.')
        return revision,state,previous

    def apply(self,request,now):
        if not isinstance(request,dict):raise ValueError('Expected operation object.')
        instant(now);actor=identifier(request.get('actor'));operation=request.get('operation')
        if not isinstance(operation,str):raise ValueError('Operation required.')
        expected=request.get('expected_revision')
        if type(expected) is not int or expected<0:raise ValueError('Expected revision required.')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            revision,state,previous=self.snapshot()
            if revision!=expected:raise ValueError('Stale ledger revision; reread before changing.')
            result=self._mutate(state,actor,operation,request,now)
            revision+=1
            record={'revision':revision,'at':utc(now),'actor':actor,'operation':operation,
                    'input_hash':digest(request),'previous_hash':previous,'state_hash':digest(state)}
            self.db.execute('UPDATE snapshot SET revision=?,body=? WHERE id=1',(revision,canonical(state)))
            self.db.execute('INSERT INTO audit VALUES(?,?,?)',(revision,canonical(record),digest(record)))
            self.db.commit();return {'revision':revision,**result}
        except Exception:
            self.db.rollback();raise

    def _mutate(self,state,actor,op,r,now):
        if op=='connector.configure':
            if actor!=state['owner']:raise ValueError('Only ledger owner configures connectors.')
            provider=r.get('provider')
            if provider not in PROVIDERS or type(r.get('enabled')) is not bool:raise ValueError('Invalid connector configuration.')
            account=text(r.get('account_ref'),200)
            if '\n' in account:raise ValueError('Single-line account reference required.')
            state['connectors'][provider]={'enabled':r['enabled'],'account_ref':account}
            return {'status':'connector_configured','provider':provider,'enabled':r['enabled']}
        case_id=identifier(r.get('case_id'))
        if op=='case.create':
            if actor!=state['owner'] or case_id in state['cases']:raise ValueError('Only owner creates a new case ID.')
            state['cases'][case_id]={'members':{actor:'owner'},'artifacts':{},'tasks':{},'actions':{}}
            return {'case_id':case_id,'status':'created'}
        case=state['cases'].get(case_id)
        if case is None or actor not in case['members']:raise ValueError('Actor is not assigned to this case.')
        role=case['members'][actor]
        if op=='member.add':
            member=identifier(r.get('member'))
            if role!='owner' or r.get('role') not in ROLES:raise ValueError('Case owner assigns valid roles.')
            if member in case['members']:raise ValueError('Member exists; do not silently change active assignments.')
            case['members'][member]=r['role'];return {'status':'member_added'}
        if op=='member.remove':
            member=identifier(r.get('member'))
            if role!='owner' or member not in case['members'] or case['members'][member]=='owner':
                raise ValueError('Owner may remove a non-owner member.')
            del case['members'][member]
            for versions in case['artifacts'].values():
                current=versions[-1]
                if current['status']=='in_review' and current['reviewer']==member:current.update(status='draft',reviewer=None)
            for task in case['tasks'].values():
                if task['assignee']==member and task['status']!='done':task['status']='blocked'
            return {'status':'member_removed','external_access_revoked':False}
        if op.startswith('artifact.') or op.startswith('review.'):
            artifact_id=identifier(r.get('artifact_id'));versions=case['artifacts'].get(artifact_id,[])
            if op=='artifact.revise':
                if role not in {'owner','preparer'}:raise ValueError('Editing role required.')
                sha(r.get('sha256'))
                if versions and versions[-1]['sha256']==r['sha256']:raise ValueError('No content change; retain current review.')
                item={'revision':len(versions)+1,'sha256':r['sha256'],'author':actor,'status':'draft','reviewer':None,'feedback':[]}
                versions.append(item);case['artifacts'][artifact_id]=versions
                return {'status':'draft','artifact_revision':item['revision']}
            if not versions:raise ValueError('Unknown artifact.')
            current=versions[-1]
            if type(r.get('artifact_revision')) is not int or r['artifact_revision']!=current['revision'] or r.get('sha256')!=current['sha256']:
                raise ValueError('Review must match the current artifact revision and hash.')
            if op=='review.assign':
                reviewer=identifier(r.get('reviewer'))
                if role!='owner' or case['members'].get(reviewer)!='reviewer' or reviewer==current['author']:
                    raise ValueError('Owner must assign an independent reviewer.')
                current.update(reviewer=reviewer,status='in_review');return {'status':'in_review'}
            if op=='review.decide':
                if role!='reviewer' or actor!=current['reviewer'] or actor==current['author'] or current['status']!='in_review':
                    raise ValueError('Only the assigned independent reviewer decides an active review.')
                decision=r.get('decision')
                if decision not in {'approved','changes_requested'}:raise ValueError('Unknown review decision.')
                note=text(r.get('note'),4000)
                current['status']=decision;current['feedback'].append({'actor':actor,'at':utc(now),'decision':decision,'note':note})
                return {'status':decision,'artifact_revision':current['revision']}
            raise ValueError('Unknown artifact operation.')
        if op.startswith('task.'):
            task_id=identifier(r.get('task_id'))
            if op=='task.create':
                assignee=identifier(r.get('assignee'))
                if role not in {'owner','preparer'} or task_id in case['tasks'] or assignee not in case['members']:raise ValueError('Valid new task and assignee required.')
                case['tasks'][task_id]={'assignee':assignee,'summary':text(r.get('summary'),200),'status':'todo'}
                return {'status':'todo'}
            task=case['tasks'].get(task_id)
            if op!='task.transition' or task is None or (role!='owner' and actor!=task['assignee']):raise ValueError('Only owner or assignee changes a task.')
            if r.get('status') not in {'todo','in_progress','blocked','done'}:raise ValueError('Unknown task state.')
            task['status']=r['status'];return {'status':task['status']}
        request_id=identifier(r.get('request_id'))
        actions=case['actions'];action=actions.get(request_id)
        if op=='action.prepare':
            if role not in {'owner','preparer'}:raise ValueError('Preparation role required.')
            provider=r.get('provider');operation=r.get('provider_operation')
            payload=build(provider,operation,r.get('data'))
            if operation=='calendar.create' and r['data']['case_id']!=case_id:raise ValueError('Calendar event belongs to another case.')
            if operation=='reminder.schedule' and instant(payload['when'])<=instant(now):raise ValueError('A new scheduled reminder must be in the future.')
            destination=text(r.get('destination'),300);account=text(r.get('account_ref'),200)
            if '\n' in destination or '\n' in account:raise ValueError('Single-line destination/account required.')
            not_before=utc(r.get('not_before'))
            base={'case_id':case_id,'provider':provider,'operation':operation,'account_ref':account,
                  'destination':destination,'not_before':not_before,'payload':payload}
            hashed=digest(base)
            if action:
                if action['request_hash']!=hashed:raise ValueError('Request ID already binds different content.')
                return {'status':action['status'],'request_hash':hashed,'duplicate':True}
            if any(x['request_hash']==hashed for x in actions.values()):raise ValueError('Equivalent action already exists under another ID.')
            actions[request_id]={**base,'request_id':request_id,'request_hash':hashed,'status':'prepared','grant':None,'attempt_id':None,'receipt':None,'attempts':[]}
            return {'status':'prepared','request_hash':hashed}
        if action is None:raise ValueError('Unknown action.')
        if op=='action.authorize':
            if role!='owner' or action['status'] not in {'prepared','authorized'}:raise ValueError('Case owner authorizes an unclaimed action.')
            if r.get('request_hash')!=action['request_hash']:raise ValueError('Authorization hash mismatch.')
            if instant(r.get('expires_at'))<=max(instant(now),instant(action['not_before'])):raise ValueError('Authorization must cover the dispatch time.')
            action['grant']={'by':actor,'reference':identifier(r.get('authorization_ref')),'expires_at':utc(r['expires_at']),'request_hash':action['request_hash'],'revoked':False}
            action['status']='authorized';return {'status':'authorized'}
        if op=='action.revoke':
            if role!='owner' or action['grant'] is None:raise ValueError('Case owner revokes an existing authorization.')
            action['grant']['revoked']=True
            if action['status'] in {'authorized','prepared'}:action['status']='revoked'
            return {'status':action['status'],'authorization_revoked':True}
        if op=='action.claim':
            if role not in {'owner','preparer'} or action['status']!='authorized':raise ValueError('Authorized, unclaimed action required.')
            grant=action['grant'];config=state['connectors'].get(action['provider'],{})
            if not grant or grant['revoked'] or grant['request_hash']!=action['request_hash'] or instant(grant['expires_at'])<=instant(now):raise ValueError('Authorization expired or revoked.')
            if instant(action['not_before'])>instant(now):raise ValueError('Action is not due yet.')
            if config.get('enabled') is not True or config.get('account_ref')!=action['account_ref']:raise ValueError('Connector disabled or account changed.')
            candidate=copy.deepcopy(action);candidate['attempt_id']=uuid4().hex;candidate['authorization_hash']=digest(grant)
            bridge=bridge_request(candidate,r.get('observed_capabilities'))
            action.update(status='dispatching',attempt_id=candidate['attempt_id'],claimed_by=actor,authorization_hash=candidate['authorization_hash'])
            action['attempts'].append({'attempt_id':candidate['attempt_id'],'at':utc(now),'actor':actor,
                                       'authorization_hash':candidate['authorization_hash'],'authorization_ref':grant['reference'],'expires_at':grant['expires_at'],'receipts':[]})
            return {'status':'dispatching','bridge':bridge}
        if op=='action.preflight':
            grant=action['grant'];config=state['connectors'].get(action['provider'],{})
            if role not in {'owner','preparer'} or action['status']!='dispatching' or r.get('attempt_id')!=action['attempt_id']:
                raise ValueError('Active dispatch attempt required.')
            if not grant or grant['revoked'] or instant(grant['expires_at'])<=instant(now) or config.get('enabled') is not True or config.get('account_ref')!=action['account_ref']:
                raise ValueError('Recheck failed: expired/revoked authorization or changed connector.')
            return {'status':'dispatching','preflight_at':utc(now),'attempt_id':action['attempt_id'],'request_hash':action['request_hash'],'ready_for_host_policy_check':True}
        if op=='action.receipt':
            if role not in {'owner','preparer'} or (actor!=action.get('claimed_by') and role!='owner'):
                raise ValueError('Only dispatch actor or owner records a receipt.')
            if action['status'] not in {'dispatching','unknown'} or r.get('attempt_id')!=action['attempt_id'] or r.get('request_hash')!=action['request_hash']:
                raise ValueError('Receipt must match the active dispatch attempt and content.')
            outcome=r.get('outcome')
            if outcome not in {'confirmed','not_applied','unknown'}:raise ValueError('Invalid outcome.')
            reference=identifier(r.get('result_ref'))
            external_id=None
            if outcome=='confirmed':external_id=text(r.get('external_id'),300)
            action['receipt']={'outcome':outcome,'result_ref':reference,'external_id':external_id,'recorded_at':utc(now)}
            action['attempts'][-1]['receipts'].append(copy.deepcopy(action['receipt']))
            action['status']=outcome
            return {'status':outcome,'provider_delivery_proven':False}
        if op=='action.retry':
            if role!='owner' or action['status']!='not_applied':raise ValueError('Retry only after a verified not-applied result; reconcile unknown outcomes first.')
            action.update(status='prepared',grant=None,attempt_id=None,receipt=None)
            return {'status':'prepared','authorization_required':True}
        raise ValueError('Unknown operation.')

    def summary(self,now):
        revision,state,chain=self.snapshot();point=instant(now);due=[]
        for case_id,case in state['cases'].items():
            for action in case['actions'].values():
                grant=action['grant']
                if action['status']=='authorized' and instant(action['not_before'])<=point and grant and not grant['revoked'] and instant(grant['expires_at'])>point:
                    due.append({'case_id':case_id,'request_id':action['request_id'],'provider':action['provider']})
        return {'revision':revision,'cases':len(state['cases']),'due':due,'audit_head':chain,'network_used':False,
                'limits':'Due is a local queue state, not a running scheduler or evidence of delivery.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    i=sub.add_parser('init');i.add_argument('--out',required=True);i.add_argument('--owner',required=True);i.add_argument('--now',required=True)
    for command in ('apply','status','snapshot'):
        p=sub.add_parser(command);p.add_argument('--db',required=True);p.add_argument('--now',required=True)
        if command=='apply':p.add_argument('--input',required=True);p.add_argument('--bridge-out')
        if command=='snapshot':p.add_argument('--out',required=True)
    args=parser.parse_args(argv);store=None;root=None
    try:
        if args.command=='init':result=initialize(args.out,args.owner,args.now)
        else:
            store=Store(args.db)
            if args.command=='status':result=store.summary(args.now)
            elif args.command=='snapshot':
                revision,state,chain=store.snapshot();root=private_dir(args.out);write(root/'snapshot.json',json.dumps(state,ensure_ascii=False,indent=2)+'\n')
                result={'revision':revision,'audit_head':chain,'status':'private_snapshot_exported'}
            else:
                request=load(args.input)
                if not isinstance(request,dict):raise ValueError('Expected operation object.')
                if args.bridge_out and request.get('operation')!='action.claim':raise ValueError('Bridge output is only for a dispatch claim.')
                if request.get('operation')=='action.claim' and not args.bridge_out:raise ValueError('Claim requires a new private bridge output directory.')
                # Preflight output before the atomic claim. Export failure leaves dispatching, never a retryable phantom success.
                root=private_dir(args.bridge_out) if args.bridge_out else None
                result=store.apply(request,args.now)
                bridge=result.pop('bridge',None)
                if bridge is not None:write(root/'bridge-request.json',json.dumps(bridge,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,sqlite3.Error,OverflowError):
        if root is not None and root.is_dir() and not any(root.iterdir()):root.rmdir()
        print('Coordination failed: check schema, current revision, role, source, authorization, connector availability and ledger integrity. No private values are printed.',file=sys.stderr);return 2
    finally:
        if store is not None:store.close()


if __name__=='__main__':raise SystemExit(main())
