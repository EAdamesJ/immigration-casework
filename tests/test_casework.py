import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(os.environ.get("CASEWORK_SKILL_ROOT", ROOT / "skills" / "us-immigration-casework"))
spec = importlib.util.spec_from_file_location("casework", SKILL / "scripts" / "casework.py")
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)


class ElapsedTests(unittest.TestCase):
    def test_leap_month(self):
        result = cw.elapsed("2024-01-31", "2024-03-01")
        self.assertEqual((result["elapsed_days"], result["calendar_months"], result["remaining_days"]), (30, 1, 1))

    def test_month_end_clamping(self):
        self.assertEqual(cw.elapsed("2023-01-31", "2023-02-28")["calendar_months"], 1)

    def test_before_monthly_anniversary(self):
        self.assertEqual(cw.elapsed("2024-01-31", "2024-03-30")["remaining_days"], 30)

    def test_leap_year_anniversary(self):
        self.assertEqual(cw.elapsed("2024-02-29", "2025-02-28")["calendar_months"], 12)

    def test_same_day(self):
        self.assertEqual(cw.elapsed("2024-05-01", "2024-05-01")["elapsed_days"], 0)

    def test_reverse_rejected(self):
        with self.assertRaises(ValueError): cw.elapsed("2024-05-02", "2024-05-01")

    def test_invalid_dates_rejected(self):
        for bad in ("2024-02-30", "2024-1-01", "not-a-date", "2024-01-01T00:00:00Z"):
            with self.subTest(bad=bad), self.assertRaises(ValueError): cw.parse_date(bad)

    def test_no_forecast(self):
        result = cw.elapsed("2024-01-01", "2024-06-01")
        self.assertIsNone(result["approval_forecast"])
        self.assertFalse(result["legal_deadline_calculated"])


