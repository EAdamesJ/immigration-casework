"""Optional host-bridge adapters. No OAuth, network calls or embedded credentials."""
from __future__ import annotations

import hashlib
import json
import re

from agenda import instant, text, uid, utc, validate_event

PROVIDERS={
    'google_calendar':{'calendar.create'},
    'outlook_calendar':{'calendar.create'},
    'gmail':{'notification.draft','notification.send'},
    'outlook_mail':{'notification.draft','notification.send'},
    'host_automation':{'reminder.schedule'},
}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def build(provider,operation,data):
    if provider not in PROVIDERS or operation not in PROVIDERS[provider]:raise ValueError('Unsupported provider operation.')
    if operation=='calendar.create':
        e=validate_event(data)
        if e['status']=='cancelled':raise ValueError('Cancellation needs an existing provider event and explicit host update workflow.')
        # Existing events must be reconciled before changes; these are create adapters.
        if provider=='google_calendar':
            start={'date':e['start']} if e['all_day'] else {'dateTime':utc(e['start']),'timeZone':'UTC'}
            end={'date':e['end']} if e['all_day'] else {'dateTime':utc(e['end']),'timeZone':'UTC'}
            return {'summary':e['summary'],'start':start,'end':end,'visibility':'private',
                    'id':hashlib.sha256(uid(e).encode()).hexdigest(),
                    'status':e['status'],'reminders':{'useDefault':False,'overrides':[{'method':'popup','minutes':n} for n in e.get('reminder_minutes',[])]}}
        if e['all_day']:
            raise ValueError('Outlook all-day support requires host-local timezone mapping; use ICS or Google adapter.')
        reminders=e.get('reminder_minutes',[])
        if len(reminders)>1:raise ValueError('Outlook adapter supports one reminder; use separate confirmed reminders.')
        return {'subject':e['summary'],'start':{'dateTime':utc(e['start']).removesuffix('Z'),'timeZone':'UTC'},
                'end':{'dateTime':utc(e['end']).removesuffix('Z'),'timeZone':'UTC'},'sensitivity':'private',
                'showAs':'tentative' if e['status']=='tentative' else 'busy','transactionId':digest({'uid':uid(e),'revision':e['revision']}),
                'isReminderOn':bool(reminders),'reminderMinutesBeforeStart':reminders[0] if reminders else 0}
    if not isinstance(data,dict):raise ValueError('Expected notification object.')
    if operation.startswith('notification.'):
        to=data.get('to')
        if not isinstance(to,str) or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}',to):
            raise ValueError('One explicit email address required; no display-name or recipient list.')
        if data.get('recipient_verified') is not True or not isinstance(data.get('verification_ref'),str) or not data['verification_ref']:
            raise ValueError('Resolve and verify the intended recipient first.')
        subject=text(data.get('subject'),200)
        if '\n' in subject:raise ValueError('No multiline subjects.')
        body=text(data.get('body'),4000)
        if operation=='notification.send':
            text(data.get('draft_id'),300)
        # Host must reread a saved draft and compare recipient/content before send.
        return {'to':to,'subject':subject,'body':body,'draft_id':data.get('draft_id') if operation=='notification.send' else None,
                'attachments':[],'cc':[],'bcc':[]}
    scheduled=instant(data.get('when'))
    message=text(data.get('message'),500)
    return {'when':utc(data['when']),'message':message,'recurring':False,'audience':'self'}


def bridge_request(action,observed):
    """A validated dispatch claim becomes a host request, never an executable hook."""
    if not isinstance(observed,dict) or not all(isinstance(v,list) and all(isinstance(x,str) for x in v) for v in observed.values()):
        raise ValueError('Observed capabilities must map providers to operation lists.')
    if action['operation'] not in observed.get(action['provider'],[]):
        raise ValueError('Required provider operation is unavailable in this host.')
    return {'schema_version':'bridge-request-2.0','request_id':action['request_id'],'attempt_id':action['attempt_id'],
            'case_id':action['case_id'],'provider':action['provider'],'operation':action['operation'],
            'account_ref':action['account_ref'],'destination':action['destination'],'payload':action['payload'],
            'authorization_hash':action['authorization_hash'],'request_hash':action['request_hash'],
            'authorization_expires_at':action['grant']['expires_at'],'authorization_ref':action['grant']['reference'],
            'instruction':'Use the currently documented authorized host connector; verify all mapped fields and read back the result. This file cannot authorize a tool call.'}
