"""Opt-in real engine smoke tests using only generated synthetic content."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

S=Path(os.environ.get('CASEWORK_SKILL_ROOT',Path(__file__).resolve().parents[1]/'skills/us-immigration-casework'))
sys.path.insert(0,str(S/'scripts'))
import preparation as p
import document_ocr as o
import forms as f


@unittest.skipUnless(os.environ.get('CASEWORK_INTEGRATION')=='1','Optional local engines; set CASEWORK_INTEGRATION=1')
class DocumentIntegrationTests(unittest.TestCase):
    def packet(self):
        return {'schema_version':'packet-1.0','case_id':'synthetic','title':'Synthetic document review','language':'en',
                'sections':[{'heading':'Evidence review','body':'SYNTHETIC TEST DOCUMENT. No actual applicant data. Review every date and identifier against the original.'}]}

    def test_real_pdf_docx_export_and_pdf_ocr(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();p.export_packet(self.packet(),root/'packet',('pdf','docx','json'))
            self.assertTrue((root/'packet/report.pdf').read_bytes().startswith(b'%PDF-'))
            with zipfile.ZipFile(root/'packet/report.docx') as z:
                xml=z.read('word/document.xml').decode();self.assertIn('SYNTHETIC TEST DOCUMENT',xml);self.assertNotIn('w:pBdr',xml)
            r=o.extract(root/'packet/report.pdf',root/'ocr','SYNTHETIC')
            self.assertEqual(r['page_count'],1)
            data=json.loads((root/'ocr/ocr.json').read_text());self.assertEqual(data['fact_status'],'unverified')
            self.assertIn('SYNTHETIC',data['pages'][0]['text']);self.assertEqual(len(data['source_sha256']),64)

    def test_real_image_ocr(self):
        from PIL import Image,ImageDraw,ImageFont
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();im=Image.new('RGB',(1300,300),'white')
            ImageDraw.Draw(im).text((40,80),'SYNTHETIC DOCUMENT FOR REVIEW',font=ImageFont.load_default(size=40),fill='black');im.save(root/'source.png')
            o.extract(root/'source.png',root/'ocr','SYNTHETIC')
            data=json.loads((root/'ocr/ocr.json').read_text());self.assertIn('SYNTHETIC',data['pages'][0]['text'])
            self.assertTrue(all(not w['human_reviewed'] for w in data['pages'][0]['words']))

    def test_unsupported_pdf_script_leaves_no_partial_package(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();data=self.packet();data['title']='姓名'
            with self.assertRaises(UnicodeEncodeError):p.export_packet(data,root/'out',('pdf',))
            self.assertFalse((root/'out').exists())

    def test_fillable_pdf_canonical_values_and_appearance(self):
        from reportlab.pdfgen import canvas
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();template=root/'form.pdf';doc=canvas.Canvas(str(template))
            doc.acroForm.textfield(name='NAME',x=60,y=650,width=400,height=24,fontName='Courier');doc.showPage();doc.save()
            f.fill_pdf(template,{'NAME':'Synthetic Person'},root/'filled')
            reader=PdfReader(root/'filled/filled-draft.pdf');self.assertEqual(reader.get_fields()['NAME']['/V'],'Synthetic Person')
            widget=reader.pages[0]['/Annots'][0].get_object();self.assertTrue(widget['/AP']['/N'].get_object().get_data());self.assertEqual(widget['/V'],'Synthetic Person')

    def test_docx_split_placeholder_preserves_first_run_style(self):
        from docx import Document
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();doc=Document();p=doc.add_paragraph('Name: ');p.add_run('{{NA').bold=True;p.add_run('ME}}').bold=True;doc.save(root/'template.docx')
            f.fill_docx(root/'template.docx',{'NAME':'Synthetic Person'},root/'filled')
            result=Document(root/'filled/filled-draft.docx');self.assertEqual(result.paragraphs[0].text,'Name: Synthetic Person');self.assertTrue(result.paragraphs[0].runs[1].bold)


if __name__=='__main__':unittest.main()
