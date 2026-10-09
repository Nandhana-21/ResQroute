async function api(url,opt={}){const r=await fetch(url,{headers:{'Content-Type':'application/json'},...opt,body:opt.body?JSON.stringify(opt.body):undefined});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||'Request failed');return j}
const $=id=>document.getElementById(id);
function toast(m,t=''){const d=document.createElement('div');d.className='toast-r '+t;d.setAttribute('role','status');d.textContent=m;$('toasts').appendChild(d);setTimeout(()=>d.remove(),4500)}
window.alert=m=>toast(m,'danger');
function confirmDlg(msg,ok='Confirm',cls='btn-primary'){return new Promise(res=>{const M=bootstrap.Modal.getOrCreateInstance($('confirmM')),b=$('confirmOk');$('confirmT').textContent=msg;b.textContent=ok;b.className='btn '+cls;let yes=false;
 b.onclick=()=>{yes=true;M.hide()};$('confirmM').addEventListener('hidden.bs.modal',()=>res(yes),{once:true});M.show()})}
async function withBtn(b,label,fn){const o=b.innerHTML;b.disabled=true;b.innerHTML='<span class="spinner-border"></span> '+label;try{return await fn()}finally{b.disabled=false;b.innerHTML=o}}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const SEV={CRITICAL:'danger',HIGH:'warning',MODERATE:'info'};
const LBL={pending:'Request received',waiting:'Searching for ambulance',accepted:'Ambulance assigned',on_the_way:'En route',arrived:'Arrived',picked_up:'Patient picked up',completed:'Completed',cancelled:'Cancelled'};
const STEPS=['pending','accepted','on_the_way','arrived','picked_up','completed'];
const stepper=s=>`<div class="d-flex gap-1 my-2">${STEPS.map((k,i)=>`<div class="step ${STEPS.indexOf(s)>=i?'done':''}"><i></i>${LBL[k]}</div>`).join('')}</div>`;
class LiveMap{
 constructor(id){this.m=L.map(id).setView([11.0168,76.9558],13);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(this.m);this.o={};this.fit=false;this.R={};this.q={};this.idx={}}
 put(k,ll,emoji,tip){if(!ll){this.clear(k);return}if(this.o[k]){this.o[k].setLatLng(ll)}else{this.o[k]=L.marker(ll,{icon:L.divIcon({html:emoji,className:'pin',iconSize:[30,30]})}).addTo(this.m).bindTooltip(tip)}}
 line(k,pts,color,dash){this.clear(k);if(pts)this.o[k]=L.polyline(pts,{color,weight:5,opacity:.8,dashArray:dash}).addTo(this.m)}
 clear(k){if(this.o[k]){this.m.removeLayer(this.o[k]);delete this.o[k]}}
 async route(k,a,b){if(this.R[k]||this.q[k])return;this.q[k]=1;  // real road route from OSRM (free public server); straight line if unavailable
  try{const r=await fetch(`https://router.project-osrm.org/route/v1/driving/${a[1]},${a[0]};${b[1]},${b[0]}?overview=full&geometries=geojson`);const t=(await r.json()).routes[0];
   this.R[k]={pts:t.geometry.coordinates.map(c=>[c[1],c[0]]),km:t.distance/1000,min:t.duration/60}}catch(x){this.R[k]={pts:[a,b],km:null,min:null,fb:true}}
  if(this.last)this.draw(this.last)}
 nextBody(e){if(!e||!['on_the_way','picked_up'].includes(e.status))return{};const k=e.id+(e.status==='picked_up'?'h':'p'),r=this.R[k];if(!r||r.fb)return{};
  const step=Math.max(2,Math.ceil(r.pts.length/14));this.idx[k]=Math.min((this.idx[k]||0)+step,r.pts.length-1);const p=r.pts[this.idx[k]];return{lat:p[0],lng:p[1],final:this.idx[k]>=r.pts.length-1}}
 draw(e){this.last=e;const a=e.ambulance,h=e.hospital,p=[e.lat,e.lng],picked=['picked_up','completed'].includes(e.status);
  this.put('p',picked?null:p,'🧍','Patient');this.put('a',a?[a.lat,a.lng]:null,'🚑',a?a.vehicle:'');this.put('h',h?[h.lat,h.lng]:null,'🏥',h?h.name:'');
  if(a&&!picked)this.route(e.id+'p',[a.lat,a.lng],p);if(h)this.route(e.id+'h',p,[h.lat,h.lng]);
  const r1=this.R[e.id+'p'],r2=this.R[e.id+'h'];
  if(r1&&!picked)this.line('l1',r1.pts,'#d90429');else this.clear('l1');
  if(r2)this.line('l2',r2.pts,'#0d6efd',picked?null:'8');else this.clear('l2');
  if(!this.fit&&(r1||r2)){const pts=[p];if(a)pts.push([a.lat,a.lng]);if(h)pts.push([h.lat,h.lng]);this.m.fitBounds(L.latLngBounds(pts).pad(.3));this.fit=true}}}
// notifications bell + toasts
let seen=null;
async function pollNotes(){try{const r=await api('/api/notifications');const b=$('nbadge');b.textContent=r.unread;b.classList.toggle('d-none',!r.unread);
 $('nlist').innerHTML=r.items.map(n=>`<li class="list-row ${n.read?'text-muted':'fw-semibold'}"><span class="text-muted">${n.time}</span> ${esc(n.message)}</li>`).join('')||'<li class="empty">No notifications yet</li>';
 const top=r.items[0]?r.items[0].id:0;if(seen!==null&&top>seen){r.items.filter(n=>n.id>seen).reverse().forEach(n=>{toast(n.message)})}seen=top}catch(e){}}
if($('nlist')){pollNotes();setInterval(pollNotes,3000);$('nbtn').addEventListener('click',()=>api('/api/notifications/read',{method:'POST'}))}

if(window.Chart)Chart.defaults.font.family="Inter, system-ui, sans-serif";
