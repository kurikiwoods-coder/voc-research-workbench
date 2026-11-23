"use strict";
const el = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pages = {checks:["连通性检查","pulse"],matrix:["验收矩阵","grid"],history:["运行记录","clock"],tokens:["额度中心","meter"]};
const labels = {PASS:"通过",FAIL:"失败",BLOCKED:"阻塞",PENDING:"待条件满足",NOT_TESTED:"未测试"};
const modes = {live_http:"真实 HTTP",configuration:"配置核验",local_sqlite:"SQLite 回读",contract_check:"契约校验",local_gate:"阶段判定",synthetic_fault_drill:"合成故障演练",synthetic_smoke:"合成召回测试",local_error:"本地异常"};
const sources = {tavily:"Tavily 搜索",brave:"Brave 搜索",forum_search:"论坛公开检索",forum_post:"公开原话快照",jev_admission:"Jev 调用条件",jev_shard:"Jev 分片响应",schema_gap:"响应契约缺口",sqlite_readback:"SQLite 持久化",outbound_isolation:"外发隔离演练",global_recall:"跨品类向量召回",stage_gate:"阶段准入判定",probe_error:"执行异常"};
const detailLabels = ["固定 jev-1.14.0 · 11 道判断","Choice / Score / Noul","发现 URL · 许可原文","SQLite · 分片用量","外发闸门 · 故障演练","全局 Top-K · 跨品类检索"];
const paths = {
 pulse:"M3 13h4l3-8 5 15 3-9h3",grid:"M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
 clock:"M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2",meter:"M3 17a9 9 0 0 1 18 0 M12 15l5-6 M5 20h14",
 play:"M7 4l13 8-13 8z",file:"M5 3h10l4 4v14H5z M14 3v6h5 M8 13h8 M8 16h6",branch:"M6 3v14a3 3 0 1 0 3 3 M6 11h7a5 5 0 0 0 5-5 M15 6a3 3 0 1 0 6 0 3 3 0 0 0-6 0",shield:"M12 3l8 3v6c0 5-4 8-8 10-4-2-8-5-8-10V6z M8 12l3 3 5-6",arrow:"M5 12h14 M13 6l6 6-6 6",download:"M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5",sliders:"M3 6h9m4 0h5 M3 18h3m4 0h11 M12 3v6 M7 15v6"};
