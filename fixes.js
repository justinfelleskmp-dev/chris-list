const originalRender=render,originalOpen=openItem,selected=new Set();
render=function(){
 originalRender();document.querySelector('.mark').textContent='chris list';
 document.querySelector('section > h2').firstChild.textContent='saved listings ';
 const bar=document.querySelector('.bar');let button=document.createElement('button');button.textContent='review selected messages';button.onclick=()=>{let id=selected.values().next().value;if(id)openItem(id);else alert('Select a listing first.');};bar.append(button);
 const rows=state.listings.filter(x=>x.status!=='passed');document.querySelectorAll('.cards .card').forEach((card,i)=>{let x=rows[i],label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.style.width='auto';box.checked=selected.has(x.id);box.onchange=()=>box.checked?selected.add(x.id):selected.delete(x.id);label.append(box,document.createTextNode(' Select · '+x.platform));card.prepend(label);});
 let form=document.querySelector('#lf');form.onsubmit=async e=>{e.preventDefault();let b={};for(let id of ['title','platform','price','url','image','location','note'])b[id]=form.querySelector('#'+id).value;await api('/api/listing',b);load();};
};
openItem=function(id){originalOpen(id);document.querySelector('.modal').setAttribute('role','dialog');};
showDraft=function(k){active.first_offer=document.querySelector('#firstOffer').value;active.final_offer=document.querySelector('#finalOffer').value;document.querySelector('#draftText').textContent=draft(k);};
