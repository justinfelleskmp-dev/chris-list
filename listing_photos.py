"""Extract ad galleries; never substitute recommendation images for ad photos."""
import json
from pathlib import Path
from scanner import ROOT,RUNTIME,Page,objects,fetch,atomic,now,read

def collect(row):
    cache=RUNTIME/'photos'/ (row['id']+'.json')
    if cache.exists():return read(cache,{})
    images=[];detail='';complete=False
    if row['platform']=='Facebook Marketplace':
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page();page.goto(row['url'],wait_until='domcontentloaded',timeout=45000)
                try:page.locator('img[alt^="Product photo of"]').first.wait_for(timeout=10000)
                except Exception:pass
                photos=page.locator('img[alt^="Product photo of"]')
                # These are the ad's gallery thumbnails, not Today's picks.
                count=photos.count()
                for i in range(min(count,40)):
                    thumb=photos.nth(i);src=thumb.get_attribute('src')
                    if src and src not in images:images.append(src)
                complete=count>0 and count<=40
                detail='All '+str(count)+' exposed ad-photo thumbnails collected; Facebook may provide only thumbnail resolution. Videos are not photos.' if complete else 'Facebook did not expose a complete gallery; open original ad to check.'
            finally:browser.close()
    else:
        page=Page();page.feed(fetch(row['url']))
        for obj in objects(page.scripts):
            if obj.get('@type')=='Product':
                value=obj.get('image',[])
                for image in value if isinstance(value,list) else [value]:
                    image=image.get('url','') if isinstance(image,dict) else image
                    if isinstance(image,str) and image.startswith('https://') and image not in images:images.append(image)
        detail='Ad structured-data photos collected; platform may expose more photos in its original viewer.'
    if not images:images=row.get('images') or ([row['image']] if row.get('image') else [])
    result={'images':images,'complete':complete,'detail':detail,'checked_at':now()}
    if images and (complete or len(images)>1):atomic(cache,result)
    return result
