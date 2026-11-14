export default function(c) {
 const {parentElement:p,data,setStateValue,setTriggerValue}=c;
 const input=p.querySelector('input'),list=p.querySelector('.suggestions');
 if(!input.matches(':focus'))input.value=data.query||'';
 const norm=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\b(m|ngc|ic|hd|hip)\s*(?=\d)/g,'$1 ').replace(/\s+/g,' ').trim();
 function draw(){
  list.replaceChildren();const q=norm(input.value);if(!q)return;
  const local=data.local.filter(x=>[x.id,...x.aliases].some(a=>norm(a).includes(q))).slice(0,8);
  const remote=norm(data.query||'')===q?data.remote:[];
  const seen=new Set();for(const item of [...local,...remote]){
   if(seen.has(item.id))continue;seen.add(item.id);
   const b=document.createElement('button');b.type='button';b.textContent=`${item.id} | ${item.type} | ${item.aliases.join(', ')} | ${item.source||'SIMBAD: indice verificado'}`;
   b.onclick=()=>setTriggerValue('pick',item.id);list.append(b);
  }
 }
 let timer;
 input.oninput=()=>{draw();clearTimeout(timer);timer=setTimeout(()=>setStateValue('query',input.value),650)};
 input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(timer);setTriggerValue('pick',input.value)}};
 p.querySelector('.find').onclick=()=>{clearTimeout(timer);setTriggerValue('pick',input.value)};
 draw();return ()=>clearTimeout(timer);
}