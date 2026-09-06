"""Real process contention and persisted failure tests; never contact sellers."""
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import message_queue as q
from test_listing_review import approved_message

ROW=dict(id='case',url='https://offerup.com/item/detail/case',platform='OfferUp',title='Case')

def enqueue_child(path, text):
    q.PATH=Path(path)
    q.enqueue([approved_message(ROW,text)],lambda _:ROW)

def worker_child(path, entered, release):
    q.PATH=Path(path)
    def fake_send(job, update):
        update(job['id'],'sending')
        entered.set()
        if not release.wait(10):raise RuntimeError('Test timed out')
        update(job['id'],'sent','Test receipt')
    with patch('offerup_sender.send',side_effect=fake_send),patch('message_queue.time.sleep'):
        q.process_pending()

class QueueReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p=patch.object(q,'PATH',Path(self.temp.name)/'messages.json')
        p.start();self.addCleanup(p.stop)

    def enqueue(self):
        return q.enqueue([approved_message(ROW,'Hello')],lambda _:ROW)['messages'][0]

    def test_duplicate_entries_in_one_batch_create_one_job(self):
        entry=approved_message(ROW,'Hello')
        self.assertEqual(len(q.enqueue([entry,entry],lambda _:ROW)['messages']),1)
        self.assertEqual(len(q.load_jobs()),1)

    def test_concurrent_process_enqueue_preserves_all_jobs(self):
        ctx=multiprocessing.get_context('spawn')
        children=[ctx.Process(target=enqueue_child,args=(str(q.PATH),'Hello '+str(i))) for i in range(6)]
        for child in children:child.start()
        for child in children:
            child.join(15)
            if child.is_alive():child.terminate();child.join()
            self.assertEqual(child.exitcode,0)
        self.assertEqual(len(q.load_jobs()),6)

    def test_second_worker_cannot_send_or_recover_live_send(self):
        job=self.enqueue()
        ctx=multiprocessing.get_context('spawn')
        entered,release=ctx.Event(),ctx.Event()
        child=ctx.Process(target=worker_child,args=(str(q.PATH),entered,release))
        child.start()
        try:
            self.assertTrue(entered.wait(10))
            with patch('offerup_sender.send') as send:
                self.assertFalse(q.process_pending())
                send.assert_not_called()
            self.assertEqual(q.load_jobs()[0]['status'],'sending')
        finally:
            release.set();child.join(15)
            if child.is_alive():child.terminate();child.join()
        self.assertEqual(child.exitcode,0)
        self.assertEqual(q.load_jobs()[0]['status'],'sent')
        with patch('offerup_sender.send') as send:
            q.process_pending();send.assert_not_called()

    def test_interrupted_send_is_held_without_replay(self):
        job=self.enqueue();q.update(job['id'],'sending')
        with patch('offerup_sender.send') as send:
            q.process_pending();send.assert_not_called()
        self.assertEqual(q.load_jobs()[0]['status'],'delivery_unconfirmed')

    def test_corruption_is_reported_and_never_overwritten(self):
        for raw in ['{broken','{}','[{"id":"missing fields"}]']:
            q.PATH.write_text(raw)
            with self.assertRaises(q.QueueError):self.enqueue()
            with self.assertRaises(q.QueueError):q.process_pending()
            self.assertEqual(q.PATH.read_text(),raw)
            self.assertFalse(q.snapshot()['message_queue']['ready'])

    def reconciliation(self,job,**changes):
        data=dict(id=job['id'],url=job['url'],text=job['text'],outcome='sent',confirmed=True,
                  reviewer='Test operator',evidence='Exact outgoing text and Delivered indicator at 16:27')
        data.update(changes)
        return q.reconcile(data)

    def test_reconciliation_requires_exact_message_and_evidence(self):
        job=self.enqueue();q.update(job['id'],'delivery_unconfirmed')
        for changes in ({'text':'Different text'},{'url':'https://example.com/other'},
                        {'confirmed':False},{'evidence':''},{'reviewer':''},{'outcome':'unknown'}):
            with self.assertRaises(ValueError):self.reconciliation(job,**changes)
            self.assertEqual(q.load_jobs()[0]['status'],'delivery_unconfirmed')
        self.reconciliation(job)
        saved=q.load_jobs()[0]
        self.assertEqual(saved['status'],'sent')
        self.assertEqual(saved['delivery_reviews'][0]['text'],job['text'])
        self.assertEqual(self.enqueue()['status'],'sent')

    def test_verified_failure_requires_new_approval(self):
        job=self.enqueue();q.update(job['id'],'delivery_unconfirmed')
        self.reconciliation(job,outcome='not_sent',evidence='Platform explicitly rejected send before delivery')
        saved=q.load_jobs()[0]
        self.assertEqual(saved['status'],'needs_review')
        with self.assertRaises(ValueError):q.validate_job_review(saved)
        with patch('offerup_sender.send') as send:
            q.process_pending();send.assert_not_called()
        self.assertEqual(self.enqueue()['status'],'queued')
        self.assertEqual(len(q.load_jobs()[0]['delivery_reviews']),1)

    def test_facebook_click_failures_are_not_reported_as_sent(self):
        from unittest.mock import MagicMock
        for result,status in [('not_clicked','needs_review'),('unknown','delivery_unconfirmed'),('clicked','delivery_unconfirmed')]:
            job=self.enqueue()
            q.update(job['id'],'queued')
            page=MagicMock()
            page.evaluate.side_effect=['{"login":false,"url":"https://www.facebook.com/marketplace/item/test"}','filled','1',result]
            with patch('chrome_bridge.ChromeTab') as tab,patch('message_queue.time.sleep'):
                tab.return_value.__enter__.return_value=page
                q.send_facebook(job)
            self.assertEqual(q.load_jobs()[0]['status'],status)
            script=page.evaluate.call_args.args[0]
            self.assertIn('fields[0].value!==',script)

    def test_staff_request_provenance_cannot_move_to_another_listing(self):
        import json
        event='a'*24
        folder=q.PATH.parent/'staff-requests';folder.mkdir()
        record=dict(event_id=event,status='needs_approval',listing_id=ROW['id'],listing_url=ROW['url'],listing_title=ROW['title'],exact_staff_text='Offer $40 for this listing',send_authorized=False)
        (folder/f'{event}.json').write_text(json.dumps(record))
        entry=approved_message(ROW,'Would you accept $40?');entry['staff_event']=event
        job=q.enqueue([entry],lambda _:ROW)['messages'][0]
        self.assertEqual(job['review']['staff_request'],record)
        q.validate_job_review(job)
        record['listing_id']='different'
        (folder/f'{event}.json').write_text(json.dumps(record))
        with self.assertRaises(ValueError):q.enqueue([entry],lambda _:ROW)
        with self.assertRaises(ValueError):q.validate_job_review(job)

if __name__=='__main__':unittest.main()
