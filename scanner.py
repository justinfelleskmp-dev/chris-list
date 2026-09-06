#!/usr/bin/env python3
"""Token-free public marketplace scanner; Python standard library only.

Run: python3 scanner.py [--publish]. Configuration: scanner-config.json.
No login/session extraction, CAPTCHA bypass, model, or paid API.
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.parse as up
import urllib.request as ur

from machine_rules import eligible, annotate

ROOT = Path(__file__).resolve().parent
FEED = ROOT / 'scan-results.json'
RUNTIME = ROOT / '.scanner'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path, fallback):
    return json.loads(path.read_text()) if path.exists() else fallback


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


PLATFORMS = {
 'Craigslist': ('https://orangecounty.craigslist.org/search/sss?query={q}', r'craigslist\.org/(?:view/d/|.*/\d+\.html)'),
 'OfferUp': ('https://offerup.com/search?q={q}', r'offerup\.com/item/detail/'),
 'Facebook Marketplace': ('https://www.facebook.com/marketplace/anaheim/search?query={q}', r'facebook\.com/marketplace/item/'),
 'Nextdoor': ('https://nextdoor.com/for_sale_and_free/?query={q}', r'nextdoor\.com/(?:for_sale_and_free|p)/[^/?]+'),
 '5miles': ('https://www.5miles.com/search?keyword={q}', r'5miles\.com/item/'),
 'VarageSale': ('https://www.varagesale.com/search?q={q}', r'varagesale\.com/i/'),
 'Mercari': ('https://www.mercari.com/search/?keyword={q}', r'mercari\.com/us/item/'),
 'Poshmark': ('https://poshmark.com/search?query={q}', r'poshmark\.com/listing/'),
 'Depop': ('https://www.depop.com/search/?q={q}', r'depop\.com/products/'),
 'eBay': ('https://www.ebay.com/sch/i.html?_nkw={q}', r'ebay\.com/itm/'),
}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.current = None; self.scripts = []
        self.script = None; self.row_title = ''

    def handle_starttag(self, tag, attributes):
        a = dict(attributes)
        if tag == 'li' and 'cl-static-search-result' in a.get('class', ''):
            self.row_title = a.get('title', '')
        if tag == 'a':
            self.current = {'url': a.get('href', ''), 'title': a.get('title') or self.row_title,
                            'label': a.get('aria-label', ''), 'text': '', 'image': ''}
        if tag == 'img' and self.current is not None:
            self.current['image'] = a.get('src', '')
            self.current['title'] = self.current['title'] or a.get('alt', '')
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self.script = ''

    def handle_data(self, value):
        if self.current is not None: self.current['text'] += ' ' + value
        if self.script is not None: self.script += value

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(self.current); self.current = None
        if tag == 'li': self.row_title = ''
        if tag == 'script' and self.script is not None:
            try: self.scripts.append(json.loads(self.script))
            except ValueError: pass
            self.script = None


def objects(value):
    if isinstance(value, dict):
        yield value
        for v in value.values(): yield from objects(v)
    elif isinstance(value, list):
        for v in value: yield from objects(v)


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(str(value or ''))).strip()


def relevant(row):
    # Marketplaces may return unrelated recommendations even for an exact query.
    # Only accept a match when most meaningful query words appear in the title.
    stop = {'old','large','commercial','vintage','and','or','the','of','with','a'}
    def tokens(text):
        return {w.rstrip('s') for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in stop and len(w)>2}
    query = tokens(row.get('matched_query',''))
    title = tokens(row.get('title',''))
    return eligible(row) and bool(query) and len(query & title) >= max(1, (len(query)*2+2)//3)


def parse_page(source, url, body, watch, timestamp):
    page = Page(); page.feed(body)
    products = {clean(o.get('name')).lower(): o for o in objects(page.scripts)
                if o.get('@type') == 'Product'}
    results = {}
    for link in page.links:
        address = up.urljoin(url, link['url']).split('?')[0].rstrip('/')
        if not re.search(PLATFORMS[source][1], address): continue
        title = clean(link['title'] or link['label'] or link['text'])
        if not title: continue
        product = products.get(title.lower(), {})
        offer = product.get('offers', {})
        if isinstance(offer, list): offer = offer[0] if offer else {}
        if not isinstance(offer, dict): offer = {}
        availability = str(offer.get('availability', ''))
        if any(s in availability for s in ['SoldOut', 'OutOfStock', 'Discontinued']): continue
        words = clean(link['label'] + ' ' + link['text'])
        if re.search(r'\b(sold out|sold)\b', words, re.I): continue
        match = re.search(r'\$([\d,]+(?:\.\d{2})?)', words)
        price = str(offer.get('price', match.group(1) if match else ''))
        images = product.get('image') or link['image']
        image = images[0] if isinstance(images, list) and images else images
        if isinstance(image, dict): image = image.get('url', '')
        place = offer.get('availableAtOrFrom', {})
        city = place.get('address', {}).get('addressLocality', '') if isinstance(place, dict) else ''
        if not city:
            location = re.search(r'\bin (.+?,\s*[A-Z]{2})\b', words)
            city = location.group(1) if location else ''
        key = hashlib.sha256(address.encode()).hexdigest()[:24]
        results[key] = {'id': 'scan-'+key, 'title': title[:240], 'url': address, 'platform': source,
            'price': ('$'+price) if price else 'Not listed', 'image': image or '',
            'location': city or 'Location unverified', 'priority': watch.get('priority', 'primary'),
            'watch_ids': [watch['id']], 'matched_query': watch['query'], 'last_seen': timestamp,
            'availability': 'Shown in search; seller confirmation needed', 'status': 'saved',
            'delivery': 'Pickup listing; confirm address' if source == 'Craigslist' else 'Pickup / shipping unverified',
            'images': [i for i in (images if isinstance(images,list) else [image]) if isinstance(i,str) and i.startswith('http')],
            'requirements': watch.get('description',''),
            'note': clean(product.get('description'))[:1500] or 'Found on the platform search page. Dimensions and working condition need verification.'}
    return list(results.values())


def fetch(url):
    request = ur.Request(url, headers={'User-Agent': 'ChrisList/1.0 personal saved-search monitor'})
    with ur.urlopen(request, timeout=20) as r:
        raw = r.read(8_000_001)
        if len(raw) > 8_000_000: raise ValueError('Page exceeds size limit')
        return raw.decode('utf-8', 'replace')


def matches_constraints(row, watch):
    text=(row.get('title','')+' '+row.get('note','')).lower()
    if any(str(t).lower() not in text for t in watch.get('include',[])):return False
    if any(str(t).lower() in text for t in watch.get('exclude',[])):return False
    if watch.get('price_max') is not None:
        price=re.search(r'[\d,]+(?:\.\d+)?',row.get('price',''))
        if not price or float(price[0].replace(',',''))>float(watch['price_max']):return False
    return True


def scan_source(source, watches):
    if source == "Facebook Marketplace":
        from facebook_scanner import scan
        return scan(watches)
    stamp = now(); rows = []; errors = []; attempted = 0
    for w in watches:
        attempted += 1
        url = PLATFORMS[source][0].format(q=up.quote(w['query']))
        try:
            body = fetch(url)
            found = parse_page(source, url, body, w, stamp)
            # A 200 HTML login shell is not evidence of a successful zero-result search.
            if not found and not re.search(r'no results|no listings|0 results|nothing found', body, re.I):
                errors.append('No readable listing records; login, script rendering, or parser support required')
                break
            rows.extend([x for x in found if relevant(x) and matches_constraints(x,w)][:30])
        except Exception as error:
            errors.append(str(error)); break
        time.sleep(0.5)
    return rows, {'platform': source, 'checked_at': stamp, 'attempted_queries': attempted,
        'total_queries': len(watches), 'records': len(rows), 'status': 'partial' if rows and errors else 'blocked' if errors else 'ok',
        'detail': '; '.join(errors) or 'Public search pages parsed; results are snapshots, not seller-confirmed availability.'}


def merge(previous, discovered):
    existing = {x['id']: annotate(x) for x in previous if eligible(x)}; new = []
    for x in discovered:
        if not eligible(x): continue
        annotate(x)
        old = existing.get(x['id'])
        if old:
            x['first_seen'] = old.get('first_seen', x['last_seen'])
            x['watch_ids'] = sorted(set(old.get('watch_ids', []) + x['watch_ids']))
            if old.get('priority') == 'primary': x['priority'] = 'primary'
        else:
            x['first_seen'] = x['last_seen']; new.append(x)
        existing[x['id']] = x
    return list(existing.values()), new


def notify(new, results):
    from alert_delivery import notify as deliver_alerts
    return deliver_alerts(RUNTIME, new, relevant)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--publish', action='store_true'); parser.add_argument('--limit', type=int); parser.add_argument('--platform', choices=list(PLATFORMS))
    args = parser.parse_args(); RUNTIME.mkdir(exist_ok=True)
    import fcntl
    lock = (RUNTIME/'lock').open('w')
    try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: print('Scan already running'); return
    config = read(ROOT/'scanner-config.json', {})
    watches = config.get('watches', []) + read(RUNTIME/'watches.json', [])
    # Repository-owner search requests bridge the phone UI to this local job.
    # Requests from other issue authors are ignored, and no issue text is executed.
    intake_error = ''
    try:
        issues = json.loads(fetch('https://api.github.com/repos/justinfelleskmp-dev/chris-list/issues?state=open&per_page=100'))
        for issue in issues:
            if issue.get('user',{}).get('login') != 'justinfelleskmp-dev': continue
            if not issue.get('title','').startswith('Chris List search: '): continue
            query = issue['title'].removeprefix('Chris List search: ').strip()[:150]
            if query: watches.append({'id':'request-'+str(issue['number']),'query':query,'priority':'primary'})
    except Exception as error: intake_error = 'Phone search requests could not be read: '+str(error)
    if not watches: raise SystemExit('No scanner watches configured')
    watches = sorted(watches, key=lambda w: w.get('priority') == 'secondary')
    if args.limit: watches = watches[:args.limit]
    old = read(FEED, {'listings': []}); discovered = []; statuses = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(scan_source, source, watches): source for source in ([args.platform] if args.platform else PLATFORMS)}
        for job in concurrent.futures.as_completed(jobs):
            rows, status = job.result(); discovered.extend(rows); statuses.append(status)
            print(status['platform'], status['status'], len(rows), flush=True)
    if args.platform:
        statuses += [s for s in old.get('platforms', []) if s['platform'] != args.platform]
    listings, new = merge([x for x in old.get('listings', []) if relevant(x)], discovered)
    results = {'ran_at': now(), 'platforms': statuses, 'listings': listings, 'new_count': len(new),
               'summary': f'{len(new)} newly discovered matches. {sum(x["status"]=="ok" for x in statuses)}/10 sources fully scanned.'}
    results['intake_status'] = intake_error or 'Repository-owner search requests checked (first 100 open issues)'
    results['alert_status'] = notify(new, results)
    atomic(FEED, results)
    print(results['summary']); print(results['alert_status'])
    if args.publish:
        subprocess.run(['git','add','scan-results.json'], cwd=ROOT, check=True)
        if subprocess.run(['git','diff','--cached','--quiet','--','scan-results.json'],cwd=ROOT).returncode:
            subprocess.run(['git','commit','-m','Update marketplace scan snapshot','--','scan-results.json'],cwd=ROOT,check=True)
            subprocess.run(['git','push'],cwd=ROOT,check=True)


if __name__ == '__main__': main()
