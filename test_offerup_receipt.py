import json
import unittest
from unittest.mock import MagicMock,patch
from offerup_receipt import check

JOB={'url':'https://offerup.com/item/detail/example-id','text':'Exact approved text'}

class ReceiptTests(unittest.TestCase):
    def run_check(self,**changes):
        data={'url':'https://offerup.com/inbox/message/123','messages':[{'text':JOB['text'],'status':'Delivered','time':'04:27 PM'}]}
        canonical=changes.pop('canonical',JOB['url']);data.update(changes)
        page=MagicMock();page.evaluate.side_effect=[json.dumps(data),'opened',json.dumps({'url':'https://offerup.com/item/detail/456','canonical':canonical})]
        with patch('offerup_receipt.time.sleep'):return check(page,JOB)

    def test_matching_bubble_and_canonical_listing_keep_evidence(self):
        receipt=self.run_check()
        self.assertEqual(receipt['listing_url'],JOB['url'])
        self.assertEqual(receipt['exact_text'],JOB['text'])
        self.assertEqual(receipt['conversation_url'],'https://offerup.com/inbox/message/123')

    def test_different_listing_cannot_confirm(self):
        self.assertIsNone(self.run_check(canonical='https://offerup.com/item/detail/other'))

    def test_stale_toast_changed_text_pending_and_duplicate_bubbles_fail(self):
        for messages in ([],[{'text':'Wrong message','status':'Delivered'}],
                         [{'text':JOB['text'],'status':'Sending'}],
                         [{'text':JOB['text'],'status':'Delivered'}]*2):
            self.assertIsNone(self.run_check(messages=messages))

    def test_listing_page_and_lookalike_hosts_cannot_confirm(self):
        for url in (JOB['url'],'https://offerup.com.evil.test/inbox/message/123','http://offerup.com/inbox/message/123'):
            self.assertIsNone(self.run_check(url=url))

    def test_stale_canonical_before_navigation_cannot_confirm(self):
        page=MagicMock()
        snapshot={'url':'https://offerup.com/inbox/message/123','messages':[{'text':JOB['text'],'status':'Delivered'}]}
        stale=json.dumps({'url':snapshot['url'],'canonical':JOB['url']})
        page.evaluate.side_effect=[json.dumps(snapshot),'opened']+[stale]*5
        with patch('offerup_receipt.time.sleep'):self.assertIsNone(check(page,JOB))

if __name__=='__main__':unittest.main()
