"""OfferUp's documented Ask -> New Message -> Send flow in signed-in Chrome."""
import json
import time
from chrome_bridge import ChromeTab

# OfferUp associates "New message" with its textarea using a <label for=...>.
MESSAGE_FIELDS = """[...document.querySelectorAll('textarea,input')].filter(e=>e.getClientRects().length&&/new message|message/i.test([e.getAttribute('aria-label')||'',e.getAttribute('placeholder')||'',...[...(e.labels||[])].map(l=>l.innerText)].join(' ')))"""

def send(job, update):
    try:
        with ChromeTab() as page:
            page.goto(job['url'])
            result=page.evaluate("""(()=>{const buttons=[...document.querySelectorAll('button,[role=button]')].filter(e=>e.getClientRects().length&&(e.getAttribute('aria-label')||e.innerText).trim()==='Ask');if(buttons.length!==1)return 'missing';buttons[0].click();return 'opened';})()""")
            if result!='opened':return update(job['id'],'needs_review','OfferUp Ask button not found. No message sent.')
            time.sleep(2)
            login=page.evaluate("!![...document.querySelectorAll('input[type=password],input[type=email]')].find(e=>e.getClientRects().length)")
            if login=='true':return update(job['id'],'needs_login','Sign in to OfferUp in Chrome on the Mac mini, then retry this saved batch. No message sent.')
            field=MESSAGE_FIELDS
            filled=page.evaluate("(()=>{const fields="+field+";if(fields.length!==1)return 'missing';const e=fields[0];Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,"+json.dumps(job['text'])+");e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return 'filled';})()")
            if filled!='filled':return update(job['id'],'needs_review','OfferUp did not expose its New Message field. Sign-in or the OfferUp app may be required. No message sent.')
            time.sleep(1)
            control="[...document.querySelectorAll('button,[role=button]')].filter(e=>e.getClientRects().length&&(e.getAttribute('aria-label')||e.innerText).trim()==='Send'&&!e.disabled&&e.getAttribute('aria-disabled')!=='true')"
            if page.evaluate(control+'.length')!='1':return update(job['id'],'needs_review','OfferUp Send button not found. No message sent.')
            update(job['id'],'sending','Sending through OfferUp; checking delivery')
            clicked=page.evaluate('(()=>{const fields='+field+';const b='+control+";if(fields.length!==1||fields[0].value!=="+json.dumps(job['text'])+"||b.length!==1)return 'not_clicked';b[0].click();return 'clicked';})()")
            if clicked=='not_clicked':
                return update(job['id'],'needs_review','OfferUp composer changed before Send. No message sent.')
            if clicked!='clicked':
                return update(job['id'],'delivery_unconfirmed','Send result unknown; check the OfferUp conversation before retrying.')
            time.sleep(3)
            # A toast anywhere on the page does not prove this message arrived.
            update(job['id'],'delivery_unconfirmed','Send clicked; verify the exact message in the OfferUp conversation and record delivery before any retry.')
    except Exception as error:
        from scanner import read
        import message_queue
        current=next((x for x in read(message_queue.PATH,[]) if x['id']==job['id']),{})
        update(job['id'],'delivery_unconfirmed' if current.get('status')=='sending' else 'needs_connection',str(error)[:500])
