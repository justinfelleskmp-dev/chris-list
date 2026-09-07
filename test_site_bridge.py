import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import companion

class SiteBridgeTests(unittest.TestCase):
    def test_only_configured_site_can_read_and_preflight(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(companion,'RUNTIME',Path(tmp)),patch.object(companion,'ROOT',Path(tmp)):
            Path(tmp,'site-bridge.json').write_text(json.dumps({'origin':'https://board.test'}))
            Path(tmp,'scan-results.json').write_text(json.dumps({'listings':[]}))
            server=ThreadingHTTPServer(('127.0.0.1',0),companion.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                url='http://127.0.0.1:'+str(server.server_port)+'/local/feed'
                for method in ('GET','OPTIONS'):
                    request=urllib.request.Request(url,headers={'Origin':'https://board.test'},method=method)
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://board.test')
                        self.assertEqual(response.headers['Access-Control-Allow-Private-Network'],'true')
                    for origin in ('https://evil.test','https://board.test.evil.test'):
                        with self.assertRaises(urllib.error.HTTPError) as error:
                            urllib.request.urlopen(urllib.request.Request(url,headers={'Origin':origin},method=method))
                        self.assertEqual(error.exception.code,403)
                        self.assertIsNone(error.exception.headers.get('Access-Control-Allow-Origin'));error.exception.close()
                Path(tmp,'site-bridge.json').write_text('{bad')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url,headers={'Origin':'https://board.test'}))
                error.exception.close()
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
