"""Генератор рилса (вертикальный 9:16 анимированный HTML) по позиции/сделке.

render_reel_html(data) — чистая функция: из данных позиции собирает самодостаточный
анимированный HTML в фирменном «Crypto Neural Universe» стиле (космос, glow, частицы,
count-up P&L). Это «запись экрана платформы» в виде проигрываемого ролика.

Из HTML сервер может получить mp4 headless-браузером (см. DEPLOY.md). Для этого модуля
важно, что сам HTML детерминирован и тестируется без сети.
"""
from __future__ import annotations

import html
from dataclasses import dataclass


@dataclass
class ReelData:
    symbol: str
    chain: str
    verdict: str            # PASS/REVIEW/BLOCK
    risk_score: int
    status: str             # open/closed
    entry_price: float
    last_price: float
    pnl_pct: float
    pnl_usd: float
    exit_reason: str | None = None
    confidence: float | None = None


def _vcolor(v: str) -> str:
    return {"PASS": "#34D399", "REVIEW": "#FBBF24", "BLOCK": "#F87171"}.get(v, "#8B5CF6")


def _spark_path(pnl_pct: float, w: int = 360, h: int = 90) -> str:
    """Простая траектория: вверх при плюсе, вниз при минусе, с шумом."""
    import math

    pts = []
    n = 24
    end = max(-0.9, min(2.5, pnl_pct / 100.0))
    for i in range(n):
        t = i / (n - 1)
        base = end * t
        noise = 0.06 * math.sin(i * 1.7) * (1 - t)
        y = h - (0.15 + (base + noise) * 0.55) * h
        x = t * w
        pts.append(f"{x:.1f},{max(2, min(h - 2, y)):.1f}")
    return "M" + " L".join(pts)


def render_reel_html(d: ReelData) -> str:
    vcol = _vcolor(d.verdict)
    pnl_sign = "+" if d.pnl_pct >= 0 else ""
    pnl_col = "#34D399" if d.pnl_pct >= 0 else "#F87171"
    status_label = "ПОЗИЦИЯ ЗАКРЫТА" if d.status == "closed" else "ОТКРЫТАЯ ПОЗИЦИЯ"
    reason = html.escape(d.exit_reason or ("ведётся" if d.status == "open" else "—"))
    sym = html.escape(d.symbol)
    chain = html.escape(d.chain)
    spark = _spark_path(d.pnl_pct)
    conf = f"{round(d.confidence * 100)}%" if d.confidence is not None else "—"

    return _TEMPLATE \
        .replace("{{SYM}}", sym) \
        .replace("{{CHAIN}}", chain) \
        .replace("{{VERDICT}}", html.escape(d.verdict)) \
        .replace("{{VCOL}}", vcol) \
        .replace("{{RISK}}", str(d.risk_score)) \
        .replace("{{STATUS}}", status_label) \
        .replace("{{ENTRY}}", f"{d.entry_price:.8g}") \
        .replace("{{LAST}}", f"{d.last_price:.8g}") \
        .replace("{{PNLPCT}}", f"{d.pnl_pct:.1f}") \
        .replace("{{PNLSIGN}}", pnl_sign) \
        .replace("{{PNLUSD}}", f"{pnl_sign}${abs(d.pnl_usd):,.0f}") \
        .replace("{{PNLCOL}}", pnl_col) \
        .replace("{{REASON}}", reason) \
        .replace("{{CONF}}", conf) \
        .replace("{{SPARK}}", spark)


_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALTSR reel · {{SYM}}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#05060B;overflow:hidden;font-family:Inter,system-ui,sans-serif;color:#EAF0FF}
#stage{position:relative;width:100vw;height:100vh;min-height:560px;display:flex;align-items:center;justify-content:center}
#bg{position:absolute;inset:0}
.card{position:relative;z-index:2;width:min(440px,94vw);aspect-ratio:9/16;max-height:96vh;border-radius:28px;
  background:linear-gradient(180deg,rgba(18,22,38,.6),rgba(8,10,20,.72));border:1px solid rgba(130,150,210,.14);
  backdrop-filter:blur(10px);box-shadow:0 30px 90px rgba(0,0,0,.5);padding:30px 28px;display:flex;flex-direction:column;overflow:hidden}
