// Source choices are a browser preference, separate from saved listing records.
const sourcePreferenceKey='chris-list-sources-v1';
let includedSources=null;
try {
 const saved=JSON.parse(localStorage.getItem(sourcePreferenceKey));
 if(Array.isArray(saved)&&saved.every(x=>typeof x==='string'))includedSources=new Set(saved);
} catch (_) { /* Invalid preferences default to all sources. */ }
function listingSource(row){return String(row.platform||'Other').trim()||'Other';}
function visibleListings(){return state.listings.filter(row=>row.status!=='passed'&&(includedSources===null||includedSources.has(listingSource(row))));}
function renderSourceFilters(){
 const rows=state.listings.filter(row=>row.status!=='passed');
 const counts=new Map([['Facebook Marketplace',0],['Craigslist',0]]);
 for(const row of rows){const source=listingSource(row);counts.set(source,(counts.get(source)||0)+1);}
 for(const source of includedSources||[])if(!counts.has(source))counts.set(source,0);
 const panel=document.createElement('fieldset');panel.className='source-filters';
 const legend=document.createElement('legend');legend.textContent='Sources';panel.append(legend);
 const choices=document.createElement('div');choices.className='source-choices';panel.append(choices);
 function update(next,focusKey){
  includedSources=next;
  try{localStorage.setItem(sourcePreferenceKey,JSON.stringify(next===null?null:[...next]));}catch(_){}
  // Hidden ads must not remain silently selected for email or messaging.
  const visible=new Set(visibleListings().map(row=>row.id));
  for(const id of selected)if(!visible.has(id))selected.delete(id);
  render();
  const target=Array.from(document.querySelectorAll('[data-source-focus]')).find(el=>el.dataset.sourceFocus===focusKey);
  target?.focus({preventScroll:true});
 }
 for(const [source,count] of counts){
  const label=document.createElement('label'),box=document.createElement('input');
  box.type='checkbox';box.checked=includedSources===null||includedSources.has(source);box.dataset.sourceFocus=source;
  box.onchange=()=>{const next=new Set(includedSources===null?counts.keys():includedSources);if(box.checked)next.add(source);else next.delete(source);update(next,source);};
  label.append(box,document.createTextNode(source+' ('+count.toLocaleString()+')'));choices.append(label);
 }
 const actions=document.createElement('div');actions.className='source-actions';panel.append(actions);
 for(const [label,key,next] of [['Show all','all',null],['Clear all','none',new Set()]]){
  const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.sourceFocus=key;button.onclick=()=>update(next,key);actions.append(button);
 }
 const status=document.createElement('span');status.setAttribute('role','status');status.textContent='Showing '+visibleListings().length.toLocaleString()+' of '+rows.length.toLocaleString()+' listings';actions.append(status);
 if(!visibleListings().length){const empty=document.createElement('p');empty.textContent=includedSources?.size===0?'Choose at least one source to see listings.':'No saved listings from these sources. Try Show all.';panel.append(empty);}
 document.querySelector('#results').prepend(panel);
}