class SourceTests(unittest.TestCase):
    def test_official_subdomain(self):
        self.assertTrue(cw.classify_source("https://egov.uscis.gov/processing-times/")["official_domain_candidate"])

    def test_lookalike_rejected(self):
        for url in ("https://uscis.gov.example.test", "https://uscis-gov.example.test", "https://example.test/uscis.gov"):
            with self.subTest(url=url): self.assertFalse(cw.classify_source(url)["official_domain_candidate"])

    def test_userinfo_rejected(self):
        self.assertFalse(cw.classify_source("https://someone@uscis.gov/")["official_domain_candidate"])

    def test_scheme_port_and_malformed_rejected(self):
        for url in ("http://uscis.gov", "file:///uscis.gov", "https://uscis.gov:444", "https://[broken", "https://uscis.gov:bad", "https://uscis.gov /x"):
            with self.subTest(url=url): self.assertFalse(cw.classify_source(url)["official_domain_candidate"])

    def test_no_query_echo_and_no_fetch(self):
        result = cw.classify_source("https://www.uscis.gov/a?private=DO_NOT_ECHO#hidden")
        self.assertNotIn("DO_NOT_ECHO", json.dumps(result))
        self.assertFalse(result["page_fetched"])


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.case = cw.blank_case("synthetic-case", "en")

    def codes(self, case=None, **kwargs):
        return {issue["code"] for issue in cw.audit(self.case if case is None else case, **kwargs)["issues"]}

    def add_notice(self):
        self.case["evidence"] = [{"id": "E1", "label": "Synthetic notice excerpt"}]
        self.case["sources"] = [{"id": "S1", "kind": "notice", "title": "Synthetic notice", "access_method": "user_copy", "checked_at": "2024-05-01", "evidence_id": "E1"}]

    def test_empty_manifest_valid(self):
        self.assertEqual(self.codes(), set())

    def test_missing_root_field(self):
        del self.case["stage"]
        self.assertIn("required_field", self.codes())

    def test_wrong_type(self):
        self.case["facts"] = "private"
        self.assertIn("wrong_type", self.codes())

    def test_duplicate_ids(self):
        self.case["evidence"] = [{"id": "E1", "label": "a"}, {"id": "E1", "label": "b"}]
        self.assertIn("duplicate_id", self.codes())

    def test_dangling_source(self):
        self.case["facts"] = [{"id": "F1", "key": "status", "value": "pending", "status": "user_reported", "source_ids": ["Missing"]}]
        self.assertIn("missing_source_reference", self.codes())

    def test_verified_requires_inspected_source(self):
        self.case["facts"] = [{"id": "F1", "key": "status", "value": "pending", "status": "document_verified", "source_ids": []}]
        self.assertIn("verified_claim_requires_inspected_source", self.codes())

    def test_notice_source_links_valid(self):
        self.add_notice()
        self.case["facts"] = [{"id": "F1", "key": "receipt_date", "value": "2024-01-01", "status": "document_verified", "source_ids": ["S1"]}]
        self.assertEqual(self.codes(), set())

    def test_notice_requires_evidence(self):
        self.add_notice()
        del self.case["sources"][0]["evidence_id"]
        self.assertIn("notice_requires_evidence", self.codes())

    def test_inference_requires_explanation(self):
        self.add_notice()
        self.case["facts"] = [{"id": "F1", "key": "conclusion", "value": "unsettled", "status": "inferred", "source_ids": ["S1"]}]
        self.assertIn("inference_requires_sources_and_explanation", self.codes())

    def test_unresolved_contradiction(self):
        self.case["facts"] = [{"id": "F1", "key": "stage", "value": None, "status": "contradicted", "source_ids": []}]
        self.assertIn("unresolved_contradiction", self.codes())

    def test_submitted_requires_evidence(self):
        self.case["actions"] = [{"id": "A1", "description": "Inquiry", "state": "submitted", "source_ids": []}]
        self.assertIn("submission_requires_evidence", self.codes())

    def test_valid_submission_reference(self):
        self.case["evidence"] = [{"id": "E1", "label": "Synthetic confirmation"}]
        self.case["actions"] = [{"id": "A1", "description": "Inquiry", "state": "submitted", "source_ids": [], "submission_evidence_id": "E1"}]
        self.assertEqual(self.codes(), set())

    def test_deadline_requires_primary_source(self):
        self.case["deadlines"] = [{"id": "D1", "date": "2024-07-01", "time_zone": "UTC", "action": "Respond", "delivery_rule": "Verify actual notice", "source_id": "S1"}]
        self.assertIn("deadline_requires_source", self.codes())

    def test_bad_deadline_date(self):
        self.case["deadlines"] = [{"id": "D1", "date": "2024-02-30", "time_zone": "UTC", "action": "Respond", "delivery_rule": "Received", "source_id": "S1"}]
        self.assertIn("invalid_date", self.codes())

    def test_deadline_basis_must_be_inspected(self):
        self.add_notice()
        self.case["sources"][0]["access_method"] = "not_checked"
        self.case["deadlines"] = [{"id": "D1", "date": "2024-07-01", "time_zone": "UTC", "action": "Respond", "delivery_rule": "Received", "source_id": "S1"}]
        self.assertIn("deadline_basis_not_inspected", self.codes())

    def test_valid_deadline_record(self):
        self.add_notice()
        self.case["deadlines"] = [{"id": "D1", "date": "2024-07-01", "time_zone": "UTC", "action": "Respond", "delivery_rule": "Received", "source_id": "S1"}]
        self.assertEqual(self.codes(), set())

    def test_case_stage_conflict(self):
        self.case.update(process="consular", stage="uscis_pending")
        self.case["events"] = [{"id": "T1", "kind": "visa_issued", "date": "2024-05-01", "status": "user_reported", "source_ids": []}]
        self.assertIn("stage_event_conflict", self.codes())

    def test_adjustment_interview_not_consular_conflict(self):
        self.case.update(process="adjustment", stage="uscis_pending")
        self.case["events"] = [{"id": "T1", "kind": "interview_taken", "date": "2024-05-01", "status": "user_reported", "source_ids": []}]
        self.assertNotIn("stage_event_conflict", self.codes())

    def test_reverse_chronology(self):
        self.case.update(process="consular", stage="nvc_pending")
        self.case["events"] = [{"id": "T1", "kind": "uscis_approved", "date": "2024-06-01", "status": "user_reported", "source_ids": []}, {"id": "T2", "kind": "nvc_created", "date": "2024-05-01", "status": "user_reported", "source_ids": []}]
        self.assertIn("chronology_conflict", self.codes())

    def test_future_completed_event(self):
        self.case["events"] = [{"id": "T1", "kind": "interview_taken", "date": "2024-07-01", "status": "user_reported", "source_ids": []}]
        self.assertIn("completed_event_in_future", self.codes(as_of="2024-05-01"))

    def test_future_appointment_allowed(self):
        self.case["events"] = [{"id": "T1", "kind": "interview_scheduled", "date": "2024-07-01", "status": "user_reported", "source_ids": []}]
        self.assertNotIn("completed_event_in_future", self.codes(as_of="2024-05-01"))

    def test_audit_does_not_echo_private_values_or_unknown_keys(self):
        self.case["DO_NOT_ECHO"] = "DO_NOT_ECHO"
        self.assertNotIn("DO_NOT_ECHO", json.dumps(cw.audit(self.case)))

    def test_input_not_mutated(self):
        before = copy.deepcopy(self.case)
        cw.audit(self.case)
        self.assertEqual(self.case, before)


