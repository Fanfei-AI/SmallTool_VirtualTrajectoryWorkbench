const $=id=>document.getElementById(id);
const message=t=>$('message').textContent=t;
let map,markers=[],pins=[],base,routeLine,trailLine,dot,active=false,busy=false,runPid=null,trail=[],lastTime=0,routeLoaded=false,routeVersion=null;
let selectedPin=null,movingPin=null,insertingPin=null,pointMenuOpen=false;
let startRequestPending=false,statusRevision=0;
function showLoading(loading){$('mapLoading').hidden=!loading;$('mapLoading').setAttribute('aria-busy',String(loading));$('start').textContent=loading?'连接中…':'启动轨迹';}
async function api(path,body){const r=await fetch('/api/'+path,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'请求失败');return data;}
function pace(id){const raw=$(id+'Minutes').value.trim(),minutes=Number(raw);if(!raw||!Number.isFinite(minutes)||minutes<0.5||minutes>120)throw Error('配速请输入 0.5～120 分钟，可使用小数。');return minutes;}
function setPace(id,value){$(id+'Minutes').value=value;}
function fmt(p){let s=Math.round(p*60);return `${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}
function config(){return {pins,paceMin:pace('paceMin'),paceMax:pace('paceMax'),jitter:+$('jitter').value,pinJitter:+$('pinJitter').value,hz:+$('hz').value,loopEnabled:$('loopEnabled').checked,loopStart:Number($('loopStart').value)};}
function lock(){document.querySelectorAll('input').forEach(e=>e.disabled=active||busy);for(const id of ['start','save','cancelMove'])$(id).disabled=active||busy;$('parameterMask').hidden=!active;$('parameterContent').inert=active||busy;$('parameterArea').classList.toggle('is-locked',active);$('stop').classList.toggle('is-running',active);if((active||busy)&&(selectedPin!==null||movingPin!==null||insertingPin!==null)){selectedPin=null;movingPin=null;insertingPin=null;map.closePopup();redraw();}}
function updateEditHint(){
  $('mapEditHelp').hidden=movingPin===null&&insertingPin===null;
  $('cancelMove').hidden=movingPin===null&&insertingPin===null;$('cancelMove').textContent=insertingPin!==null?'取消插入':'取消移动';
  $('map').classList.toggle('moving',movingPin!==null||insertingPin!==null);
  $('editHint').textContent=insertingPin!==null?`请点击地图，在第 ${insertingPin+1} 点之前插入新点。`:movingPin!==null?`请左键点击地图，设置第 ${movingPin+1} 点的新位置；编号不变。`:'左键点击地图新增点；右键点击已有点，直接选择编辑或移动。';
}
function removePin(i){
  if(active||busy)return;
  const loopStart=Number($('loopStart').value);
  pins.splice(i,1);
  if(i+1<loopStart)$('loopStart').value=loopStart-1;
  selectedPin=null;movingPin=null;insertingPin=null;map.closePopup();redraw();
}
function selectPin(i){
  if(active||busy)return;
  selectedPin=i;movingPin=null;insertingPin=null;redraw();
  const menu=document.createElement('div');menu.className='pin-menu';
  const title=document.createElement('strong');title.textContent=`已选中第 ${i+1} 点`;menu.append(title);
  for(const [label,handler] of [['编辑',()=>editPin(i)],['移动',()=>{movingPin=i;map.closePopup();updateEditHint();}],['删除',()=>removePin(i)],['在此点之前插入一个点',()=>{insertingPin=i;movingPin=null;map.closePopup();updateEditHint();}]]){const button=document.createElement('button');button.textContent=label;button.onclick=()=>{if(!active&&!busy)handler();};menu.append(button);}
  L.DomEvent.disableClickPropagation(menu);L.DomEvent.disableScrollPropagation(menu);
  markers[i].bindPopup(menu,{closeOnClick:false}).on('popupclose',()=>{pointMenuOpen=false;}).openPopup();
  pointMenuOpen=true;
}
function editPin(i){
  if(active||busy)return;
  const form=document.createElement('div');form.className='pin-editor';
  const title=document.createElement('strong');title.textContent=`编辑第 ${i+1} 点`;form.append(title);
  const inputs=['纬度','经度'].map((name,k)=>{const label=document.createElement('label');label.textContent=name;const input=document.createElement('input');input.type='number';input.step='any';input.value=pins[i][k];label.append(input);form.append(label);return input;});
  const error=document.createElement('div');error.setAttribute('role','status');form.append(error);
  const save=document.createElement('button');save.textContent='应用坐标';save.onclick=()=>{if(active||busy)return;const values=inputs.map(input=>Number(input.value));if(inputs.some(input=>!input.value.trim())||!values.every(Number.isFinite)||Math.abs(values[0])>85||Math.abs(values[1])>180){error.textContent='请输入有效坐标：纬度 -85～85，经度 -180～180。';return;}pins[i]=values;map.closePopup();redraw();message(`第 ${i+1} 点已更新，请保存设置。`);};form.append(save);
  const remove=document.createElement('button');remove.textContent='删除这个点';remove.className='danger';remove.onclick=()=>removePin(i);form.append(remove);
  L.DomEvent.disableClickPropagation(form);L.DomEvent.disableScrollPropagation(form);markers[i].setPopupContent(form);
}
function mapPoint(ll){
  if(active||busy)return;
  if(pointMenuOpen){pointMenuOpen=false;selectedPin=null;map.closePopup();redraw();return;}
  if(insertingPin!==null){const i=insertingPin; pins.splice(i,0,[ll.lat,ll.lng]);if(i+1<=Number($('loopStart').value))$('loopStart').value=Number($('loopStart').value)+1;insertingPin=null;selectedPin=i;map.closePopup();redraw();message(`已插入为第 ${i+1} 点，后续编号顺延。请保存设置。`);return;}
  if(movingPin!==null){const i=movingPin;pins[i]=[ll.lat,ll.lng];movingPin=null;selectedPin=i;map.closePopup();redraw();message(`第 ${i+1} 点位置已替换，仍是第 ${i+1} 点。请保存设置。`);}
  else{selectedPin=null;map.closePopup();pins.push([ll.lat,ll.lng]);redraw();}
}
function applyConfig(c){
  pins=c.pins.map(p=>[...p]);selectedPin=null;movingPin=null;insertingPin=null;map.closePopup();
  $('loopEnabled').checked=!!c.loopEnabled;$('loopStart').value=c.loopStart||1;
  setPace('paceMin',c.paceMin);setPace('paceMax',c.paceMax);
  for(const k of ['jitter','pinJitter','hz'])$(k).value=c[k];
  redraw();routeLine.setLatLngs([]);trailLine.setLatLngs([]);trail=[];dot.setStyle({opacity:0,fillOpacity:0});
  if(pins.length)map.fitBounds(pins,{maxZoom:16,padding:[40,40]});
}
async function showHistory(){
  if(!$('settingsDialog').open)$('settingsDialog').showModal();$('historyList').textContent='正在读取…';
  try{const records=await api('history');$('historyList').replaceChildren();
    if(!records.length)$('historyList').textContent='还没有历史记录。可从“保存设置”菜单中命名保存。';
    for(const record of records){const b=document.createElement('button');b.className='history-entry';b.textContent=`${record.name} · ${record.config.pins.length} 个点 · ${new Date(record.time*1000).toLocaleString()}`;
      b.onclick=async()=>{if(active||busy){$('historyNotice').textContent='请先停止当前任务，再载入历史设置。';return;}busy=true;lock();try{await api('save',record.config);applyConfig(record.config);$('settingsDialog').close();message(`已载入“${record.name}”，可直接启动。`);}catch(e){$('historyNotice').textContent=e.message;}finally{busy=false;lock();}};
      const row=document.createElement('div');row.className='history-row';
      const remove=document.createElement('button');remove.className='history-delete';remove.textContent='删除';remove.setAttribute('aria-label',`删除历史记录“${record.name}”`);
      remove.onclick=async()=>{
        if(remove.disabled)return;
        if(!window.confirm(`确定删除历史记录“${record.name}”吗？\n删除后无法恢复。当前页面的设置及正在运行的轨迹不受影响。`))return;
        remove.disabled=true;
        try{await api('history/delete',{id:record.id});$('historyNotice').textContent=`已删除“${record.name}”。`;await showHistory();}
        catch(e){$('historyNotice').textContent=e.message;remove.disabled=false;}
      };
      row.append(b,remove);$('historyList').append(row);
    }
  }catch(e){$('historyList').textContent=e.message;}
}
function openHistorySave(){if(active||busy)return;$('saveMenu').hidden=true;$('historyName').value='';$('nameError').textContent='';$('nameDialog').showModal();$('historyName').focus();}
async function saveHistory(event){
  event.preventDefault();if(active||busy)return;busy=true;lock();$('confirmHistory').disabled=true;
  try{await api('history',{name:$('historyName').value,config:config()});$('nameDialog').close();message('当前设置已命名保存到历史记录。');}
  catch(e){$('nameError').textContent=e.message;}finally{busy=false;lock();$('confirmHistory').disabled=false;}
}
function initMenus(){
  $('parameterMask').onclick=()=>{window.alert('轨迹正在运行，请先点击“停止并恢复真实定位”，再修改参数。');};
  $('openPrepare').onclick=()=>$('prepareDialog').showModal();
  $('closePrepare').onclick=()=>$('prepareDialog').close();
  $('save').onclick=()=>{if(active||busy)return;$('saveMenu').hidden=!$('saveMenu').hidden;};
  $('saveTemp').onclick=()=>{if(active||busy)return;$('saveMenu').hidden=true;action('save');};
  $('saveHistory').onclick=openHistorySave;
  $('settings').onclick=()=>{$('historyNotice').textContent='';showHistory();};
  $('closeSettings').onclick=()=>$('settingsDialog').close();
  $('cancelHistory').onclick=()=>$('nameDialog').close();
  $('historyForm').onsubmit=saveHistory;
  document.addEventListener('click',e=>{if(!e.target.closest('.save-wrap'))$('saveMenu').hidden=true;});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){insertingPin=null;movingPin=null;$('saveMenu').hidden=true;updateEditHint();}});
}
function redraw(){
  markers.forEach(m=>m.remove());markers=[];
  pins.forEach((p,i)=>{
    const m=L.marker(p,{draggable:false,bubblingMouseEvents:false,icon:L.divIcon({className:'pin-target'+(selectedPin===i?' selected':''),html:`<span class="pin-face">${i+1}</span>`,iconSize:[44,44],iconAnchor:[22,22],popupAnchor:[0,-16]})}).addTo(map);
    const element=m.getElement();
    element.title=`第 ${i+1} 点 · 右键编辑、移动、删除或插入`;
    element.setAttribute('aria-label',element.title);
    // Catch the native event before Leaflet redraws/removes the selected marker.
    element.addEventListener('contextmenu',event=>{event.preventDefault();event.stopPropagation();selectPin(i);});
    m.on('click',()=>{if(movingPin!==null||insertingPin!==null)mapPoint(m.getLatLng());});markers.push(m);
  });base.setLatLngs(pins);updateEditHint();
}
async function action(name){busy=true;lock();try{const body=name==='stop'?{}:config();if(name==='start'){startRequestPending=true;statusRevision++;showLoading(true);$('phase').textContent='正在连接手机…';}const r=await api(name,body);message(name==='save'?'设置已保存。':name==='start'?'正在接管定位并连接手机，请保持 USB 连接。':r.message);if(name==='start'){active=true;routeLoaded=false;trail=[];trailLine.setLatLngs([]);routeLine.setLatLngs([]);}if(name==='stop')active=true;}catch(e){if(name==='start'){showLoading(false);$('phase').textContent='启动未完成';}message(e.message);}finally{if(name==='start'){startRequestPending=false;statusRevision++;}busy=false;lock();}}
const names={idle:'尚未启动',connecting:'连接手机中…',running:'正在移动',holding_endpoint:'已到达 · 持续保持终点',simulation_cleared:'',failed:'定位任务出错',unresponsive:'连接状态未确认'};
async function poll(){const revision=statusRevision;try{const s=await api('status');if(startRequestPending||revision!==statusRevision)return;showLoading(s.phase==='connecting');active=['connecting','running','holding_endpoint','unresponsive'].includes(s.phase);lock();$('phase').textContent=names[s.phase]??s.phase;if(s.loop&&s.phase==='running')$('phase').textContent=s.lap>0?'循环中 · 第 '+s.lap+' 圈':'正在前往循环起点';$('phase').title=s.error||'';if(s.pid!==runPid){runPid=s.pid;routeLoaded=false;trail=[];lastTime=0;trailLine.setLatLngs([]);}if(s.route_version!==routeVersion){routeLoaded=false;}if(['running','holding_endpoint'].includes(s.phase)&&!routeLoaded){const r=await api('route');if(r.points.length){routeLine.setLatLngs(r.points);routeLoaded=true;routeVersion=s.route_version;}}if(s.latitude!==undefined&&s.time!==lastTime){const point=[s.latitude,s.longitude];dot.setStyle({opacity:1,fillOpacity:1});dot.setLatLng(point);if(!trail.length||L.latLng(trail[trail.length-1]).distanceTo(point)>.05)trail.push(point);if(trail.length>12000)trail.splice(0,2000);trailLine.setLatLngs(trail);lastTime=s.time;$('stats').textContent=`${s.latitude.toFixed(6)}, ${s.longitude.toFixed(6)}　｜　${(s.distance/1000).toFixed(2)} / ${(s.total/1000).toFixed(2)} km　｜　${s.pace?fmt(s.pace)+' / km':'静止保持'}`;}}catch(e){if(!startRequestPending&&revision===statusRevision){showLoading(false);$('phase').textContent='工作台连接中断';}}finally{setTimeout(poll,300);}}
async function init(){if(!window.L){message('地图组件加载失败，请检查网络后刷新页面。');return;}map=L.map('map',{attributionControl:false}).setView([20,0],2);const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);tiles.on('tileerror',()=>message('部分在线地图未加载，请检查网络。'));base=L.polyline([],{color:'#8498ae',weight:2,dashArray:'5 8'}).addTo(map);routeLine=L.polyline([],{color:'#1973e8',weight:4}).addTo(map);trailLine=L.polyline([],{color:'#0da684',weight:4}).addTo(map);dot=L.circleMarker([20,0],{radius:7,color:'#fff',weight:2,fillColor:'#ef553f',opacity:0,fillOpacity:0}).addTo(map);map.on('click',e=>mapPoint(e.latlng));$('cancelMove').onclick=()=>{if(active||busy)return;movingPin=null;insertingPin=null;updateEditHint();};initMenus();for(const name of ['start','stop'])$(name).onclick=()=>action(name);try{const c=await api('config');pins=c.pins;$('loopEnabled').checked=!!c.loopEnabled;$('loopStart').value=c.loopStart||1;setPace('paceMin',c.paceMin);setPace('paceMax',c.paceMax);for(const k of ['jitter','pinJitter','hz'])$(k).value=c[k];redraw();if(pins.length)map.fitBounds(pins,{maxZoom:16,padding:[40,40]});}catch(e){message(e.message);}poll();}
init();