const app=document.querySelector('#app');let state,active;
const E=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(p,b){let r=await fetch(p,{method:b?'POST':'GET',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined}),j=await r.json();if(!r.ok)throw Error(j.error);return j}
function places(q){let e=encodeURIComponent(q);return [['Facebook Marketplace','https://www.facebook.com/marketplace/anaheim/search?query='+e],['OfferUp','https://offerup.com/search?q='+e],['Craigslist','https://orangecounty.craigslist.org/search/sss?query='+e+'&postal=92805&search_distance=60&sort=date'],['Nextdoor','https://nextdoor.com/for_sale_and_free/?query='+e],['5miles','https://www.5miles.com/search?keyword='+e],['VarageSale','https://www.varagesale.com/search?q='+e],['Mercari','https://www.mercari.com/search/?keyword='+e],['Poshmark','https://poshmark.com/search?query='+e],['Depop','https://www.depop.com/search/?q='+e],['eBay local pickup','https://www.ebay.com/sch/i.html?_nkw='+e+'&LH_Distance=60&_stpos=92805'],['eBay shipping','https://www.ebay.com/sch/i.html?_nkw='+e]]}
function think(x){const fit=machineFit(x);if(fit.is_machine){if(!fit.eligible)return 'Does not meet the verified pen-and-cutter requirement.';const m=fit.model;return m.tools+' Working width: '+m.working_width+'. Body width: '+m.body_width+'. '+m.roll;}const n=Number(String(x.price).replace(/[^0-9.]/g,''));return (/kiosk|fixture|auction|display/i.test(x.title+' '+x.platform)?'Confirm interior width, rear access, and whether the front can be modified.':'Confirm the exact model and a working demonstration.')+(n&&n<=500?' Price is within the target range.':n?' Above the target budget; consider a lower offer.':'');}
function item(x){let img=x.image||'https://placehold.co/500x300?text=Image+unavailable';return '<article class="card"><img class="item-image" src="'+E(img)+'" onerror="this.src=\'https://placehold.co/500x300?text=Image+unavailable\'" alt=""><a class="item-title" onclick="openItem(\''+x.id+'\')">'+E(x.title)+'</a><div class="price">'+E(x.price||'Price not listed')+'</div><div class="small">'+E(x.location)+' · '+E(x.platform)+'</div><p class="thought"><b>Thoughts:</b> '+E(think(x))+'</p></article>'}
function render(){let cards=visibleListings().map(item).join('')||'<p>No listings match these sources.</p>';let watches=state.watches.map(w=>'<div class="watch"><b>'+E(w.description.slice(0,90))+(w.description.length>90?'…':'')+'</b><div class="links">'+places(w.description).map(a=>'<a class="small" href="'+a[1]+'" target="_blank">'+a[0]+'</a>').join(' · ')+'</div></div>').join('');app.innerHTML='<div class="shell"><header class="bar"><div class="mark">chris list</div><a class="results-link" href="#results">View matched listings ↓</a><div class="muted">local classifieds viewer · Anaheim / Southern California</div><button onclick="emailDigest()">Email selected ad links</button></header><div class="grid"><aside><div class="panel"><b>search watches</b><form id="wf"><textarea id="desc" required placeholder="What are you looking for?"></textarea><button>add search</button></form>'+watches+'</div><div class="panel small"><b>last scan</b><br>'+E(state.last_scan?.ran_at||'Not run')+'<br><span class="muted">'+E(state.last_scan?.summary||'')+'</span><p><b>eBay local pickup</b> limits results to 60 miles. <b>eBay shipping</b> can be ordered from anywhere.</p></div></aside><section id="results"><h2>available now <span class="muted small">'+state.listings.length+' saved</span></h2><div class="cards">'+cards+'</div></section></div></div>';wf.onsubmit=async e=>{e.preventDefault();await api('/api/watch',{description:desc.value});load()}}
function draft(k){let x=active,f=x.first_offer||'[your first offer]',z=x.final_offer||'[your maximum offer]';if(k==='free')return 'Hi! I’m building an unattended caricature-drawing robot for a local art project. If this is still available and you mainly need it out of the way, I’d be grateful to pick it up free and can pick up quickly. If not, please keep me in mind if it does not sell.';if(k==='first')return 'Hi! I’m building an art project and am interested in your '+x.title+'. I can pick up promptly. Would you consider '+f+'?';return 'Thanks for getting back to me. My final budget for this project is '+z+', and I can pick up at a time that is convenient for you. If that works, I’m ready to make it easy.'}
function openItem(id){active=state.listings.find(x=>x.id===id);let x=active,img=x.image||'https://placehold.co/500x300?text=Image+unavailable';let m=document.createElement('div');m.className='modal-back';m.id='modal';m.innerHTML='<div class="modal"><button class="close" onclick="closeModal()">×</button><div class="detail"><img src="'+E(img)+'" alt=""><div><h2>'+E(x.title)+'</h2><div class="price">'+E(x.price)+'</div><p>'+E(x.location)+' · '+E(x.platform)+'</p><p>'+E(x.note)+'</p><p class="thought"><b>Thoughts:</b> '+E(think(x))+'</p><a href="'+E(x.url)+'" target="_blank">open original listing ↗</a></div></div><div class="label">Offer plan</div><div class="row"><input id="firstOffer" value="'+E(x.first_offer)+'" placeholder="First offer, e.g. $125"><input id="finalOffer" value="'+E(x.final_offer)+'" placeholder="Final offer, e.g. $250"><button onclick="savePlan()">save</button></div><div class="label">Message drafts</div><div class="choice"><button onclick="showDraft(\'free\')">ask for free pickup</button><button onclick="showDraft(\'first\')">make first offer</button><button onclick="showDraft(\'final\')">make final offer</button></div><div class="draft" id="draftText">'+E(draft('free'))+'</div><button onclick="copyDraft()">copy this message</button><span class="small muted">Copying prepares it; you choose whether to send it.</span><div class="label">Negotiation timeline</div><textarea id="timeline" placeholder="Paste seller replies or note what happened.">'+E(x.timeline)+'</textarea><button onclick="savePlan()">save timeline</button></div>';document.body.append(m)}
function showDraft(k){draftText.textContent=draft(k)}function closeModal(){document.querySelector('#modal')?.remove()}async function copyDraft(){await navigator.clipboard.writeText(draftText.textContent);alert('Message copied.')}async function savePlan(){active.first_offer=firstOffer.value;active.final_offer=finalOffer.value;active.timeline=timeline.value;await api('/api/listing/update',{id:active.id,first_offer:active.first_offer,final_offer:active.final_offer,timeline:active.timeline});closeModal();load()}async function load(){state=await api('/api/state');render()}load();
