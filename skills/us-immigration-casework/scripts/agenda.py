#!/usr/bin/env python3
"""Validate source-backed calendar entries and export portable private iCalendar."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from preparation import identifier, iso, load, private_dir, write


def instant(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})',value):
        raise ValueError('Use a timestamp with seconds and explicit UTC offset.')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('A UTC offset is required.')
    return result


def utc(value):
    return instant(value).astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def text(value,limit=1000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 and c!='\n' for c in value):
        raise ValueError('Expected bounded plain text without controls.')
    return value


def validate_event(data):
    if not isinstance(data,dict) or data.get('schema_version')!='event-2.0':raise ValueError('Expected event-2.0.')
    for key in ('case_id','event_id'):identifier(data.get(key))
    if type(data.get('revision')) is not int or data['revision']<1:raise ValueError('Positive revision required.')
    if data.get('kind') not in {'appointment','reminder','documented_deadline'}:raise ValueError('Unknown event kind.')
    text(data.get('summary'),200)
    if data.get('status') not in {'confirmed','tentative','cancelled'}:raise ValueError('Invalid calendar status.')
    all_day=data.get('all_day')
    if type(all_day) is not bool:raise ValueError('all_day must be boolean.')
    if all_day:
        if iso(data.get('end'))<=iso(data.get('start')):raise ValueError('End date is exclusive and must follow start.')
        if data.get('reminder_minutes'):raise ValueError('All-day alarms require a separately confirmed time; use a timed reminder event.')
    else:
        start,end=instant(data.get('start')),instant(data.get('end'))
        if end<=start:raise ValueError('End must follow start.')
        zone=data.get('timezone')
        if not isinstance(zone,str):raise ValueError('Specify an IANA timezone.')
        try:z=ZoneInfo(zone)
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Timezone data unavailable; install tzdata or correct the IANA name.') from None
        for point in (start,end):
            local=point.astimezone(z)
            if local.replace(tzinfo=None)!=point.replace(tzinfo=None) or local.utcoffset()!=point.utcoffset():
                raise ValueError('Timestamp offset does not match timezone; resolve DST gaps/ambiguities explicitly.')
    offsets=data.get('reminder_minutes',[])
    if not isinstance(offsets,list) or len(offsets)>5 or len(set(str(x) for x in offsets))!=len(offsets) or any(type(n) is not int or not 0<=n<=40320 for n in offsets):
        raise ValueError('Use at most five unique reminder offsets from 0 to 40320 minutes.')
    source=data.get('source',{})
    if not isinstance(source,dict):raise ValueError('Source must be an object.')
    if data['kind']=='documented_deadline':
        if source.get('human_reviewed') is not True or source.get('status')!='document_verified':
            raise ValueError('A legal deadline needs actual human source review.')
        identifier(source.get('document_id'))
        if type(source.get('page')) is not int or source['page']<1:raise ValueError('A positive source page is required.')
        iso(source.get('checked_on'))
        text(source.get('basis'),1000)
    return data


def escape(value):
    return value.replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    # Fold UTF-8 by octets without splitting code points. Continuation space counts.
    parts=[];current='';size=0
    for char in line:
        width=len(char.encode('utf-8'))
        if size+width>75:
            parts.append(current);current=' ';size=1
        current+=char;size+=width
    parts.append(current)
    return '\r\n'.join(parts)


def uid(data):
    return hashlib.sha256((data['case_id']+'\0'+data['event_id']).encode()).hexdigest()+'@immigration-casework.local'


def ical(events,generated_at):
    stamp=instant(generated_at).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Immigration Casework//Agenda 2.0//EN','CALSCALE:GREGORIAN']
    seen=set()
    for raw in events:
        e=validate_event(raw);key=(e['case_id'],e['event_id'])
        if key in seen:raise ValueError('Duplicate case/event ID.')
        seen.add(key)
        lines+=['BEGIN:VEVENT','UID:'+uid(e),'DTSTAMP:'+stamp,'SEQUENCE:'+str(e['revision']-1),'CLASS:PRIVATE',
                'SUMMARY:'+escape(e['summary']),'STATUS:'+e['status'].upper()]
        if e['all_day']:
            lines+=['DTSTART;VALUE=DATE:'+iso(e['start']).strftime('%Y%m%d'),'DTEND;VALUE=DATE:'+iso(e['end']).strftime('%Y%m%d')]
        else:
            for name,key in (('DTSTART','start'),('DTEND','end')):
                lines.append(name+':'+instant(e[key]).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        # No attendees, sensitive notes, attachments, meeting requests or remote alarms.
        if e['status']!='cancelled':
            for minutes in e.get('reminder_minutes',[]):
                lines+=['BEGIN:VALARM','ACTION:DISPLAY','DESCRIPTION:Casework reminder','TRIGGER:-PT'+str(minutes)+'M','END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(line) for line in lines)+'\r\n'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True);parser.add_argument('--out',required=True);parser.add_argument('--generated-at',required=True)
    args=parser.parse_args(argv)
    try:
        data=load(args.input)
        if not isinstance(data,dict) or not isinstance(data.get('events'),list):raise ValueError('events list required.')
        result=ical(data['events'],args.generated_at)
        root=private_dir(args.out);write(root/'agenda.ics',result)
        print(json.dumps({'events':len(data['events']),'status':'exported_not_scheduled','network_used':False}));return 0
    except (ValueError,TypeError,OSError,OverflowError):
        print('Agenda failed: verify event schema, timezone data, source review and new private output directory.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
