const originalRender=render,originalOpen=openItem,selected=new Set();
render=function(){
 originalRender();document.querySelector('.mark').textContent='chris list';
 document.querySelector('section > h2').firstChild.textContent='saved listings ';
 const bar=document.querySelector('.bar');let button=document.createElement('button');button.textContent='review selected messages';button.onclick=()=>{let id=selected.values().next().value;if(id)openItem(id);else alert('Select a listing first.');};bar.append(button);
 const rows=state.listings.filter(x=>x.status!=='passed');document.querySelectorAll('.cards .card').forEach((card,i)=>{let x=rows[i],label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.style.width='auto';box.checked=selected.has(x.id);box.onchange=()=>box.checked?selected.add(x.id):selected.delete(x.id);label.append(box,document.createTextNode(' Select · '+x.platform));card.prepend(label);});
 let form=document.querySelector('#lf');form.onsubmit=async e=>{e.preventDefault();let b={};for(let id of ['title','platform','price','url','image','location','note'])b[id]=form.querySelector('#'+id).value;await api('/api/listing',b);load();};
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
 const priority=document.createElement('select');priority.id='priority';priority.setAttribute('aria-label','Listing priority');priority.innerHTML='<option value="primary">Primary item</option><option value="secondary">Lower-priority donor</option>';form.insertBefore(priority,form.querySelector('button'));
 const submit=form.onsubmit;form.onsubmit=async e=>{e.preventDefault();let b={};for(const id of ['title','platform','price','url','image','location','note','priority'])b[id]=form.querySelector('#'+id).value;await api('/api/listing',b);load();};
};
openItem=function(id){originalOpen(id);document.querySelector('.modal').setAttribute('role','dialog');};
showDraft=function(k){active.first_offer=document.querySelector('#firstOffer').value;active.final_offer=document.querySelector('#finalOffer').value;document.querySelector('#draftText').textContent=draft(k);};