.sg{font-family:'Space Grotesk',sans-serif}
.top{display:flex;align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center;gap:10px}
.logo .g{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#8B5CF6,#22D3EE);display:flex;align-items:center;justify-content:center;color:#0a0b16;font-weight:700}
.tag{font-size:11px;letter-spacing:2px;color:#9AA6C4;border:1px solid rgba(130,150,210,.2);border-radius:999px;padding:5px 11px}
.orb{margin:30px auto 6px;width:120px;height:120px;border-radius:50%;position:relative;display:flex;align-items:center;justify-content:center}
.orb .core{width:120px;height:120px;border-radius:50%;background:radial-gradient(circle at 40% 35%,{{VCOL}},transparent 70%);filter:blur(2px);position:absolute;animation:pulse 2.4s ease-in-out infinite}
.orb .sym{position:relative;z-index:2;font-weight:700;font-size:26px}
@keyframes pulse{0%,100%{transform:scale(1);opacity:.9}50%{transform:scale(1.08);opacity:1}}
.status{text-align:center;font-size:12px;letter-spacing:3px;color:#9AA6C4;margin-top:4px}
.badges{display:flex;gap:8px;justify-content:center;margin-top:14px}
.badge{border-radius:8px;padding:4px 10px;font-size:12px;font-weight:600}
.pnl{text-align:center;margin-top:26px}
.pnl .big{font-size:64px;font-weight:700;line-height:1;color:{{PNLCOL}}}
.pnl .usd{font-size:18px;color:{{PNLCOL}};margin-top:6px;font-weight:600}
.row{display:flex;justify-content:space-between;font-size:13px;color:#9AA6C4;margin-top:22px;padding:0 4px}
.row b{color:#EAF0FF;font-weight:600}
.spark{margin:18px 0 6px}
.reason{margin-top:auto;background:rgba(10,12,22,.5);border:1px solid rgba(130,150,210,.14);border-radius:12px;padding:11px 14px;font-size:13px}
.reason .l{font-size:10px;letter-spacing:1.5px;color:#66708C}
.disc{margin-top:12px;font-size:10.5px;color:#66708C;line-height:1.5;text-align:center}
.reveal{opacity:0;transform:translateY(14px);animation:rise .7s ease-out forwards}
@keyframes rise{to{opacity:1;transform:none}}
.r1{animation-delay:.15s}.r2{animation-delay:.35s}.r3{animation-delay:.6s}.r4{animation-delay:.9s}.r5{animation-delay:1.1s}
@media (prefers-reduced-motion: reduce){.reveal{animation:none;opacity:1;transform:none}.orb .core{animation:none}}
</style></head>
<body>
<div id="stage">
  <canvas id="bg"></canvas>
  <div class="card">
    <div class="top reveal r1">
      <div class="logo"><div class="g sg">◎</div><div><div class="sg" style="font-weight:700">ALTSR</div><div style="font-size:10px;color:#9AA6C4;margin-top:-2px">Early Crypto Radar</div></div></div>
      <div class="tag">PAPER</div>
    </div>

    <div class="orb reveal r2"><div class="core"></div><div class="sym sg">${{SYM}}</div></div>
    <div class="status reveal r2">{{STATUS}} · {{CHAIN}}</div>
    <div class="badges reveal r3">
      <span class="badge" style="background:{{VCOL}}22;color:{{VCOL}}">{{VERDICT}} · risk {{RISK}}</span>
      <span class="badge" style="background:rgba(139,92,246,.18);color:#c4b5fd">conf {{CONF}}</span>
    </div>

    <div class="pnl reveal r3">
      <div class="big sg" id="pnl" data-to="{{PNLPCT}}">{{PNLSIGN}}0.0%</div>
      <div class="usd sg">{{PNLUSD}}</div>
    </div>

    <svg class="spark reveal r4" width="100%" height="90" viewBox="0 0 360 90" preserveAspectRatio="none">
      <path d="{{SPARK}}" fill="none" stroke="{{PNLCOL}}" stroke-width="2.5" stroke-linecap="round" pathLength="1"
        style="stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1.2s ease-out .9s forwards"/>
      <style>@keyframes draw{to{stroke-dashoffset:0}}</style>
    </svg>

    <div class="row reveal r4"><span>Вход <b>{{ENTRY}}</b></span><span>Выход <b>{{LAST}}</b></span></div>

    <div class="reason reveal r5"><div class="l">ПРИЧИНА ВЫХОДА</div><div style="margin-top:4px">{{REASON}}</div></div>
    <div class="disc reveal r5">Бумажная симуляция · не инвест-рекомендация · ~98% новых токенов обнуляются</div>
  </div>
</div>
<script>
// count-up P&L
(function(){
  var el=document.getElementById('pnl'); if(!el)return;
  var to=parseFloat(el.dataset.to)||0, sign=to>=0?'+':'', t0=null, dur=1100, start=Math.min(0,to), from=0;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){el.textContent=sign+to.toFixed(1)+'%';return;}
  function step(ts){if(!t0)t0=ts;var p=Math.min(1,(ts-t0)/dur);var v=from+(to-from)*(1-Math.pow(1-p,3));
    el.textContent=(v>=0?'+':'')+v.toFixed(1)+'%';if(p<1)requestAnimationFrame(step);}
  setTimeout(()=>requestAnimationFrame(step),600);
})();
// particle bg
(function(){
  var cv=document.getElementById('bg'),ctx=cv.getContext('2d'),w,h,ps=[];
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  function rz(){w=cv.width=innerWidth;h=cv.height=innerHeight;ps=[];for(var i=0;i<140;i++)ps.push({x:Math.random()*w,y:Math.random()*h,r:Math.random()*1.5+.3,vx:(Math.random()-.5)*.15,vy:(Math.random()-.5)*.15,a:Math.random()});}
  rz();addEventListener('resize',rz);
  function d(){ctx.clearRect(0,0,w,h);for(var i=0;i<ps.length;i++){var p=ps[i];p.x+=p.vx;p.y+=p.vy;if(p.x<0)p.x+=w;if(p.x>w)p.x-=w;if(p.y<0)p.y+=h;if(p.y>h)p.y-=h;ctx.globalAlpha=.4+Math.sin(p.a+=.01)*.3;ctx.fillStyle=Math.random()>.97?'#8B5CF6':'#6675a0';ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,6.28);ctx.fill();}ctx.globalAlpha=1;if(!reduce)requestAnimationFrame(d);}
  d();
})();
</script>
</body></html>
"""