const ic = key => `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[key]||paths.file}"/></svg>`;
let state=null, current=pages[location.hash.slice(1)]?location.hash.slice(1):"checks", selected=null, audit=null, busy=false, busyLabel="", checkFilter="ALL", search="", stage="ALL", statusFilter="ALL";
const number = n=>n==null?"—":new Intl.NumberFormat("zh-CN").format(n);
const ts = (value,short=false)=>value?new Intl.DateTimeFormat("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",...(short?{}:{second:"2-digit"}),hour12:false}).format(new Date(value)):"未记录";
const badge = s=>`<span class="status ${esc(s)}" title="${esc(s)}">${esc(labels[s]||s)}</span>`;
const act = (a,t,kind="secondary",attr="")=>`<button class="${kind}" data-action="${a}" ${attr}>${t}</button>`;
const link = (href,label)=>`<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
const getRows = ()=>state.requirements.filter(r=>r.requirement_id.startsWith("C0-"));
const getRow = id=>state.requirements.find(r=>r.requirement_id===id);
const refsFor = r=>(audit?.attempts||[]).flatMap(a=>a.evidence).filter(e=>r?.evidence.includes(e.id));
const newestEvidence = ()=>(audit?.attempts||[]).at(-1)?.evidence||[];
const tell = msg=>{el("toast").textContent=msg;el("toast").classList.add("active");clearTimeout(tell.t);tell.t=setTimeout(()=>el("toast").classList.remove("active"),3500)};
async function api(url,options){
 const response=await fetch(url,{cache:"no-store",...options});
 if(!response.ok){let message="本地服务暂时不可用";try{const data=await response.json();if(typeof data.detail==="string")message=data.detail}catch{}throw new Error(message+"（"+response.status+"）")}
 return response.json();
}
async function refresh(id=selected){
 const data=await api("/api/workspace"+(id?"?run_id="+encodeURIComponent(id):""));
 const evidence=data.selected?await api("/api/runs/"+data.selected.id+"/evidence"):null;
 state=data;selected=data.selected?.id||null;audit=evidence;render();
}
function nav(){
 el("nav").innerHTML=Object.entries(pages).map(([key,[name,icon]])=>`<a class="navlink" href="#${key}" ${current===key?'aria-current="page"':""}>${ic(icon)}${name}</a>`).join("");
 el("crumb").textContent=pages[current][0]; document.title=pages[current][0]+" · VOC 研究工作台";
}
function renderQuota(){
 const t=state.token,pct=Math.min(100,Math.max(0,t.percent||0));
 el("top-token").innerHTML=`<button class="token-open" data-action="token-view" aria-label="查看 Jev Token Center">${ic("meter")}<span><strong>Jev Token Center</strong><small>${esc(t.warning||(t.remaining==null?"额度未同步":number(t.remaining)+" 剩余"))}</small></span><span class="minibar ${t.percent==null?"unknown":""}"><i style="width:${pct}%"></i></span><small class="desktop-token">消耗 ${number(t.input_tokens)}<br>${t.last_synced_at?"同步 "+esc(ts(t.last_synced_at,true)):"最近同步 —"}</small></button><a class="small-link" href="${esc(t.purchase_url)}" target="_blank" rel="noopener noreferrer">补充额度 ↗</a>`;
}
function head(kicker,title,subtitle,buttons=""){
 return `<section class="page-head"><div><div class="kicker">${kicker}</div><h1>${title}</h1><p>${subtitle}</p></div><div class="actions">${buttons}</div></section>`;
}
function shellPanel(title,subtitle,inside){
 return `<section class="panel"><div class="panel-head"><div><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:""}</div></div>${inside}</section>`;
}
function stageList(){
 return `<section class="panel side-panel"><div class="panel-head"><h3>阶段进度</h3></div><div class="body">${[["P0-0","技术连通","本批"],["P0","核心闭环","待准入"],["P1","完整分析","待准入"],["P2","扩展研究","待准入"]].map(([id,label,s],i)=>`<div class="stage-line"><i class="stage-dot ${i?"":"current"}"></i><b>${id}</b><span>${label}</span><small class="faint">${s}</small></div>`).join("")}</div></section>`;
}
function recentSide(){
 const wanted=["forum_post","outbound_isolation","global_recall"], rows=newestEvidence().filter(e=>wanted.includes(e.name));
 const items=rows.map(e=>`<button class="evi-link" data-action="one-evidence" data-id="${e.id}"><span class="tiny-icon">${ic(e.name==="forum_post"?"file":e.name==="global_recall"?"branch":"shield")}</span><span><span class="row-name">${esc(sources[e.name])}</span><span class="row-sub">${esc(modes[e.mode])} · ${e.status_code?"HTTP "+e.status_code:ts(e.checked_at,true)}</span></span></button>`).join("");
 return `<aside class="side"><section class="panel side-panel"><div class="panel-head"><h3>本批证据</h3></div><div class="body">${items||'<p class="support">运行后可查看原话快照、隔离演练和召回结果。</p>'}</div></section>${stageList()}</aside>`;
}
function checks(){
 const rows=getRows(), gate=getRow("G-1"), count=s=>rows.filter(r=>r.status===s).length;
 const options=[["ALL","全部",6],["BLOCKED","阻塞",count("BLOCKED")],["PASS","通过",count("PASS")]];
 if(count("FAIL"))options.push(["FAIL","失败",count("FAIL")]);
 const displayed=rows.filter(r=>checkFilter==="ALL"||r.status===checkFilter);
 const title=busy?"正在执行检查":gate.status==="PASS"?"P0 准入已通过":gate.status==="NOT_TESTED"?"等待首次运行":"P0 准入暂缓";
 const desc=busy?"正在运行预设探针并保存响应，可继续查看已保存的证据。":gate.status==="NOT_TESTED"?"运行六项前置检查，建立第一份验收记录。":gate.status==="PASS"?"同一批次的六项检查和供应商审查均已通过。":`已通过 ${count("PASS")} 项，阻塞 ${count("BLOCKED")} 项${count("FAIL")?"，失败 "+count("FAIL")+" 项":""}。可逐项查看原因与取证记录。`;
 const runButton=act("run",ic("play")+(busy?"执行中…":"运行检查"),"primary",busy?"disabled":"");
 const hero=`<section class="hero"><div><span class="eyebrow">G-1　阶段准入</span><h2>${title}</h2><p>${desc}</p></div><div class="trackbox"><div class="tracklabel"><span>本批检查通过数</span><strong>${count("PASS")} <small>/ 6</small></strong></div><div class="segments">${rows.map(r=>`<button class="segment ${r.status}" data-action="detail" data-id="${r.requirement_id}" aria-label="${esc(r.requirement_id+" "+labels[r.status])}"></button>`).join("")}</div><div class="trackfoot"><span>C0-1</span><span>C0-6</span></div></div></section>`;
 const list=`<div class="chips" aria-label="按检查状态筛选">${options.map(([val,name,n])=>act("filter-check",name+" "+n,"chip "+(checkFilter===val?"on":""),'data-id="'+val+'" aria-pressed="'+(checkFilter===val)+'"')).join("")}</div><div class="wide-table"><table class="table workbench-table"><thead><tr><th>编号</th><th>检查项</th><th>状态</th><th>证据</th></tr></thead><tbody>${displayed.map(r=>`<tr class="check-row"><td class="id">${r.requirement_id}</td><td><span class="row-name">${esc(r.title)}</span><span class="row-sub">${esc(detailLabels[Number(r.requirement_id.at(-1))-1])}</span></td><td>${badge(r.status)}</td><td>${act("detail","查看 ›","link",'data-id="'+r.requirement_id+'" aria-label="查看 '+r.requirement_id+' 证据"')}</td></tr>`).join("")}</tbody></table></div>${displayed.length?"":'<div class="state-box"><b>此筛选下没有检查项</b>可切换到全部检查。</div>'}`;
 return head("P0-0 / CONNECTIVITY","连通性检查","核验外部服务、数据隔离与跨品类召回。",act("config",ic("sliders")+"连接配置")+runButton)+hero+
 `<div class="workspace-grid">${shellPanel("检查清单","同批次的技术验收与执行证据",list)}${recentSide()}</div><div class="footerline"><span>${selected?"批次 "+esc(selected.slice(0,8))+" · "+esc(ts(state.selected.started_at)):"尚无运行批次"}</span><span>验收分母 6 项 · 正式研究样本 0 条</span></div>`;
}
function choices(values,val){return values.map(([id,label])=>`<option value="${esc(id)}" ${id===val?"selected":""}>${esc(label)}</option>`).join("")}
function filteredMatrix(){
 const q=search.trim().toLowerCase();return state.requirements.filter(r=>(stage==="ALL"||stage===r.stage)&&(statusFilter==="ALL"||statusFilter===r.status)&&(!q||[r.requirement_id,r.title,r.description].join(" ").toLowerCase().includes(q)));
}
function matrixRows(){
 const rows=filteredMatrix();return `<div class="wide-table"><table class="table matrix-table"><thead><tr><th>需求编号</th><th>阶段</th><th>验收项</th><th>状态</th><th>明细</th></tr></thead><tbody>${rows.map(r=>`<tr><td class="id">${esc(r.requirement_id)}</td><td class="id">${esc(r.stage)}</td><td>${esc(r.title)}</td><td>${badge(r.status)}</td><td>${act("detail","查看 ›","link",'data-id="'+esc(r.requirement_id)+'"')}</td></tr>`).join("")}</tbody></table></div>${rows.length?"":'<div class="state-box"><b>没有匹配的需求</b>请调整关键词或筛选条件。</div>'}`;
}
function matrix(){
 const inputs=`<div class="tools"><input class="field search" id="matrix-search" aria-label="搜索验收项" placeholder="搜索编号或关键词" value="${esc(search)}"><select class="field" id="stage-filter" aria-label="阶段筛选">${choices([["ALL","全部阶段"],...["P0-0","P0","P1","P2"].map(s=>[s,s])],stage)}</select><select class="field" id="status-filter" aria-label="状态筛选">${choices([["ALL","全部状态"],...Object.entries(labels)],statusFilter)}</select></div><div id="matrix-rows">${matrixRows()}</div>`;
 return head("REQUIREMENTS / PDT 1.3.1","验收矩阵","按编号、阶段和状态查找需求，追溯实现位置、测试与证据。",act("export-matrix",ic("download")+"导出矩阵"))+shellPanel("需求映射","共 "+state.requirements.length+" 项 · 专案 v2.2 与 PDT v1.3.1",inputs);
}
function history(){
 const rows=state.history;
 const body=rows.length?`<div class="wide-table"><table class="table matrix-table"><thead><tr><th>批次 / 开始时间</th><th>供应商</th><th>执行次数</th><th>准入结果</th><th>操作</th></tr></thead><tbody>${rows.map(r=>`<tr><td><b class="mono">${esc(r.id.slice(0,8))}</b><span class="row-sub">${esc(ts(r.started_at))}</span></td><td>${esc(r.provider)}</td><td>${r.attempts}</td><td>${badge(r.gate||"NOT_TESTED")}</td><td>${act("open-run","查看批次 ›","link",'data-id="'+r.id+'"')}</td></tr>`).join("")}</tbody></table></div>`:'<div class="state-box"><b>还没有运行记录</b>从连通性检查页运行第一批检查。</div>';
 return head("AUDIT / RUNS","运行记录","每次执行保存独立记录，原始证据可在离线时回看。",act("goto-checks","返回检查"))+shellPanel("本地批次","按最新开始时间排列",body);
}
function tokens(){
 const t=state.token;
 const stats=[[t.unit==="input tokens"?"供应商剩余额度":"供应商账户余额",number(t.remaining),t.remaining==null?"未同步":"响应头余额"],["本机累计消耗",number(t.input_tokens),"按唯一成功分片合计 · input tokens"],["最近余额同步",t.last_synced_at?ts(t.last_synced_at,true):"—",t.last_synced_at?"供应商响应头":"等待可信余额记录"]];
 const metrics=`<div class="metrics">${stats.map(([a,b,c])=>`<div class="metric"><span>${esc(a)}</span><b>${esc(b)}</b><small>${esc(c)}</small></div>`).join("")}</div>`;
 const table=t.records.length?`<div class="wide-table"><table class="table"><thead><tr><th>批次</th><th>分片</th><th>输入 tokens</th><th>状态</th><th>时间</th></tr></thead><tbody>${t.records.map(r=>`<tr><td>${act("open-run",esc(r.run_id.slice(0,8)),"link",'data-id="'+r.run_id+'"')}</td><td>${r.shard_no}</td><td>${number(r.tokens)}</td><td>${esc(r.state)} · ${r.status_code||"—"}</td><td>${esc(ts(r.updated_at,true))}</td></tr>`).join("")}</tbody></table></div>`:'<div class="state-box"><b>本机账本暂无分片</b>真实 Jev 响应会在这里留下输入用量及同步依据。</div>';
 return head("JEV / TOKEN CENTER","额度中心",esc(t.provider)+" · "+esc(t.model)+" · 账户单位 "+esc(t.unit),act("refresh","刷新状态")+link(t.purchase_url,"补充额度"))+
 (t.warning?`<div class="warning">${esc(t.warning)} · 请核对供应商账户或查看最近分片。</div>`:"")+metrics+shellPanel("最近分片","按当前供应商与本机凭证隔离，最多 20 次。",table);
}
function render(){
 nav();renderQuota();el("main").innerHTML={checks,matrix,history,tokens}[current]();
}
function openDrawer(title,kicker,html){
 el("drawer-title").textContent=title;el("drawer-kicker").textContent=kicker;el("drawer-body").innerHTML=html;
 if(!el("drawer").open)el("drawer").showModal();el("drawer").scrollTop=0;
}
function evidenceCard(e,open=false){
 const obj=e.response, http=e.status_code==null?"未记录 HTTP":("HTTP "+e.status_code);
 const citation=e.name==="forum_post"&&obj.verified?`<blockquote lang="en">${esc(obj.text)}</blockquote><p>${link(obj.url,"原文")} · ${esc(obj.author)} · ${link(obj.license_url,obj.license)}<br>原文日期 ${esc(new Date(obj.published_at).toLocaleDateString("zh-CN"))} · 采样 ${esc(ts(e.checked_at))}</p>`:"";
 return `<details class="evidence-card" ${open?"open":""}><summary>${esc(sources[e.name]||e.name)}　<small>${esc(modes[e.mode]||e.mode)} · ${esc(http)}</small></summary>${citation}<p>记录 #${e.id} · ${esc(ts(e.checked_at))}</p><h4>脱敏请求</h4><pre>${esc(JSON.stringify(e.request,null,2))}</pre><h4>响应或本机结果</h4><pre>${esc(JSON.stringify(obj,null,2))}</pre></details>`;
}
function detail(id){
 const r=getRow(id);if(!r)return;
 const evidence=refsFor(r);
 const content=`<section class="drawer-section">${badge(r.status)}<p>${esc(r.detail||r.description)}</p>${r.blocker?`<div class="warning">${esc(r.blocker)}</div>`:""}<dl><dt>研究阶段</dt><dd>${esc(r.stage)}</dd><dt>最近核验</dt><dd>${esc(ts(r.last_checked_at))}</dd><dt>实现位置</dt><dd class="mono">${esc(r.implementation)}</dd><dt>测试用例</dt><dd class="mono">${esc(r.test_case)}</dd></dl></section><section class="drawer-section"><h3>验收标准</h3><p>${esc(r.description)}</p></section><section class="drawer-section"><h3>执行证据 · ${evidence.length}</h3>${evidence.map(e=>evidenceCard(e)).join("")||'<p>此项尚无执行证据。</p>'}</section>`;
 openDrawer(r.title,id+" / 验收详情",content);
}
function config(){
 const keys=Object.entries(state.config.key_names).map(([k,v])=>`<dt class="mono">${esc(k)}</dt><dd>${v?"已配置":"未配置"}</dd>`).join("");
 openDrawer("连接配置","本机服务",`<section class="drawer-section"><h3>后端环境变量</h3><p>在项目根目录复制 .env.example 为 .env，填写所选供应商的密钥，保存并重启本机服务。</p><dl style="grid-template-columns:minmax(145px,1fr) 1fr">${keys}</dl></section><section class="drawer-section"><h3>公开语料的留存审查</h3><p>当前供应商 ${esc(state.config.provider)} · ${state.config.review?"已核验":"待核验"}。将审核凭证保留在本机，并在 JEV_REVIEW_FILE 中填写本机路径。配置格式见仓库 docs/connectivity.md。</p><p>内部 CX 与非公开材料仅在本机处理。</p></section>`);
}
function save(name,content){
 const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:"application/json"}));
 const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
}
function runDialog(resume=false){
 const action=resume?"commit-resume":"commit-run";
 openDrawer(resume?"恢复此批次":"运行六项连接检查","P0-0 / 执行范围",`<section class="drawer-section"><h3>本次执行</h3><p>从许可来源检索一条公开原话，核验数据库，运行合成隔离与召回测试。已配置凭证并通过留存审查时，后台会向 ${esc(state.config.provider)} 发送最多两个固定分片，分别有 8 题和 3 题，产生供应商用量。重试遵守同一分片键。</p><p>${resume?"已成功的分片从原账本读取。":"检查记录保存在一个新批次。"} 全部诊断材料的正式研究分母为零。</p>${act(action,resume?"恢复执行":"开始运行","primary")}</section>`);
}
function batchInfo(){
 const info=state.selected;if(!info)return;
 const timeline=[...audit.attempts].reverse().map(a=>`<section class="drawer-section"><h3>执行 #${a.id} · ${esc(ts(a.started_at))}</h3>${a.evidence.map(e=>evidenceCard(e)).join("")}</section>`).join("");
 openDrawer("批次 "+info.id.slice(0,8),"运行记录",`<section class="drawer-section"><p class="mono">${esc(info.id)}</p><div class="actions">${act("export-audit",ic("download")+"导出证据")}${info.state!=="complete"?act("resume","恢复此批次","primary",busy?"disabled":""):""}</div></section>`+timeline);
}
async function execute(resume){
 if(busy)return;busy=true;el("drawer").close();current="checks";location.hash="checks";render();
 const storeKey="voc-pending-request";
 try{
  let key=sessionStorage.getItem(storeKey);if(!key){key=crypto.randomUUID();sessionStorage.setItem(storeKey,key)}
  const out=await api(resume?"/api/runs/"+selected+"/resume":"/api/runs",{method:"POST",headers:{"Content-Type":"application/json","X-VOC-Action":"connectivity"},...(!resume?{body:JSON.stringify({request_key:key})}:{})});
  sessionStorage.removeItem(storeKey);checkFilter="ALL";await refresh(out.run_id);tell("检查执行记录已保存");
 }catch(error){openDrawer("执行遇到问题","本机服务",`<section class="drawer-section"><p>${esc(error.message)}</p>${act("refresh","重新读取已有记录")}</section>`)}
 finally{busy=false;render()}
}
function gotoPage(page){if(el("drawer").open)el("drawer").close();location.hash=page;if(current===page)render()}
document.addEventListener("click",async event=>{
 const b=event.target.closest("[data-action]");if(!b)return;const a=b.dataset.action,id=b.dataset.id;
 try{
  if(a==="menu"){const open=el("rail").classList.toggle("open");b.setAttribute("aria-expanded",String(open));return}
  if(a==="close"){el("drawer").close();return}
  if(a==="refresh"||a==="retry-load"){await refresh();if(el("drawer").open)el("drawer").close();tell("已刷新本地记录");return}
  if(a==="config")config();
  if(a==="detail")detail(id);
  if(a==="token-view")gotoPage("tokens");
  if(a==="goto-checks")gotoPage("checks");
  if(a==="filter-check"){checkFilter=id;render()}
  if(a==="run"||a==="resume")runDialog(a==="resume");
  if(a==="commit-run"||a==="commit-resume")await execute(a==="commit-resume");
  if(a==="one-evidence"){const e=newestEvidence().find(x=>String(x.id)===id);if(e)openDrawer(sources[e.name],"本批证据",`<section class="drawer-section">${evidenceCard(e,true)}</section>`)}
  if(a==="open-run"){await refresh(id);batchInfo()}
  if(a==="export-audit"&&audit)save("voc-evidence-"+selected+".json",audit);
  if(a==="export-matrix")save("voc-requirements.json",filteredMatrix());
 }catch(error){tell(error.message)}
});
document.addEventListener("input",e=>{if(e.target.id==="matrix-search"){search=e.target.value;el("matrix-rows").innerHTML=matrixRows()}});
document.addEventListener("change",e=>{if(e.target.id==="stage-filter"||e.target.id==="status-filter"){stage=el("stage-filter").value;statusFilter=el("status-filter").value;el("matrix-rows").innerHTML=matrixRows()}});
window.addEventListener("hashchange",()=>{current=pages[location.hash.slice(1)]?location.hash.slice(1):"checks";el("rail").classList.remove("open");document.querySelector(".menu-btn").setAttribute("aria-expanded","false");if(state)render();window.scrollTo(0,0)});
function loadError(error){el("main").innerHTML=`<div class="panel state-box"><b>无法读取本地工作台</b><p>${esc(error.message)}</p>${act("retry-load","重新读取")}</div>`}
nav();refresh(null).catch(loadError);
