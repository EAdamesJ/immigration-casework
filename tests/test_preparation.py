"""Synthetic deterministic checks; no real applicant data or network."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

S=Path(os.environ.get('CASEWORK_SKILL_ROOT',Path(__file__).resolve().parents[1]/'skills/us-immigration-casework'))
sys.path.insert(0,str(S/'scripts'))
import preparation as p
import document_ocr as o


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((S/'assets/ds160-worksheet.json').read_text())
        self.record=json.loads((S/'assets/refusal-record.json').read_text())
        self.packet=json.loads((S/'assets/export-packet.json').read_text())

    def review(self):return p.ds160(self.data,'2026-10-31')

    def complete(self):
        for row in self.data['fields'].values():row.update(value='Synthetic',status='user_reported',applicant_confirmed=True)
        for field,value in {'birth_date':'1990-01-01','passport_issue':'2020-01-01','passport_expiry':'2030-01-01','arrival_date':'2027-01-01','departure_date':'2027-01-10','prior_refusal':False,'immigrant_petition':False}.items():self.data['fields'][field]['value']=value
        self.data['ceac_question_by_question_reviewed']=True

    def test_blank_never_ready(self):
        r=self.review();self.assertEqual(r['status'],'review_required');self.assertFalse(r['submission_authorized'])

    def test_no_default_security_answer(self):self.assertIsNone(self.data['fields']['security_questions']['value'])
    def test_complete_is_only_worksheet(self):
        self.complete();r=self.review();self.assertEqual(r['status'],'worksheet_review_complete');self.assertFalse(r['submission_authorized'])

    def test_ascii_not_language_validation(self):
        self.complete();self.data['fields']['occupation']['value']='Médico';self.assertIn({'field':'occupation','code':'english_character_review'},self.review()['issues'])

    def test_string_false_not_boolean(self):
        self.complete();self.data['fields']['prior_refusal']['value']='false';self.assertIn({'field':'prior_refusal','code':'boolean_required'},self.review()['issues'])

    def test_yes_requires_explanation(self):
        self.complete();self.data['fields']['prior_refusal']['value']=True;self.assertIn({'field':'prior_refusal','code':'explanation_required'},self.review()['issues'])

    def test_document_pointer_required(self):
        self.complete();self.data['fields']['surname']['status']='document_verified';self.assertIn({'field':'surname','code':'document_page_reference_missing'},self.review()['issues'])

    def test_invalid_boolean_page(self):
        self.complete();self.data['fields']['surname'].update(status='document_verified',evidence=[{'document_id':'E1','page':True}]);self.assertIn({'field':'surname','code':'document_page_reference_missing'},self.review()['issues'])

    def test_invalid_date_flagged(self):
        self.complete();self.data['fields']['birth_date']['value']='1990-02-30';self.assertIn({'field':'birth_date','code':'invalid_date'},self.review()['issues'])

    def test_chronology(self):
        self.complete();self.data['fields']['departure_date']['value']='2026-01-01';self.assertIn({'field':'departure_date','code':'chronology_conflict'},self.review()['issues'])

    def test_confirmation_not_assumed(self):
        self.complete();self.data['fields']['surname']['applicant_confirmed']=False;self.assertEqual(self.review()['status'],'review_required')

    def test_live_question_review_required(self):
        self.complete();self.data['ceac_question_by_question_reviewed']=False;self.assertIn({'field':'worksheet','code':'live_ceac_questions_not_reviewed'},self.review()['issues'])

    def test_no_values_in_findings(self):
        self.data['fields']['surname']['value']='PRIVATE_SENTINEL';self.assertNotIn('PRIVATE_SENTINEL',json.dumps(self.review()))

    def test_refusal_unknown(self):self.assertEqual(p.refusal(self.record)['routes'],['unknown_obtain_notice'])
    def test_214b_unverified(self):
        self.record['grounds']=['INA 214(b)'];r=p.refusal(self.record);self.assertEqual(r['ground_source'],'unverified');self.assertIsNone(r['deadline']);self.assertIsNone(r['approval_probability'])

    def test_multiple_grounds_preserved(self):
        self.record['grounds']=['214(b)','221(g)','212(a)(6)(C)(i)'];self.assertEqual(len(p.refusal(self.record)['routes']),3)

    def test_refused_label_not_ground(self):
        self.record['grounds']=['Refused'];self.assertEqual(p.refusal(self.record)['routes'],['specialist_ground_review'])

    def test_inspected_notice_needs_reference(self):
        self.record['notice']['human_reviewed']=True;self.assertEqual(p.refusal(self.record)['ground_source'],'unverified')

    def test_inspected_notice(self):
        self.record['notice'].update(human_reviewed=True,document_id='E1',page=1);self.assertEqual(p.refusal(self.record)['ground_source'],'document_reviewed')

    def test_malformed_ground(self):
        self.record['grounds']=[{}]
        with self.assertRaises(ValueError):p.refusal(self.record)

    def test_export_integrity_and_explicit_attachments(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();source=root/'source.txt';source.write_text('SYNTHETIC');(root/'unselected.txt').write_text('DO NOT EXPORT')
            p.export_packet(self.packet,root/'out',attachments=[source])
            manifest=json.loads((root/'out/manifest.json').read_text())
            for f in manifest['files']:self.assertEqual(f['sha256'],hashlib.sha256((root/'out'/f['path']).read_bytes()).hexdigest())
            with zipfile.ZipFile(root/'out/packet.zip') as z:
                self.assertEqual(set(z.namelist()),{f['path'] for f in manifest['files']}|{'manifest.json'});self.assertNotIn('unselected.txt',z.namelist())
            self.assertFalse(manifest['encrypted']);self.assertFalse(manifest['redacted'])
            self.assertEqual(json.loads((root/'out/report.json').read_text())['submitted'],False)
            if os.name=='posix':self.assertEqual((root/'out').stat().st_mode&0o777,0o700)

    def test_export_html_escape(self):
        with tempfile.TemporaryDirectory() as t:
            self.packet['sections'][0]['body']='<script>alert(1)</script>'
            out=Path(t).resolve()/'out';p.export_packet(self.packet,out)
            text=(out/'report.html').read_text();self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)

    def test_output_collision_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();out=root/'out';out.mkdir();(out/'keep').write_text('KEEP')
            with self.assertRaises(FileExistsError):p.export_packet(self.packet,out)
            self.assertEqual((out/'keep').read_text(),'KEEP')

    def test_git_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();(root/'.git').mkdir()
            with self.assertRaises(ValueError):p.export_packet(self.packet,root/'out')

    def test_unsafe_case_id_rejected(self):
        self.packet['case_id']='../elsewhere'
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):p.export_packet(self.packet,Path(t).resolve()/'out')

    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            file=Path(t)/'in.json';file.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError):p.load(file)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            file=Path(t)/'in.json'
            for value in ('NaN','Infinity','-Infinity','1e999'):
                file.write_text('{"x":'+value+'}')
                with self.assertRaises(ValueError):p.load(file)

    def test_cli_error_omits_private_input(self):
        with tempfile.TemporaryDirectory() as t:
            file=Path(t)/'in.json';file.write_text('{"schema_version":"PRIVATE_SENTINEL"}')
            r=subprocess.run([sys.executable,str(S/'scripts/preparation.py'),'refusal','--input',str(file)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2);self.assertNotIn('PRIVATE_SENTINEL',r.stderr+r.stdout)


class OCRTests(unittest.TestCase):
    def test_word_coordinates_and_review(self):
        tsv='left\ttop\twidth\theight\tconf\ttext\n10\t20\t30\t40\t84\tSYNTHETIC\n'
        w=o.words_from_tsv(tsv)[0];self.assertEqual(w['bbox_pixels'],[10,20,30,40]);self.assertTrue(w['low_confidence']);self.assertFalse(w['human_reviewed'])

    def test_high_confidence_not_verified(self):
        w=o.words_from_tsv('left\ttop\twidth\theight\tconf\ttext\n0\t0\t3\t4\t99\tA\n')[0];self.assertFalse(w['human_reviewed'])

    def test_empty_page(self):self.assertEqual(o.words_from_tsv('left\ttop\twidth\theight\tconf\ttext\n'),[])
    def test_invalid_confidence(self):
        with self.assertRaises(ValueError):o.words_from_tsv('left\ttop\twidth\theight\tconf\ttext\n0\t0\t3\t4\tNaN\tA\n')

    def test_invalid_language_no_command(self):
        with self.assertRaises(ValueError):o.extract('none','none','E1','eng;command')

    def test_page_limit_no_command(self):
        with self.assertRaises(ValueError):o.extract('none','none','E1',max_pages=101)


if __name__=='__main__':unittest.main()
