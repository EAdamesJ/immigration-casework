"""Synthetic offline agenda, adapters, concurrent revisions and dispatch state tests."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

S=Path(os.environ.get('CASEWORK_SKILL_ROOT',Path(__file__).resolve().parents[1]/'skills/us-immigration-casework'))
sys.path.insert(0,str(S/'scripts'))
import agenda as a
import connectors as c
import coordination as w

NOW='2026-10-31T15:00:00Z'
LATER='2026-11-01T15:00:00Z'
EXPIRES='2026-11-02T15:00:00Z'


def event():
    return {'schema_version':'event-2.0','case_id':'case1','event_id':'meeting','revision':1,'kind':'appointment',
            'summary':'Casework review','status':'tentative','all_day':False,
            'start':'2027-01-12T09:00:00+00:00','end':'2027-01-12T09:30:00+00:00','timezone':'UTC','reminder_minutes':[60]}


class AgendaTests(unittest.TestCase):
    def test_utc_calendar(self):
        out=a.ical([event()],NOW);self.assertIn('DTSTART:20270112T090000Z',out);self.assertIn('CLASS:PRIVATE',out);self.assertIn('ACTION:DISPLAY',out)
        self.assertNotIn('ATTENDEE',out);self.assertNotIn('ACTION:EMAIL',out)
    def test_floating_timestamp_rejected(self):
        with self.assertRaises(ValueError):a.instant('2026-10-31T15:00:00')
    def test_end_before_start(self):
        e=event();e['end']='2027-01-12T08:30:00Z'
        with self.assertRaises(ValueError):a.validate_event(e)
    def test_wrong_offset(self):
        e=event();e['start']='2027-01-12T09:00:00-04:00'
        with self.assertRaises(ValueError):a.validate_event(e)
    def test_dst_gap(self):
        e=event();e.update(start='2027-03-14T02:15:00-05:00',end='2027-03-14T03:30:00-04:00',timezone='America/New_York')
        with self.assertRaises(ValueError):a.validate_event(e)
    def test_dst_fall_back_explicit(self):
        e=event();e.update(start='2026-11-01T01:15:00-04:00',end='2026-11-01T01:45:00-04:00',timezone='America/New_York');a.validate_event(e)
    def test_all_day_exclusive(self):
        e=event();e.update(all_day=True,start='2027-01-12',end='2027-01-13',reminder_minutes=[])
        out=a.ical([e],NOW);self.assertIn('DTEND;VALUE=DATE:20270113',out)
    def test_all_day_alarm_not_guessed(self):
        e=event();e.update(all_day=True,start='2027-01-12',end='2027-01-13')
        with self.assertRaises(ValueError):a.validate_event(e)
    def test_deadline_needs_source(self):
        e=event();e['kind']='documented_deadline'
        with self.assertRaises(ValueError):a.validate_event(e)
    def test_deadline_source_pointer(self):
        e=event();e.update(kind='documented_deadline',source={'document_id':'E1','page':1,'human_reviewed':True,'status':'document_verified','checked_on':'2026-10-31','basis':'Synthetic notice explicitly states this date.'});a.validate_event(e)
    def test_uid_stable_sequence_changes(self):
        e=event();first=a.ical([e],NOW);e['revision']=2;second=a.ical([e],LATER)
        self.assertEqual([x for x in first.splitlines() if x.startswith('UID:')],[x for x in second.splitlines() if x.startswith('UID:')]);self.assertIn('SEQUENCE:1',second)
    def test_cancelled_has_no_alarm(self):
        e=event();e['status']='cancelled';out=a.ical([e],NOW);self.assertIn('STATUS:CANCELLED',out);self.assertNotIn('BEGIN:VALARM',out)
    def test_utf8_folding_and_escape(self):
        e=event();e['summary']='Revisión, documentos; '+('á'*90)+'\nNEXT'
        out=a.ical([e],NOW);self.assertTrue(all(len(x.encode())<=75 for x in out.split('\r\n')))
        unfolded=out.replace('\r\n ','');self.assertIn('Revisión\\, documentos\\;',unfolded);self.assertIn('\\nNEXT',unfolded)
    def test_control_injection_rejected(self):
        e=event();e['summary']='Safe\r\nATTENDEE:bad'
        with self.assertRaises(ValueError):a.ical([e],NOW)
    def test_duplicate_event(self):
        with self.assertRaises(ValueError):a.ical([event(),event()],NOW)


class AdapterTests(unittest.TestCase):
    def test_google_private_no_attendees(self):
        p=c.build('google_calendar','calendar.create',event());self.assertEqual(p['visibility'],'private');self.assertNotIn('attendees',p);self.assertEqual(len(p['id']),64)
    def test_outlook_rejects_multiple_reminders(self):
        e=event();e['reminder_minutes']=[60,1440]
        with self.assertRaises(ValueError):c.build('outlook_calendar','calendar.create',e)
    def test_unverified_recipient_rejected(self):
        with self.assertRaises(ValueError):c.build('gmail','notification.draft',{'to':'synthetic@example.invalid','subject':'Review','body':'Review task.'})
    def test_email_header_injection_rejected(self):
        with self.assertRaises(ValueError):c.build('gmail','notification.draft',{'to':'synthetic@example.invalid\r\nBcc:other@example.invalid','subject':'Review','body':'Review task.','recipient_verified':True,'verification_ref':'synthetic'})
    def test_send_requires_existing_draft(self):
        with self.assertRaises(ValueError):c.build('gmail','notification.send',{'to':'synthetic@example.invalid','subject':'Review','body':'Review task.','recipient_verified':True,'verification_ref':'synthetic'})
    def test_no_unsupported_provider(self):
        with self.assertRaises(ValueError):c.build('whatsapp','notification.send',{})


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        w.initialize(self.root/'team','owner',NOW);self.path=self.root/'team/coordination.sqlite3';self.store=w.Store(self.path)
        self.op('case.create')
    def tearDown(self):self.store.close();self.temp.cleanup()
    def op(self,operation,actor='owner',now=NOW,**fields):
        revision=self.store.snapshot()[0]
        return self.store.apply({'actor':actor,'expected_revision':revision,'operation':operation,'case_id':'case1',**fields},now)
    def prepare(self,request_id='notify',**changes):
        r={'request_id':request_id,'provider':'gmail','provider_operation':'notification.draft','account_ref':'account1','destination':'mailbox1','not_before':NOW,
           'data':{'to':'synthetic@example.invalid','recipient_verified':True,'verification_ref':'synthetic-contact','subject':'Review task','body':'Please review task T1.'}}
        r.update(changes);return self.op('action.prepare',**r)
    def authorize(self):
        hashed=self.prepare()['request_hash'];self.op('action.authorize',request_id='notify',request_hash=hashed,authorization_ref='synthetic-instruction',expires_at=EXPIRES)
        self.op('connector.configure',provider='gmail',enabled=True,account_ref='account1')
        return hashed
    def claim(self):return self.op('action.claim',request_id='notify',observed_capabilities={'gmail':['notification.draft']})['bridge']
    def add_reviewers(self):
        self.op('member.add',member='prep',role='preparer');self.op('member.add',member='review',role='reviewer')
        self.op('artifact.revise',actor='prep',artifact_id='packet',sha256='a'*64)
        self.op('review.assign',artifact_id='packet',artifact_revision=1,sha256='a'*64,reviewer='review')
    def test_initialized_permissions(self):
        if os.name=='posix':self.assertEqual(self.path.stat().st_mode&0o777,0o600)
    def test_stale_revision_rejected(self):
        with self.assertRaises(ValueError):self.store.apply({'actor':'owner','expected_revision':0,'operation':'case.create','case_id':'other'},NOW)
    def test_concurrent_operator_sees_conflict(self):
        other=w.Store(self.path)
        try:
            old=other.snapshot()[0];self.op('member.add',member='prep',role='preparer')
            with self.assertRaises(ValueError):other.apply({'actor':'owner','expected_revision':old,'operation':'member.add','case_id':'case1','member':'review','role':'reviewer'},NOW)
        finally:other.close()
    def test_cross_case_actor_rejected(self):
        self.op('member.add',member='prep',role='preparer');self.op('case.create',case_id='case2')
        with self.assertRaises(ValueError):self.op('artifact.revise',actor='prep',case_id='case2',artifact_id='packet',sha256='a'*64)
    def test_observer_cannot_edit(self):
        self.op('member.add',member='read',role='observer')
        with self.assertRaises(ValueError):self.op('artifact.revise',actor='read',artifact_id='packet',sha256='a'*64)
    def test_independent_review_and_revision(self):
        self.add_reviewers();self.op('review.decide',actor='review',artifact_id='packet',artifact_revision=1,sha256='a'*64,decision='approved',note='Synthetic review completed.')
        self.op('artifact.revise',actor='prep',artifact_id='packet',sha256='b'*64)
        versions=self.store.snapshot()[1]['cases']['case1']['artifacts']['packet'];self.assertEqual(versions[-1]['status'],'draft');self.assertEqual(versions[0]['status'],'approved')
    def test_stale_artifact_review_rejected(self):
        self.add_reviewers();self.op('artifact.revise',actor='prep',artifact_id='packet',sha256='b'*64)
        with self.assertRaises(ValueError):self.op('review.decide',actor='review',artifact_id='packet',artifact_revision=1,sha256='a'*64,decision='approved',note='Old copy.')
    def test_preparer_not_reviewer(self):
        self.add_reviewers()
        with self.assertRaises(ValueError):self.op('review.decide',actor='prep',artifact_id='packet',artifact_revision=1,sha256='a'*64,decision='approved',note='Self.')
    def test_remove_reviewer_unassigns_pending_review(self):
        self.add_reviewers();self.op('member.remove',member='review');self.assertEqual(self.store.snapshot()[1]['cases']['case1']['artifacts']['packet'][-1]['status'],'draft')
    def test_task_assignee_transitions(self):
        self.op('member.add',member='prep',role='preparer');self.op('task.create',task_id='T1',assignee='prep',summary='Review evidence')
        self.op('task.transition',actor='prep',task_id='T1',status='done');self.assertEqual(self.store.snapshot()[1]['cases']['case1']['tasks']['T1']['status'],'done')
    def test_disabled_connector_cannot_claim(self):
        hashed=self.prepare()['request_hash'];self.op('action.authorize',request_id='notify',request_hash=hashed,authorization_ref='synthetic',expires_at=EXPIRES)
        with self.assertRaises(ValueError):self.claim()
    def test_authorization_wrong_hash(self):
        self.prepare()
        with self.assertRaises(ValueError):self.op('action.authorize',request_id='notify',request_hash='0'*64,authorization_ref='synthetic',expires_at=EXPIRES)
    def test_expired_authorization(self):
        self.authorize()
        with self.assertRaises(ValueError):self.op('action.claim',now=EXPIRES,request_id='notify',observed_capabilities={'gmail':['notification.draft']})
    def test_missing_capability_no_claim(self):
        self.authorize()
        with self.assertRaises(ValueError):self.op('action.claim',request_id='notify',observed_capabilities={})
        self.assertEqual(self.store.snapshot()[1]['cases']['case1']['actions']['notify']['status'],'authorized')
    def test_wrong_capability_shape(self):
        self.authorize()
        with self.assertRaises(ValueError):self.op('action.claim',request_id='notify',observed_capabilities={'gmail':'notification.draft'})
    def test_account_changed(self):
        self.authorize();self.op('connector.configure',provider='gmail',enabled=True,account_ref='account2')
        with self.assertRaises(ValueError):self.claim()
    def test_exact_duplicate_prepare(self):
        a1=self.prepare();a2=self.prepare();self.assertTrue(a2['duplicate']);self.assertEqual(a1['request_hash'],a2['request_hash'])
    def test_same_request_changed_target(self):
        self.prepare()
        with self.assertRaises(ValueError):self.prepare(destination='other-mailbox')
    def test_equivalent_payload_new_id(self):
        self.prepare()
        with self.assertRaises(ValueError):self.prepare(request_id='second')
    def test_unapproved_action_never_claims(self):
        self.prepare();self.op('connector.configure',provider='gmail',enabled=True,account_ref='account1')
        with self.assertRaises(ValueError):self.claim()
    def test_revoked_action(self):
        self.authorize();self.op('action.revoke',request_id='notify')
        with self.assertRaises(ValueError):self.claim()
    def test_dispatch_claim_only_once(self):
        self.authorize();bridge=self.claim();self.assertEqual(bridge['authorization_expires_at'],EXPIRES)
        with self.assertRaises(ValueError):self.claim()
    def test_preflight_checks_revocation_after_claim(self):
        self.authorize();bridge=self.claim();self.op('action.revoke',request_id='notify')
        with self.assertRaises(ValueError):self.op('action.preflight',request_id='notify',attempt_id=bridge['attempt_id'])
    def test_unknown_result_cannot_retry(self):
        self.authorize();bridge=self.claim();self.op('action.receipt',request_id='notify',attempt_id=bridge['attempt_id'],request_hash=bridge['request_hash'],outcome='unknown',result_ref='synthetic-timeout')
        with self.assertRaises(ValueError):self.op('action.retry',request_id='notify')
    def test_receipt_wrong_attempt_rejected(self):
        self.authorize();bridge=self.claim()
        with self.assertRaises(ValueError):self.op('action.receipt',request_id='notify',attempt_id='wrong',request_hash=bridge['request_hash'],outcome='confirmed',result_ref='synthetic-result',external_id='synthetic-draft')
    def test_confirmed_is_not_delivery(self):
        self.authorize();bridge=self.claim();r=self.op('action.receipt',request_id='notify',attempt_id=bridge['attempt_id'],request_hash=bridge['request_hash'],outcome='confirmed',result_ref='synthetic-result',external_id='synthetic-draft');self.assertFalse(r['provider_delivery_proven'])
    def test_not_applied_retry_clears_authorization(self):
        self.authorize();bridge=self.claim();self.op('action.receipt',request_id='notify',attempt_id=bridge['attempt_id'],request_hash=bridge['request_hash'],outcome='not_applied',result_ref='synthetic-result');self.op('action.retry',request_id='notify')
        with self.assertRaises(ValueError):self.claim()
        history=self.store.snapshot()[1]['cases']['case1']['actions']['notify']['attempts']
        self.assertEqual(history[0]['receipts'][0]['outcome'],'not_applied')
    def test_due_summary_has_no_private_content(self):
        self.authorize();summary=self.store.summary(NOW);self.assertEqual(len(summary['due']),1);self.assertNotIn('example.invalid',json.dumps(summary));self.assertNotIn('Please review',json.dumps(summary))
    def test_snapshot_corruption_detected(self):
        state=self.store.snapshot()[1];state['owner']='tampered';self.store.db.execute('UPDATE snapshot SET body=?',(json.dumps(state),));self.store.db.commit()
        with self.assertRaises(ValueError):self.store.snapshot()
    def test_audit_deletion_detected(self):
        self.store.db.execute('DELETE FROM audit WHERE seq=0');self.store.db.commit()
        with self.assertRaises(ValueError):self.store.snapshot()
    def test_failed_operation_rolls_back(self):
        before=self.store.snapshot()[0]
        with self.assertRaises(ValueError):self.op('member.add',member='bad',role='invalid')
        self.assertEqual(self.store.snapshot()[0],before)


if __name__=='__main__':unittest.main()
