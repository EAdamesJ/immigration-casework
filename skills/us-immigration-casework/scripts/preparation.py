#!/usr/bin/env python3
"""Offline DS-160 worksheet review, refusal triage, and curated draft exports."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import zipfile

STATUSES = {'document_verified', 'user_reported', 'inferred', 'unverified', 'contradicted'}
CORE_FIELDS = ('surname', 'given_names', 'birth_date', 'nationality', 'passport_number',
               'passport_issue', 'passport_expiry', 'travel_purpose', 'arrival_date',
               'departure_date', 'payer', 'us_contact', 'address', 'occupation',
               'travel_history', 'prior_us_travel', 'prior_refusal', 'immigrant_petition',
               'family', 'education', 'social_media', 'security_questions', 'preparer')
BOOL_FIELDS = ('prior_refusal', 'immigrant_petition')


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key.')
            result[key] = value
        return result
    if Path(path).stat().st_size > 10_000_000:
        raise ValueError('JSON exceeds 10 MB limit.')
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number.')))


def iso(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Use an exact ISO date.')
    return date.fromisoformat(value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Use a short non-sensitive alphanumeric ID.')
    return value


def private_dir(path):
    path = Path(path).expanduser().absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Output must not contain symbolic links.')
        if (part / '.git').exists():
            raise ValueError('Store private outputs outside Git workspaces.')
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path


def write(path, content):
    with open(path, 'xb') as stream:
        if os.name == 'posix':
            os.fchmod(stream.fileno(), 0o600)
        stream.write(content.encode('utf-8') if isinstance(content, str) else content)


def ds160(data, as_of):
    today = iso(as_of)
    if not isinstance(data, dict) or data.get('schema_version') != 'ds160-1.0':
        raise ValueError('Expected ds160-1.0 worksheet.')
    fields = data.get('fields')
    if not isinstance(fields, dict):
        raise ValueError('fields must be an object.')
    issues = []
    def flag(field, code):
        issues.append({'field': field, 'code': code})
    for name in CORE_FIELDS:
        row = fields.get(name)
        if not isinstance(row, dict):
            flag(name, 'missing_field'); continue
        if row.get('status') not in STATUSES:
            raise ValueError('Invalid evidence status.')
        value = row.get('value')
        if value is None or value == '' or value == [] or value == {} or (isinstance(value, str) and not value.strip()):
            flag(name, 'missing_answer')
        elif name in BOOL_FIELDS and type(value) is not bool:
            flag(name, 'boolean_required')
        elif name in BOOL_FIELDS and value and not row.get('explanation'):
            flag(name, 'explanation_required')
        if row.get('status') in {'contradicted', 'unverified', 'inferred'}:
            flag(name, row['status'])
        if row.get('applicant_confirmed') is not True:
            flag(name, 'applicant_confirmation_missing')
        if row.get('status') == 'document_verified':
            refs = row.get('evidence', [])
            if not isinstance(refs, list) or not refs or not all(
                isinstance(r, dict) and isinstance(r.get('document_id'), str) and
                bool(r['document_id']) and type(r.get('page')) is int and r['page'] > 0 for r in refs):
                flag(name, 'document_page_reference_missing')
        if row.get('not_applicable') is True and not row.get('explanation'):
            flag(name, 'not_applicable_basis_missing')
        if isinstance(value, str) and not value.isascii():
            flag(name, 'english_character_review')
    dates = {}
    for name in ('birth_date', 'passport_issue', 'passport_expiry', 'arrival_date', 'departure_date'):
        value = fields.get(name, {}).get('value') if isinstance(fields.get(name), dict) else None
        if value:
            try: dates[name] = iso(value)
            except ValueError: flag(name, 'invalid_date')
    for earlier, later in (('birth_date', 'passport_issue'), ('passport_issue', 'passport_expiry'),
                           ('arrival_date', 'departure_date')):
        if earlier in dates and later in dates and dates[earlier] > dates[later]:
            flag(later, 'chronology_conflict')
    if dates.get('birth_date', today) > today: flag('birth_date', 'future_birth_date')
    if dates.get('passport_expiry', today) < today: flag('passport_expiry', 'expired_document')
    if dates.get('passport_expiry', date.max) < dates.get('departure_date', date.min):
        flag('passport_expiry', 'expires_before_trip_ends')
    if data.get('ceac_question_by_question_reviewed') is not True:
        flag('worksheet', 'live_ceac_questions_not_reviewed')
    return {'module': 'ds160', 'status': 'review_required' if issues else 'worksheet_review_complete',
            'issues': issues, 'checked_as_of': as_of, 'submission_authorized': False,
            'limits': ['Selected worksheet checks only; not the complete conditional CEAC form.',
                       'ASCII checks do not detect English, truthfulness, eligibility or every error.',
                       'Applicant must inspect original documents, all live questions and sign personally unless an official exception applies.']}


def refusal(data):
    if not isinstance(data, dict) or data.get('schema_version') != 'refusal-1.0':
        raise ValueError('Expected refusal-1.0 record.')
    grounds = data.get('grounds', [])
    if not isinstance(grounds, list) or not all(isinstance(g, str) and len(g) <= 100 for g in grounds):
        raise ValueError('grounds must be short strings transcribed from the notice.')
    notice = data.get('notice', {})
    if not isinstance(notice, dict): raise ValueError('notice must be an object.')
    inspected = (notice.get('human_reviewed') is True and isinstance(notice.get('document_id'), str)
                 and bool(notice['document_id']) and type(notice.get('page')) is int and notice['page'] > 0)
    normalized = [re.sub(r'\s+', '', g).lower().removeprefix('ina').removeprefix('section') for g in grounds]
    routes = []
    for ground in normalized:
        if ground == '214(b)': route = '214b_new_application_review'
        elif ground == '221(g)': route = '221g_notice_and_processing_review'
        else: route = 'specialist_ground_review'
        if route not in routes: routes.append(route)
    if not routes: routes = ['unknown_obtain_notice']
    return {'module': 'refusal', 'status': 'review_required',
            'ground_source': 'document_reviewed' if inspected else 'unverified',
            'routes': routes, 'source_verification_required': True,
            'deadline': None, 'approval_probability': None, 'waiver_eligibility': None,
            'next_actions': ['Preserve the refusal notice and all cited grounds; verify exact wording and page.',
                             'Separate written findings, applicant recollection, OCR and hypotheses.',
                             'Verify current DOS and consular instructions before choosing a response or reapplication.',
                             'For 221(g), identify requested documents versus administrative processing; preserve every notice deadline.',
                             'For 214(b), compare actual changes and information with the prior application; do not invent a cause or waiting period.'],
            'legal_decision_made': False}


def export_packet(data, out, formats=('md', 'html', 'json'), attachments=()):
    if not isinstance(data, dict) or data.get('schema_version') != 'packet-1.0':
        raise ValueError('Expected packet-1.0 report.')
    case_id = identifier(data.get('case_id'))
    title = data.get('title')
    sections = data.get('sections')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('A short report title is required.')
    if not isinstance(sections, list) or not sections or not all(
        isinstance(s, dict) and isinstance(s.get('heading'), str) and
        isinstance(s.get('body'), str) and len(s['heading']) <= 200 for s in sections):
        raise ValueError('Each report section needs heading and plain-text body.')
    formats = set(formats)
    if not formats or not formats <= {'md', 'html', 'json', 'pdf', 'docx'}:
        raise ValueError('Unknown output format.')
    if 'pdf' in formats:
        import reportlab
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    if 'docx' in formats:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
    files = []
    for source in attachments:
        p = Path(source).expanduser().absolute()
        if p.is_symlink() or any(x.is_symlink() for x in p.parents) or not p.is_file():
            raise ValueError('Attachments must be explicit regular files without symbolic links.')
        if p.stat().st_size > 25_000_000: raise ValueError('Attachment exceeds 25 MB.')
        if p.suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg', '.txt', '.json', '.docx'}:
            raise ValueError('Unsupported attachment type.')
        files.append(p)
    if sum(p.stat().st_size for p in files) > 100_000_000:
        raise ValueError('Attachments exceed 100 MB total.')
    root = private_dir(out)
    banner = 'DRAFT / BORRADOR - PRIVATE - REVIEW REQUIRED\nPrepared for review; not an official DS-160, filing, signature or certified translation.'
    try:
        if 'json' in formats:
            write(root/'report.json', json.dumps({**data, 'status': 'draft', 'submitted': False}, ensure_ascii=False, indent=2)+'\n')
        if 'md' in formats:
            write(root/'report.md', '# '+title+'\n\n'+banner+'\n\n'+ '\n\n'.join('## '+s['heading']+'\n\n'+s['body'] for s in sections)+'\n')
        if 'html' in formats:
            body = ''.join('<section><h2>'+html.escape(s['heading'])+'</h2><p>'+html.escape(s['body']).replace('\n','<br>')+'</p></section>' for s in sections)
            write(root/'report.html', '<!doctype html><html lang="'+('es' if data.get('language')=='es' else 'en')+'"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>'+html.escape(title)+'</title><style>body{max-width:850px;margin:40px auto;padding:0 24px;font:16px/1.6 system-ui;color:#182533}h1{font-size:30px}h2{font-size:21px;margin-top:30px}p{overflow-wrap:anywhere}.notice{padding:16px;background:#edf2f6}@media print{body{margin:0}h2{break-after:avoid}}</style><h1>'+html.escape(title)+'</h1><p class="notice">'+html.escape(banner).replace('\n','<br>')+'</p>'+body+'</html>')
        if 'pdf' in formats:
            fonts = Path(reportlab.__file__).parent/'fonts'
            pdfmetrics.registerFont(TTFont('CaseworkSans',str(fonts/'Vera.ttf')))
            pdfmetrics.registerFont(TTFont('CaseworkSansBold',str(fonts/'VeraBd.ttf')))
            pdfmetrics.registerFontFamily('CaseworkSans',normal='CaseworkSans',bold='CaseworkSansBold',italic='CaseworkSans',boldItalic='CaseworkSansBold')
            styles = getSampleStyleSheet()
            for style in styles.byName.values():
                style.fontName = 'CaseworkSansBold' if style.name in {'Title','Heading2'} else 'CaseworkSans'
            # This bundled font path supports Western text; refuse unsupported scripts.
            (title+banner+''.join(s['heading']+s['body'] for s in sections)).encode('cp1252')
            story = [Paragraph(html.escape(title), styles['Title']), Paragraph(html.escape(banner), styles['BodyText']), Spacer(1,16)]
            for s in sections:
                story.extend([Paragraph(html.escape(s['heading']), styles['Heading2']), Paragraph(html.escape(s['body']).replace('\n','<br/>'), styles['BodyText']), Spacer(1,10)])
            def footer(canvas, doc):
                canvas.setFont('CaseworkSans',8); canvas.drawString(48,30,'DRAFT / BORRADOR - '+case_id); canvas.drawRightString(560,30,str(doc.page))
            SimpleDocTemplate(str(root/'report.pdf'), leftMargin=48,rightMargin=48,topMargin=44,bottomMargin=48).build(story,onFirstPage=footer,onLaterPages=footer)
        if 'docx' in formats:
            doc = Document(); sec=doc.sections[0]; sec.top_margin=sec.bottom_margin=Inches(.7)
            doc.styles['Normal'].font.name='Calibri'; doc.styles['Normal'].font.size=Pt(11)
            for style_name in ('Title','Heading 2'):
                style=doc.styles[style_name];style.font.color.rgb=RGBColor(0,0,0);style.font.underline=False
                for border in list(style.element.xpath('.//w:pBdr')):border.getparent().remove(border)
            doc.add_paragraph(title,'Title'); doc.add_paragraph(banner)
            for s in sections:
                doc.add_heading(s['heading'],2); doc.add_paragraph(s['body'])
            for border in list(doc.element.xpath('.//w:pBdr')):border.getparent().remove(border)
            sec.footer.paragraphs[0].text='DRAFT / BORRADOR - '+case_id
            doc.save(root/'report.docx')
        if files:
            folder=root/'attachments'; folder.mkdir(mode=0o700)
            for n,p in enumerate(files,1):
                write(folder/(str(n).zfill(3)+p.suffix.lower()),p.read_bytes())
        entries=[]
        for p in sorted(root.rglob('*')):
            if p.is_file():
                if os.name=='posix':p.chmod(0o600)
                entries.append({'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size})
        manifest={'schema_version':'packet-manifest-1.0','case_id':case_id,'status':'draft','files':entries,
                  'attachments_explicit_only':True,'encrypted':False,'redacted':False,'review_before_sharing':True}
        write(root/'manifest.json',json.dumps(manifest,indent=2)+'\n')
        archive=root/'packet.zip'
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(root.rglob('*')):
                if p.is_file() and p!=archive:z.write(p,p.relative_to(root).as_posix())
        if os.name=='posix': archive.chmod(0o600)
        return {'status':'draft','formats':sorted(formats),'file_count':len(entries),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'encrypted':False,'redacted':False,'network_used':False}
    except Exception:
        shutil.rmtree(root)
        raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('ds160');d.add_argument('--input',required=True);d.add_argument('--as-of',required=True)
    r=sub.add_parser('refusal');r.add_argument('--input',required=True)
    e=sub.add_parser('export');e.add_argument('--input',required=True);e.add_argument('--out',required=True)
    e.add_argument('--formats',nargs='+',choices=['md','html','json','pdf','docx'],default=['md','html','json'])
    e.add_argument('--attach',action='append',default=[])
    args=p.parse_args(argv)
    try:
        data=load(args.input)
        if args.command=='ds160':result=ds160(data,args.as_of)
        elif args.command=='refusal':result=refusal(data)
        else:result=export_packet(data,args.out,args.formats,args.attach)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (OSError,ValueError,TypeError,ImportError,zipfile.BadZipFile):
        print('Preparation failed: check the input schema, new private output path and optional dependencies. No private values are printed.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
