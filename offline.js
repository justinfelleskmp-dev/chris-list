const originalFetch=window.fetch.bind(window);
window.fetch=async function(url,options={}) {
 if(!String(url).startsWith('/api/'))return originalFetch(url,options);
 const key='chris-list-v1';let d=JSON.parse(localStorage.getItem(key)||'null')||{watches:[{id:'plotter',description:'Graphtec CE6000-60'},{id:'enclosure',description:'72 inch display cabinet'}],listings:[],last_scan:{ran_at:'No verified scan',summary:'Search links open marketplaces. Saved records are snapshots, not confirmed live inventory.'}};
 const b=JSON.parse(options.body||'{}');
 if(url==='/api/watch')d.watches.push({id:crypto.randomUUID(),description:b.description});
 if(url==='/api/listing')d.listings.push({...b,id:crypto.randomUUID(),status:'saved'});
 if(url==='/api/listing/update'||url==='/api/listing/status'){let x=d.listings.find(x=>x.id===b.id);if(x)Object.assign(x,b);}
 localStorage.setItem(key,JSON.stringify(d));return new Response(JSON.stringify(url==='/api/state'?d:{ok:true}),{headers:{'Content-Type':'application/json'}});
};
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js');
