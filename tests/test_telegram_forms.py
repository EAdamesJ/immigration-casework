"""Synthetic Telegram transport stubs and private worksheet checks; no live accounts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

S=Path(os.environ.get('CASEWORK_SKILL_ROOT',Path(__file__).resolve().parents[1]/'skills/us-immigration-casework'))
sys.path.insert(0,str(S/'scripts'))
import forms as f
import telegram_bot as t

NOW=1793458800


class FakeAPI:
    def __init__(self,error=None):self.calls=[];self.error=error
    def call(self,method,data=None,**kwargs):
        self.calls.append((method,data))
        if self.error:raise self.error
        return {'username':'synthetic_bot'} if method=='getMe' else {'message_id':1}


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.store=t.BotStore(self.root/'bot.sqlite3');self.update_id=0;self.now=NOW
    def tearDown(self):self.store.close();self.temp.cleanup()
    def message(self,text,chat=1,**extra):
        self.update_id+=1;self.now+=1
        update={'update_id':self.update_id,'message':{'chat':{'id':chat,'type':'private'},'from':{'id':chat,'is_bot':False},'text':text,**extra}}
        self.store.handle(update,self.now);return update
    def last(self,chat=1):
        row=self.store.db.execute('SELECT body FROM outbox WHERE chat=? ORDER BY id DESC LIMIT 1',(chat,)).fetchone();return row[0] if row else ''
    def start(self,chat=1):self.message('/start',chat)
    def test_menu_setup(self):
        api=FakeAPI();r=t.configure(api);self.assertEqual(r['commands'],16);methods=[x[0] for x in api.calls];self.assertIn('setMyCommands',methods);self.assertIn('setChatMenuButton',methods);self.assertNotIn('sendMessage',methods)
    def test_names_and_commands_valid(self):
        self.assertTrue(all(cmd.isascii() and len(cmd)<=32 and len(description)<=256 for cmd,description in t.COMMANDS));self.assertLessEqual(len(t.NAME),64)
    def test_start_required(self):
        self.message('/pendientes');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
    def test_start_opt_out_by_default(self):
        self.start();self.assertEqual(self.store.db.execute('SELECT alerts FROM users').fetchone()[0],0)
    def test_group_ignored(self):
        self.store.handle({'update_id':1,'message':{'chat':{'id':-1,'type':'group'},'from':{'id':1},'text':'/start'}},NOW);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
    def test_sender_mismatch_ignored(self):
        self.store.handle({'update_id':1,'message':{'chat':{'id':1,'type':'private'},'from':{'id':2},'text':'/start'}},NOW);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
    def test_own_tasks_only(self):
        self.start(1);self.start(2);self.message('/nuevo PRIVATE_TASK_ONE',1);self.message('/pendientes',2);self.assertNotIn('PRIVATE_TASK_ONE',self.last(2))
    def test_cannot_complete_other_users_task(self):
        self.start(1);self.start(2);self.message('/nuevo Review',1);task_id=self.store.db.execute('SELECT id FROM tasks').fetchone()[0];self.message('/hecho '+str(task_id),2);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
    def test_duplicate_update_no_duplicate_task(self):
        self.start();update=self.message('/nuevo Review');self.store.handle(update,self.now);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
    def test_offset_is_durable(self):
        self.start();self.assertEqual(self.store.offset(),2)
    def test_file_not_downloaded(self):
        self.start();self.message('',document={'file_id':'synthetic-file'});self.assertIn('No descargo',self.last());self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
    def test_obvious_identifier_not_saved_as_task(self):
        self.start();self.message('/nuevo SSN 000-00-0000');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
    def test_interview_does_not_retain_answer(self):
        self.start();self.message('/entrevista b1b2');self.message('UNIQUE_PRIVATE_INTERVIEW_ANSWER');dump='\n'.join(self.store.db.iterdump());self.assertNotIn('UNIQUE_PRIVATE_INTERVIEW_ANSWER',dump)
    def test_interview_next_and_cancel(self):
        self.start();self.message('/entrevista inmigrante');self.message('/siguiente');self.assertIn('omitida',self.last());self.message('/cancelar');self.assertIsNone(self.store.db.execute('SELECT practice FROM users').fetchone()[0])
    def test_no_unrequested_generative_chat(self):
        self.start();self.message('¿Tengo garantizada la aprobación?');self.assertIn('no soy',self.last().lower());self.assertIsNone(self.store.db.execute('SELECT practice FROM users').fetchone()[0])
    def test_reminder_needs_optin_and_zone(self):
        self.start();self.message('/recordar 2026-11-01T09:00:00+00:00 Review');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM reminders').fetchone()[0],0)
    def schedule(self):
        self.start();self.message('/zona UTC');self.message('/avisos activar');self.message('/recordar 2026-11-01T09:00:00+00:00 Review')
    def test_reminder_queued_only_when_due(self):
        self.schedule();self.store.tick(NOW);self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox WHERE kind='reminder'").fetchone()[0],0)
        self.store.tick(NOW+86400);self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM outbox WHERE kind='reminder'").fetchone()[0],1)
    def test_optout_cancels_reminders(self):
        self.schedule();self.message('/avisos desactivar');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM reminders').fetchone()[0],0)
    def test_wrong_timezone_offset_rejected(self):
        self.start();self.message('/zona UTC');self.message('/avisos activar');self.message('/recordar 2026-11-01T09:00:00-04:00 Review');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM reminders').fetchone()[0],0)
    def test_unknown_send_not_retried(self):
        self.start();api=FakeAPI(t.ApiError());self.store.flush_one(api,NOW+100);self.assertEqual(self.store.db.execute("SELECT status FROM outbox").fetchone()[0],'unknown');self.assertFalse(self.store.flush_one(FakeAPI(),NOW+101))
    def test_429_retries_after_wait(self):
        self.start();self.store.flush_one(FakeAPI(t.ApiError(429,30)),NOW+100);self.assertFalse(self.store.flush_one(FakeAPI(),NOW+110));self.assertTrue(self.store.flush_one(FakeAPI(),NOW+131))
    def test_success_reply_removed(self):
        self.start();self.store.flush_one(FakeAPI(),NOW+100);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
    def test_blocked_user_optout(self):
        self.start();self.message('/avisos activar');self.store.flush_one(FakeAPI(t.ApiError(403)),NOW+100);self.assertEqual(self.store.db.execute('SELECT alerts FROM users').fetchone()[0],0)
    def test_delete_user_data(self):
        self.start();self.message('/nuevo Review');self.message('/borrar confirmar');self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
    def test_retention(self):
        self.start();self.message('/nuevo Review');self.store.tick(NOW+91*86400);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
    def test_rate_limit(self):
        self.start()
        for _ in range(20):self.message('/nuevo Review')
        self.assertLessEqual(self.store.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],14)
    def test_new_user_capacity(self):
        self.store.max_users=1;self.start(1);self.start(2);self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
    def test_ds260_not_collecting_credentials(self):
        self.start();self.message('/ds260');self.assertIn('No envíes',self.last());self.assertIn('travel.state.gov',self.last())
    def test_extreme_task_number_is_handled(self):
        self.start();self.message('/hecho '+'9'*100);self.assertIn('Usa /hecho',self.last())
    def test_ledger_binding_is_scoped_and_hides_case_titles(self):
        import coordination as w
        ledger_root=self.root/'team';w.initialize(ledger_root,'owner','2026-10-31T15:00:00Z');ledger=w.Store(ledger_root/'coordination.sqlite3')
        try:
            for operation in [dict(operation='case.create'),dict(operation='member.add',member='prep',role='preparer'),dict(operation='task.create',task_id='OWN_TASK',assignee='prep',summary='PRIVATE_CASE_DETAILS'),dict(operation='task.create',task_id='OTHER_TASK',assignee='owner',summary='OTHER_PRIVATE_DETAILS')]:
                ledger.apply({'actor':'owner','case_id':'C1','expected_revision':ledger.snapshot()[0],**operation},'2026-10-31T15:00:00Z')
            self.start(1);self.start(2);self.store.link(1,ledger_root/'coordination.sqlite3','C1','prep','synthetic-authorization')
            self.message('/pendientes',1);self.assertIn('OWN_TASK',self.last(1));self.assertNotIn('OTHER_TASK',self.last(1));self.assertNotIn('PRIVATE_CASE_DETAILS',self.last(1))
            self.message('/pendientes',2);self.assertNotIn('OWN_TASK',self.last(2))
            ledger.apply({'actor':'owner','case_id':'C1','expected_revision':ledger.snapshot()[0],'operation':'member.remove','member':'prep'},'2026-10-31T15:00:00Z')
            self.message('/pendientes',1);self.assertIn('Vínculo no disponible',self.last(1))
        finally:ledger.close()


class FormTests(unittest.TestCase):
    def setUp(self):self.data=json.loads((S/'assets/ds260-worksheet.json').read_text(encoding='utf-8'))
    def test_blank_ds260(self):self.assertEqual(f.review(self.data)['status'],'review_required')
    def test_no_submission(self):self.assertFalse(f.review(self.data)['submission_authorized'])
    def test_missing_section(self):
        self.data['fields']=[r for r in self.data['fields'] if r['section']!='security_background'];self.assertIn({'field':'security_background','code':'missing_preparation_section'},f.review(self.data)['issues'])
    def test_duplicate_field_rejected(self):
        self.data['fields'].append(self.data['fields'][0])
        with self.assertRaises(ValueError):f.review(self.data)
    def test_ambiguous_date(self):
        row=next(r for r in self.data['fields'] if r['id']=='birth_date');row['value']='12/08/1990';self.assertIn({'field':'birth_date','code':'invalid_or_ambiguous_date'},f.review(self.data)['issues'])
    def test_false_string_not_boolean(self):
        row=self.data['fields'][0];row.update(type='boolean',value='false');self.assertIn({'field':row['id'],'code':'boolean_required'},f.review(self.data)['issues'])
    def test_unsupported_na(self):
        row=self.data['fields'][0];row.update(not_applicable=True,explanation='Unknown');self.assertIn({'field':row['id'],'code':'not_applicable_needs_live_form_permission_and_basis'},f.review(self.data)['issues'])
    def test_findings_omit_private_values(self):
        self.data['fields'][0]['value']='PRIVATE_SENTINEL';self.assertNotIn('PRIVATE_SENTINEL',json.dumps(f.review(self.data)))
    def test_generic_fields(self):
        self.data.update(form_kind='generic',current_form_question_by_question_reviewed=True,fields=[{'id':'name','section':'identity','label':'Name','type':'text','value':'Synthetic Person','required':True,'status':'user_reported','applicant_confirmed':True}]);self.assertEqual(f.review(self.data)['status'],'worksheet_review_complete')
    def test_mapping_rejects_nested(self):
        with self.assertRaises(ValueError):f.mapping_check({'NAME':{'nested':'value'}})


if __name__=='__main__':unittest.main()
