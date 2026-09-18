// ===========================================================
// turtbo-agent landing page · interactions
// ===========================================================
(function(){
  'use strict';

  // ---- 1. 构造叶轮叶片 (SVG path) ---------------------------
  const rotor = document.getElementById('rotor');
  const stator = document.getElementById('stator');
  const turbineSvg = document.querySelector('.turbine');

  // 占位：JS 加载完成前先放 11 个小蓝点，避免叶轮区空洞
  if (rotor && !rotor.children.length) {
    for (let i=0;i<11;i++){
      const a=(360/11)*i, r=(a-90)*Math.PI/180;
      const cx=Math.cos(r)*90, cy=Math.sin(r)*90;
      const c = document.createElementNS('http://www.w3.org/2000/svg','circle');
      c.setAttribute('cx',cx); c.setAttribute('cy',cy); c.setAttribute('r','3');
      c.setAttribute('fill','#19d3ff'); c.setAttribute('opacity','0.5');
      rotor.appendChild(c);
    }
  }

  if (rotor && stator) {
    const N_ROTOR = 11;   // DF90-001 转子 12 → 11
    const N_STATOR = 11;

    // 单片叶片形状 - 流线型
    const bladePath = (length, width, lean) => {
      // 根部 → 叶尖 的扭叶片
      const p = [];
      const w = width;
      const L = length;
      // 压力面
      p.push(`M ${-w*0.5} 4`);
      p.push(`C ${-w*0.6+lean} ${L*0.3}, ${-w*0.3+lean} ${L*0.7}, ${-w*0.05} ${L}`);
      // 叶尖
      p.push(`Q ${w*0.25} ${L+2}, ${w*0.4} ${L*0.95}`);
      // 吸力面
      p.push(`C ${w*0.5+lean} ${L*0.7}, ${w*0.6+lean} ${L*0.3}, ${w*0.5} 4`);
      // 根部封口
      p.push(`Z`);
      return p.join(' ');
    };

    const buildRing = (host, n, opts={}) => {
      const {length=140, width=22, lean=8, fill='url(#bladeFill)', stroke='#19d3ff', strokeOpacity=0.6, innerR=46} = opts;
      for (let i=0; i<n; i++){
        const ang = (360/n) * i;
        const g = document.createElementNS('http://www.w3.org/2000/svg','g');
        g.setAttribute('transform', `rotate(${ang})`);
        const path = document.createElementNS('http://www.w3.org/2000/svg','path');
        path.setAttribute('d', bladePath(length, width, lean));
        path.setAttribute('fill', fill);
        path.setAttribute('stroke', stroke);
        path.setAttribute('stroke-width', '0.8');
        path.setAttribute('stroke-opacity', strokeOpacity);
        path.setAttribute('opacity', '0.85');
        // 让叶片从 hub 边缘向外伸出
        path.setAttribute('transform', `translate(${innerR-6}, 0)`);
        g.appendChild(path);
        host.appendChild(g);
      }
    };

    buildRing(rotor,  N_ROTOR,  {length:138, width:24, lean:10, stroke:'#19d3ff', strokeOpacity:0.7, innerR:46});
    // 静子：参数更瘦、外圈、淡绿
    buildRing(stator, N_STATOR, {length:124, width:18, lean:-6, stroke:'#7af0c5', strokeOpacity:0.35, innerR:72});
  }

  // ---- 2. 刻度线 --------------------------------------------
  const ticksG = turbineSvg && turbineSvg.querySelector('.ticks');
  if (ticksG) {
    for (let i=0; i<72; i++){
      const ang = (360/72) * i;
      const isMajor = i % 6 === 0;
      const r1 = 178, r2 = isMajor ? 168 : 174;
      const a = (ang - 90) * Math.PI / 180;
      const x1 = Math.cos(a)*r1, y1 = Math.sin(a)*r1;
      const x2 = Math.cos(a)*r2, y2 = Math.sin(a)*r2;
      const line = document.createElementNS('http://www.w3.org/2000/svg','line');
      line.setAttribute('x1', x1); line.setAttribute('y1', y1);
      line.setAttribute('x2', x2); line.setAttribute('y2', y2);
      line.setAttribute('stroke', '#19d3ff');
      line.setAttribute('stroke-width', isMajor ? '1.2' : '0.5');
      line.setAttribute('opacity', isMajor ? '0.9' : '0.4');
      ticksG.appendChild(line);
    }
    // 角度文字
    for (let i=0; i<12; i++){
      const ang = (360/12) * i - 90;
      const r = 158;
      const x = Math.cos(ang*Math.PI/180)*r;
      const y = Math.sin(ang*Math.PI/180)*r;
      const t = document.createElementNS('http://www.w3.org/2000/svg','text');
      t.setAttribute('x', x); t.setAttribute('y', y);
      t.setAttribute('text-anchor','middle'); t.setAttribute('dominant-baseline','middle');
      t.setAttribute('fill','#19d3ff'); t.setAttribute('opacity','0.6');
      t.setAttribute('font-family','JetBrains Mono, monospace');
      t.setAttribute('font-size','6');
      t.textContent = (i*30) + '°';
      ticksG.appendChild(t);
    }
  }

  // ---- 3. 数字计数动画 --------------------------------------
  const counters = document.querySelectorAll('[data-count]');
  const animateCount = (el) => {
    const target = parseInt(el.getAttribute('data-count'), 10);
    const dur = 1400;
    const start = performance.now();
    const tick = (now) => {
      const t = Math.min((now-start)/dur, 1);
      const ease = 1 - Math.pow(1-t, 3);
      el.textContent = Math.floor(target * ease).toString();
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = target.toString();
    };
    requestAnimationFrame(tick);
  };

  // ---- 4. IntersectionObserver 触发动画 ----------------------
  const seen = new WeakSet();
  const io = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if (e.isIntersecting && !seen.has(e.target)){
        seen.add(e.target);
        e.target.classList.add('in');
        e.target.querySelectorAll('[data-count]').forEach(animateCount);
      }
    });
  }, {threshold:0.25});

  document.querySelectorAll('.strip-cell').forEach(c=>io.observe(c));

  // ---- 5. 闸门进入动画 --------------------------------------
  const gateIO = new IntersectionObserver((entries)=>{
    entries.forEach(e=>{
      if (e.isIntersecting){
        e.target.style.opacity = '1';
        e.target.style.transform = 'translateX(0)';
      }
    });
  }, {threshold:0.15});
  document.querySelectorAll('.gate').forEach((g,i)=>{
    g.style.opacity = '0';
    g.style.transform = 'translateX(-30px)';
    g.style.transition = `all 0.7s cubic-bezier(.2,.7,.2,1) ${i*0.06}s`;
    gateIO.observe(g);
  });

  // ---- 6. 滚动时叶轮视差 ------------------------------------
  let ticking = false;
  window.addEventListener('scroll', ()=>{
    if (!ticking){
      requestAnimationFrame(()=>{
        const y = window.scrollY;
        if (turbineSvg){
          turbineSvg.style.transform = `translateY(${y * -0.05}px) rotate(${y * 0.02}deg)`;
        }
        ticking = false;
      });
      ticking = true;
    }
  }, {passive:true});

  // ---- 7. 终端日志逐字出现 ----------------------------------
  const logEl = document.querySelector('.side-log');
  if (logEl){
    const html = logEl.innerHTML;
    logEl.innerHTML = '';
    let i = 0;
    const typer = () => {
      if (i >= html.length) return;
      logEl.innerHTML = html.slice(0, i);
      i += 3;
      setTimeout(typer, 12);
    };
    setTimeout(typer, 800);
  }

  // ---- 8. 入口 greeting --------------------------------------
  console.log('%c turtbo·agent ', 'background:#f6c860;color:#000;font-weight:700;padding:4px 10px;border-radius:2px;font-family:JetBrains Mono;font-size:12px');
  console.log('%c FOUNDRY · 叶轮机械气动设计的 agent 工作流 ', 'color:#19d3ff;font-family:JetBrains Mono;font-size:11px');
  console.log('%c → 七道闸门 · 三条规矩 · 一个工作台 ', 'color:#7d97b9;font-family:JetBrains Mono;font-size:10px');

})();
