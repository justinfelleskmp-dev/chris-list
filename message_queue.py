"""Explicitly submitted messages only. Never retry a possibly sent message."""
import hashlib
import threading
import time
import json
import os
import fcntl
from contextlib import contextmanager
from scanner import RUNTIME, read, now
from listing_review import approve
LOCK=threading.Lock()
PATH=RUNTIME/'messages.json'
SUPPORTED={'Facebook Marketplace','OfferUp'}

class QueueError(ValueError):
    pass

def atomic(path, jobs):
    # Flush the send marker before any external click, including the rename.
    temporary=path.with_suffix('.json.tmp')
    with temporary.open('w') as handle:
        json.dump(jobs,handle,ensure_ascii=False,indent=2)
        handle.write('\n');handle.flush();os.fsync(handle.fileno())
    temporary.replace(path)
    directory=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(directory)
    finally:os.close(directory)

@contextmanager
def file_lock(kind, blocking=True):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.with_suffix('.'+kind+'.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:yield True
        finally:fcntl.flock(handle, fcntl.LOCK_UN)

@contextmanager
def queue_lock():
    with LOCK, file_lock('state'):
        yield

def load_jobs():
    # Never turn malformed persisted state into an empty queue (and resend).
    try:
        jobs=read(PATH, [])
        required=('id','listing_id','url','platform','title','text','status')
        if not isinstance(jobs,list) or any(not isinstance(j,dict) or any(not isinstance(j.get(k),str) or not j[k] for k in required) for j in jobs):
            raise ValueError('invalid message records')
        if len({j['id'] for j in jobs})!=len(jobs):raise ValueError('duplicate message IDs')
        return jobs
    except (ValueError, OSError) as error:
        raise QueueError('Seller queue needs repair; sending paused and original data preserved: '+str(error)) from error

def snapshot():
    try:return {'messages':load_jobs(),'message_queue':{'ready':True}}
    except QueueError as error:return {'messages':[],'message_queue':{'ready':False,'detail':str(error)}}

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
        review=approve(entry,row)
        review.update(confirmed=True,approved_at=now(),approved_text=text,listing_id=row['id'],listing_url=row['url'])
        key=hashlib.sha256((row['url']+'\n'+text).encode()).hexdigest()[:24]
        additions.append({'id':key,'listing_id':row['id'],'url':row['url'],'platform':row['platform'],'title':row['title'],'text':text,'review':review,'status':'queued','updated_at':now()})
    with queue_lock():
        jobs=load_jobs();known={x['id'] for x in jobs}
        for x in additions:
            if x['id'] not in known:
                jobs.append(x);known.add(x['id'])
            else:
                old=next(j for j in jobs if j['id']==x['id'])
                if old['status'] in ['needs_login','needs_connection','failed','manual_send_required','needs_review']:old.update(status=x['status'],detail='',review=x['review'],updated_at=now())
        atomic(PATH,jobs)
    return {'messages':[x for x in jobs if x['id'] in {a['id'] for a in additions}]}
def update(key,status,detail='',receipt=None):
    with queue_lock():
        jobs=load_jobs()
        for x in jobs:
            if x['id']==key:
                x.update(status=status,detail=detail,updated_at=now())
                if receipt is not None:x['receipt']=receipt
        atomic(PATH,jobs)

def reconcile(data):
    if data.get('outcome') not in ('sent','not_sent') or data.get('confirmed') is not True:
        raise ValueError('Choose a verified delivery outcome and confirm the exact conversation')
    for field in ('reviewer','evidence'):
        if not isinstance(data.get(field),str) or not data[field].strip():
            raise ValueError('Record who checked the conversation and the delivery evidence')
    with file_lock('worker',blocking=False) as acquired:
        if not acquired:raise ValueError('A sender is active; wait until delivery checking finishes')
        with queue_lock():
            jobs=load_jobs()
            job=next((j for j in jobs if j['id']==data.get('id')),None)
            if not job or job['status']!='delivery_unconfirmed':raise ValueError('Only uncertain deliveries can be reconciled')
            if data.get('url')!=job['url'] or data.get('text')!=job['text']:
                raise ValueError('The reviewed listing or exact message changed')
            record={key:data[key].strip() for key in ('reviewer','evidence','outcome')}
            record.update(checked_at=now(),url=job['url'],text=job['text'])
            job.setdefault('delivery_reviews',[]).append(record)
            job.update(status='sent' if data['outcome']=='sent' else 'needs_review',
                       detail='Conversation checked by '+record['reviewer']+': '+record['evidence'],updated_at=now())
            if data['outcome']=='not_sent':job.pop('review',None)
            atomic(PATH,jobs)
            return {'message':job}
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
            clicked=page.evaluate('(()=>{const fields=[...document.querySelectorAll("textarea,input")].filter(e=>e.getClientRects().length&&/send seller a message|message seller/i.test(e.getAttribute("aria-label")||e.getAttribute("placeholder")||""));const buttons='+control+";if(fields.length!==1||fields[0].value!=="+json.dumps(job['text'])+"||buttons.length!==1)return 'not_clicked';buttons[0].click();return 'clicked';})()")
            if clicked=='not_clicked':return update(job['id'],'needs_review','Facebook composer changed before Send. No message sent.')
            if clicked!='clicked':return update(job['id'],'delivery_unconfirmed','Send result unknown; check the Facebook conversation before retrying.')
            time.sleep(3)
            # A page-wide toast is not a receipt tied to this seller and text.
            update(job['id'],'delivery_unconfirmed','Send clicked; verify the exact message in the Facebook conversation and record delivery before any retry')
    except Exception as error:
        current=next((x for x in read(PATH,[]) if x['id']==job['id']),{})
        update(job['id'],'delivery_unconfirmed' if current.get('status')=='sending' else 'needs_connection',str(error)[:500])

def validate_job_review(job):
    review=job.get('review',{})
    if not review.get('approved_at') or review.get('approved_text')!=job.get('text') or review.get('listing_url')!=job.get('url') or review.get('listing_id')!=job.get('listing_id'):
        raise ValueError('Missing or changed approval; review this listing and exact message again')
    approve({'review':review,'url':job['url'],'title':job['title']},job)

def process_pending():
    # Holding the OS lock across the entire send prevents a second process
    # from claiming or recovering a job while its first worker is still live.
    with file_lock('worker', blocking=False) as acquired:
        if not acquired:return False
        for job in load_jobs():
            if job['status']=='sending':
                update(job['id'],'delivery_unconfirmed','Interrupted send; verify in the seller conversation before any retry')
        for job in load_jobs():
            if job['status']=='queued':
                try:validate_job_review(job)
                except ValueError as error:
                    update(job['id'],'needs_review',str(error));continue
                if job['platform']=='OfferUp':
                    from offerup_sender import send
                    send(job,update)
                else:send_facebook(job)
                time.sleep(5)
        return True

def worker():
    while True:
        try:process_pending()
        except Exception as error:
            # A bad record or storage failure must not silently kill the worker.
            print('Seller messaging paused: '+str(error),flush=True)
        time.sleep(15)
