// Controlled failures for the actual iframe JavaScript, with an isolated DOM/Aladin double.
const fs=require('fs'),assert=require('assert');
const html=fs.readFileSync(0,'utf8'),mode=process.argv[2];
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{id,checked:id==='wise',value:id==='band'?'W1':'',disabled:true,
 textContent:'',children:[],classList:{add(){},remove(){}},parentElement:{append(){}},append(x){this.children.push(x)}});return nodes.get(id)}
const document={getElementById:node,createElement:()=>({})};
const catalogs=[],layers=[],events={};let built=0;
const MockA={init:mode==='aladin_error'?Promise.reject(Error('WebGL disabled')):Promise.resolve(),
 aladin:()=>{built++;return {setFoVRange(){},on:(key,fn)=>events[key]=fn,getRaDec:()=>[10,0],
  gotoRaDec(){},getRotation:()=>0,setRotation(){},setFoV(){},addOverlay(){},addCatalog(){},
  newImageSurvey:(url,opts)=>{let l={url,opts,alpha:0,setAlpha(v){this.alpha=v}};layers.push(l);return l},
  setOverlayImageLayer(){}}},
 graphicOverlay:()=>({add(){}}),circle(){},source:(ra,dec,data)=>({ra,dec,data}),
 catalog:()=>{let c={visible:true,addSources(s){this.sources=s},show(){this.visible=true},hide(){this.visible=false}};catalogs.push(c);return c}};
let fail=mode==='wise_error',requests=0;
async function fetch(url){requests++;return {ok:!fail,status:fail?503:200,blob:async()=>({text:async()=>'hips_order = 8'})}}
async function createImageBitmap(){return {close(){}}}
const js=html.split('<script type="module">')[1].split('</script>')[0].replace('await import(cfg.aladin)','({default:MockA})');
(async()=>{
 await eval('(async()=>{'+js+'})()');
 if(mode==='aladin_error'){assert(node('engine').textContent.includes('WebGL disabled'));assert.equal(built,0);return}
 assert.equal(built,1);assert.equal(catalogs[0].visible,true);assert.equal(catalogs[1].visible,false);
 if(mode==='wise_error'){
  assert(node('wisestatus').textContent.includes('no disponible (HTTP 503)'));assert.equal(layers.length,0);
  assert.equal(node('gaia').disabled,false);fail=false;await node('retry').onclick();
 }
 assert(node('wisestatus').textContent.includes('tesela central JPEG recibida'));
 node('gaia').checked=false;node('gaia').onchange();assert.equal(catalogs[0].visible,false);assert.equal(layers[0].alpha,1);
 node('motion').checked=true;node('motion').onchange();assert.equal(catalogs[1].visible,true);
 node('wise').checked=false;await node('wise').onchange();assert.equal(layers[0].alpha,0);assert.equal(catalogs[1].visible,true);
 const count=requests;node('wise').checked=true;await node('wise').onchange();assert.equal(requests,count);
 node('band').value='W2';await node('band').onchange();assert.equal(layers[0].alpha,0);assert.equal(layers[1].alpha,1);
 assert.equal(built,1);assert.equal(catalogs[0].visible,false);assert.equal(catalogs[1].visible,true);
 // A late Aladin failure must remain visible after hiding and showing the same band.
 node('wise').checked=false;await node('wise').onchange();node('wise').checked=true;await node('wise').onchange();
 layers[1].opts.errorCallback();assert(node('wisestatus').textContent.includes('No se pudo cargar AllWISE W2'));
 assert.equal(catalogs[1].visible,true);await node('retry').onclick();assert.equal(layers.length,3);assert.equal(layers[2].alpha,1);
 console.log(mode+' passed');
})().catch(err=>{console.error(err);process.exitCode=1});
