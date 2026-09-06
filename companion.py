#!/usr/bin/env python3
"""Local Chris List services. Local Ollama only; no cloud LLM endpoints."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import urllib.request as ur
import urllib.parse as up
import uuid
from scanner import ROOT, RUNTIME, read, atomic, now
from machine_rules import eligible

MUTEX=threading.Lock()
STATIC={'index.html','app.js','offline.js','fixes.js','scan-ui.js','machine-rules.js','donors.js','style.css','sections.css','sw.js','workspace-ui.js','scan-results.json'}
SYSTEM='''You help Chris clarify secondhand-item searches. Run a conversation until the user is satisfied; ask one or two useful questions per turn, preserve every stated constraint, and never invent machine capabilities or say a scan/message happened. Return JSON {"reply": "short reply and question", "spec": {"query": "short marketplace keywords", "description": "complete requirements", "include": [], "exclude": [], "price_max": null, "priority": "primary"}}. Include/exclude are literal title/description filters ONLY when explicitly requested. price_max only if user wants to HIDE higher asking prices (offers are not asking-price limits). Technical constraints such as pen + cutter, dimensions, roll feeding require evidence; preserve them in description, never certify them. Query must be a few search keywords rather than the entire requirement. The user reviews and edits the spec before saving. Do not suggest single-tool plotters for drawing and cutting without a manual swap.'''

def assistant(messages):
    history=[{'role':x['role'],'content':str(x['content'])[:6000]} for x in messages[-20:] if x.get('role') in ['user','assistant']]
    data={'model':'qwen3.5:latest','messages':[{'role':'system','content':SYSTEM}]+history,'stream':False,'think':False,'format':'json','options':{'temperature':0.2,'num_predict':700,'num_ctx':8192},'keep_alive':'10m'}
    request=ur.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with ur.urlopen(request,timeout=180) as response: result=json.load(response)
    value=json.loads(result['message']['content'])
    if not isinstance(value.get('reply'),str) or not isinstance(value.get('spec'),dict): raise ValueError('Local model returned an invalid draft; please try again.')
    return value

def save_watch(spec):
    query=str(spec.get('query','')).strip()[:150]
    if not query: raise ValueError('Search keywords required')
    watch={'id':'local-'+uuid.uuid4().hex[:12],'query':query,'description':str(spec.get('description',''))[:6000],
           'priority':'secondary' if spec.get('priority')=='secondary' else 'primary',
           'include':[str(x)[:100] for x in spec.get('include',[])][:20], 'exclude':[str(x)[:100] for x in spec.get('exclude',[])][:20]}
    if spec.get('price_max') is not None:
        price=float(spec['price_max'])
        if price<0 or price>1e9: raise ValueError('Invalid maximum price')
        watch['price_max']=price
    with MUTEX:
        watches=read(RUNTIME/'watches.json',[]);watches.append(watch);atomic(RUNTIME/'watches.json',watches)
    return watch

def listing(key):
    row=next((x for x in read(ROOT/'scan-results.json',{}).get('listings',[]) if x['id']==key),None)
    if not row or not eligible(row): raise ValueError('Listing is unavailable or fails the machine requirements')
    return row

class Handler(BaseHTTPRequestHandler):
    def respond(self,value,status=200):
        body=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def trusted(self):
        host=self.headers.get('Host','').split(':')[0].lower()
        allowed={'localhost','127.0.0.1','192.168.68.68','100.79.212.46','kms-mac-mini.local','kms-mac-mini-1.tail016811.ts.net'}
        origin=self.headers.get('Origin')
        return host in allowed and (not origin or up.urlparse(origin).netloc==self.headers.get('Host'))
    def do_GET(self):
        if not self.trusted(): return self.respond({'error':'Unrecognized host or origin'},403)
        path=up.urlparse(self.path).path
        if path=='/local/status':return self.respond({'local':True,'model':'qwen3.5:latest','watches':read(RUNTIME/'watches.json',[]),'messages':read(RUNTIME/'messages.json',[])})
        if path=='/local/photos':
            try:
                row=listing(up.parse_qs(up.urlparse(self.path).query).get('id',[''])[0])
                from listing_photos import collect
                return self.respond(collect(row))
            except Exception as e:return self.respond({'error':str(e)},400)
        name=path.lstrip('/') or 'index.html'
        if name not in STATIC:return self.respond({'error':'Not found'},404)
        import mimetypes
        try:body=(ROOT/name).read_bytes()
        except FileNotFoundError:return self.respond({'error':'Not found'},404)
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-cache');self.end_headers();self.wfile.write(body)
    def do_POST(self):
        if not self.trusted() or self.headers.get('X-Chris-List')!='local':return self.respond({'error':'Same-origin app request required'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=100000:raise ValueError('Request is empty or too large')
            data=json.loads(self.rfile.read(length))
            if self.path=='/local/assistant':result=assistant(data.get('messages',[]))
            elif self.path=='/local/watch':result=save_watch(data)
            elif self.path=='/local/scan':
                subprocess.Popen(['/opt/homebrew/bin/python3',str(ROOT/'scanner.py'),'--publish'],cwd=ROOT,stdout=(RUNTIME/'manual-scan.log').open('a'),stderr=subprocess.STDOUT)
                result={'status':'Scan requested; results update when the Mac finishes. An already-running scan is kept.'}
            elif self.path=='/local/messages':
                from message_queue import enqueue
                result=enqueue(data.get('messages',[]),listing)
            else:return self.respond({'error':'Not found'},404)
            self.respond(result)
        except Exception as e:self.respond({'error':str(e)},400)
    def log_message(self,*args):pass

if __name__=='__main__':
    RUNTIME.mkdir(exist_ok=True)
    from message_queue import worker
    threading.Thread(target=worker,daemon=True).start()
    print('Chris List local app: http://127.0.0.1:8766 — also available through the Mac LAN/Tailscale address',flush=True)
    ThreadingHTTPServer(('0.0.0.0',8766),Handler).serve_forever()
