"""Explicitly submitted messages only. Never retry a possibly sent message."""
import hashlib
import threading
import time
from scanner import RUNTIME, read, atomic, now
LOCK=threading.Lock()
PATH=RUNTIME/'messages.json'
SUPPORTED={'Facebook Marketplace','OfferUp'}

def preflight(platforms):
    unsupported=sorted(set(platforms)-SUPPORTED)
    if unsupported:return {'ready':False,'detail':'Not sent. Automatic messaging is not connected for '+', '.join(unsupported)+'. Remove those ads from the batch.'}
    from chrome_bridge import check_connection
    try:
        check_connection()
    except Exception as error:
        return {'ready':False,'detail':'Not sent. '+str(error)}
    return {'ready':True,'detail':'Chrome is connected. Each seller message still requires a signed-in platform session; delivery will be checked separately.'}

def enqueue(messages,lookup):
    if not messages or len(messages)>30:raise ValueError('Choose 1–30 ads per batch')
    additions=[]
    for entry in messages:
        row=lookup(entry['id'])
        if row['platform'] not in SUPPORTED:raise ValueError('Not sent: '+row['platform']+' messaging is not connected')
        text=str(entry.get('text','')).strip()
        if not text or len(text)>2000:raise ValueError('Messages must contain 1–2000 characters')
        key=hashlib.sha256((row['url']+'\n'+text).encode()).hexdigest()[:24]
        additions.append({'id':key,'listing_id':row['id'],'url':row['url'],'platform':row['platform'],'title':row['title'],'text':text,'status':'queued','updated_at':now()})
    with LOCK:
        jobs=read(PATH,[]);known={x['id'] for x in jobs}
        for x in additions:
            if x['id'] not in known:jobs.append(x)
            else:
                old=next(j for j in jobs if j['id']==x['id'])
                if old['status'] in ['needs_login','needs_connection','failed','manual_send_required','needs_review']:old.update(status=x['status'],detail='',updated_at=now())
        atomic(PATH,jobs)
    return {'messages':[x for x in jobs if x['id'] in {a['id'] for a in additions}]}
def update(key,status,detail=''):
    with LOCK:
        jobs=read(PATH,[])
        for x in jobs:
            if x['id']==key:x.update(status=status,detail=detail,updated_at=now())
        atomic(PATH,jobs)
def send_facebook(job):
    from chrome_bridge import ChromeTab
    import json
    try:
        with ChromeTab() as page:
            page.goto(job['url'])
            state=json.loads(page.evaluate("JSON.stringify({login:!!document.querySelector('input[type=password]'),url:location.href})"))
            if state['login'] or '/login' in state['url'] or '/checkpoint' in state['url']:
                return update(job['id'],'needs_login','Sign in to Facebook in Chrome, then resubmit this message.')
            filled=page.evaluate("""(()=>{const fields=[...document.querySelectorAll('textarea,input')].filter(e=>e.getClientRects().length&&/send seller a message|message seller/i.test(e.getAttribute('aria-label')||e.getAttribute('placeholder')||''));if(fields.length!==1)return 'missing';const field=fields[0];Object.getOwnPropertyDescriptor(field.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(field,"""+json.dumps(job['text'])+""");field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));return 'filled';})()""")
            if filled!='filled':return update(job['id'],'manual_send_required','Facebook seller-message field was not identified. No message sent.')
            time.sleep(1)
            # Only an unambiguous visible Send control can be clicked.
            control="[...document.querySelectorAll('[role=button],button')].filter(e=>e.getClientRects().length&&(e.getAttribute('aria-label')||e.innerText).trim()==='Send'&&e.getAttribute('aria-disabled')!=='true'&&!e.disabled)"
            if page.evaluate(control+'.length')!='1':return update(job['id'],'manual_send_required','Facebook Send button was not identified. No message sent.')
            update(job['id'],'sending','Do not resubmit while delivery is checked')
            page.evaluate('(()=>{const buttons='+control+";if(buttons.length===1){buttons[0].click();return 'clicked';}return 'missing';})()")
            time.sleep(3)
            confirmed=page.evaluate("/message sent/i.test(document.body.innerText)")
            update(job['id'],'sent' if confirmed=='true' else 'delivery_unconfirmed','Facebook displayed Message sent' if confirmed=='true' else 'Send clicked; check Facebook before any retry')
    except Exception as error:
        current=next((x for x in read(PATH,[]) if x['id']==job['id']),{})
        update(job['id'],'delivery_unconfirmed' if current.get('status')=='sending' else 'needs_connection',str(error)[:500])

def worker():
    # An interrupted send is never silently replayed after a restart.
    for x in read(PATH,[]):
        if x['status']=='sending':update(x['id'],'delivery_unconfirmed','Interrupted send; verify in Facebook')
    while True:
        for job in read(PATH,[]):
            if job['status']=='queued':
                if job['platform']=='OfferUp':
                    from offerup_sender import send
                    send(job,update)
                else:send_facebook(job)
                time.sleep(5)
        time.sleep(15)
