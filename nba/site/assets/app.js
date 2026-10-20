/* Beatn’ the Books · NBA. Every page loads data.js (window.EDGE, written by nba/board.py) and this file.
   The page to render comes from <main data-page="...">. Built from the NFL site's app.js (Oct 20, 2026): same look,
   bet tracker, pick log and search; days instead of weeks, a basketball court instead of a football field.
   Writing rule for this file: every number on screen says what it means in plain words
   (dollars on $100 bets, "chance to win", "better/worse than fair"), never a bare code. */
(function(){
'use strict';
const D=window.EDGE;
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const MINUS='−';
const odds=o=>o==null||!isFinite(o)?'—':(o>0?'+':MINUS)+Math.abs(Math.round(o));
const pct=p=>Math.round(p*100)+'%';
const signed=(x,d=1)=>(x>0?'+':x<0?MINUS:'')+Math.abs(x).toFixed(d);
const usd=v=>(v>0?'+':v<0?MINUS:'')+'$'+Math.round(Math.abs(v)).toLocaleString('en-US');
const per100=u=>usd(u*100);
const money=v=>(v>0?'+':v<0?MINUS:'')+'$'+Math.abs(v).toFixed(2);
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const WDAY=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const ymd=s=>{const [y,m,d]=s.split('-').map(Number); return new Date(Date.UTC(y,m-1,d));};
const fmtDay=s=>{const d=ymd(s); return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;};
const dayName=s=>{const d=ymd(s); return `${WDAY[d.getUTCDay()]}, ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;};
const dayTitle=s=>s===D.today?'Today':s===addDays(D.today,1)?'Tomorrow':s===addDays(D.today,-1)?'Yesterday':dayName(s);
const addDays=(s,n)=>{const d=ymd(s); d.setUTCDate(d.getUTCDate()+n); return d.toISOString().slice(0,10);};
const wkName=w=>{const r=((D.summary||{}).byWeek||[]).find(x=>x.wk===w); return `Week ${w}`+(r?` · ${fmtDay(r.from)}–${fmtDay(r.to)}`:'');};
const NAME={}; (D.teams||[]).forEach(t=>NAME[t.team]=t.name);
const TCOLOR={}; (D.teams||[]).forEach(t=>TCOLOR[t.team]=t.color);
const teamHref=t=>`teams.html#${encodeURIComponent(t)}`;
/* Team logos: ESPN's public dark-background set, on a round badge in the team's color. If a logo is blocked or fails,
   the badge shows the team's letters. (No NBA logo on purpose: on a betting site it would look like an official product.) */
const logo=(code,size='')=>`<span class="tl ${size}" style="--tc:${TCOLOR[code]||'#4c3a8f'}" aria-hidden="true"><b>${esc(code)}</b>`+
  `<img src="https://a.espncdn.com/i/teamlogos/nba/500-dark/${esc(String(code).toLowerCase())}.png" alt="" loading="lazy" decoding="async"></span>`;
const tcv=code=>`--tc:${TCOLOR[code]||'#4c3a8f'}`;
const withLogo=(code,name,size='xs')=>`<span class="tteam" style="${tcv(code)}">${logo(code,size)}${esc(name)}</span>`;
const inBadge=t=>t&&t.tagName==='IMG'&&t.parentElement&&t.parentElement.classList.contains('tl');
document.addEventListener('load',e=>{if(inBadge(e.target)) e.target.parentElement.classList.add('ok');},true);
document.addEventListener('error',e=>{if(inBadge(e.target)) e.target.remove();},true);
const day=s=>ymd(s).getTime()/864e5;
const plural=(n,w,ws)=>`${n} ${n===1?w:(ws||w+'s')}`;
const cls=v=>v>0?'ok':v<0?'no':'push';
/* Elo rating -> chance to beat an average team on a neutral court */
const vsAvg=r=>1/(1+Math.pow(10,-(r-1505)/400));
const tipTime=g=>g.ko.split(' · ')[1].replace(' CT','');

/* Spread in words. Line = expected home margin (positive = home team favored). */
function favorite(line,g){
  if(line==null) return null;
  if(line===0) return 'Pick ’em';
  const a=Math.abs(line), n=Number.isInteger(a)?a:a.toFixed(1);
  return line>0?`${g.homeName} by ${n}`:`${g.awayName} by ${n}`;
}
function vsFair(ev){
  if(ev==null) return '<span class="push">Different line, not comparable</span>';
  if(Math.abs(ev)<0.05) return '<span class="push">Same as fair</span>';
  return ev>0?`<span class="ok">${ev.toFixed(1)}% better than fair</span>`:`<span class="no">${Math.abs(ev).toFixed(1)}% worse than fair</span>`;
}

/* ======================= shared chrome ======================= */
/* Scoreboard strip above the header on every page: today's games (or the next game day), live during games (ESPN). */
function scoreStrip(){
  const d=D.currentDay, gs=D.games.filter(g=>g.day===d), bar=$('header.bar');
  if(!gs.length||!bar) return;
  let sb=$('#scoreStrip');
  if(!sb){ sb=document.createElement('div'); sb.id='scoreStrip'; sb.className='sb'; sb.setAttribute('aria-label','Scores'); bar.before(sb); }
  const tile=g=>{
    const L=liveOf(g), f=g.status==='final'||(L&&L.state==='post'), on=L&&L.state==='in';
    const hs=L?L.hs:g.hs, as=L?L.as:g.as, show=f||!!L;
    const st=f?'Final':on?L.detail:g.status==='live'?'In progress':tipTime(g);
    const row=(code,s,o)=>`<div class="sb-t ${f&&s<o?'lose':''}" style="${tcv(code)}">${logo(code,'xs')}<span class="sb-c">${esc(code)}</span>`
      +`${show?`<span class="sc">${s??''}</span>`:''}</div>`;
    return `<a class="sb-g ${on?'on':''}" href="index.html#day${g.day}"><span class="sb-st ${f?'final':on?'live':''}">`
      +`${on?'<span class="livedot"></span>':''}${esc(st)}</span>${row(g.away,as,hs)}${row(g.home,hs,as)}</a>`;
  };
  sb.innerHTML=`<div class="sb-in"><a class="sb-wk" href="index.html#day${d}">${esc(dayTitle(d))}<span>${plural(gs.length,'game')}</span></a>${gs.map(tile).join('')}</div>`;
}
function chrome(){
  scoreStrip();
  watchLive(()=>D.currentDay,()=>scoreStrip());
  $$('[data-stamp]').forEach(el=>el.textContent='Updated '+D.updatedLabel);
  $$('[data-foot]').forEach(el=>el.textContent=`Updated ${D.updatedLabel}. Kalshi and Polymarket prices as of that update.`);
}

/* ======================= line chart ======================= */
function lineChart(box, opt){
  const draw=()=>{
    const W=Math.max(300, box.clientWidth), H=opt.height||250;
    const narrow=W<520;
    const m={t:14,r:(opt.endLabels&&!narrow)?150:16,b:30,l:opt.left||56};
    const all=opt.series.flatMap(s=>s.points);
    if(!all.length){ box.innerHTML=`<p class="why">${esc(opt.empty||'No data yet.')}</p>`; return; }
    const xs=all.map(p=>p.x), ys=all.map(p=>p.y).concat(opt.refY!=null?[opt.refY]:[]).concat(opt.zero?[0]:[]);
    let x0=Math.min(...xs), x1=Math.max(...xs); if(x0===x1){x0-=1;x1+=1;}
    let y0=Math.min(...ys), y1=Math.max(...ys); if(y0===y1){y0-=1;y1+=1;}
    const ticks=niceTicks(y0,y1,5); y0=Math.min(y0,ticks[0]); y1=Math.max(y1,ticks[ticks.length-1]);
    const X=x=>m.l+(x-x0)/(x1-x0)*(W-m.l-m.r), Y=y=>m.t+(1-(y-y0)/(y1-y0))*(H-m.t-m.b);
    let s=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opt.label)}">`;
    ticks.forEach(t=>{ s+=`<line class="gridline" x1="${m.l}" x2="${W-m.r}" y1="${Y(t)}" y2="${Y(t)}"/>
      <text class="tick" x="${m.l-10}" y="${Y(t)+4}" text-anchor="end">${opt.yFmt?opt.yFmt(t):t}</text>`; });
    if(opt.zero&&y0<0&&y1>0) s+=`<line class="zero" x1="${m.l}" x2="${W-m.r}" y1="${Y(0)}" y2="${Y(0)}"/>`;
    if(opt.refY!=null){ s+=`<line class="ref" x1="${m.l}" x2="${W-m.r}" y1="${Y(opt.refY)}" y2="${Y(opt.refY)}"/>`;
      if(opt.refLabel) s+=`<text class="tick" x="${W-m.r}" y="${Y(opt.refY)-6}" text-anchor="end">${esc(opt.refLabel)}</text>`; }
    let last=-1e9;
    (opt.xTicks||[]).forEach(t=>{ const px=X(t.x); if(px<m.l-1||px>W-m.r+1||px-last<52) return; last=px;
      s+=`<text class="tick" x="${px}" y="${H-8}" text-anchor="middle">${esc(t.label)}</text>`; });
    opt.series.forEach(se=>{
      if(!se.points.length) return;
      const d=se.points.map((p,i)=>(i?'L':'M')+X(p.x).toFixed(1)+','+Y(p.y).toFixed(1)).join('');
      s+=`<path class="line s${se.n}" d="${d}"/>`;
      const e=se.points[se.points.length-1];
      s+=`<circle class="d${se.n}" cx="${X(e.x)}" cy="${Y(e.y)}" r="4.5"/>`;
      if(opt.endLabels&&!narrow) s+=`<text class="dlabel" x="${X(e.x)+10}" y="${Y(e.y)+4}">${esc(se.name)} ${esc(opt.yFmt?opt.yFmt(e.y):e.y)}</text>`;
    });
    s+=`<line class="cross" x1="0" x2="0" y1="${m.t}" y2="${H-m.b}" visibility="hidden"/>`;
    s+=`<rect x="${m.l}" y="0" width="${W-m.l-m.r}" height="${H}" fill="transparent"/></svg><div class="tip" hidden></div>`;
    box.innerHTML=s;
    const svg=box.querySelector('svg'), cross=svg.querySelector('.cross'), tip=box.querySelector('.tip');
    const move=ev=>{
      const r=svg.getBoundingClientRect(); const px=(ev.clientX-r.left);
      const xv=x0+(px-m.l)/(W-m.l-m.r)*(x1-x0);
      let best=null; all.forEach(p=>{ if(!best||Math.abs(p.x-xv)<Math.abs(best.x-xv)) best=p; });
      if(!best) return;
      const cx=X(best.x); cross.setAttribute('x1',cx); cross.setAttribute('x2',cx); cross.setAttribute('visibility','visible');
      tip.innerHTML=opt.tip(best.x); tip.hidden=false;
      const tw=tip.offsetWidth; tip.style.left=Math.min(Math.max(0,cx+12), W-tw)+'px'; tip.style.top='8px';
      if(cx+12+tw>W) tip.style.left=Math.max(0,cx-12-tw)+'px';
    };
    const leave=()=>{cross.setAttribute('visibility','hidden'); tip.hidden=true;};
    svg.addEventListener('pointermove',move); svg.addEventListener('pointerleave',leave);
  };
  draw();
  box._draw=draw;
  if(!box._bound){ box._bound=true; let t=null;
    window.addEventListener('resize',()=>{clearTimeout(t); t=setTimeout(()=>box._draw(),150);}); }
}
function niceTicks(a,b,n){
  const span=b-a, step0=span/n, mag=Math.pow(10,Math.floor(Math.log10(step0)));
  const step=[1,2,2.5,5,10].map(k=>k*mag).find(k=>span/k<=n)||10*mag;
  const out=[]; for(let v=Math.floor(a/step)*step; v<=b+step*0.999; v+=step) out.push(Math.round(v*1e6)/1e6);
  return out;
}
function monthTicks(d0,d1){
  const out=[]; const a=new Date(d0*864e5), b=new Date(d1*864e5);
  let y=a.getUTCFullYear(), mo=a.getUTCMonth()+1;
  while(Date.UTC(y,mo,1)<=b.getTime()){ if(mo>11){mo=0;y++;} out.push({x:Date.UTC(y,mo,1)/864e5,label:MONTHS[mo]}); mo++; }
  return out;
}

/* ---------- picks: built in Python (the NFL site's picks.py) so the same list feeds the cards, the log and the
   scoreboard. Each game's g.picks: best first by realistic edge (expected profit per $1 at that price). Started games
   show the suggestions logged before tip-off, graded at the price first shown (p.grade: units, beat the close). */
const EVID={gap:['gap','Price gap · unproven'],lean:['lean','Model pick · no proven edge'],spread:['lean','Model pick · no proven edge']};
const fmtLogged=s=>{const d=new Date(s+':00'); return isNaN(d)?s:`${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][d.getDay()]} ${MONTHS[d.getMonth()]} ${d.getDate()}, ${((d.getHours()+11)%12)+1}:${String(d.getMinutes()).padStart(2,'0')} ${d.getHours()<12?'AM':'PM'} CT`;};
const modelOnly=p=>p.edgeFrom==='lean'||p.edgeFrom==='spread';
const rankEdge=p=>p.edge;
const pickEdge=p=>modelOnly(p)&&p.model!=null
  ?`<span class="pedge model">${signed(p.model)}%<small> model edge</small></span>`
  :`<span class="pedge ${p.edge>0?'ok':'no'}">${signed(p.edge)}%<small> edge</small></span>`;
const logBtn=(g,p)=>`<button type="button" class="btn small logbet" data-gid="${esc(g.id)}" data-key="${esc(p.key)}">Log this bet</button>`;
/* "Kalshi ↗ / Polymarket ↗": the market's own page, read from each exchange's open listings at every site update. */
const betLinks=(g,p)=>{
  const L=g.links; if(!L) return '';
  const kx=L.kalshi&&L.kalshi[p.key.split('|')[0]], a=[];
  if(kx) a.push(['kalshi','Kalshi',kx]);
  if(L.polymarket) a.push(['poly','Polymarket',L.polymarket]);
  if(p.price&&/poly/i.test(p.price.book||'')) a.reverse();
  return a.map(([c,n,u])=>`<a class="xlink ${c}" href="${esc(u)}" target="_blank" rel="noopener noreferrer" title="Open this market on ${n}">${n} <span aria-hidden="true">↗</span></a>`).join('');
};
/* Live scores: the page reads ESPN's public scoreboard for a day while its games are on (every 30 s; every 5 min
   otherwise). Nothing is saved; results still come from the site's own updates. */
const LIVE=new Map();
const liveOf=g=>{const v=LIVE.get(g.id); return v&&v.state!=='pre'?v:null;};
async function fetchLive(games,d){
  if(!games.length) return [];
  const r=await fetch(`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=${d.replace(/-/g,'')}`);
  const j=await r.json(), changed=[];
  for(const e of j.events||[]){
    const g=games.find(x=>x.id===String(e.id)); if(!g) continue;
    const c=(e.competitions||[])[0]; if(!c) continue;
    const t={}; c.competitors.forEach(x=>{t[x.homeAway]=Number(x.score);});
    const s=c.status.type;
    const v={state:s.state, detail:s.shortDetail||s.detail||'', hs:t.home, as:t.away};
    if(JSON.stringify(LIVE.get(g.id))!==JSON.stringify(v)){ LIVE.set(g.id,v); changed.push(g); }
  }
  return changed;
}
const liveSubs=[];
let liveTimer=null, liveFirst=true;
const watchLive=(dayFn,onChange)=>liveSubs.push({dayFn,onChange});
async function liveTick(){
  clearTimeout(liveTimer);
  const now=new Date(), today=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
  let fast=false;
  for(const d of [...new Set(liveSubs.map(s=>s.dayFn()).filter(x=>x!=null))]){
    const gs=D.games.filter(g=>g.day===d);
    const due=d<=today&&gs.some(g=>g.status!=='final'&&!(LIVE.get(g.id)&&LIVE.get(g.id).state==='post'));
    if(!due||(document.hidden&&!liveFirst)) continue;
    try{
      const changed=await fetchLive(gs,d);
      if(changed.length) liveSubs.filter(s=>s.dayFn()===d).forEach(s=>s.onChange(changed,gs));
      if(gs.some(g=>(LIVE.get(g.id)||{}).state==='in')) fast=true;
    }catch(_){}
  }
  liveFirst=false;
  liveTimer=setTimeout(liveTick,fast?30000:300000);
}
document.addEventListener('visibilitychange',()=>{ if(!document.hidden) liveTick(); });
/* Unit sizing: 1 unit = D.unitPct (2%) of the Kalshi bankroll typed into My bets (kept in this browser only). */
const BANK_KEY='btb.kalshiBankroll', UPCT=()=>D.unitPct||2;
const bankroll=()=>{try{const v=Number(localStorage.getItem(BANK_KEY)); return v>0?v:null;}catch(_){return null;}};
const unitUsd=()=>{const b=bankroll(); return b?b*UPCT()/100:null;};
const fmtU=x=>`${+Number(x).toFixed(2)}u`;
const usdAmt=x=>'$'+(x<10?x.toFixed(2):Math.round(x).toLocaleString('en-US'));
const unitChip=p=>{ if(!p.units) return ''; const u=unitUsd();
  return `<span class="ustake" title="${fmtU(p.units)} = ${+(p.units*UPCT()).toFixed(2)}% of your Kalshi bankroll">${fmtU(p.units)}${u?` · ${usdAmt(p.units*u)}`:''}</span>`; };
const pctOf=u=>`${+(u*UPCT()).toFixed(2)}%`;
function unitKey(){
  const u=unitUsd(), row=(size,label,tag)=>`<span class="ukey-i"><b>${size}</b><span class="push">${pctOf(parseFloat(size))}</span>${tag?`<span class="tag ${tag}">${label}</span>`:esc(label)}</span>`;
  return `<div class="ukey" role="note"><span class="ukey-h">Unit key</span>
    <span class="ukey-i ukey-main"><b>1u</b> = <b>${UPCT()}%</b> of your Kalshi bankroll${u?` = <b>${usdAmt(u)}</b>`:''}</span>
    ${row('0.75u','Price gap the model agrees with','gap')}${row('0.5u','Price gap','gap')}
    ${row('0.25u','Model pick (no proven edge)','lean')}
    ${u?'':'<span class="ukey-i push">Enter your Kalshi bankroll in <a href="index.html#bets">My bets</a> to see dollar amounts.</span>'}</div>`;
}
const priceTxt=pr=>!pr?'':pr.cents!=null?`${Number(pr.cents).toFixed(0)}¢ on ${esc(pr.book)}`:`${odds(pr.odds)} at sportsbooks`;

/* ======================= day page ======================= */
function dayPage(){
  const days=[...new Set(D.games.map(g=>g.day))].sort();
  let cur=D.currentDay, filter='all';
  const m=location.hash.match(/^#day(\d{4}-\d\d-\d\d)$/); if(m&&days.includes(m[1])) cur=m[1];

  function rail(){
    $('#rail').innerHTML=days.map(d=>{const dt=ymd(d);
      return `<button type="button" class="wk day ${d===D.today?'cur':''}" data-day="${d}" aria-pressed="${d===cur}"><small>${WDAY[dt.getUTCDay()].slice(0,3)}</small>${MONTHS[dt.getUTCMonth()]} ${dt.getUTCDate()}</button>`;}).join('');
    const on=$('#rail .wk[aria-pressed="true"]'); if(on) on.scrollIntoView({block:'nearest',inline:'center'});
  }
  function chanceRow(label,pA,pH,cA,cH,g){
    return `<div class="crow"><span class="clab">${label}</span>
      <span class="track" role="img" aria-label="${label}: ${esc(g.awayName)} ${pct(pA)}, ${esc(g.homeName)} ${pct(pH)}">
        <span style="width:${pA*100}%;background:${cA}"></span><span style="width:${pH*100}%;background:${cH}"></span></span>
      <span class="cval"><b>${esc(g.away)} ${pct(pA)}</b> · <b>${esc(g.home)} ${pct(pH)}</b></span></div>`;
  }
  function restLine(g){
    const R=g.rest||{}, d=(n,b2b)=>b2b?'back-to-back (played yesterday)':n>=7?'first game of the season':`${n} days since last game`;
    const tag=R.hb2b||R.ab2b?'<span class="tag roof">Back-to-back</span>':'<span class="dot"></span>';
    return `<div class="sig ${R.hb2b||R.ab2b?'warn':'muted'}">${tag}<span><b>Rest:</b> ${esc(g.awayName)} ${d(R.away,R.ab2b)} · ${esc(g.homeName)} ${d(R.home,R.hb2b)}.
      ${R.hb2b||R.ab2b?'Our model takes about 1 point off a team on a back-to-back. The betting line already accounts for it: in testing, back-to-backs didn’t beat the closing price.':''}</span></div>`;
  }
  function leanLine(g){
    if(!g.mkt) return `<div class="sig muted"><span class="dot"></span><span><b>Model lean:</b> waiting for betting lines.</span></div>`;
    if(!g.mkt.lean) return `<div class="sig muted"><span class="dot"></span><span><b>Model lean:</b> none. Our model and the market roughly agree.</span></div>`;
    const t=g.mkt.lean==='home'?g.homeName:g.awayName;
    const price=g.mkt.leanCents!=null?`${g.mkt.leanCents.toFixed(0)}¢ on ${esc(g.mkt.leanBook)}`:odds(g.mkt.leanOdds);
    const r=(D.modelRecord||{}).ml;
    return `<div class="sig lean"><span class="tag lean">Model lean</span><span><b>${esc(t)}</b> at ${price}, expected return ${signed(g.mkt.leanEv)}% by our model’s count.
      No proven edge${r&&r.n?`: model picks this strong returned ${signed(r.roi)}% over ${r.n.toLocaleString('en-US')} bets in ${esc(r.seasons)} at the closing line`:''}. Our model doesn’t know who’s injured or resting; the market does.</span></div>`;
  }
  function shopBlock(g){
    const s=g.shop; if(!s) return '';
    const team=side=>side==='home'?g.homeName:g.awayName;
    const rows=[['ml','away',`${team('away')} to win`],['ml','home',`${team('home')} to win`],
      ['spread','away',null],['spread','home',null],['total','over',null],['total','under',null]]
      .map(([mk,side,label])=>{
        const x=s[mk]&&s[mk][side]; if(!x) return '';
        const lab=label||(mk==='spread'?`${team(side)} ${x.point>0?'+':''}${x.point}`:`${side==='over'?'Over':'Under'} ${x.point}`);
        return `<tr><td>${esc(lab)}</td><td class="n">${x.cents.toFixed(0)}¢</td><td>${esc(x.book)}</td><td>${vsFair(x.ev)}</td></tr>`;
      }).join('');
    if(!rows) return '';
    return `<div class="block"><div class="bh">Kalshi &amp; Polymarket prices <span class="why">(fees included) compared with the fair price: the middle of DraftKings, Kalshi and Polymarket</span></div>
      <div class="tablebox flat"><table class="mini"><thead><tr><th>Bet</th><th class="n">Price</th><th>Where</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }
  function injuryBlock(g){
    const I=g.injuries; if(!I||g.status==='final'||(liveOf(g)||{}).state==='post') return '';
    if(!(I.away||[]).length&&!(I.home||[]).length) return '';
    const side=(code,name,list)=>`<div class="iteam"><div class="ihead">${logo(code,'xs')}<b>${esc(name)}</b></div>${list.length
      ?list.map(p=>`<div class="iplayer" title="${esc(p.comment)}"><span class="ist ${p.status.toLowerCase().replace(/[^a-z]/g,'')}">${esc(p.status)}</span>
          <span><b>${esc(p.name)}</b> <span class="push">${esc(p.pos)}</span></span></div>`).join('')
      :'<div class="push small">Nobody listed</div>'}</div>`;
    return `<div class="block"><div class="bh">Injury report <span class="why">ESPN · our model doesn’t use it, the market does</span></div>
      <div class="injuries">${side(g.away,g.awayName,I.away||[])}${side(g.home,g.homeName,I.home||[])}</div></div>`;
  }
  function picksBlock(g){
    const P=g.picks||[], f=g.status==='final', started=g.status!=='upcoming'||!!liveOf(g);
    const good=P.filter(p=>p.good), weak=P.filter(p=>!p.good);
    const head=`<div class="bh">${f?'Picks before tip-off':started?'Picks (locked at tip-off)':'Bets to take'}
      <span class="why">best first by each kind of bet’s real record · edge = expected profit per $1 at that price (purple = our model’s own estimate, which runs high)</span></div>`;
    const res=u=>u==null?'':`<span class="pill ${cls(u)}">${u>0?'Won':u<0?'Lost':'Push'} ${per100(u)}</span>`;
    const clv=gr=>!gr||gr.beat==null?'':gr.clv!=null
      ?`<span class="pill ${gr.beat?'ok':'no'}">${gr.beat?'Beat':'Worse than'} the closing price ${signed(gr.clv)}%</span>`
      :`<span class="pill ${gr.beat?'ok':'no'}">${Math.abs(gr.clvPts)} pt ${gr.beat?'better':'worse'} than the closing line</span>`;
    const recTxt=p=>{const r=(D.modelRecord||{})[p.rec], s=((D.summary||{}).picks||{})[p.rec==='ml'?'lean':'spread'];
      const now=s&&s.n?` · this season <b>${s.won}–${s.lost}${s.push?'–'+s.push:''}</b>, <b class="${cls(s.units)}">${signed(s.units/s.n*100)}%</b> (${plural(s.n,'bet')})`:'';
      return r&&r.n?`<div class="prec">Model picks this strong: <b class="${cls(r.roi)}">${signed(r.roi)}%</b> over ${r.n.toLocaleString('en-US')} bets in ${esc(r.seasons)}${now}.</div>`:'';};
    const row=(p,i)=>`<div class="pick ${i===0?'top':''}"><span class="rank">${i+1}</span><div class="pmain">
      <div class="pline"><b>${esc(p.text)}</b><span class="pprice">${priceTxt(p.price)}</span>${unitChip(p)}${pickEdge(p)}</div>
      <div class="pwhy">${(p.src||[]).map(s=>EVID[s]?`<span class="tag ${EVID[s][0]}">${EVID[s][1]}</span>`:'').join('')}
        <span>${esc((p.why||[]).join(' · '))}</span>${p.grade?res(p.grade.units)+clv(p.grade):''}</div>${modelOnly(p)?recTxt(p):''}${started?'':`<div class="pact">${logBtn(g,p)}${betLinks(g,p)}</div>`}</div></div>`;
    const conflict=new Set(good.map(p=>p.key.split('|')[0])).size<good.length?
      '<div class="why">Two picks bet against each other on the same market: take the higher one, or pass.</div>':'';
    const none=!good.length?`<div class="nobet"><b>No bet${started?' was suggested':''}.</b> ${!g.mkt?'Waiting for betting lines.':started?'Nothing on this game showed a real edge before tip-off.':'Nothing on this game shows a real edge at the available prices, so pass.'}</div>`:'';
    const skip=weak.length&&!started?`<div class="skips"><span class="why">Not worth it at this price:</span> ${weak.map(p=>
      `<span class="skip">${esc(p.text)} <span class="no">${signed(p.edge)}%</span> ${EVID[p.src[0]]?`<span class="tag ${EVID[p.src[0]][0]}">${EVID[p.src[0]][1]}</span>`:''}</span>`).join('')}</div>`:'';
    const note=good.some(p=>p.reconstructed)?'<div class="why">Reconstructed at closing prices: this game was played before the site started saving its suggestions.</div>'
      :good.some(p=>p.logged)?`<div class="why">As shown ${esc(fmtLogged(good.map(p=>p.logged).sort()[0]))}, graded at that price.</div>`:'';
    return `<div class="block picks">${head}${good.map(row).join('')}${conflict}${none}${skip}${started?note:''}</div>`;
  }
  function results(g){
    if(g.status!=='final') return '';
    const winner=g.hs>g.as?g.homeName:g.awayName;
    const out=[];
    if('eloRight' in g){ const pick=g.pElo>=0.5?g.homeName:g.awayName;
      out.push(`<span class="pill ${g.eloRight?'ok':'no'}">${g.eloRight?'✓':'✗'} Model picked ${esc(pick)}</span>`); }
    if(g.mkt&&'mktRight' in g.mkt){ const fav=g.mkt.fair>=0.5?g.homeName:g.awayName;
      out.push(`<span class="pill ${g.mkt.mktRight?'ok':'no'}">${g.mkt.mktRight?'✓':'✗'} Market favored ${esc(fav)}</span>`); }
    const tot=g.total&&g.total.line!=null?` <span class="why">· ${g.hs+g.as} points, line was ${g.total.line} (${g.hs+g.as>g.total.line?'over':g.hs+g.as<g.total.line?'under':'push'})</span>`:'';
    return `<div class="results"><div class="rhead">${esc(winner)} won by ${Math.abs(g.hs-g.as)}${g.ot?' in overtime':''}${tot}</div>
      ${out.length?`<div class="pills">${out.join('')}</div><div class="why">Bet results are per $100 bet.</div>`:''}</div>`;
  }
  function card(g){
    const L=!(g.status==='final')&&liveOf(g), f=g.status==='final'||(L&&L.state==='post');
    const hs=L?L.hs:g.hs, as=L?L.as:g.as, aw=f&&as>hs, hw=f&&hs>as, showScore=f||!!L;
    const status=f?`<span class="chip final">Final${g.ot?' / OT':''}</span>`
      :L?`<span class="chip live"><span class="livedot"></span>Live · ${esc(L.detail)}</span>`
      :g.status==='live'?'<span class="chip live">In progress</span>':'';
    const kind=g.type==='POST'?'<span class="chip venue">Playoffs</span>':g.type==='PLAYIN'?'<span class="chip venue">Play-in</span>':'';
    const mk=g.mkt, sp=g.spread, tt=g.total;
    const fav=sp?favorite(sp.line,g):null, modelFav=favorite(g.eloLine,g);
    const notes=(g.notes||[]).map(n=>`<div class="note">${esc(n)}</div>`).join('');
    const moved=(o,c,fmt)=>o!=null&&c!=null&&o!==c?` · opened ${fmt(o)}`:'';
    const team=(code,name,score,win)=>`<div class="trow ${f?(win?'win':'lose'):''}" style="${tcv(code)}"><span class="tname">${logo(code)}<a href="${teamHref(code)}">${esc(name)}</a></span>${showScore?`<span class="score">${score}</span>`:''}</div>`;
    return `<article class="game ${g.gaps&&g.gaps.length?'sig-card':''}" id="g-${esc(g.id)}">
      <header class="ghead">
        <div class="gmeta"><span>${esc(g.ko)}</span>${status}${kind}${g.neutral?`<span class="chip venue">${esc(g.city||g.venue)}</span>`:''}</div>
        <div class="teams">${team(g.away,g.awayName,as,aw)}${team(g.home,g.homeName,hs,hw)}</div>
        <div class="why">${esc(g.awayName)} at ${esc(g.homeName)}</div>
      </header>
      <div class="gbody">
        ${picksBlock(g)}
        <div class="block"><div class="bh">Chance to win</div>
          ${chanceRow('Our model',1-g.pElo,g.pElo,'var(--away)','var(--home)',g)}
          ${mk?chanceRow('Betting market',1-mk.fair,mk.fair,'var(--mkt-away)','var(--mkt-home)',g):'<div class="crow"><span class="clab">Betting market</span><span class="why">No betting line yet</span></div>'}
        </div>
        <dl class="facts">
          <div><dt>Favorite (point spread)</dt><dd>${fav||'Not posted yet'}</dd><dd class="sub">Our model: ${modelFav}${moved(g.openSpread,sp&&sp.line,v=>favorite(v,g))}</dd></div>
          <div><dt>Total points line</dt><dd>${tt&&tt.line!=null?tt.line+' points':'Not posted yet'}</dd><dd class="sub">${tt&&tt.oo?`Over ${odds(tt.oo)} · Under ${odds(tt.uo)}`:'&nbsp;'}${moved(g.openTotal,tt&&tt.line,v=>v)}</dd></div>
          <div><dt>Moneyline odds</dt>${mk&&mk.aml!=null
            ?`<dd>${esc(g.awayName)} ${odds(mk.aml)}</dd><dd class="sub">${esc(g.homeName)} ${odds(mk.hml)}${g.lineSrc?` · ${esc(g.lineSrc)}`:''}</dd>`
            :`<dd>${mk?esc(g.homeName)+' '+pct(mk.fair)+' to win':'Not posted yet'}</dd><dd class="sub">${mk?'fair chance from Kalshi and Polymarket':'&nbsp;'}</dd>`}</div>
        </dl>
        ${injuryBlock(g)}
        ${shopBlock(g)}
        <div class="block signals"><div class="bh">Signals</div>${restLine(g)}${leanLine(g)}</div>
        ${notes?`<div class="block">${notes}</div>`:''}
      </div>
      ${f?`<footer class="gfoot">${results(g)}</footer>`:''}
    </article>`;
  }
  function bestBets(gs){
    const open=games=>games.filter(g=>g.status==='upcoming'&&!liveOf(g))
      .flatMap(g=>(g.picks||[]).filter(p=>p.good).map(p=>({g,p}))).sort((a,b)=>rankEdge(b.p)-rankEdge(a.p));
    let list=open(gs), ahead=null;
    if(!list.length&&cur===D.currentDay){                     // tonight's games all started: show the next day's
      const next=days.find(d=>d>cur&&open(D.games.filter(g=>g.day===d)).length);
      if(next){ list=open(D.games.filter(g=>g.day===next)); ahead=next; }
    }
    const wrap=$('#playsWrap');
    if(!list.length){
      const done=gs.flatMap(g=>(g.picks||[]).filter(p=>p.grade&&p.good));
      wrap.hidden=!done.length; if(!done.length) return;
      const u=done.reduce((s,p)=>s+p.grade.units,0), w=done.filter(p=>p.grade.won).length, l=done.filter(p=>p.grade.won===false).length;
      $('#playsTitle').textContent=`${dayTitle(cur)}’s picks`;
      $('#plays').className='plays';
      $('#plays').innerHTML=`<div class="bestsum">${plural(done.length,'pick')} graded · ${w}–${l} · <b class="${cls(u)}">${per100(u)}</b> on $100 bets <a href="season.html">Full scoreboard</a></div>`;
      return;
    }
    $('#playsTitle').textContent=ahead?`Best bets · next up, ${dayTitle(ahead)}`:`Best bets · ${dayTitle(cur)}`;
    wrap.hidden=false;
    const SHOW=8;
    $('#plays').className='plays';
    $('#plays').innerHTML=unitKey()+list.map(({g,p},i)=>`<div class="best ${i>=SHOW?'more':''}"><span class="rank">${i+1}</span>
      <div class="bmain"><div class="bline"><span class="duo">${logo(g.away,'sm')}${logo(g.home,'sm')}</span><b>${esc(p.text)}</b>
        <span class="pprice">${priceTxt(p.price)}</span>${unitChip(p)}</div>
        <div class="bwhy"><span>${esc(g.awayName)} at ${esc(g.homeName)} · ${esc(g.ko)}</span>
          ${(p.src||[]).map(s=>EVID[s]?`<span class="tag ${EVID[s][0]}">${EVID[s][1]}</span>`:'').join('')}</div></div>
      <div class="bedge">${pickEdge(p)}</div>
      <div class="bact">${betLinks(g,p)}${logBtn(g,p)}<a href="#g-${esc(g.id)}" data-goto="g-${esc(g.id)}">See game</a></div></div>`).join('')
      +(list.length>SHOW?`<button type="button" class="btn ghost small showall" data-showall>Show all ${list.length}</button>`:'');
  }
  function render(){
    rail();
    const gs=D.games.filter(g=>g.day===cur);
    const fin=gs.filter(g=>g.status==='final').length;
    const b2b=gs.filter(g=>g.rest&&(g.rest.hb2b||g.rest.ab2b)).length;
    const gaps=gs.filter(g=>g.status==='upcoming'&&g.gaps&&g.gaps.length);
    const picks=gs.filter(g=>(g.picks||[]).some(p=>p.good&&modelOnly(p))).length;
    $('#weekEyebrow').textContent=`NBA · ${D.seasonLabel} season${cur===D.today?' · today':''}`;
    $('#weekTitle').textContent=dayTitle(cur);
    $('#weekSub').textContent=gs.length?`${cur===D.today||dayTitle(cur)!==dayName(cur)?dayName(cur)+' · ':''}${plural(gs.length,'game')} · first tip ${tipTime(gs[0])} CT`:'';
    $('#kpis').innerHTML=`
      <div class="kpi"><div class="v">${gs.length}</div><div class="l">Games<br><span>${fin} finished, ${gs.length-fin} to play</span></div></div>
      <div class="kpi"><div class="v ${gaps.length?'good':''}">${gaps.length}</div><div class="l">Price gaps<br><span>Kalshi/Polymarket ${D.gapEv}%+ better than fair</span></div></div>
      <div class="kpi"><div class="v">${picks}</div><div class="l">Model picks<br><span>model edge ${D.modelMinEdge}%+, no proven edge</span></div></div>
      <div class="kpi"><div class="v">${b2b}</div><div class="l">Back-to-backs<br><span>games with a tired team</span></div></div>`;
    bestBets(gs);
    const shown=gs.filter(g=>filter==='all'||(filter==='gap'&&g.gaps&&g.gaps.length)||(filter==='lean'&&(g.picks||[]).some(p=>p.good&&modelOnly(p)))
      ||(filter==='b2b'&&g.rest&&(g.rest.hb2b||g.rest.ab2b))||(filter==='final'&&g.status==='final'));
    $('#games').innerHTML=shown.map(card).join('')||`<div class="empty">No games match this filter on ${esc(dayName(cur))}.</div>`;
  }
  document.addEventListener('click',e=>{
    const lb=e.target.closest('[data-key][data-gid]');
    if(lb){ pendingLog={gid:lb.dataset.gid,key:lb.dataset.key};
      if(location.hash==='#bets') route(); else location.hash='#bets';
      return; }
    const sa=e.target.closest('[data-showall]');
    if(sa){ $('#plays').classList.add('all'); sa.remove(); return; }
    const gt=e.target.closest('[data-goto]');
    if(gt){ const id=gt.dataset.goto, g=D.games.find(x=>'g-'+x.id===id);
      if(g&&g.day!==cur){ e.preventDefault(); cur=g.day; filter='all'; try{history.replaceState(null,'','#day'+cur);}catch(_){} render(); }
      const el=document.getElementById(id); if(el){ e.preventDefault(); el.scrollIntoView({behavior:REDUCE?'auto':'smooth',block:'start'}); }
      return; }
    const b=e.target.closest('[data-day]');
    if(b){ cur=b.dataset.day; filter='all';
      $$('#filters button').forEach(x=>x.setAttribute('aria-pressed',x.dataset.f==='all'));
      try{history.replaceState(null,'','#day'+cur);}catch(_){}
      render(); setTimeout(liveTick,50); return; }
    const f=e.target.closest('[data-f]');
    if(f){ filter=f.dataset.f; $$('#filters button').forEach(x=>x.setAttribute('aria-pressed',x===f)); render(); }
  });
  function route(){
    const bets=location.hash==='#bets';
    const dm=location.hash.match(/^#day(\d{4}-\d\d-\d\d)$/);
    if(dm&&days.includes(dm[1])) cur=dm[1];
    $('#betsView').hidden=!bets; $('#weekView').hidden=bets; $('#rail').hidden=bets;
    $('#navWeek').toggleAttribute('aria-current',!bets); $('#navBets').toggleAttribute('aria-current',bets);
    if(bets){ $('#navBets').setAttribute('aria-current','page'); betsView();
      if(pendingLog&&fillBet){ const pl=pendingLog; pendingLog=null; fillBet(pl); } }
    else { $('#navWeek').setAttribute('aria-current','page'); render(); }
  }
  window.addEventListener('hashchange',route);
  route();
  watchLive(()=>location.hash==='#bets'?null:cur,(changed,gs)=>{
    changed.forEach(g=>{const el=document.getElementById('g-'+g.id); if(el) el.outerHTML=card(g);});
    bestBets(gs);
  });
  window.addEventListener('hashchange',()=>setTimeout(liveTick,50));
  dayStep=d=>{const i=days.indexOf(cur); const n=days[i+d]; if(n){ const b=$(`#rail [data-day="${n}"]`); if(b) b.click(); }};
  dayAt=()=>[days.indexOf(cur),days.length];
}
let dayStep=null, dayAt=null;

/* ======================= bet tracker ======================= */
const VENUE={kalshi:'Kalshi',polymarket:'Polymarket',other:'Other'};
const REASON={gap:'Price gap',lean:'Model pick',other:'Other'};
const GAME=new Map(D.games.map(g=>[g.id,g]));
const feePer=(venue,p)=>((D.fees||{})[venue]||0)*p*(1-p);

function betText(b,g){
  const team=s=>g?(s==='home'?g.homeName:g.awayName):s;
  if(b.mk==='ml') return `${team(b.side)} to win`;
  if(b.mk==='spread') return `${team(b.side)} ${b.point>0?'+':''}${b.point}`;
  return `${b.side==='over'?'Over':'Under'} ${b.point}`;
}
function betMath(b){
  const g=GAME.get(b.gid), p=b.cents/100, n=b.n, fee=feePer(b.venue,p)*n;
  const out={g,cost:n*p+fee,fee};
  if(!g) return out;
  const cf=g.closeFair;
  if(cf&&g.status!=='upcoming'){
    const eff=1/(p+feePer(b.venue,p));
    let pf=null, pts=null;
    if(b.mk==='ml'&&cf.home!=null) pf=b.side==='home'?cf.home:1-cf.home;
    if(b.mk==='spread'&&cf.spreadLine!=null){
      pts=b.point-(b.side==='home'?-cf.spreadLine:cf.spreadLine);
      if(pts===0&&cf.spreadHome!=null) pf=b.side==='home'?cf.spreadHome:1-cf.spreadHome;
    }
    if(b.mk==='total'&&cf.total!=null){
      pts=b.side==='under'?b.point-cf.total:cf.total-b.point;
      if(pts===0&&cf.over!=null) pf=b.side==='over'?cf.over:1-cf.over;
    }
    if(pf!=null) out.clvEv=(pf*eff-1)*100;
    if(pts) out.clvPts=pts;
    out.beat=out.clvPts!=null?out.clvPts>0:out.clvEv!=null?out.clvEv>0:null;
  }
  if(g.status==='final'){
    const m=b.mk==='ml'?(b.side==='home'?g.hs-g.as:g.as-g.hs)
      :b.mk==='spread'?(b.side==='home'?g.hs-g.as:g.as-g.hs)+b.point
      :b.side==='over'?(g.hs+g.as)-b.point:b.point-(g.hs+g.as);
    out.result=m>0?'won':m<0?'lost':'push';
    out.pl=m>0?n*(1-p)-fee:m<0?-n*p-fee:-fee;
  }
  return out;
}
function fairNow(g,mk,side,point){
  const f=g&&g.shop&&g.shop.fair; if(!f) return null;
  if(mk==='ml'&&f.home!=null) return side==='home'?f.home:1-f.home;
  if(mk==='spread'&&f.spreadHome!=null){
    if(side==='home'&&point===f.spreadPoint) return f.spreadHome;
    if(side==='away'&&point===-f.spreadPoint) return 1-f.spreadHome;
  }
  if(mk==='total'&&f.over!=null&&point===f.totalPoint) return side==='over'?f.over:1-f.over;
  return null;
}

/* Storage: the claude.ai page's private database when available, else this browser. */
async function betStore(){
  let db=null;
  try{ if(window.claude&&window.claude.use) db=await window.claude.use('db'); }catch(_){}
  if(db){
    const col=db.collection('bets');
    return {kind:'db',
      subscribe:(cb,err)=>col.onSnapshot(s=>cb(s.docs.map(d=>Object.assign({id:d.id},d.data()))),err),
      add:b=>col.add(b), remove:id=>col.doc(id).delete()};
  }
  const K='btb.nba.bets.v1', subs=[];
  const read=()=>{try{return JSON.parse(localStorage.getItem(K))||[];}catch(_){return [];}};
  const write=a=>{try{localStorage.setItem(K,JSON.stringify(a));}catch(_){} subs.forEach(f=>f(a));};
  return {kind:'local',
    subscribe:cb=>{subs.push(cb); cb(read()); return ()=>{};},
    add:b=>{write(read().concat([Object.assign({id:Date.now().toString(36)+Math.random().toString(36).slice(2,6)},b)])); return Promise.resolve();},
    remove:id=>{write(read().filter(x=>x.id!==id)); return Promise.resolve();}};
}

function vsCloseTxt(r){
  if(r.clvPts!=null) return `<span class="${r.clvPts>0?'ok':'no'}">${Math.abs(r.clvPts)} pt${Math.abs(r.clvPts)===1?'':'s'} ${r.clvPts>0?'better':'worse'}</span>`;
  if(r.clvEv!=null) return Math.abs(r.clvEv)<0.05?'<span class="push">Same price</span>'
    :`<span class="${r.clvEv>0?'ok':'no'}">${Math.abs(r.clvEv).toFixed(1)}% ${r.clvEv>0?'better':'worse'}</span>`;
  return '<span class="push">After tip-off</span>';
}

let betsReady=false, store=null, bets=[];
let pendingLog=null, fillBet=null;
function betsView(){
  if(betsReady) return; betsReady=true;
  const soon=addDays(D.today,3), since=addDays(D.today,-21);
  const up=D.games.filter(g=>g.status!=='final'&&g.day<=soon);
  const fin=D.games.filter(g=>g.status==='final'&&g.day>=since);
  const opt=g=>`<option value="${esc(g.id)}">${esc(fmtDay(g.day))} · ${esc(g.awayName)} at ${esc(g.homeName)} · ${esc(tipTime(g))}</option>`;
  const finDays=[...new Set(fin.map(g=>g.day))].sort().reverse();
  $('#bGame').innerHTML=(up.length?`<optgroup label="Upcoming">${up.map(opt).join('')}</optgroup>`:'')
    +finDays.map(d=>`<optgroup label="${esc(dayName(d))} · final">${fin.filter(g=>g.day===d).map(opt).join('')}</optgroup>`).join('');
  const sides=()=>{
    const g=GAME.get($('#bGame').value), mk=$('#bMarket').value;
    if(!g) return;
    $('#bSide').innerHTML=mk==='total'?'<option value="under">Under</option><option value="over">Over</option>'
      :`<option value="away">${esc(g.awayName)}</option><option value="home">${esc(g.homeName)}</option>`;
    $('#bPointWrap').hidden=mk==='ml';
    prefill();
  };
  const prefill=()=>{
    const g=GAME.get($('#bGame').value), mk=$('#bMarket').value, side=$('#bSide').value;
    if(!g) return;
    const o=g.shop&&g.shop[mk]&&g.shop[mk][side];
    let pt=o&&o.point!=null?o.point:null;
    if(pt==null&&mk==='spread'&&g.spread) pt=side==='home'?-g.spread.line:g.spread.line;
    if(pt==null&&mk==='total'&&g.total) pt=g.total.line;
    $('#bPoint').value=pt==null?'':pt;
    $('#bCents').value=o?o.cents.toFixed(0):'';
    if(o&&VENUE[o.key]) $('#bVenue').value=o.key;
    preview();
  };
  const preview=()=>{
    const g=GAME.get($('#bGame').value), mk=$('#bMarket').value, side=$('#bSide').value;
    const p=Number($('#bCents').value)/100, n=Number($('#bQty').value)||0;
    if(!(p>0&&p<1)||!n){ $('#bPreview').textContent='Enter the price you paid and how many contracts.'; return; }
    const fee=feePer($('#bVenue').value,p)*n, point=mk==='ml'?null:Number($('#bPoint').value);
    const pf=fairNow(g,mk,side,point);
    const ev=pf==null?'':` It’s ${(()=>{const v=(pf/(p+fee/n)-1)*100; return Math.abs(v)<0.05?'right at':Math.abs(v).toFixed(1)+'% '+(v>0?'better than':'worse than');})()} the fair price right now.`;
    $('#bPreview').textContent=`Costs about ${money(n*p+fee).replace('+','')} including about ${money(fee).replace('+','')} in fees, and pays $${n.toFixed(0)} if it wins.${ev}`;
  };
  $('#bGame').addEventListener('change',sides);
  $('#bMarket').addEventListener('change',sides);
  $('#bSide').addEventListener('change',prefill);
  ['bCents','bQty','bPoint','bVenue'].forEach(id=>$('#'+id).addEventListener('input',preview));
  sides();
  const bankTxt=()=>{const u=unitUsd(); $('#bUnit').innerHTML=unitKey()
    +(u?'':'<p class="why">Your bankroll is saved in this browser only and never sent anywhere.</p>');};
  const b0=bankroll(); if(b0) $('#bBank').value=b0;
  $('#bBank').addEventListener('input',()=>{const v=Number($('#bBank').value);
    try{ if(v>0) localStorage.setItem(BANK_KEY,String(v)); else localStorage.removeItem(BANK_KEY); }catch(_){}
    bankTxt();});
  bankTxt();
  fillBet=({gid,key})=>{
    const g=GAME.get(gid), p=g&&(g.picks||[]).find(x=>x.key===key); if(!p) return;
    if(![...$('#bGame').options].some(o=>o.value===gid)) $('#bGame').insertAdjacentHTML('afterbegin',opt(g));
    $('#bGame').value=gid; $('#bMarket').value=p.mk; sides();
    $('#bSide').value=p.side; prefill();
    if(p.point!=null) $('#bPoint').value=p.point;
    const pr=p.price||{}, book=String(pr.book||'');
    $('#bVenue').value=/kalshi/i.test(book)?'kalshi':/polymarket/i.test(book)?'polymarket':'other';
    const c=pr.cents!=null?pr.cents:pr.odds!=null?(pr.odds<0?-pr.odds/(100-pr.odds):100/(pr.odds+100))*100:null;
    if(c!=null) $('#bCents').value=Number(c).toFixed(0);
    $('#bReason').value={gap:'gap',lean:'lean',spread:'lean'}[p.edgeFrom]||'other';
    $('#bNote').value=`Suggested: ${p.units?fmtU(p.units)+' ':''}${p.text}, ${signed(p.edge)}% edge`.slice(0,140);
    const u=unitUsd(), cc=Number($('#bCents').value)/100;
    if(p.units&&u&&cc>0&&cc<1){ const per=cc+feePer($('#bVenue').value,cc); $('#bQty').value=Math.max(1,Math.floor(p.units*u/per)); }
    preview();
    $('#bStatus').textContent=unitUsd()&&p.units
      ?`Filled in: ${fmtU(p.units)} = ${usdAmt(p.units*unitUsd())}. Set the price you actually paid, then Save.`
      :'Filled in from the pick: set the price you actually paid and how many contracts, then Save. (Enter your Kalshi bankroll above to size it in units.)';
    $('#betForm').scrollIntoView({behavior:'smooth',block:'center'});
    $('#bQty').focus({preventScroll:true});
  };

  $('#betForm').addEventListener('submit',async e=>{
    e.preventDefault();
    if(!store){ $('#bStatus').textContent='Still connecting to your saved bets. Try again in a moment.'; return; }
    const mk=$('#bMarket').value, cents=Number($('#bCents').value), n=Math.round(Number($('#bQty').value));
    const point=mk==='ml'?null:Number($('#bPoint').value);
    if(!(cents>0&&cents<100)||!(n>=1)||(mk!=='ml'&&!isFinite(point))||$('#bPoint').value===''&&mk!=='ml'){
      $('#bStatus').textContent='Check the line, the price (1–99¢) and the number of contracts.'; return; }
    const doc={gid:$('#bGame').value,mk,side:$('#bSide').value,point,venue:$('#bVenue').value,
      cents,n,reason:$('#bReason').value,note:$('#bNote').value.trim().slice(0,140),placed:new Date().toISOString(),v:1};
    $('#bSave').disabled=true; $('#bStatus').textContent='Saving…';
    try{ await store.add(doc); $('#bStatus').textContent='Saved.'; $('#bNote').value=''; }
    catch(err){ $('#bStatus').textContent=err&&err.code==='quota_exceeded'?'Storage is full. Delete old bets to add more.':'Couldn’t save. Try again.'; }
    finally{ $('#bSave').disabled=false; }
  });

  document.addEventListener('click',async e=>{
    const del=e.target.closest('[data-del]'); if(!del) return;
    if(del.dataset.armed!=='1'){ del.dataset.armed='1'; del.textContent='Confirm'; setTimeout(()=>{del.dataset.armed=''; del.textContent='Delete';},3000); return; }
    del.disabled=true; try{ await store.remove(del.dataset.del); }catch(_){ del.disabled=false; del.textContent='Delete'; }
  });
  const draw=()=>{
    const rows=bets.map(b=>Object.assign({b},betMath(b))).sort((x,y)=>(y.b.placed||'').localeCompare(x.b.placed||''));
    const settled=rows.filter(r=>r.result), won=settled.filter(r=>r.result==='won').length, lost=settled.filter(r=>r.result==='lost').length;
    const pushes=settled.length-won-lost;
    const pl=settled.reduce((s,r)=>s+r.pl,0), staked=settled.reduce((s,r)=>s+r.cost,0);
    const judged=rows.filter(r=>r.beat!=null), beat=judged.filter(r=>r.beat).length;
    const evs=rows.filter(r=>r.clvEv!=null), avgEv=evs.length?evs.reduce((s,r)=>s+r.clvEv,0)/evs.length:null;
    $('#betKpis').innerHTML=`
      <div class="kpi"><div class="v">${rows.length}</div><div class="l">Bets logged<br><span>${rows.length-settled.length} still open</span></div></div>
      <div class="kpi"><div class="v ${pl>0?'good':pl<0?'bad':''}">${settled.length?money(pl):'$0'}</div><div class="l">Profit so far<br><span>${settled.length?`${won} won, ${lost} lost${pushes?`, ${pushes} pushed`:''}${staked?` · ${signed(pl/staked*100)}% return`:''}`:'no finished bets yet'}</span></div></div>
      <div class="kpi"><div class="v ${judged.length&&beat/judged.length>0.5?'good':''}">${judged.length?Math.round(beat/judged.length*100)+'%':'n/a'}</div><div class="l">Beat the closing line<br><span>${judged.length?`${beat} of ${judged.length} bets; over 50% is a good sign`:'shows once your games tip off'}</span></div></div>
      <div class="kpi"><div class="v">${avgEv==null?'n/a':(avgEv>=0?'+':MINUS)+Math.abs(avgEv).toFixed(1)+'%'}</div><div class="l">Your price vs closing price<br><span>${avgEv==null?'needs bets at the closing line':avgEv>=0?'average, you paid less than the close':'average, you paid more than the close'}</span></div></div>`;
    $('#betTable').innerHTML=`<thead><tr><th>Game</th><th>Bet</th><th>Where</th><th class="n">Price paid</th><th class="n">Cost</th><th>Reason</th><th>Vs closing line</th><th>Result</th><th></th></tr></thead>
      <tbody>${rows.map(r=>{const b=r.b,g=r.g;
        const res=r.result?`<span class="${r.pl>0?'ok':r.pl<0?'no':'push'}">${r.result==='won'?'Won':r.result==='lost'?'Lost':'Push'} ${money(r.pl)}</span>`
          :`<span class="push">${g?(g.status==='live'?'In progress':'Not played yet'):'Unknown game'}</span>`;
        return `<tr><td>${g?`${fmtDay(g.day)} · ${withLogo(g.away,g.awayName)} at ${withLogo(g.home,g.homeName)}`:esc(b.gid)}</td>
          <td>${esc(betText(b,g))}${b.note?`<div class="push small">${esc(b.note)}</div>`:''}</td>
          <td>${esc(VENUE[b.venue]||b.venue)}</td><td class="n">${Number(b.cents).toFixed(0)}¢ × ${b.n}</td>
          <td class="n">${money(r.cost).replace('+','')}</td><td>${esc(REASON[b.reason]||b.reason)}</td>
          <td>${vsCloseTxt(r)}</td><td>${res}</td>
          <td><button type="button" class="btn ghost small" data-del="${esc(b.id)}">Delete</button></td></tr>`;}).join('')
        ||'<tr><td colspan="9" class="push">No bets yet. Add your first one above.</td></tr>'}</tbody>`;
    let cum=0; const pts=settled.slice().sort((x,y)=>x.g.day<y.g.day?-1:1).map((r,i)=>({x:i+1,y:Math.round((cum+=r.pl)*100)/100,r}));
    lineChart($('#betChart'),{label:'Running profit in dollars, finished bets',series:[{name:'Profit',n:1,points:pts.length?[{x:0,y:0},...pts]:[]}],
      zero:true,height:220,yFmt:v=>(v<0?MINUS:'')+'$'+Math.abs(v),empty:'No finished bets yet. Your running profit appears here once your games end.',
      xTicks:pts.length?[{x:0,label:'Start'},{x:pts.length,label:`Bet ${pts.length}`}]:[],
      tip:x=>{const q=pts[Math.round(x)-1]; return q?`<div>${esc(betText(q.r.b,q.r.g))} · ${fmtDay(q.r.g.day)}</div><div>Running total <b>${money(q.y)}</b></div>`:'<div>Start <b>$0</b></div>';}});
  };
  draw();
  $('#betsWhere').textContent='Connecting to your saved bets…';
  betStore().then(s=>{
    store=s;
    $('#betsWhere').textContent=s.kind==='db'?'Saved privately to your account':'Saved in this browser only';
    s.subscribe(list=>{bets=list; draw();},()=>{$('#betsWhere').textContent='Live sync stopped. Reload the page.';});
  });
}

/* ======================= season page ======================= */
function seasonBets(){
  const fin=D.games.filter(g=>g.status==='final').slice().sort((a,b)=>a.koIso<b.koIso?-1:1);
  const out=[];
  fin.forEach(g=>{
    if(g.mkt&&'leanUnits' in g.mkt){ const side=g.mkt.lean==='home'?g.homeName:g.awayName;
      out.push({g,type:'lean',label:`${side} to win`,price:g.mkt.leanOdds,cents:g.mkt.leanCents,detail:`Model’s expected return ${signed(g.mkt.leanEv)}%`,u:g.mkt.leanUnits}); }
    const s=g.spreadLean; if(s&&'units' in s){ const side=s.side==='home'?g.homeName:g.awayName;
      out.push({g,type:'spread',label:`${side} ${s.point>0?'+':''}${s.point}`,price:s.odds,cents:s.cents,detail:`Model’s expected return ${signed(s.ev)}%`,u:s.units}); }
  });
  return out;
}
function seasonPage(){
  const s=D.summary, c=u=>u>0?'good':u<0?'bad':'';
  const rec=o=>`${o.won} won, ${o.lost} lost${o.n-o.won-o.lost?`, ${o.n-o.won-o.lost} pushed`:''}`;
  const ret=o=>o.n?` · ${signed(o.units/o.n*100)}% return`:'';
  $('#seasonTitle').textContent=`${D.seasonLabel} season so far`;
  $('#seasonSub').textContent=`${s.final} games played · results are profit on $100 bets`;
  const better=s.eloLL==null?null:Math.abs(s.eloLL-s.mktLL)<0.002?'About even':s.mktLL<s.eloLL?'Betting market':'Our model';
  $('#kpis').innerHTML=`
    <div class="kpi"><div class="v ${c(s.lean.units)}">${s.lean.n?per100(s.lean.units):'$0'}</div><div class="l">Every model lean, moneyline<br><span>${s.lean.n?rec(s.lean)+ret(s.lean):'none finished yet'}</span></div></div>
    <div class="kpi"><div class="v ${c(s.spread.units)}">${s.spread.n?per100(s.spread.units):'$0'}</div><div class="l">Every model lean, spread<br><span>${s.spread.n?rec(s.spread)+ret(s.spread):'none finished yet'}</span></div></div>
    <div class="kpi"><div class="v">${s.eloAcc!=null?pct(s.eloAcc):'n/a'} <small>vs ${s.mktAcc!=null?pct(s.mktAcc):'n/a'}</small></div><div class="l">Winners picked<br><span>our model vs the betting market (${s.withLines} games)</span></div></div>
    <div class="kpi"><div class="v small-v">${better||'n/a'}</div><div class="l">More accurate overall<br><span>judged by how confident each was, not just picks</span></div></div>`;

  const B=s.picks;
  if(B&&$('#pickBoard')){
    const KIND=[['gap','Price gaps','gap'],['lean','Model picks · moneyline','lean'],['spread','Model picks · spread','lean']];
    const line=(label,o,tag)=>`<tr${tag===null?' class="sel"':''}><td>${tag?`<span class="tag ${tag}">${label}</span>`:`<b>${label}</b>`}</td>
      <td class="n">${o.n}</td><td>${o.n?`${o.won}–${o.lost}${o.push?`–${o.push}`:''}`:'<span class="push">none yet</span>'}</td>
      <td class="n ${cls(o.units)}">${o.n?per100(o.units):'—'}</td><td class="n ${cls(o.units)}">${o.n?signed(o.units/o.n*100)+'%':'—'}</td>
      <td class="n ${cls(o.sized)}">${o.n?`${o.sized>0?'+':o.sized<0?MINUS:''}${fmtU(Math.abs(o.sized))} <span class="push small">on ${fmtU(o.staked)}</span>`:'—'}</td>
      <td>${o.judged?`<b class="${o.beat/o.judged>0.5?'ok':'no'}">${o.beat} of ${o.judged}</b>${o.clvAvg!=null?` <span class="push">· ${signed(o.clvAvg)}% avg</span>`:''}`:'<span class="push">once logged picks finish</span>'}</td></tr>`;
    $('#pickBoard').innerHTML=`<thead><tr><th>Kind of bet</th><th class="n">Bets</th><th>Won–lost</th><th class="n">Profit on $100 each</th><th class="n">Return</th><th class="n">As sized (units)</th><th>Beat the closing price</th></tr></thead>
      <tbody>${KIND.map(([k,l,t])=>line(l,B[k],t)).join('')}${line('All suggestions',B.all,null)}</tbody>`;
    const st=s.pickLogStarted;
    $('#pickBoardNote').textContent=`Every bet the “Bets to take” boxes suggested, graded at the price shown when it first appeared.`
      +` “Beat the closing price” compares that price with the final line before tip-off: beating it more than half the time is`
      +` the best early sign of a real edge, long before wins and losses mean anything.`
      +(st?` The site started saving its suggestions ${fmtLogged(st)}.`:'');
  }

  const bets=seasonBets();
  const first=D.games.length?day(D.games.map(g=>g.day).sort()[0])-1:0;
  const series=[{name:'Moneyline leans',n:1,type:'lean'},{name:'Spread leans',n:2,type:'spread'}].map(se=>{
    let cum=0; const pts=[];
    bets.filter(b=>b.type===se.type).forEach(b=>{ cum+=b.u*100; pts.push({x:day(b.g.day),y:Math.round(cum)}); });
    const byDay=new Map(); pts.forEach(p=>byDay.set(p.x,p));
    return {name:se.name,n:se.n,points:[{x:first,y:0},...byDay.values()]};
  });
  const at=(se,x)=>{let v=0; se.points.forEach(p=>{if(p.x<=x) v=p.y;}); return v;};
  const xs=series.flatMap(se=>se.points.map(p=>p.x));
  lineChart($('#cumChart'),{label:'Running profit on $100 bets: model moneyline and spread leans',series,zero:true,endLabels:true,height:270,left:64,
    yFmt:v=>usd(v),
    xTicks:xs.length?[{x:Math.min(...xs),label:'Start'},...monthTicks(Math.min(...xs),Math.max(...xs))]:[],
    empty:'No bets finished yet this season.',
    tip:x=>{const d=new Date(x*864e5); return `<div>${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}</div>`+
      series.map(se=>`<div><span style="color:var(--series-${se.n})">●</span> ${se.name} <b>${usd(at(se,x))}</b></div>`).join('');}});

  const cnt=(n,u)=>n?`<span class="${cls(u)}">${per100(u)}</span> <span class="push">· ${plural(n,'bet')}</span>`:'<span class="push">No bets</span>';
  $('#byWeek').innerHTML=`<thead><tr><th>Week</th><th class="n">Games</th><th class="n">Model picks right</th><th class="n">Market picks right</th>
    <th>Moneyline leans</th><th>Spread leans</th></tr></thead><tbody>${s.byWeek.slice().reverse().map(r=>`<tr>
    <td><a href="index.html#day${r.from}">Week ${r.wk}</a> <span class="push">· ${fmtDay(r.from)}–${fmtDay(r.to)}</span></td><td class="n">${r.games}</td>
    <td class="n">${r.eloRight} of ${r.decided}</td><td class="n">${r.mktRight} of ${r.decided}</td>
    <td>${cnt(r.leanN,r.leanUnits)}</td><td>${cnt(r.spreadN,r.spreadUnits)}</td></tr>`).join('')
    ||'<tr><td colspan="6">No finished games yet.</td></tr>'}</tbody>`;

  let f='all';
  const log=()=>{
    const rows=bets.filter(b=>f==='all'||b.type===f).slice().reverse().slice(0,400);
    $('#betLog').innerHTML=`<thead><tr><th>Date</th><th>Game and final score</th><th>Bet</th><th class="n">Price</th><th>Why</th><th>Result on $100</th></tr></thead>
      <tbody>${rows.map(b=>`<tr><td>${fmtDay(b.g.day)}</td>
        <td>${withLogo(b.g.away,b.g.awayName)} ${b.g.as}, ${withLogo(b.g.home,b.g.homeName)} ${b.g.hs}</td>
        <td><span class="tag lean">${b.type==='lean'?'Moneyline':'Spread'}</span> ${esc(b.label)}</td>
        <td class="n">${b.cents!=null?Number(b.cents).toFixed(0)+'¢':odds(b.price)}</td><td class="push">${esc(b.detail)}</td>
        <td class="${cls(b.u)}">${b.u>0?'Won':b.u<0?'Lost':'Push'} ${per100(b.u)}</td></tr>`).join('')||'<tr><td colspan="6">No bets yet.</td></tr>'}</tbody>`;
  };
  document.addEventListener('click',e=>{const b=e.target.closest('[data-f]'); if(!b) return; f=b.dataset.f;
    $$('#filters button').forEach(x=>x.setAttribute('aria-pressed',x===b)); log();});
  log();
}

/* ======================= teams page ======================= */
function teamsPage(){
  const T=D.teams; if(!T.length) return;
  const max=vsAvg(T[0].rating), min=vsAvg(T[T.length-1].rating);
  let sel=decodeURIComponent((location.hash||'').slice(1)); if(!NAME[sel]) sel=T[0].team;
  $('#powerSub').textContent=`Updated after every game. “Win chance” is the chance to beat an average team on a neutral court. Change is over the last 7 days.`;
  const change=r=>{
    if(r.delta==null) return '<span class="push">Season starting</span>';
    const x=(vsAvg(r.rating)-vsAvg(r.rating-r.delta))*100;
    if(Math.abs(x)<0.05) return '<span class="push">No change</span>';
    return `<span class="${x>0?'ok':'no'}">${x>0?'▲':'▼'} ${Math.abs(x).toFixed(1)}%</span>`;
  };
  const table=()=>{
    $('#power').innerHTML=`<thead><tr><th class="n">Rank</th><th>Team</th><th>Record</th><th class="n">Win chance</th><th>Change</th><th aria-hidden="true"></th></tr></thead>
      <tbody>${T.map((r,i)=>`<tr class="${r.team===sel?'sel':''}"><td class="n">${i+1}</td>
        <td><button type="button" class="teamlink" data-team="${esc(r.team)}" style="${tcv(r.team)}">${logo(r.team,'sm')}${esc(r.name)}</button></td>
        <td>${esc(r.record)}</td><td class="n"><b>${pct(vsAvg(r.rating))}</b></td>
        <td>${change(r)}</td>
        <td style="width:22%"><span class="rbar" style="width:${8+92*(vsAvg(r.rating)-min)/Math.max(0.01,max-min)}%"></span></td></tr>`).join('')}</tbody>`;
  };
  const detail=()=>{
    const t=T.find(x=>x.team===sel), rank=T.indexOf(t)+1;
    $('#teamName').innerHTML=logo(t.team,'lg')+`<span>${esc(t.full||t.name)}</span>`;
    $('#teamName').style.setProperty('--tc',TCOLOR[t.team]||'#4c3a8f');
    $('#teamSub').textContent=`Ranked ${rank} of 30 · ${t.record} this season · would beat an average team ${pct(vsAvg(t.rating))} of the time`;
    const pts=t.hist.map((h,i)=>({x:i,y:Math.round(vsAvg(h[1])*1000)/10}));
    const xTicks=[]; t.hist.forEach((h,i)=>{ if(i===0||h[3]!==t.hist[i-1][3]) xTicks.push({x:i,label:`${h[3]-1}–${String(h[3]).slice(2)}`}); });
    lineChart($('#teamChart'),{label:`${t.name}: chance to beat an average team, last two seasons and this one`,series:[{name:t.name,n:1,points:pts}],
      refY:50,refLabel:'Average team',height:220,left:48,yFmt:v=>Math.round(v)+'%',xTicks,
      tip:x=>{const h=t.hist[Math.round(x)]; return `<div>${fmtDay(h[0])}, ${h[0].slice(0,4)}</div><div>${h[2]?'Before playing '+esc(NAME[h[2]]||h[2]):'Now'}: <b>${pct(vsAvg(h[1]))}</b></div>`;}});
    const gs=D.games.filter(g=>g.home===sel||g.away===sel);
    $('#teamGames').innerHTML=`<thead><tr><th>Date</th><th>Opponent</th><th class="n">Our model</th><th class="n">Betting market</th><th>Result</th></tr></thead>
      <tbody>${gs.map(g=>{const home=g.home===sel, opp=home?g.away:g.home, pe=home?g.pElo:1-g.pElo;
        const pm=g.mkt?(home?g.mkt.fair:1-g.mkt.fair):null;
        let r='<span class="push">'+esc(tipTime(g))+' CT</span>';
        if(g.status==='final'){const us=home?g.hs:g.as, them=home?g.as:g.hs; r=`<span class="${us>them?'ok':'no'}">${us>them?'Won':'Lost'} ${us}–${them}${g.ot?' (OT)':''}</span>`;}
        return `<tr><td><a href="index.html#day${g.day}">${fmtDay(g.day)}</a></td><td>${home?'vs':'at'} ${withLogo(opp,NAME[opp]||opp)}</td>
          <td class="n">${pct(pe)} to win</td><td class="n">${pm==null?'<span class="push">No line yet</span>':pct(pm)+' to win'}</td><td>${r}</td></tr>`;}).join('')
        ||'<tr><td colspan="5" class="push">No games in the next week.</td></tr>'}</tbody>`;
  };
  document.addEventListener('click',e=>{const b=e.target.closest('[data-team]'); if(!b) return; sel=b.dataset.team;
    try{history.replaceState(null,'','#'+sel);}catch(_){} table(); detail();
    if(innerWidth<780) $('#teamName').scrollIntoView({behavior:'smooth',block:'start'});});
  table(); detail();
}

/* ======================= method page ======================= */
function methodPage(){
  $$('[data-season]').forEach(el=>el.textContent=D.seasonLabel);
  $$('[data-hfa]').forEach(el=>el.textContent=D.hfaPts!=null?D.hfaPts.toFixed(1):'about 2.5');
  const MR=(D.summary||{}).models;
  if(MR&&MR.length&&$('#thisYear')){
    const mkt=MR.find(r=>r.kind==='market'), n=MR[0].n;
    const ret=(v,b)=>`<td class="n ${cls(v)}">${b?signed(v)+'%':'—'} <span class="push small">${b?plural(b,'bet'):''}</span></td>`;
    $('#thisYearTitle').textContent=`This season so far (${D.seasonLabel}, ${plural(n,'game')})`;
    $('#thisYear').innerHTML=`<thead><tr><th>Model</th><th class="n">Accuracy score<br>(lower is better)</th><th class="n">Winners picked</th>
      <th class="n">Return, every edge</th><th class="n">Return, edges over 3%</th></tr></thead><tbody>${MR.map(r=>r.kind==='market'
        ?`<tr><td>${esc(r.label)}</td><td class="n">${r.ll.toFixed(4)}</td><td class="n">${(r.acc*100).toFixed(1)}%</td><td class="n push">benchmark</td><td class="n"></td></tr>`
        :`<tr${r.kind==='site'?' class="sel"':''}><td>${esc(r.label)}</td><td class="n ${mkt&&r.ll<mkt.ll?'ok':''}">${r.ll.toFixed(4)}</td><td class="n">${(r.acc*100).toFixed(1)}%</td>`
          +ret(r.roi,r.bets)+ret(r.roi3,r.bets3)+'</tr>').join('')}</tbody>`;
    $('#thisYearNote').textContent=`${plural(n,'game')} is a small sample: one season can swing a lot, so the seven-season table above is the better guide.`;
  } else if($('#thisYear')){ $('#thisYearTitle').textContent='This season so far'; $('#thisYearNote').textContent='Shows once this season’s first games are final.'; }
}

/* ======================= motion + navigation ======================= */
const REDUCE=matchMedia('(prefers-reduced-motion: reduce)').matches;

/* Moving background: a basketball court gliding toward you under arena lights (hardwood boards, sidelines, center
   circle, keys, three-point arcs), camera flashes in the crowd, dust in the light. Same budget as the NFL site's
   stadium: ≤30 fps (24 on phones), paused in hidden tabs, one still frame with reduced motion. */
function courtBg(page){
  const layer=document.createElement('div'); layer.className='bgfx'; layer.setAttribute('aria-hidden','true');
  const cv=document.createElement('canvas'); layer.appendChild(cv);
  layer.insertAdjacentHTML('beforeend','<i class="grain"></i><i class="vig"></i>');
  document.body.prepend(layer);
  const ctx=cv.getContext('2d'); if(!ctx) return;
  const M={x:innerWidth/2,on:false};
  addEventListener('pointermove',e=>{M.x=e.clientX; M.on=e.pointerType==='mouse';},{passive:true});
  document.documentElement.addEventListener('pointerleave',()=>{M.on=false;});
  let W=0,H=0,dpr=1,motes=[],flashes=[],cx=0;
  const size=()=>{
    const d=Math.min(1.5,devicePixelRatio||1), w=Math.round(innerWidth*d), h=Math.round(innerHeight*d);
    if(w===W&&Math.abs(h-H)<160*d) return;
    dpr=d; W=cv.width=w; H=cv.height=h;
    motes=Array.from({length:innerWidth<700?24:60},()=>({x:Math.random(),y:Math.random(),s:.6+Math.random()*1.8,v:.008+Math.random()*.025,ph:Math.random()*6.283}));
    flashes=Array.from({length:innerWidth<700?18:40},()=>({x:Math.random(),y:Math.random(),t:Math.random()*40,ph:Math.random()*6.283}));
  };
  const glow=(x,y,r,stops)=>{const g=ctx.createRadialGradient(x,y,0,x,y,r); stops.forEach(([o,c])=>g.addColorStop(o,c)); ctx.fillStyle=g; ctx.fillRect(x-r,y-r,2*r,2*r);};
  const a3=v=>v.toFixed(3);
  const LEN=94, HALF=25;                                                                       // court: 94 x 50 feet
  function frame(t){
    ctx.globalCompositeOperation='source-over'; ctx.clearRect(0,0,W,H);
    const hz=H*.42, F=H*.95, camH=9, zmin=camH*F/(H-hz)*.92, zfar=190;
    cx+=(((M.on?M.x/innerWidth:.5)-.5)*14-cx)*.04;
    const camZ=t*9+scrollY*.05;
    const px=(x,z)=>W/2+(x-cx)*F/z, py=z=>hz+camH*F/z;
    const fade=z=>Math.max(0,Math.min(1,1-(z-zmin)/(zfar-zmin)))**.9;
    glow(W/2,hz,W*.6,[[0,'rgba(124,58,237,.42)'],[.35,'rgba(76,29,149,.18)'],[1,'rgba(9,8,13,0)']]);
    // crowd: camera flashes and phone lights in the stands along the horizon
    flashes.forEach(f=>{const k=(t+f.t)%6, on=k<.12?1-k/.12:0, base=.18+.12*Math.sin(t*1.3+f.ph);
      const x=f.x*W, y=hz-H*.03-f.y*H*.13, r=(1.2+on*5)*dpr;
      ctx.fillStyle=`rgba(${on?'255,255,255':'196,181,253'},${a3(Math.min(.9,base+on*.8))})`; ctx.beginPath(); ctx.arc(x,y,r,0,6.283); ctx.fill();});
    // hardwood: boards run the length of the court, alternate tone every 12 feet of length
    for(let Y=Math.floor((camZ+zmin)/12)*12-12; Y<camZ+zfar; Y+=12){
      const za=Math.max(zmin*.8,Y-camZ), zb=Math.max(zmin*.8,Y+12-camZ); if(zb<=za) continue;
      const a=.5*fade((za+zb)/2);
      ctx.fillStyle=((Y/12)%2+2)%2===1?`rgba(52,30,92,${a3(a)})`:`rgba(36,20,70,${a3(a)})`;
      ctx.beginPath(); ctx.moveTo(px(-HALF,za),py(za)); ctx.lineTo(px(HALF,za),py(za)); ctx.lineTo(px(HALF,zb),py(zb)); ctx.lineTo(px(-HALF,zb),py(zb)); ctx.fill();
    }
    ctx.globalCompositeOperation='lighter';
    for(let x=-HALF+2.5; x<HALF; x+=2.5){                                                       // board seams
      const z0=zmin*.8, z1=zfar*.7;
      ctx.strokeStyle='rgba(167,139,250,.07)'; ctx.lineWidth=Math.max(1,6*dpr/z0);
      ctx.beginPath(); ctx.moveTo(px(x,z0),py(z0)); ctx.lineTo(px(x,z1),py(z1)); ctx.stroke();
    }
    const line=(pts,alpha,wd)=>{ if(pts.length<2) return;
      const zm=pts.reduce((s,p)=>s+p[1],0)/pts.length, a=alpha*fade(zm); if(a<=0.01) return;
      ctx.strokeStyle=`rgba(216,204,255,${a3(a)})`; ctx.lineWidth=Math.max(1,wd*dpr/Math.max(zmin,zm));
      ctx.beginPath(); pts.forEach(([x,z],i)=>{ const X=px(x,z), Y=py(z); i?ctx.lineTo(X,Y):ctx.moveTo(X,Y); }); ctx.stroke(); };
    const arc=(x0,z0,r,a0,a1,n=40)=>{const out=[]; for(let i=0;i<=n;i++){const a=a0+(a1-a0)*i/n; out.push([x0+r*Math.cos(a),z0+r*Math.sin(a)]);} return out;};
    const clip=pts=>pts.map(([x,z])=>[x,z-camZ]).filter(([,z])=>z>zmin*.8);
    const first=Math.floor((camZ-LEN)/LEN)*LEN;
    for(let c=first; c<camZ+zfar; c+=LEN){                                                       // court after court
      const B0=c, B1=c+LEN;
      const segs=[
        [[-HALF,B0],[HALF,B0]], [[-HALF,B1],[HALF,B1]],                                           // baselines
        [[-HALF,B0+LEN/2],[HALF,B0+LEN/2]],                                                        // half-court line
        [[-8,B0],[-8,B0+19],[8,B0+19],[8,B0]], [[-8,B1],[-8,B1-19],[8,B1-19],[8,B1]],              // keys
        [[-22,B0],[-22,B0+14]], [[22,B0],[22,B0+14]], [[-22,B1],[-22,B1-14]], [[22,B1],[22,B1-14]] // corner threes
      ];
      segs.forEach(s=>{ const p=clip(s); if(p.length===s.length) line(p,.75,40); });
      const curves=[arc(0,B0+LEN/2,6,0,6.2832,48), arc(0,B0+19,6,0,6.2832,36), arc(0,B1-19,6,0,6.2832,36),
        arc(0,B0+5.25,23.75,Math.asin(8.75/23.75)*0+0.38,Math.PI-0.38,40), arc(0,B1-5.25,23.75,Math.PI+0.38,2*Math.PI-0.38,40)];
      curves.forEach(cu=>{ const p=clip(cu); if(p.length>4) line(p,.7,34); });
      [[0,B0+4],[0,B1-4]].forEach(([x,z])=>{ const zz=z-camZ; if(zz>18){ const r=Math.max(1.5,F/zz*.9);      // rims (far ones only:
        ctx.strokeStyle=`rgba(251,146,60,${a3(.8*fade(zz))})`; ctx.lineWidth=Math.max(1,30*dpr/zz);                 // up close they'd fill the screen)
        ctx.beginPath(); ctx.ellipse(px(x,zz),py(zz)-F/zz*10,r,r*.35,0,0,6.283); ctx.stroke(); }});
      const zc=B0+LEN/2-camZ; if(zc>24){ const k=Math.min(1,(zc-24)/30)*fade(zc);                               // center-court glow,
        ctx.save(); ctx.translate(px(0,zc),py(zc)); ctx.scale(1,camH/zc*1.6);                                      // capped and faded near the camera
        glow(0,0,Math.min(W*.2,F/zc*7),[[0,`rgba(167,139,250,${a3(.28*k)})`],[1,'rgba(139,92,246,0)']]); ctx.restore(); }
    }
    [-HALF,HALF].forEach(x=>{ for(let z=zmin*.8; z<zfar; z*=1.18){ const z2=Math.min(zfar,z*1.18);     // sidelines
      ctx.strokeStyle=`rgba(216,204,255,${a3(.75*fade(z))})`; ctx.lineWidth=Math.max(1,40*dpr/z);
      ctx.beginPath(); ctx.moveTo(px(x,z),py(z)); ctx.lineTo(px(x,z2),py(z2)); ctx.stroke(); }});
    const hg=ctx.createLinearGradient(0,hz-H*.02,0,hz+H*.1); hg.addColorStop(0,'rgba(124,58,237,.35)'); hg.addColorStop(1,'rgba(124,58,237,0)');
    ctx.fillStyle=hg; ctx.fillRect(0,hz-H*.02,W,H*.12);
    // the scoreboard over center court, and two spotlights sweeping the floor
    const jx=W/2+Math.sin(t*.2)*W*.01, jy=H*.11;
    glow(jx,jy,H*.28,[[0,'rgba(233,221,255,.35)'],[.25,'rgba(167,139,250,.18)'],[1,'rgba(139,92,246,0)']]);
    ctx.fillStyle='rgba(255,255,255,.85)'; const bw=W*.05, bh=H*.03;
    ctx.fillRect(jx-bw/2,jy-bh/2,bw,bh*.18); ctx.fillRect(jx-bw/2,jy+bh/2-bh*.18,bw,bh*.18);
    [[W*.12,0,.55],[W*.88,0,-.55]].forEach(([lx,ly,dir],k)=>{
      const ang=Math.PI/2-dir*(.5+.25*Math.sin(t*(.4+k*.1)+k*2)), sp=.07, len=H*1.6;
      const g=ctx.createLinearGradient(lx,ly,lx+Math.cos(ang)*len,ly+Math.sin(ang)*len);
      g.addColorStop(0,'rgba(221,214,254,.30)'); g.addColorStop(.45,'rgba(167,139,250,.10)'); g.addColorStop(1,'rgba(139,92,246,0)');
      ctx.fillStyle=g; ctx.beginPath(); ctx.moveTo(lx,ly);
      ctx.lineTo(lx+Math.cos(ang-sp)*len,ly+Math.sin(ang-sp)*len); ctx.lineTo(lx+Math.cos(ang+sp)*len,ly+Math.sin(ang+sp)*len); ctx.fill();
      const hit=(hz+H*.25-ly)/Math.sin(ang);
      ctx.save(); ctx.translate(lx+Math.cos(ang)*hit,hz+H*.25); ctx.scale(1,.32); glow(0,0,W*.12,[[0,'rgba(196,181,253,.22)'],[1,'rgba(139,92,246,0)']]); ctx.restore();
    });
    motes.forEach(m=>{ m.y-=m.v/30; if(m.y<-.05){m.y=1.05; m.x=Math.random();}
      ctx.fillStyle=`rgba(221,214,254,${a3(.25+.35*(.5+.5*Math.sin(t*1.7+m.ph)))})`;
      ctx.beginPath(); ctx.arc((m.x+.02*Math.sin(t*.6+m.ph))*W,m.y*H,m.s*dpr,0,6.283); ctx.fill(); });
    ctx.globalCompositeOperation='source-over';
  }
  size(); addEventListener('resize',size);
  const floor=page==='method'?.32:.55; let op=-1;
  const dim=()=>{const v=Math.round((1-Math.min(1,scrollY/600)*(1-floor))*100)/100; if(v!==op){op=v; cv.style.opacity=v;}};
  dim(); addEventListener('scroll',dim,{passive:true});
  if(REDUCE){ frame(7); addEventListener('resize',()=>frame(7)); return; }
  const fps=innerWidth<700?24:30, t0=performance.now(); let last=-1e9;
  const tick=now=>{requestAnimationFrame(tick); if(document.hidden||now-last<1000/fps-2) return; last=now; frame((now-t0)/1000);};
  requestAnimationFrame(tick);
}

/* Search (Ctrl+K, / or the magnifier): pages, teams, the next few days' games and every game day. Day arrows and
   ← → keys on the day page, back-to-top, cards sliding in, numbers counting up, phone tab bar. */
function navExtras(page){
  const PAGEFILE={week:'index.html',season:'season.html',teams:'teams.html',method:'method.html'};
  const svg=d=>`<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const ICON={'index.html':svg('<rect x="3" y="4" width="18" height="17" rx="3"/><path d="M3 9h18M8 2v4M16 2v4"/>'),
    'index.html#bets':svg('<path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/>'),
    'season.html':svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
    'teams.html':svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3v18M5.6 5.6c3.5 3.5 3.5 9.3 0 12.8M18.4 5.6c-3.5 3.5-3.5 9.3 0 12.8"/>'),
    'method.html':svg('<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7"/>')};
  $$('.nav a').forEach(a=>{const k=a.getAttribute('href'); if(ICON[k]&&!a.querySelector('svg')) a.innerHTML=ICON[k]+`<span>${esc(a.textContent)}</span>`;});

  const cur=D.currentDay, days=[...new Set(D.games.map(g=>g.day))].sort();
  const near=new Set(days.filter(d=>d>=cur).slice(0,3));
  const ITEMS=[
    {grp:'Pages',label:'Today',href:`index.html#day${cur}`,ico:'◉'},
    {grp:'Pages',label:'Best bets',href:`index.html#day${cur}`,goto:'playsWrap',ico:'★'},
    {grp:'Pages',label:'My bets',href:'index.html#bets',ico:'$'},
    {grp:'Pages',label:'Season & scoreboard',href:'season.html',ico:'▲'},
    {grp:'Pages',label:'Teams & power ratings',href:'teams.html',ico:'◆'},
    {grp:'Pages',label:'Method & research',href:'method.html',ico:'?'},
    ...(D.teams||[]).map(t=>({grp:'Teams',label:t.full||t.name,href:teamHref(t.team),goto:'teamName',teams:[t.team],sub:t.record})),
    ...D.games.filter(g=>near.has(g.day)).map(g=>({grp:'Games',label:`${g.awayName} at ${g.homeName}`,href:`index.html#day${g.day}`,
      goto:'g-'+g.id,teams:[g.away,g.home],sub:`${fmtDay(g.day)} · ${tipTime(g)}`})),
    ...days.slice().reverse().map(d=>({grp:'Days',label:dayName(d),href:`index.html#day${d}`,ico:String(ymd(d).getUTCDate()),sub:d===D.today?'today':''}))
  ].map(it=>({...it,keys:`${it.label} ${(it.teams||[]).join(' ')}`.toLowerCase().split(/[\s·&,]+/).filter(Boolean)}));
  const bar=$('.brandrow');
  let btn=null;
  if(bar){ btn=document.createElement('button'); btn.type='button'; btn.className='cmdk-btn'; btn.setAttribute('aria-label','Search the site');
    btn.innerHTML=svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>')+'<span>Search</span><kbd>Ctrl K</kbd>';
    bar.insertBefore(btn,bar.querySelector('.stamp')); btn.addEventListener('click',()=>open()); }
  const ov=document.createElement('div'); ov.className='cmdk'; ov.hidden=true;
  ov.innerHTML=`<div class="cmdk-box" role="dialog" aria-modal="true" aria-label="Search the site">
    <input type="text" placeholder="Search teams, games, days, pages…" aria-label="Search" aria-controls="cmdkList" autocomplete="off" spellcheck="false">
    <div class="cmdk-list" id="cmdkList" role="listbox"></div><div class="cmdk-foot">↑ ↓ to move · Enter to open · Esc to close</div></div>`;
  document.body.appendChild(ov);
  const inp=ov.querySelector('input'), list=ov.querySelector('.cmdk-list');
  let shown=[], sel=0;
  function draw(){
    const q=inp.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    shown=q.length?ITEMS.filter(it=>q.every(w=>it.keys.some(k=>k.startsWith(w)))).slice(0,40)
      :ITEMS.filter(it=>it.grp==='Pages'||(it.grp==='Games'&&it.href.endsWith('#day'+cur)));
    sel=Math.min(sel,Math.max(0,shown.length-1));
    let last='';
    list.innerHTML=shown.map((it,i)=>{const h=it.grp!==last?`<div class="cmdk-grp">${it.grp}</div>`:''; last=it.grp;
      const icon=it.teams?`<span class="cmdk-logos">${it.teams.map(c=>logo(c,'xs')).join('')}</span>`:`<span class="cmdk-ico">${esc(it.ico)}</span>`;
      return h+`<div class="cmdk-it${i===sel?' on':''}" data-i="${i}" role="option" aria-selected="${i===sel}">${icon}<span>${esc(it.label)}</span>${it.sub?`<span class="sub">${esc(it.sub)}</span>`:''}</div>`;}).join('')
      ||'<div class="cmdk-none">Nothing found.</div>';
    const on=list.querySelector('.on'); if(on) on.scrollIntoView({block:'nearest'});
  }
  function open(){ ov.hidden=false; inp.value=''; sel=0; draw(); inp.focus(); }
  function close(){ if(ov.hidden) return; ov.hidden=true; if(btn) btn.focus({preventScroll:true}); }
  function go(it){
    if(!it) return; close();
    const [file,hash='']=it.href.split('#');
    if(file!==PAGEFILE[page]){ try{sessionStorage.setItem('btb.goto',it.goto||'');}catch(_){} location.href=it.href; return; }
    if(page==='teams'&&hash){ const b=$(`[data-team="${CSS.escape(decodeURIComponent(hash))}"]`); if(b) b.click(); }
    else if(location.hash!=='#'+hash) location.hash=hash;
    setTimeout(()=>goTo(it.goto||(page==='week'?'':'top')),120);
  }
  function goTo(id){
    if(id==='top'){ scrollTo({top:0,behavior:REDUCE?'auto':'smooth'}); return; }
    const el=id&&document.getElementById(id); if(!el||!el.offsetParent) return;
    el.scrollIntoView({behavior:REDUCE?'auto':'smooth',block:'start'});
    if(el.classList.contains('game')&&el.animate) el.animate([{boxShadow:'0 0 0 3px #a78bfa'},{boxShadow:'0 0 0 0 rgba(167,139,250,0)'}],{duration:1800});
  }
  inp.addEventListener('input',()=>{sel=0; draw();});
  inp.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){sel=Math.min(sel+1,shown.length-1); draw(); e.preventDefault();}
    else if(e.key==='ArrowUp'){sel=Math.max(sel-1,0); draw(); e.preventDefault();}
    else if(e.key==='Enter'){e.preventDefault(); go(shown[sel]);}
    else if(e.key==='Escape'){close();}
  });
  list.addEventListener('click',e=>{const it=e.target.closest('[data-i]'); if(it) go(shown[+it.dataset.i]);});
  ov.addEventListener('click',e=>{if(e.target===ov) close();});
  setTimeout(()=>{let id=''; try{id=sessionStorage.getItem('btb.goto')||''; sessionStorage.removeItem('btb.goto');}catch(_){} if(id) goTo(id);},350);

  if(page==='week'&&$('#weekTitle')&&dayStep){
    const box=document.createElement('span'); box.className='wkarrows';
    box.innerHTML='<button type="button" aria-label="Previous day">‹</button><button type="button" aria-label="Next day">›</button>';
    $('#weekTitle').after(box);
    const [prev,next]=box.children;
    const sync=()=>{const [i,n]=dayAt(); prev.disabled=i<=0; next.disabled=i<0||i>=n-1;};
    prev.addEventListener('click',()=>dayStep(-1)); next.addEventListener('click',()=>dayStep(1));
    new MutationObserver(sync).observe($('#rail'),{childList:true}); sync();
  }
  document.addEventListener('keydown',e=>{
    const typing=/^(input|select|textarea)$/i.test((e.target||{}).tagName||'')||(e.target&&e.target.isContentEditable);
    if((e.key==='k'||e.key==='K')&&(e.ctrlKey||e.metaKey)){ e.preventDefault(); ov.hidden?open():close(); return; }
    if(!ov.hidden||typing||e.ctrlKey||e.metaKey||e.altKey) return;
    if(e.key==='/'){ e.preventDefault(); open(); return; }
    if(dayStep&&(e.key==='ArrowLeft'||e.key==='ArrowRight')&&$('#weekView')&&!$('#weekView').hidden) dayStep(e.key==='ArrowLeft'?-1:1);
  });

  const top=document.createElement('button'); top.type='button'; top.className='totop'; top.setAttribute('aria-label','Back to top'); top.textContent='↑';
  document.body.appendChild(top); top.addEventListener('click',()=>scrollTo({top:0,behavior:REDUCE?'auto':'smooth'}));
  addEventListener('scroll',()=>top.classList.toggle('show',scrollY>700),{passive:true});

  if(REDUCE||!('IntersectionObserver' in window)) return;
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in'); io.unobserve(e.target);}}),{rootMargin:'0px 0px -40px 0px'});
  $$('.game,.best,.kpi,.tablebox,.panel,.chart,.prose h2,.ukey').forEach((el,i)=>{
    const r=el.getBoundingClientRect(); if(!el.offsetParent||r.top<innerHeight) return;
    el.classList.add('rv'); el.style.transitionDelay=(i%3)*70+'ms'; io.observe(el);});
  $$('.kpi .v').forEach(el=>{
    const node=el.firstChild; if(el.childNodes.length!==1||!node||node.nodeType!==3) return;
    const m=node.textContent.match(/^([^\d−-]*)([−-]?)([\d,]+(?:\.\d+)?)(.*)$/); if(!m) return;
    const target=parseFloat(m[3].replace(/,/g,'')), dec=(m[3].split('.')[1]||'').length, t0=performance.now(), final=node.textContent;
    const tick=t=>{const k=Math.min(1,(t-t0)/900), v=target*(1-Math.pow(1-k,3));
      node.textContent=k<1?m[1]+m[2]+v.toLocaleString('en-US',{minimumFractionDigits:dec,maximumFractionDigits:dec})+m[4]:final; if(k<1) requestAnimationFrame(tick);};
    requestAnimationFrame(tick);
  });
}

window.EDGE_TEST={betMath,fairNow,feePer,betText};
chrome();
const page=($('main')||{}).dataset?.page;
({week:dayPage,season:seasonPage,teams:teamsPage,method:methodPage}[page]||(()=>{}))();
liveTick();
if(page){ courtBg(page); navExtras(page); }
})();
