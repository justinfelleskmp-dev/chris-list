"""OfferUp's documented Ask -> New Message -> Send flow in signed-in Chrome."""
import json
import time
from chrome_bridge import ChromeTab

def send(job, update):
    try:
        with ChromeTab() as page:
            page.goto(job['url'])
            result=page.evaluate("""(()=>{const buttons=[...document.querySelectorAll('button,[role=button]')].filter(e=>e.getClientRects().length&&(e.getAttribute('aria-label')||e.innerText).trim()==='Ask');if(buttons.length!==1)return 'missing';buttons[0].click();return 'opened';})()""")
            if result!='opened':return update(job['id'],'needs_review','OfferUp Ask button not found. No message sent.')
            time.sleep(2)
            login=page.evaluate("!![...document.querySelectorAll('input[type=password],input[type=email]')].find(e=>e.getClientRects().length)")
            if login=='true':return update(job['id'],'needs_login','Sign in to OfferUp in Chrome on the Mac mini, then retry this saved batch. No message sent.')
            field="[...document.querySelectorAll('textarea,input')].filter(e=>e.getClientRects().length&&/new message|message/i.test((e.getAttribute('aria-label')||'')+' '+(e.getAttribute('placeholder')||'')))"
            filled=page.evaluate("(()=>{const fields="+field+";if(fields.length!==1)return 'missing';const e=fields[0];Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(job['text'])+");e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return 'filled';})()")
            if filled!='filled':return update(job['id'],'needs_review','OfferUp did not expose its New Message field. Sign-in or the OfferUp app may be required. No message sent.')
            time.sleep(1)
            control="[...document.querySelectorAll('button,[role=button]')].filter(e=>e.getClientRects().length&&(e.getAttribute('aria-label')||e.innerText).trim()==='Send'&&!e.disabled&&e.getAttribute('aria-disabled')!=='true')"
            if page.evaluate(control+'.length')!='1':return update(job['id'],'needs_review','OfferUp Send button not found. No message sent.')
            update(job['id'],'sending','Sending through OfferUp; checking delivery')
            page.evaluate('(()=>{const b='+control+";if(b.length!==1)return 'missing';b[0].click();return 'clicked';})()")
            time.sleep(3)
            confirmed=page.evaluate("/message sent/i.test(document.body.innerText)")=='true'
            update(job['id'],'sent' if confirmed else 'delivery_unconfirmed','OfferUp displayed Message sent' if confirmed else 'Send clicked; check the OfferUp conversation before retrying.')
    except Exception as error:
        from scanner import read
        import message_queue
        current=next((x for x in read(message_queue.PATH,[]) if x['id']==job['id']),{})
        update(job['id'],'delivery_unconfirmed' if current.get('status')=='sending' else 'needs_connection',str(error)[:500])
