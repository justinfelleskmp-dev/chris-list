import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from machine_rules import classify
from scanner import matches_constraints,merge
from facebook_scanner import card_html
from scanner import parse_page
import message_queue
class FeatureTests(unittest.TestCase):
 def test_single_and_unknown_tool_machines_hidden(self):
  for title in ['Roland CAMM-1','Graphtec CE6000-60','Vinyl cutter','Silhouette Cameo 4','Cricut Joy','Cameo 5 Plus','Cameo 5α','Cameo 30','Replacement blade for Cameo 3']:
   self.assertFalse(classify({'title':title})['eligible'],title)
 def test_verified_holders_with_roll_caveat(self):
  for title in ['Silhouette Cameo 3 w/accessories','Cameo 5','Cricut Explore Air 2']:
   result=classify({'title':title});self.assertTrue(result['eligible']);self.assertIn('500',result['model']['roll'])
  self.assertTrue(classify({'title':'Glass display case'})['eligible'])
 def test_constraints(self):
  row={'title':'glass display case','note':'working','price':'$150'}
  self.assertTrue(matches_constraints(row,{'include':['glass'],'price_max':200}))
  self.assertFalse(matches_constraints(row,{'exclude':['glass']}))
  self.assertFalse(matches_constraints(row,{'price_max':100}))
 def test_facebook_card(self):
  body=card_html({'url':'https://www.facebook.com/marketplace/item/123','text':'$60\nSilhouette Cameo 3\nTorrance, CA','image':'https://example.com/p.jpg'})
  rows=parse_page('Facebook Marketplace','https://www.facebook.com',body,{'id':'a','query':'Cameo 3'},'today')
  self.assertEqual(rows[0]['title'],'Silhouette Cameo 3');self.assertEqual(rows[0]['price'],'$60')
 def test_no_automatic_duplicate_sends(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(message_queue,'PATH',Path(directory)/'messages.json'):
   lookup=lambda _: {'id':'a','title':'Cameo 3','url':'https://www.facebook.com/marketplace/item/123','platform':'Facebook Marketplace'}
   payload=[{'id':'a','text':'Hello, is this available?'}]
   first=message_queue.enqueue(payload,lookup)['messages'][0]
   message_queue.update(first['id'],'sent')
   again=message_queue.enqueue(payload,lookup)['messages'];self.assertEqual(len(again),1);self.assertEqual(again[0]['status'],'sent')
 def test_old_incompatible_feed_removed(self):
  rows,_=merge([{'id':'a','title':'Roland CAMM-1'}],[]);self.assertEqual(rows,[])
if __name__=='__main__':unittest.main()

class SendRepairTests(unittest.TestCase):
 def test_chrome_block_preflight(self):
  with patch('chrome_bridge.apple',side_effect=RuntimeError('disabled')):
   check=message_queue.preflight(['OfferUp']);self.assertFalse(check['ready']);self.assertIn('Not sent',check['detail'])
 def test_unsupported_platform_preflight(self):
  check=message_queue.preflight(['Mercari']);self.assertFalse(check['ready']);self.assertIn('Mercari',check['detail'])
 def test_offerup_old_blocked_job_can_be_resubmitted_without_duplicates(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(message_queue,'PATH',Path(directory)/'messages.json'):
   lookup=lambda _: {'id':'a','title':'Display case','url':'https://offerup.com/item/detail/abc','platform':'OfferUp'}
   payload=[{'id':'a','text':'Would you consider $50?'}]
   job=message_queue.enqueue(payload,lookup)['messages'][0];self.assertEqual(job['status'],'queued')
   message_queue.update(job['id'],'manual_send_required')
   result=message_queue.enqueue(payload,lookup)['messages'];self.assertEqual(len(result),1);self.assertEqual(result[0]['status'],'queued')
   message_queue.update(job['id'],'delivery_unconfirmed')
   self.assertEqual(message_queue.enqueue(payload,lookup)['messages'][0]['status'],'delivery_unconfirmed')
 def test_unsupported_batch_not_silently_queued(self):
  lookup=lambda _: {'id':'a','title':'Case','url':'https://mercari.com/us/item/a','platform':'Mercari'}
  with self.assertRaisesRegex(ValueError,'Not sent'):
   message_queue.enqueue([{'id':'a','text':'Hello'}],lookup)
