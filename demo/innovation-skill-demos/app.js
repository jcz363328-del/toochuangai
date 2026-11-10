'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const nf = new Intl.NumberFormat('zh-CN');
const df = new Intl.DateTimeFormat('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'});
const names = ['林晓','陈思远','王晨','李欣悦'];
let proposals = [
 {id:1,title:'AI 数据日报自动生成',person:'陈思远',department:'AI',category:'技术创新',date:'2026-11-02',status:'已采纳',points:10,description:'将常用数据查询整理为日报生成流程，自动汇总核心指标。\n\n预期价值：减少人工整理时间，让团队及时获取关键变化。'},
 {id:2,title:'内容生产智能质检工具',person:'林晓',department:'内容生产工厂',category:'工具提效',date:'2026-11-03',status:'已采纳',points:10,description:'把素材尺寸、命名和完整性检查整理为统一检查项。\n\n改善方案：提交素材时进行基础检查，集中提示需要调整的内容，减少重复人工核对。'},
 ...Array.from({length:10},(_,i)=>({id:i+3,title:['素材标签与复用流程优化','多平台内容一键分发','热点选题协同推荐','部门知识库检索优化','图片归档命名规范','提案评审反馈模板','素材下载与权限梳理','内容排期冲突提醒','重复报表自动合并','跨部门需求看板'][i],person:names[i%4],department:['内容生产工厂','AI','运营管理部'][i%3],category:['流程优化','工具提效','成本优化'][i%3],date:`2026-11-0${4+i%3}`,status:i%3===0?'推进中':'待评审',points:0,description:'围绕当前工作中的重复操作进行改善，通过流程梳理和工具辅助，减少沟通成本。\n\n本条为展示提案详情交互的示例内容。'})),
 {id:13,title:'历史素材索引整理',person:'王晨',department:'内容生产工厂',category:'流程优化',date:'2026-10-20',status:'已采纳',points:5,description:'整理历史素材索引，提升重复素材的查询与复用效率。'}
];
const params = new URLSearchParams(location.search);
let theme = ['blue','navy','green'].includes(params.get('theme'))?params.get('theme'):'blue';
let view = ['overview','proposals','points','stars'].includes(location.hash.slice(1))?location.hash.slice(1):'overview';
let status = ['all','待评审','推进中','已采纳'].includes(params.get('status'))?params.get('status'):'all';
let appliedStart = /^\d{4}-\d{2}-\d{2}$/.test(params.get('start')||'')?params.get('start'):'2026-11-01';
let appliedEnd = /^\d{4}-\d{2}-\d{2}$/.test(params.get('end')||'')?params.get('end'):'2026-11-30';
let toastTimer;
const escapeHtml = value => String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatDate = value => df.format(new Date(value+'T12:00:00+08:00'));
function syncUrl(){const p=new URLSearchParams({theme,status,start:appliedStart,end:appliedEnd});const search=$('#search');if(search?.value)p.set('q',search.value);history.replaceState(null,'',`?${p}#${view}`);}
function setTheme(next){theme=next;document.body.dataset.theme=theme;$$('[data-theme-choice]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.themeChoice===theme)));syncUrl();}
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('visible');toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
function dateRows(){return proposals.filter(p=>(!appliedStart||p.date>=appliedStart)&&(!appliedEnd||p.date<=appliedEnd));}
function visibleRows(){const q=$('#search')?.value.trim().toLowerCase()||'';return dateRows().filter(p=>(status==='all'||p.status===status)&&`${p.title} ${p.person} ${p.department}`.toLowerCase().includes(q)).sort((a,b)=>b.date.localeCompare(a.date)||b.id-a.id);}
function render(){
 const data=dateRows(),adopted=data.filter(p=>p.status==='已采纳').length;
 const labelStart=appliedStart||'全部日期',labelEnd=appliedEnd||'全部日期';
 if($('#dateLabel')) $('#dateLabel').textContent=`${labelStart} 至 ${labelEnd} · 已更新`;
 $('#total').textContent=nf.format(data.length);$('#adopted').textContent=nf.format(adopted);$('#rate').innerHTML=`${new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(data.length?adopted/data.length*100:0)}<em>%</em>`;
 const departments={},people={};data.filter(p=>p.points).forEach(p=>{departments[p.department]=(departments[p.department]||0)+p.points;people[p.person]=(people[p.person]||0)+p.points;});
 const dept=Object.entries(departments).sort((a,b)=>b[1]-a[1]);
 $('#bars').innerHTML=dept.length?dept.map(([name,value])=>`<div class="bar-row"><span>${escapeHtml(name)}</span><div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${value/Math.max(...dept.map(d=>d[1]))*100}%"></div></div><b>${nf.format(value)}</b></div>`).join(''):'<p class="chart-foot">所选时间内暂无部门积分记录。</p>';
 let lastPoints=-1,rank=0;$('#ranking').innerHTML=Object.entries(people).sort((a,b)=>b[1]-a[1]).map(([person,points],i)=>{if(points!==lastPoints)rank=i+1;lastPoints=points;return `<li><b>${rank}</b><span>${escapeHtml(person)}<small>${escapeHtml(data.find(p=>p.person===person).department)}</small></span><strong>${nf.format(points)} 分</strong></li>`;}).join('')||'<li>所选时间内暂无积分记录。</li>';
 const rows=visibleRows();const rowsEl=$('#rows');if(rowsEl)rowsEl.innerHTML=rows.map(p=>`<tr><td>${escapeHtml(p.title)}</td><td>${escapeHtml(p.person)}<small>${escapeHtml(p.department)}</small></td><td>${escapeHtml(p.category)}</td><td>${formatDate(p.date)}</td><td><span class="badge ${p.status==='已采纳'?'adopted':p.status==='推进中'?'progress':''}">${p.status}</span></td><td><button class="detail-link" data-detail="${p.id}" aria-label="查看${escapeHtml(p.title)}详情">查看</button></td></tr>`).join('');
 const empty=$('#empty');if(empty)empty.hidden=rows.length>0;const count=$('#count');if(count)count.textContent=`共 ${nf.format(rows.length)} 项提案`;
 $$('[data-status]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.status===status)));
 $$('[data-period]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.period==='month'?appliedStart==='2026-11-01'&&appliedEnd==='2026-11-30':!appliedStart&&!appliedEnd)));
}
function setView(next){view=next;$$('nav [data-view]').forEach(a=>{if(a.dataset.view===view)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});const overviewVisible=['overview','proposals'].includes(view);$('.overview-content').hidden=!overviewVisible;$('.reference-charts').hidden=!overviewVisible;const proposalSection=$('.proposal-section');if(proposalSection)proposalSection.hidden=!overviewVisible;$('.points-content').hidden=view!=='points';$('.stars-content').hidden=view!=='stars';$('#filters').hidden=['points','stars'].includes(view);const titles={overview:['创新数据看板','从提案规模、有效率、积分贡献、人员表现和创新方向全面管理团队创新活力。'],proposals:['承接管理','看板保留核心统计，承接处理从顶部入口进入。'],points:['个人积分','每一份贡献，都有迹可循。'],stars:['创新星主场','让优秀的实践，被更多人看见。']};$('#sectionTitle').textContent=titles[view][0];$('#sectionDescription').textContent=titles[view][1];syncUrl();}
function openDetails(id){const p=proposals.find(p=>p.id===Number(id));if(!p)return;$('#detailTitle').textContent=p.title;$('#detailMeta').textContent=`${p.person} · ${p.department} · ${formatDate(p.date)} · ${p.status}`;$('#detailBody').textContent=p.description;$('#detailDialog').showModal();}
$$('[data-theme-choice]').forEach(b=>b.addEventListener('click',()=>setTheme(b.dataset.themeChoice)));
$$('[data-view]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();setView(a.dataset.view);$('#dashboard').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}));
$$('[data-create]').forEach(b=>b.addEventListener('click',()=>$('#createDialog').showModal()));
$$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
document.addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b)openDetails(b.dataset.detail);});
document.querySelector('[data-action="rebind"]')?.addEventListener('click',()=>toast('身份已更新：林晓 · 内容生产工厂'));
$('#filters').addEventListener('submit',e=>{e.preventDefault();const start=$('#start').value,end=$('#end').value;if(start&&end&&start>end){$('#dateError').textContent='结束日期应晚于或等于开始日期，请调整日期。';$('#end').focus();return;}$('#dateError').textContent='';appliedStart=start;appliedEnd=end;render();syncUrl();toast('已应用日期筛选');});
$$('[data-period]').forEach(b=>b.addEventListener('click',()=>{appliedStart=b.dataset.period==='month'?'2026-11-01':'';appliedEnd=b.dataset.period==='month'?'2026-11-30':'';$('#start').value=appliedStart;$('#end').value=appliedEnd;$('#dateError').textContent='';render();syncUrl();}));
$$('[data-status]').forEach(b=>b.addEventListener('click',()=>{status=b.dataset.status;render();syncUrl();}));
$('#search')?.addEventListener('input',()=>{render();syncUrl();});
$('#reset')?.addEventListener('click',()=>{status='all';if($('#search'))$('#search').value='';appliedStart='';appliedEnd='';$('#start').value='';$('#end').value='';$('#dateError').textContent='';render();syncUrl();});
$('#createForm').addEventListener('submit',e=>{e.preventDefault();const f=new FormData(e.target);const title=f.get('title').trim(),description=f.get('description').trim();if(!title||!description){const field=!title?e.target.elements.title:e.target.elements.description;field.setCustomValidity('请输入内容，不能只填写空格。');field.reportValidity();return;}proposals.unshift({id:Math.max(...proposals.map(p=>p.id))+1,title,description,department:f.get('department'),category:f.get('category'),date:'2026-11-06',person:'林晓',status:'待评审',points:0});e.target.reset();$('#createDialog').close();status='all';if($('#search'))$('#search').value='';appliedStart='2026-11-01';appliedEnd='2026-11-30';$('#start').value=appliedStart;$('#end').value=appliedEnd;setView('overview');render();toast('提案已模拟提交，数据已计入看板');});
$('#createForm').addEventListener('input',e=>e.target.setCustomValidity?.(''));
$('#export').addEventListener('click',()=>{const cell=value=>'"'+String(value).replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')+'"';const csv=[['提案名称','提交人','部门','方向','日期','状态'],...visibleRows().map(p=>[p.title,p.person,p.department,p.category,p.date,p.status])].map(row=>row.map(cell).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob(['\uFEFF'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='创新提案-demo.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出当前筛选结果');});
window.addEventListener('beforeunload',e=>{if($('#createDialog').open&&($('#createForm').elements.title.value||$('#createForm').elements.description.value)){e.preventDefault();e.returnValue='';}});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(['overview','proposals','points','stars'].includes(next))setView(next);});
$('#start').value=appliedStart;$('#end').value=appliedEnd;if($('#search'))$('#search').value=params.get('q')||'';setTheme(theme);setView(view);render();

