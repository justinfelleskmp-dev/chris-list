"""Read-only receipt checks based on the observed OfferUp conversation DOM."""
import json
import re
import time
from urllib.parse import urlsplit
from scanner import now

# Observed September 6, 2026: Content-Text and Status share the indexed
# MessagingChatPageMessagingChatMessage container. Global toasts are excluded.
SNAPSHOT = r'''JSON.stringify((()=>{
 const rows=[...document.querySelectorAll('[data-testid]')].filter(e=>/^MessagingChatPageMessagingChatMessage\d+$/.test(e.getAttribute('data-testid'))&&e.getClientRects().length);
 return {url:location.href,messages:rows.map(e=>({
  text:e.querySelector('[data-testid$=".Content-Text"]')?.textContent||'',
  status:e.querySelector('[data-testid$=".Status"]')?.textContent||'',
  time:e.querySelector('[data-testid$=".Date"]')?.textContent||''
 }))};
})())'''

def item_url(value):
    url=urlsplit(value)
    if url.scheme!='https' or url.netloc!='offerup.com' or not re.fullmatch(r'/item/detail/[a-zA-Z0-9-]+/?',url.path):
        return None
    return 'https://offerup.com'+url.path.rstrip('/')

def check(page,job):
    """Require the exact delivered bubble and canonical listing, or return None.

    This establishes that the approved text was delivered in this conversation;
    it does not assert when the seller read it or that a seller replied.
    """
    snapshot=json.loads(page.evaluate(SNAPSHOT))
    url=urlsplit(snapshot.get('url',''))
    if url.scheme!='https' or url.netloc!='offerup.com' or not re.fullmatch(r'/inbox/message/\d+/?',url.path):return None
    matches=[r for r in snapshot.get('messages',[]) if r.get('text')==job['text'] and r.get('status','').strip() in ('Delivered','Read')]
    if len(matches)!=1:return None
    clicked=page.evaluate("""(()=>{const buttons=[...document.querySelectorAll('[data-testid="MessagingChatPageItemDetailSeeItemDetails"]')].filter(e=>e.getClientRects().length);if(buttons.length!==1)return 'missing';buttons[0].click();return 'opened';})()""")
    if clicked!='opened':return None
    canonical=None
    for _ in range(5):
        time.sleep(1)
        destination=json.loads(page.evaluate("JSON.stringify({url:location.href,canonical:document.querySelector('link[rel=canonical]')?.href||''})"))
        canonical=destination.get('canonical','') if item_url(destination.get('url','')) else None
        if canonical and item_url(canonical):break
    expected=item_url(job['url'])
    if not expected or item_url(canonical)!=expected:return None
    return dict(platform='OfferUp',conversation_url=snapshot['url'],listing_url=expected,
                exact_text=job['text'],status=matches[0]['status'].strip(),displayed_time=matches[0].get('time',''),
                checked_at=now(),source='Exact conversation bubble and item-details canonical URL')
