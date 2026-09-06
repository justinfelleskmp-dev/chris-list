const sectionStyle=document.createElement('link');sectionStyle.rel='stylesheet';sectionStyle.href='sections.css';document.head.append(sectionStyle);
const originalRender=render,originalOpen=openItem,selected=new Set();
render=function(){
 originalRender();document.querySelector('.mark').textContent='chris list';
 document.querySelector('section > h2').firstChild.textContent='saved listings ';
 const bar=document.querySelector('.bar');let button=document.createElement('button');button.textContent='review selected messages';button.onclick=()=>{let id=selected.values().next().value;if(id)openItem(id);else alert('Select a listing first.');};bar.append(button);
 const offlineStatus=document.createElement('p');offlineStatus.className='muted';offlineStatus.textContent=(navigator.onLine?'Online':'Offline')+' · Saved board runs without AI tokens. New marketplace listings and messages require internet. Automatic collection is not connected.';bar.append(offlineStatus);
 const backup=document.createElement('button');backup.textContent='Export board backup';backup.onclick=()=>{const file=new Blob([localStorage.getItem('chris-list-v1')],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(file);link.download='chris-list-backup.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);};bar.append(backup);
 const restoreLabel=document.createElement('label');restoreLabel.textContent='Import board backup ';const restore=document.createElement('input');restore.type='file';restore.accept='.json,application/json';restore.onchange=async()=>{try{const imported=JSON.parse(await restore.files[0].text());if(!Array.isArray(imported.watches)||!Array.isArray(imported.listings))throw Error('Invalid backup');const existing=JSON.parse(localStorage.getItem('chris-list-v1'));for(const key of ['watches','listings'])for(const record of imported[key]){if(typeof record.id!=='string'||typeof record.description!=='string'&&key==='watches'||typeof record.title!=='string'&&key==='listings')throw Error('Invalid record');if(key==='listings'&&!/^https?:\/\//i.test(record.url||''))throw Error('Listing link must use HTTP or HTTPS');if(!existing[key].some(x=>x.id===record.id))existing[key].push(record);}localStorage.setItem('chris-list-v1',JSON.stringify(existing));load();}catch(error){alert('Could not import: '+error.message);}};restoreLabel.append(restore);bar.append(restoreLabel);
 const rows=state.listings.filter(x=>x.status!=='passed');document.querySelectorAll('.cards .card').forEach((card,i)=>{let x=rows[i],label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.style.width='auto';box.checked=selected.has(x.id);box.onchange=()=>box.checked?selected.add(x.id):selected.delete(x.id);label.append(box,document.createTextNode(' Select · '+x.platform));card.prepend(label);});
 const content=document.querySelector('.cards').parentElement;
 const cards=Array.from(content.querySelectorAll('.cards .card'));
 const primaryGrid=content.querySelector('.cards');
 const title=content.querySelector('h2');title.textContent='Your primary items';
 const secondary=document.createElement('section');secondary.className='secondary-section';
 secondary.innerHTML='<h2>Lower-priority donor ideas</h2><p class="muted">Secondary searches for future exhibits. Your primary items stay above this divider.</p><div class="secondary-listings cards"></div><h3>Donor search categories</h3><p class="muted">These are search ideas, not available listings.</p><div class="donor-directory"></div>';
 content.append(secondary);
 rows.forEach((x,i)=>{if(x.priority==='secondary')secondary.querySelector('.cards').append(cards[i]);});
 if(!primaryGrid.children.length)primaryGrid.innerHTML='<p>No primary listings saved yet.</p>';
 if(!secondary.querySelector('.cards').children.length)secondary.querySelector('.cards').innerHTML='<p>No lower-priority listings saved yet.</p>';
 const watchPanel=document.querySelector('#wf').parentElement;
 watchPanel.querySelectorAll('.watch').forEach(w=>w.remove());
 function watchRow(w){const row=document.createElement('div');row.className='watch';row.innerHTML='<strong>'+E(w.description)+'</strong>'+(w.note?'<p>'+E(w.note)+'</p>':'')+'<div class="links">'+places(w.description).map(a=>'<a class="small" href="'+a[1]+'" target="_blank" rel="noopener">'+E(a[0])+'</a>').join(' · ')+'</div>';return row;}
 state.watches.filter(w=>w.priority!=='secondary').forEach(w=>watchPanel.append(watchRow(w)));
 state.watches.filter(w=>w.priority==='secondary').forEach(w=>secondary.querySelector('.donor-directory').append(watchRow(w)));

};
openItem=function(id){const row=state.listings.find(x=>x.id===id);if(!row||!machineFit(row).eligible)return;originalOpen(id);const fit=machineFit(row);if(fit.model){const links=document.createElement('p');links.textContent='Model documentation: ';for(const url of fit.model.sources){const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener';a.textContent='manufacturer source ';links.append(a);}document.querySelector('.detail').append(links);}document.querySelector('.modal').setAttribute('role','dialog');};
showDraft=function(k){active.first_offer=document.querySelector('#firstOffer').value;active.final_offer=document.querySelector('#finalOffer').value;document.querySelector('#draftText').textContent=draft(k);};
