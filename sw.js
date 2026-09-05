const CACHE='chris-list-3';
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['./','./index.html','./app.js','./style.css','./sections.css','./offline.js','./fixes.js','./donors.js'])));self.skipWaiting();});
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method==='GET'&&new URL(e.request.url).origin===self.location.origin)e.respondWith(fetch(e.request).then(r=>{if(r.ok){let copy=r.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));}return r;}).catch(()=>caches.match(e.request)));});