class FileTests(unittest.TestCase):
    def test_init_and_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp).resolve() / "private-case"
            result = cw.init_workspace(output, "synthetic-case", "es")
            self.assertEqual(result["files"], len(list(output.iterdir())))
            self.assertEqual(cw.audit(cw.load_json(output / "case.json"))["issues"], [])
            self.assertEqual((output / ".gitignore").read_text(), "*\n!.gitignore\n")
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o700)
                self.assertEqual((output / "case.json").stat().st_mode & 0o777, 0o600)

    def test_existing_workspace_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "case"
            cw.init_workspace(path, "synthetic-case", "en")
            before = (path / "case.json").read_bytes()
            with self.assertRaises(ValueError): cw.init_workspace(path, "other-case", "en")
            self.assertEqual((path / "case.json").read_bytes(), before)

    def test_git_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp).resolve() / ".git").mkdir()
            with self.assertRaises(ValueError): cw.init_workspace(Path(temp).resolve() / "case", "case", "en")

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "bad.json"
            path.write_text('{"stage":"unknown","stage":"admitted"}')
            with self.assertRaises(ValueError): cw.load_json(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "bad.json"
            path.write_text('{"value":NaN}')
            with self.assertRaises(ValueError): cw.load_json(path)

    def test_redaction_and_limits(self):
        synthetic = "IOE0000000000 A000000000 000-00-0000 sample@example.test +1 (202) 555-0100 Alex's diagnosis"
        result = cw.redact(synthetic)
        for label in ("[RECEIPT]", "[A-NUMBER]", "[SSN]", "[EMAIL]", "[PHONE]"):
            self.assertIn(label, result)
        self.assertIn("Alex's diagnosis", result)  # Deliberate documented limitation.

    def test_cli_exit_codes(self):
        script = SKILL / "scripts" / "casework.py"
        good = subprocess.run([sys.executable, str(script), "wait", "--received", "2024-01-01", "--as-of", "2024-01-02"], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0)
        self.assertEqual(json.loads(good.stdout)["elapsed_days"], 1)
        bad = subprocess.run([sys.executable, str(script), "wait", "--received", "bad", "--as-of", "2024-01-02"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)


if __name__ == "__main__": unittest.main()
