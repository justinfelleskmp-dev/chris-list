// Published scan snapshots are merged without overwriting private offers/notes.
async function syncScan(){
 try{
  const response=await originalFetch('https://raw.githubusercontent.com/justinfelleskmp-dev/chris-list/master/scan-results.json',{cache:'no-store'});
  if(!response.ok)throw Error('No published scan yet');const feed=await response.json();
  const key='chris-list-v1',board=JSON.parse(localStorage.getItem(key));
  if(!board)return;
  const records=new Map(board.listings.map(x=>[x.id,x]));
  const unseen=feed.listings.filter(x=>!records.has(x.id));
  for(const row of feed.listings){const old=records.get(row.id)||{};records.set(row.id,{...old,...row,status:old.status||'saved',first_offer:old.first_offer||'',final_offer:old.final_offer||'',timeline:old.timeline||''});}
  board.listings=Array.from(records.values());const {listings,...metadata}=feed;board.last_scan=metadata;localStorage.setItem(key,JSON.stringify(board));await load();
  if(unseen.length&&localStorage.getItem('chris-alerts')==='on'&&'Notification' in window&&Notification.permission==='granted'){
   const registration=await navigator.serviceWorker.ready;await registration.showNotification('Chris List: '+unseen.length+' new matches',{body:unseen.slice(0,3).map(x=>x.title).join(' · '),tag:'chris-list-new'});
  }
 }catch(error){console.info('Showing saved snapshot:',error.message);}
}
const beforeScanRender=render;
render=function(){
 beforeScanRender();
 const bar=document.querySelector('.bar');
 const info=Array.from(bar.querySelectorAll('p')).find(x=>x.textContent.includes('Automatic collection'));
 if(info)info.textContent=(navigator.onLine?'Online':'Offline')+' · Token-free scanner; saved results are search-page snapshots.';
 const refresh=document.createElement('button');refresh.textContent='Refresh scan results';refresh.onclick=syncScan;bar.append(refresh);
 const alerts=document.createElement('button');alerts.textContent=localStorage.getItem('chris-alerts')==='on'?'Browser alerts on (while open)':'Enable browser alerts (while open)';alerts.onclick=async()=>{if(!('Notification' in window))return alert('This browser does not support notifications here.');const permission=await Notification.requestPermission();localStorage.setItem('chris-alerts',permission==='granted'?'on':'off');await load();};bar.append(alerts);
 const trigger=document.createElement('a');trigger.href='https://github.com/justinfelleskmp-dev/chris-list/actions/workflows/scan.yml';trigger.target='_blank';trigger.rel='noopener';trigger.textContent='Scan now (GitHub → Run workflow)';bar.append(trigger);
 const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Source status & alerts';details.append(summary);
 const feed=state.last_scan||{};for(const source of feed.platforms||[]){const line=document.createElement('p');line.textContent=source.platform+': '+source.status+' · '+source.attempted_queries+'/'+source.total_queries+' queries · '+source.records+' records. '+source.detail;details.append(line);}
 const alert=document.createElement('p');alert.textContent=feed.alert_status||'No completed scan.';details.append(alert);bar.append(details);
  const rows=state.listings.filter(x=>x.status!=='passed');const ordered=[...rows.filter(x=>x.priority!=='secondary'),...rows.filter(x=>x.priority==='secondary')];
 document.querySelectorAll('.cards article').forEach((card,i)=>{const x=ordered[i];if(!x?.last_seen)return;const meta=document.createElement('p');meta.className='small';meta.textContent='Seen '+new Date(x.last_seen).toLocaleString()+' · '+x.delivery+' · '+x.availability;card.append(meta);});
};
setTimeout(syncScan,0);
setInterval(()=>{if(navigator.onLine&&document.visibilityState==='visible')syncScan();},300000);
