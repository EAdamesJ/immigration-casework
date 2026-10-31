#!/usr/bin/env python3
"""Private DS-260/general worksheets and explicit template field filling."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import zipfile

from preparation import STATUSES, export_packet, identifier, iso, load, private_dir

DS260_SECTIONS={'identity','passport','contact','address_history','family','travel_history',
                'employment_education','petitioner','security_background','ssn_choice','preparer','applicant_review'}


def review(data):
    if not isinstance(data,dict) or data.get('schema_version')!='form-draft-2.1':raise ValueError('Expected form-draft-2.1.')
    identifier(data.get('case_id'))
    if data.get('form_kind') not in {'DS-260','generic'}:raise ValueError('Unknown form kind.')
    if not isinstance(data.get('form_name'),str) or not data['form_name'].strip():raise ValueError('Form name required.')
    fields=data.get('fields')
    if not isinstance(fields,list) or not fields or len(fields)>1000:raise ValueError('A bounded field list is required.')
    issues=[];ids=set();sections=set()
    for field in fields:
        if not isinstance(field,dict):raise ValueError('Invalid field row.')
        key=identifier(field.get('id'))
        if key in ids:raise ValueError('Duplicate field ID.')
        ids.add(key);section=identifier(field.get('section'));sections.add(section)
        kind=field.get('type');value=field.get('value')
        if kind not in {'text','date','boolean','number'} or type(field.get('required')) is not bool or field.get('status') not in STATUSES:
            raise ValueError('Invalid field type, requirement or evidence status.')
        def flag(code):issues.append({'field':key,'code':code})
        exempt=field.get('not_applicable') is True and field.get('allows_not_applicable') is True and bool(field.get('explanation'))
        empty=value is None or value=='' or isinstance(value,str) and not value.strip()
        if field.get('not_applicable') is True and not exempt:flag('not_applicable_needs_live_form_permission_and_basis')
        if field['required'] and empty and not exempt:flag('missing_answer')
        if not empty and not exempt:
            if kind=='boolean' and type(value) is not bool:flag('boolean_required')
            if kind=='text' and not isinstance(value,str):flag('text_required')
            if kind=='date':
                try:iso(value)
                except (ValueError,TypeError):flag('invalid_or_ambiguous_date')
            if kind=='number' and (type(value) not in (int,float) or not math.isfinite(value)):flag('finite_number_required')
            if field.get('explanation_required_when_true') is True and value is True and not field.get('explanation'):flag('explanation_required')
            if field.get('english_characters') is True and isinstance(value,str) and not value.isascii():flag('english_character_review')
        if field['required'] and field.get('applicant_confirmed') is not True:flag('applicant_confirmation_missing')
        if field.get('status') in {'unverified','contradicted','inferred'} and (not empty or field['required']):flag(field['status'])
        if field.get('status')=='document_verified':
            refs=field.get('evidence',[])
            if not isinstance(refs,list) or not refs or not all(isinstance(r,dict) and isinstance(r.get('document_id'),str) and r['document_id'] and type(r.get('page')) is int and r['page']>0 for r in refs):flag('document_page_reference_missing')
    if data['form_kind']=='DS-260':
        for section in sorted(DS260_SECTIONS-sections):issues.append({'field':section,'code':'missing_preparation_section'})
    if data.get('current_form_question_by_question_reviewed') is not True:issues.append({'field':'form','code':'current_form_review_missing'})
    return {'status':'review_required' if issues else 'worksheet_review_complete','issues':issues,'field_count':len(fields),
            'submission_authorized':False,'limits':'Preparation checks only; not a complete CEAC schema, legal review, signature or filing.'}


def packet(data,out,formats):
    result=review(data)
    sections=[{'heading':'Scope and review status','body':result['limits']+'\nStatus: '+result['status']}]
    for section in dict.fromkeys(f['section'] for f in data['fields']):
        lines=[]
        for f in data['fields']:
            if f['section']!=section:continue
            value=f.get('value');answer='[PENDING]' if value is None or value=='' else str(value)
            refs=', '.join(str(r.get('document_id'))+' page '+str(r.get('page')) for r in f.get('evidence',[]) if isinstance(r,dict))
            lines.append(str(f.get('label',f['id']))+': '+answer+'\nEvidence status: '+f['status']+'; references: '+(refs or 'none')+'\nApplicant confirmed: '+str(f.get('applicant_confirmed') is True))
        sections.append({'heading':section.replace('_',' '),'body':'\n\n'.join(lines)})
    sections.append({'heading':'Unresolved checks','body':'\n'.join(i['field']+': '+i['code'] for i in result['issues']) or 'Selected worksheet checks complete; review every current official question.'})
    return export_packet({'schema_version':'packet-1.0','case_id':data['case_id'],'title':data['form_name']+' preparation draft','language':data.get('language','es'),'sections':sections},out,formats)


def mapping_check(data):
    if not isinstance(data,dict) or not data or len(data)>500 or not all(isinstance(k,str) and k and isinstance(v,str) and len(v)<=10000 for k,v in data.items()):
        raise ValueError('Provide an explicit nonempty string-to-string field map.')
    return data


def fill_pdf(template,mapping,out):
    from pypdf import PdfReader,PdfWriter
    mapping_check(mapping);template=Path(template)
    if template.stat().st_size>25_000_000:raise ValueError('Template exceeds 25 MB.')
    reader=PdfReader(template)
    if reader.is_encrypted:raise ValueError('Use an authorized decrypted working copy.')
    fields=reader.get_fields() or {}
    if not fields or set(mapping)-set(fields):raise ValueError('Template lacks the selected canonical fillable fields.')
    if any(f.get('/FT')=='/Sig' and f.get('/V') for f in fields.values()):raise ValueError('Do not modify a signed document.')
    acro=reader.trailer['/Root'].get('/AcroForm')
    if acro and acro.get_object().get('/XFA'):raise ValueError('XFA is unsupported.')
    for key in mapping:
        if fields[key].get('/FT')!='/Tx':raise ValueError('Only text fields are supported; inspect controls separately.')
        maximum=fields[key].get('/MaxLen')
        if maximum and len(mapping[key])>int(maximum):raise ValueError('Value exceeds the template field limit.')
    writer=PdfWriter();writer.clone_document_from_reader(reader)
    writer.update_page_form_field_values(None,mapping,auto_regenerate=False)
    root=private_dir(out)
    try:
        target=root/'filled-draft.pdf'
        with open(target,'xb') as stream:writer.write(stream)
        check=PdfReader(target).get_fields() or {}
        if any(str(check.get(k,{}).get('/V',''))!=v for k,v in mapping.items()):raise ValueError('Written field readback mismatch.')
        reopened=PdfReader(target);seen=set()
        for page in reopened.pages:
            for ref in page.get('/Annots',[]):
                widget=ref.get_object()
                if widget.get('/Subtype')!='/Widget':continue
                names=[];node=widget;value=None;parents=set()
                while node is not None:
                    if id(node) in parents:raise ValueError('Cyclic PDF field parent.')
                    parents.add(id(node))
                    if node.get('/T'):names.insert(0,str(node['/T']))
                    if value is None and '/V' in node:value=node['/V']
                    parent=node.get('/Parent');node=parent.get_object() if parent else None
                name='.'.join(names)
                if name in mapping:
                    appearance=widget.get('/AP',{}).get('/N')
                    if str(value)!=mapping[name] or not appearance or not appearance.get_object().get_data():raise ValueError('PDF widget value or appearance failed verification.')
                    seen.add(name)
        if seen!=set(mapping):raise ValueError('Selected fields lack verifiable visible widgets.')
        if sys.platform!='win32':target.chmod(0o600)
        return {'status':'draft_review_required','fields_written':len(mapping),'source_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),'visual_review_required':True,'submitted':False}
    except Exception:shutil.rmtree(root);raise


def fill_docx(template,mapping,out):
    from docx import Document
    from docx.oxml.ns import qn
    mapping_check(mapping);template=Path(template)
    if template.stat().st_size>25_000_000:raise ValueError('Template exceeds 25 MB.')
    with zipfile.ZipFile(template) as archive:
        names=archive.namelist()
        if sum(i.file_size for i in archive.infolist())>50_000_000:raise ValueError('Expanded template exceeds limit.')
        if any('_xmlsignatures/' in n or 'vbaProject' in n or n.startswith('word/embeddings/') or n in {'word/footnotes.xml','word/endnotes.xml'} for n in names):
            raise ValueError('Signed, active-content and footnote templates require a specialized document workflow.')
    doc=Document(template);seen=set()
    if doc.element.xpath('.//w:ins | .//w:del'):raise ValueError('Resolve tracked changes in a separate reviewed copy first.')
    def paragraphs(container):
        yield from container.paragraphs
        for table in container.tables:
            for row in table.rows:
                for cell in row.cells:yield from paragraphs(cell)
    containers=[doc]+[part for section in doc.sections for part in (section.header,section.footer)]
    token=re.compile(r'\{\{([A-Za-z0-9_-]+)\}\}')
    for container in containers:
        for paragraph in paragraphs(container):
            full=''.join(run.text for run in paragraph.runs)
            for match in reversed(list(token.finditer(full))):
                key=match.group(1)
                if key not in mapping:raise ValueError('Template has an unmapped placeholder.')
                seen.add(key);position=0;start=end=None
                for i,run in enumerate(paragraph.runs):
                    next_position=position+len(run.text)
                    if start is None and position<=match.start()<next_position:start=(i,match.start()-position)
                    if position<match.end()<=next_position:end=(i,match.end()-position);break
                    position=next_position
                if start is None or end is None:raise ValueError('Unsupported placeholder layout.')
                a,b=start[0],end[0];prefix=paragraph.runs[a].text[:start[1]];suffix=paragraph.runs[b].text[end[1]:]
                paragraph.runs[a].text=prefix+mapping[key]+(suffix if a==b else '')
                for i in range(a+1,b):paragraph.runs[i].text=''
                if b!=a:paragraph.runs[b].text=suffix
    if set(mapping)-seen:raise ValueError('Mapping contains unused template keys.')
    for container in containers:
        for node in container._element.iter(qn('w:p')):
            if token.search(''.join(t.text or '' for t in node.iter(qn('w:t')))):raise ValueError('Unsupported or unresolved placeholder remains.')
    root=private_dir(out)
    try:
        target=root/'filled-draft.docx';doc.save(target)
        if sys.platform!='win32':target.chmod(0o600)
        return {'status':'draft_review_required','placeholders_written':len(seen),'source_sha256':hashlib.sha256(template.read_bytes()).hexdigest(),'visual_review_required':True,'submitted':False}
    except Exception:shutil.rmtree(root);raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    r=sub.add_parser('review');r.add_argument('--input',required=True)
    e=sub.add_parser('export');e.add_argument('--input',required=True);e.add_argument('--out',required=True);e.add_argument('--formats',nargs='+',choices=['md','html','json','pdf','docx'],default=['md','html','json'])
    for command in ('fill-pdf','fill-docx'):
        p=sub.add_parser(command);p.add_argument('--template',required=True);p.add_argument('--mapping',required=True);p.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='review':result=review(load(args.input))
        elif args.command=='export':result=packet(load(args.input),args.out,args.formats)
        elif args.command=='fill-pdf':result=fill_pdf(args.template,load(args.mapping),args.out)
        else:result=fill_docx(args.template,load(args.mapping),args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception:
        print('Form preparation failed. Check the current form, explicit mapping, optional dependencies and a new private output path. No private values are printed.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
