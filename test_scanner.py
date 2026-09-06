import unittest
from scanner import parse_page, merge, relevant

class ScannerTests(unittest.TestCase):
 def test_recommendations_rejected(self):
  self.assertFalse(relevant({'matched_query':'vinyl cutter','title':'Vinyl record album'}))
  self.assertFalse(relevant({'matched_query':'kiosk','title':'Coca-Cola dinnerware'}))
  self.assertTrue(relevant({'matched_query':'display case','title':'Glass display cases $100'}))
 def test_craigslist_structured_record_and_new_url(self):
  page='''<script type="application/ld+json">{"@type":"Product","name":"Display case","image":["https://example.com/photo.jpg"],"offers":{"price":"40","availableAtOrFrom":{"address":{"addressLocality":"Anaheim"}}}}</script><li class="cl-static-search-result" title="Display case"><a href="https://www.craigslist.org/view/d/anaheim-case/xyz">Display case $40</a></li>'''
  rows=parse_page('Craigslist','https://orangecounty.craigslist.org/search/sss',page,{'id':'a','query':'display case'},'2026-09-05')
  self.assertEqual(len(rows),1);self.assertEqual(rows[0]['price'],'$40');self.assertEqual(rows[0]['location'],'Anaheim');self.assertTrue(rows[0]['image'])
  first,new=merge([],rows);self.assertEqual(len(new),1)
  _,again=merge(first,rows);self.assertEqual(again,[])
 def test_login_is_not_listing(self):
  self.assertEqual(parse_page('Facebook Marketplace','https://facebook.com','<a href="/login">Sign in</a>',{'id':'a','query':'case'},'today'),[])
 def test_sold_and_unrelated_links_excluded(self):
  body='<a title="Display case" href="/item/detail/1">SOLD $50</a><a href="/login">login</a>'
  self.assertEqual(parse_page('OfferUp','https://offerup.com',body,{'id':'a','query':'case'},'today'),[])
 def test_priority_dedupe(self):
  a={'id':'a','last_seen':'today','priority':'primary','watch_ids':['primary']}
  b={'id':'a','last_seen':'later','priority':'secondary','watch_ids':['donor']}
  rows,new=merge([a],[b]);self.assertEqual(rows[0]['priority'],'primary');self.assertEqual(new,[])

class ScanFailureTests(unittest.TestCase):
 def test_source_crash_does_not_abort_alert_processing(self):
  import json, tempfile, sys
  from pathlib import Path
  from unittest.mock import patch
  import scanner
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'scanner-config.json').write_text(json.dumps({'watches':[{'query':'case'}]}))
   with patch.object(scanner,'ROOT',root),patch.object(scanner,'RUNTIME',root/'.scanner'),patch.object(scanner,'FEED',root/'scan-results.json'),patch.object(sys,'argv',['scanner.py']),patch.object(scanner,'fetch',return_value='[]'),patch.object(scanner,'scan_source',side_effect=RuntimeError('source crashed')),patch.object(scanner,'notify',return_value='queued') as notify,patch('builtins.print'):
    scanner.main()
   result=json.loads((root/'scan-results.json').read_text())
   self.assertEqual(len(result['platforms']),10)
   self.assertTrue(all(x['status']=='blocked' for x in result['platforms']))
   notify.assert_called_once()

if __name__=='__main__':unittest.main()
