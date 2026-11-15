// Execute the real region component with DOM/Aladin doubles, no browser/network dependencies.
const fs=require('fs'), assert=require('assert');
const timers=new Map(); let nextTimer=0;
const setTimeout=(fn)=>{timers.set(++nextTimer,fn);return nextTimer},clearTimeout=id=>timers.delete(id);
const nodes=new Map();
function node(id){
  if(!nodes.has(id))nodes.set(id,{value:'',checked:false,hidden:false,dataset:{},attrs:{},handlers:{},children:[],
    classList:{add(){},toggle(){}},style:{setProperty(){}},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},
    getAttribute(k){return this.attrs[k]},addEventListener(k,v){this.handlers[k]=v},querySelector:node,
    closest(){return {querySelector:node}},replaceChildren(...c){this.children=c},append(...c){this.children.push(...c)}});
  return nodes.get(id);
}
const root={querySelector:node,querySelectorAll:()=>[]};
const document={activeElement:null,createElement:()=>node(Symbol()),createTextNode:text=>({text})};
let reducedMotion=true;
const window={matchMedia:()=>({matches:reducedMotion})};
const cancelAnimationFrame=()=>{},requestAnimationFrame=()=>{};
class ResizeObserver{observe(){} disconnect(){}}
const events={},cats=[];
let center=[10,20],fov=.25;
const aladin={getFoV:()=>[fov,fov],setFoV(v){fov=v},getRaDec:()=>center,gotoRaDec(ra,dec){center=[ra,dec];events.positionChanged?.()},
  world2pix:(ra,dec)=>[ra*10,dec*10],addOverlay(){},addCatalog(){},newImageSurvey(){},setImageSurvey(){},on(k,fn){events[k]=fn}};
const A={init:Promise.resolve(),aladin:()=>aladin,circle(){},polyline(){},marker:(ra,dec,data)=>({ra,dec,data}),
  source:(ra,dec,data)=>({ra,dec,data}),graphicOverlay:()=>({add(){},removeAll(){},show(){},hide(){}}),
  catalog(opts){let c={...opts,sources:[],visible:true,addSources(s){for(const x of s)x.catalog=c;c.sources.push(...s)},
    removeAll(){c.sources=[]},show(){c.visible=true},hide(){c.visible=false}};cats.push(c);return c}};
const data={region:{ra:10,dec:20,fov:.1},rev:0,object:null,level:'simple',local:[],remote:[],layers:[{id:'x',label:'x'}],layer:'x',
  fov_min:.05,fov_max:.5,spherex_px:6.15,cube_px:12.9,anchor_arcsec:1,constellations:[],
  gaia_on:true,gaia_status:'loading',gaia_region:{ra:10,dec:20,fov:.1},gaia:[],gaia_key:null,poll:true};
const sent=[]; const api={parentElement:root,data,setStateValue:(k,v)=>sent.push([k,v]),setTriggerValue:(k,v)=>sent.push([k,v])};
const code=fs.readFileSync('skyclues/region_component.js','utf8').replace('export default function','function render')
  .replace('import(d.aladin)','Promise.resolve({default:A})');
