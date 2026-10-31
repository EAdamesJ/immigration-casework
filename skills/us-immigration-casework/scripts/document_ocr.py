#!/usr/bin/env python3
"""Local Tesseract OCR with page coordinates and mandatory human review."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from preparation import identifier, private_dir, write


def run(args):
    try:
        return subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',timeout=120).stdout
    except (OSError,subprocess.SubprocessError,UnicodeError):
        raise ValueError('Local OCR command failed; original was not changed.') from None


def words_from_tsv(tsv, threshold=85):
    words=[]
    for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
        if not row.get('text','').strip():continue
        try:
            confidence=float(row['conf'])
            if not 0 <= confidence <= 100:raise ValueError()
            box=[int(row[x]) for x in ('left','top','width','height')]
            if min(box)<0:raise ValueError()
        except (ValueError,KeyError,TypeError):raise ValueError('Malformed OCR coordinates or confidence.') from None
        words.append({'text':row['text'],'confidence':confidence,'bbox_pixels':box,
                      'low_confidence':confidence<threshold,'human_reviewed':False})
    return words


def extract(source,out,document_id,language='eng',max_pages=25,threshold=85):
    identifier(document_id)
    if not re.fullmatch(r'[a-z]{3}(?:\+[a-z]{3})*',language):raise ValueError('Invalid OCR language code.')
    if type(max_pages) is not int or not 1<=max_pages<=100:raise ValueError('Page limit must be 1..100.')
    if not 0<=threshold<=100:raise ValueError('Confidence threshold must be 0..100.')
    source=Path(source).expanduser().resolve(strict=True)
    if not source.is_file() or source.stat().st_size>50_000_000:raise ValueError('Input must be a file no larger than 50 MB.')
    if source.suffix.lower() not in {'.pdf','.png','.jpg','.jpeg','.bmp'}:
        raise ValueError('Supported input: PDF or a single PNG/JPEG/BMP image. Split multipage TIFF first.')
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    if not shutil.which('tesseract'):raise ValueError('Install local Tesseract first.')
    languages=set(run(['tesseract','--list-langs']).splitlines())
    if not set(language.split('+')) <= languages:raise ValueError('Requested Tesseract language data is unavailable.')
    count=1
    if source.suffix.lower()=='.pdf':
        if not all(shutil.which(x) for x in ('pdfinfo','pdftoppm')):raise ValueError('Install Poppler first.')
        match=re.search(r'^Pages:\s+(\d+)',run(['pdfinfo',str(source)]),re.M)
        if not match:raise ValueError('Cannot establish PDF page count.')
        count=int(match.group(1))
        if count<1 or count>max_pages:raise ValueError('PDF exceeds page limit; split explicitly. No silent truncation.')
    root=private_dir(out)
    try:
        pages=[]
        with tempfile.TemporaryDirectory(prefix='casework-ocr-') as temp:
            for number in range(1,count+1):
                image=source
                if source.suffix.lower()=='.pdf':
                    prefix=Path(temp)/('page-'+str(number))
                    run(['pdftoppm','-f',str(number),'-l',str(number),'-r','200','-scale-to','4000','-singlefile','-png',str(source),str(prefix)])
                    image=prefix.with_suffix('.png')
                words=words_from_tsv(run(['tesseract',str(image),'stdout','-l',language,'tsv']),threshold)
                pages.append({'page':number,'method':'tesseract','coordinate_space':'rendered_image_pixels',
                              'text':' '.join(w['text'] for w in words),'words':words,'human_reviewed':False,
                              'review_required':True,'empty':not words})
        if hashlib.sha256(source.read_bytes()).hexdigest()!=source_hash:
            raise ValueError('Source changed during extraction; retry from an immutable copy.')
        result={'schema_version':'ocr-1.0','document_id':document_id,
                'source_sha256':source_hash,
                'engine':run(['tesseract','--version']).splitlines()[0],
                'language':language,'low_confidence_threshold':threshold,'page_count':count,'pages':pages,
                'fact_status':'unverified','network_used':False,
                'limits':['Confidence is an engine heuristic, not correctness or authenticity.',
                          'Reading order and tables may be wrong; inspect each original page.',
                          'Names, numbers, dates, refusal grounds and deadlines always require human comparison.']}
        write(root/'ocr.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        write(root/'transcript.txt','\n\n'.join('[PAGE '+str(p['page'])+' - UNVERIFIED OCR]\n'+p['text'] for p in pages)+'\n')
        return {'document_id':document_id,'page_count':count,'low_confidence_words':sum(w['low_confidence'] for p in pages for w in p['words']),
                'empty_pages':[p['page'] for p in pages if p['empty']],'review_required':True,'network_used':False}
    except Exception:
        shutil.rmtree(root);raise


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--out',required=True)
    p.add_argument('--document-id',required=True);p.add_argument('--language',default='eng')
    p.add_argument('--max-pages',type=int,default=25);p.add_argument('--threshold',type=float,default=85)
    a=p.parse_args(argv)
    try:
        print(json.dumps(extract(a.input,a.out,a.document_id,a.language,a.max_pages,a.threshold),indent=2));return 0
    except (OSError,ValueError,TypeError):
        print('OCR failed: check local Tesseract/Poppler, installed language data, input limits and a new private output path. No private values are printed.',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
