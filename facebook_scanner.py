"""Read rendered Marketplace listing cards in a local, persistent browser.
No account credentials leave the Mac. No CAPTCHA or access-check bypass.
"""
import html
import os
from pathlib import Path
import re
import time

PROFILE = Path.home() / 'Library/Application Support/ChrisList/facebook-profile'

def card_html(card):
    """Convert only visible listing fields to the common parser's input."""
    lines = [s.strip() for s in card.get('text', '').splitlines() if s.strip()]
    title = next((s for s in lines if not re.match(r'^(\$|Free$|Just listed$|Ships to you$)', s, re.I)), '')
    if not title: return ''
    e = html.escape
    return '<a href="'+e(card['url'], quote=True)+'" title="'+e(title, quote=True)+'"><img src="'+e(card.get('image',''), quote=True)+'">'+e(' '.join(lines))+'</a>'

def scan(watches):
    from scanner import now, parse_page, relevant, matches_constraints, PLATFORMS
    stamp = now(); rows = []; attempted = 0; errors = []; scope = ''
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
        if os.getenv('GITHUB_ACTIONS'):
            raise RuntimeError('Facebook uses the Mac browser. The GitHub runner has no local Facebook session; run the Mac scanner.')
        PROFILE.mkdir(parents=True, exist_ok=True); PROFILE.chmod(0o700)
        import fcntl
        profile_lock=(PROFILE.parent/'facebook-browser.lock').open('w')
        try: fcntl.flock(profile_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Facebook browser busy; next scheduled scan will retry')
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(str(PROFILE), headless=True, viewport={'width':1200,'height':850})
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                for watch in watches:
                    attempted += 1
                    from urllib.parse import quote
                    url = PLATFORMS['Facebook Marketplace'][0].format(q=quote(watch['query']))
                    try:
                        page.goto(url, wait_until='domcontentloaded', timeout=45000)
                        try: page.locator('a[href*="/marketplace/item/"]').first.wait_for(timeout=15000)
                        except BrowserTimeout: pass
                        text = page.locator('body').inner_text(timeout=10000)
                        if re.search(r'confirm you.re human|temporarily blocked|security check|unusual activity|you.re temporarily blocked', text, re.I) or '/checkpoint' in page.url:
                            raise RuntimeError('Facebook access check; open connect-facebook.command and complete it yourself. Scan stopped.')
                        cards = page.locator('a[href*="/marketplace/item/"]').evaluate_all('''elements => elements.filter(a=>a.getClientRects().length).map(a=>({url:a.href,text:a.innerText,image:a.querySelector('img')?.src||''}))''')
                        if not cards:
                            if re.search(r'no results found|no listings found', text, re.I): continue
                            raise RuntimeError('No visible listing cards. Facebook may require login: open connect-facebook.command on the Mac.')
                        place = re.search(r'Filters\s*\n([^\n]+)', text)
                        if place: scope = place.group(1)
                        for card in cards:
                            for row in parse_page('Facebook Marketplace', url, card_html(card), watch, stamp):
                                if not relevant(row) or not matches_constraints(row,watch): continue
                                lines = [s.strip() for s in card['text'].splitlines() if s.strip()]
                                location = next((s for s in reversed(lines) if re.search(r',\s*[A-Z]{2}$', s)), '')
                                row['location'] = location or 'Location unverified'
                                row['delivery'] = 'Shipping offered' if 'Ships to you' in card['text'] else 'Local listing; confirm pickup' if location else 'Pickup / shipping unverified'
                                row['note'] = 'Observed on Facebook Marketplace. '+ ('Search area displayed by Facebook: '+scope+'. ' if scope else '')+'Seller must confirm condition, included tools, and availability.'
                                rows.append(row)
                        print('Facebook query:', watch['query'], 'visible cards:', len(cards), flush=True)
                        time.sleep(3)
                    except Exception as error:
                        errors.append(str(error)[:400]); break
            finally: browser.close()
    except Exception as error: errors.append(str(error)[:400])
    finally:
        if 'profile_lock' in locals(): profile_lock.close()
    return rows, {'platform':'Facebook Marketplace','checked_at':stamp,'attempted_queries':attempted,
        'total_queries':len(watches),'records':len(rows),'status':'partial' if rows and errors else 'blocked' if errors else 'ok',
        'detail': '; '.join(errors) or 'Rendered browser cards collected (first visible batch per query). Facebook may broaden the requested Anaheim area. '+('Displayed area: '+scope+'.' if scope else '')}

def connect():
    from playwright.sync_api import sync_playwright
    PROFILE.mkdir(parents=True, exist_ok=True); PROFILE.chmod(0o700)
    with sync_playwright() as p:
        browser=p.chromium.launch_persistent_context(str(PROFILE),headless=False)
        page=browser.pages[0] if browser.pages else browser.new_page()
        page.goto('https://www.facebook.com/marketplace/anaheim/',wait_until='domcontentloaded',timeout=45000)
        print('Sign in directly in the browser if needed. Close the browser when finished. Session stays only on this Mac.',flush=True)
        try:
            while browser.pages: page.wait_for_timeout(1000)
        except Exception: pass
        finally: browser.close()

if __name__=='__main__': connect()
