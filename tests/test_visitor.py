import importlib.util
import json
from pathlib import Path
import unittest
S=Path(__file__).resolve().parents[1]/'skills/us-immigration-casework'
spec=importlib.util.spec_from_file_location('visitor',S/'scripts/visitor.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class VisitorTests(unittest.TestCase):
 def setUp(self):
  self.p=json.loads((S/'assets/visitor-profile.json').read_text());self.b=json.loads((S/'assets/bulletin-snapshot.json').read_text())
 def compare(self,**kw):
  args=dict(category='F2A',country='SYNTHETIC',priority='2022-01-01',as_of='2024-01-15',process='consular');args.update(kw);return v.bulletin(self.b,**args)
 def test_blank(self):self.assertEqual(v.readiness(self.p)['preparation'],'incomplete')
 def test_no_probability(self):self.assertIsNone(v.readiness(self.p)['approval_probability'])
 def test_complete(self):
  for row in self.p['topics'].values():row.update(answer='Synthetic supported answer',status='document_verified',evidence_ids=['E1'])
  self.assertEqual(v.readiness(self.p)['preparation'],'complete')
 def test_unlinked_document(self):
  self.p['topics']['purpose'].update(answer='Visit',status='document_verified');self.assertIn('purpose',v.readiness(self.p)['needs_evidence_review'])
 def test_conflict_first(self):
  self.p['topics']['duration'].update(answer='Unresolved',status='contradicted');self.assertEqual(v.interview(self.p)['questions'][0]['topic'],'duration')
 def test_spanish_english(self):self.assertNotEqual(v.interview(self.p,'en')['questions'][0]['question'],v.interview(self.p,'es')['questions'][0]['question'])
 def test_invalid_profile(self):
  with self.assertRaises(ValueError):v.readiness({'visa':'F1','topics':{}})
 def test_strict_boundary(self):self.assertEqual(self.compare(priority='2023-01-01')['charts']['final_action']['result'],'waiting')
 def test_earlier(self):self.assertEqual(self.compare()['charts']['final_action']['result'],'date_condition_met')
 def test_current(self):self.assertEqual(self.compare()['charts']['filing']['result'],'date_condition_met')
 def test_unavailable(self):
  self.b['rows'][0]['cutoff']='U';self.assertEqual(self.compare()['charts']['final_action']['result'],'unavailable')
 def test_missing_country(self):self.assertEqual(self.compare(country='OTHER')['charts']['final_action']['result'],'unknown_missing_row')
 def test_duplicate(self):
  self.b['rows'].append(self.b['rows'][0]);
  with self.assertRaises(ValueError):self.compare()
 def test_future_priority(self):
  with self.assertRaises(ValueError):self.compare(priority='2025-01-01')
 def test_upcoming(self):
  self.b['month']='2024-02';self.assertEqual(self.compare()['effective_relative_to_analysis'],'upcoming')
 def test_ir_not_applicable(self):self.assertEqual(self.compare(category='IR1')['result'],'preference_bulletin_not_applicable')
 def test_unknown_uscis(self):self.assertIsNone(self.compare(process='adjustment')['uscis_selected_chart'])
 def test_mismatched_uscis(self):
  self.b['uscis_chart']={'month':'2024-02','family':'family','chart':'filing','url':'https://www.uscis.gov/visabulletininfo','checked_at':'2024-01-01'}
  with self.assertRaises(ValueError):self.compare(process='adjustment')
 def test_source_lookalike(self):
  self.b['source']['url']='https://travel.state.gov.example.test/'
  with self.assertRaises(ValueError):self.compare()
 def test_invalid_date(self):
  with self.assertRaises(ValueError):self.compare(priority='2022-02-30')
if __name__=='__main__':unittest.main()