eval(code);
(async()=>{
 render(api);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(node('.rg-gaia-status').hidden,false);assert.equal(node('.rg-gaia-status').dataset.state,'loading');
 const gaia=cats.find(c=>c.name.startsWith('Gaia'));
 center=[11,21];events.positionChanged();assert.equal(root.__skyRegion.cur.ra,11); // map remains usable while loading
 // Late result for the old region is hidden, before a debounced region event even reaches Python.
 data.gaia_status='ready';data.gaia_key='old';data.gaia=[{ra:10,dec:20,source_id:'6051234567890123456'}];data.poll=false;
 render(api);assert.equal(gaia.visible,false);
 data.gaia_region={ra:11,dec:21,fov:.1};data.gaia_key='new';
 data.gaia=[{ra:11.001,dec:21.002,source_id:'6051234567890123456'}, {ra:11.003,dec:21.004,source_id:'6051234567890123457'}];
 render(api);assert.equal(gaia.visible,true);assert.equal(node('.rg-gaia-status').hidden,true);
 // Overlapping markers: select closest hit, not last callback, and never rounded source_id.
 events.objectClicked(gaia.sources[1]);events.objectClicked(gaia.sources[0]);
 events.click({ra:11.0011,dec:21.0021,x:110.01,y:210.02,isDragging:false});
 const pick=sent.findLast(([k])=>k==='gaia_pick')[1];
 assert.equal(pick.source_id,'6051234567890123456');assert.equal(pick.fov,.1);
 assert.equal(node('#rg-q').value,'Gaia DR3 6051234567890123456');
 assert.equal(root.__skyRegion.cur.ra,11.001);assert.equal(root.__skyRegion.cur.dec,21.002);
 assert.equal(center[0],11.001); // generic click did not overwrite with pointer coordinate
 // Response/cache redraw uses the same region, no artificial loader.
 data.region={...root.__skyRegion.cur};data.gaia_region={...data.region};data.rev++;
 data.object={name:'Gaia DR3 6051234567890123456',anchor:[11.001,21.002],notes:[],gaia_source_id:pick.source_id};render(api);
 assert.equal(node('.rg-gaia-status').hidden,true);
 data.gaia_key='empty';data.gaia=[];render(api);
 assert(node('.rg-gaia-message').textContent.includes('No se encontraron'));assert(node('.rg-gaia-retry').hidden);
 data.gaia_status='error';render(api);assert.equal(node('.rg-gaia-retry').hidden,false);
 node('.rg-gaia-retry').handlers.click();assert.equal(sent.at(-1)[0],'gaia_retry');
 data.gaia_on=false;render(api);assert.equal(gaia.visible,false);assert(node('.rg-gaia-status').hidden);
 // A quick second coordinate edit must survive completion of the first move's animation.
 reducedMotion=false;
 let oldComplete,stops=0;
 aladin.animateToRaDec=(ra,dec,duration,complete)=>{oldComplete=complete};
 aladin.stopAnimation=()=>stops++;
 node('#rg-ra').value='11.01';node('#rg-ra').handlers.keydown({key:'Enter',preventDefault(){}});
 const previousMove=oldComplete;
 node('#rg-dec').value='-50';node('#rg-dec').handlers.keydown({key:'Enter',preventDefault(){}});
 previousMove();
 assert(Math.abs(center[0]-11.01)<1e-12);assert.equal(center[1],-50);assert.equal(stops,2);
 assert.equal(root.__skyRegion.cur.dec,-50);assert.equal(root.__skyRegion.cur.fov,.1);
 node('#rg-dec').handlers.blur();assert.equal(stops,2);assert.equal(root.__skyRegion.lock,false);
 // A hot update can replace the map DOM while keeping the component root alive.
 const detachedState=root.__skyRegion;
 nodes.delete('.rg-map');render(api);await new Promise(resolve=>setImmediate(resolve));
 assert.notStrictEqual(root.__skyRegion,detachedState);
 assert.equal(root.__skyRegion.mapElement,node('.rg-map'));assert.equal(root.__skyRegion.aladin,aladin);
 // Suggestions use the current query only; aliases with padded IDs never duplicate an object.
 document.activeElement=node('#rg-q');node('#rg-q').value='atlas';
 data.remote_query='ngc';data.remote=[{id:'NGC     1',label:'NGC 1',aliases:[]}];data.search_state='ready';render(api);
 assert.equal(root.__skyRegion.items.length,0);assert.equal(node('.rg-search-status').dataset.loading,'true');
 data.remote_query='atlas';data.remote=[{id:'JPL:1004083',label:'3I/ATLAS (C/2025 N1)',type:'Cometa',aliases:['3I']}];render(api);
 assert.equal(root.__skyRegion.items[0].id,'JPL:1004083');assert.equal(node('.rg-search-status').dataset.loading,'false');
 node('#rg-list').children[0].handlers.mousedown({preventDefault(){}});
 assert.equal(sent.at(-1)[0],'pick');assert.equal(sent.at(-1)[1].name,'JPL:1004083');
 assert.equal(node('#rg-q').value,'3I/ATLAS (C/2025 N1)');
 root.__skyRegion.resolving=null;render(api);assert.equal(node('.rg-search-status').hidden,true);
 root.__skyRegion.suggesting=true;node('#rg-q').value='ngc';data.remote_query='ngc';
 data.local=[{id:'NGC 1',aliases:[]}];data.remote=[{id:'NGC     1',label:'NGC 1',aliases:[]}];render(api);
 assert.equal(root.__skyRegion.items.length,1);
 console.log('Actual component: slow, stale, exact selection, empty, error/retry and cached passed');
})().catch(e=>{console.error(e);process.exitCode=1});
