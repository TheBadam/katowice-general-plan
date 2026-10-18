"""Payload builder and static exporter for the interactive map viewer.

build_map_payload() turns parsed GML features into the JSON the canvas
viewer page loads; export_static() writes that page (index.html, en/, pl/)
plus mapdata.json as a fully static site - hostable on any static file
server, no Python needed at serving time.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
from matplotlib.colors import to_rgb
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

_INTERACTIVE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GML map</title>
<style>
  html, body { margin: 0; height: 100%; font-family: system-ui, sans-serif;
               overflow: hidden; }
  body { display: flex; flex-direction: column; }
  #topbar { flex: none; display: flex; align-items: center; gap: 10px;
            padding: 8px 12px; background: #fff;
            border-bottom: 1px solid #ddd; }
  #titles { flex: 1; min-width: 0; }
  #topbar h1 { font-size: 15px; font-weight: 600; margin: 0;
               line-height: 1.4; }
  #psubtitle { font-size: 12px; color: #555; margin-top: 2px;
               line-height: 1.4; }
  #paneltoggle { width: 15px; flex: none; border: none;
                 border-left: 1px solid #ccc; background: #f7f7f7;
                 cursor: pointer; padding: 0; display: flex;
                 align-items: center; justify-content: center; }
  #paneltoggle:hover { background: #e8e8e8; }
  #paneltoggle svg { width: 8px; height: 12px; display: block;
                     transition: transform 0.15s; }
  #paneltoggle path { fill: none; stroke: #555; stroke-width: 2; }
  #paneltoggle.closed svg { transform: rotate(180deg); }
  #wrap { display: flex; flex: 1; min-height: 0; }
  #canvas { flex: 1; display: block; cursor: grab; min-width: 0;
            touch-action: none; }
  #canvas.dragging { cursor: grabbing; }
  #resizer { width: 6px; flex: none; cursor: col-resize;
             background: transparent; }
  #resizer:hover, #resizer.active { background: #0366d455; }
  #panel { width: 300px; flex: none; background: #f7f7f7;
           border-left: 1px solid #ccc; overflow-y: auto; padding: 10px;
           font-size: 13px; box-sizing: border-box;
           container-type: inline-size; }
  .group { margin-bottom: 10px; padding: 6px 8px; border: 1px solid #ddd;
           border-radius: 6px; background: #fff; }
  .group.off { opacity: 0.45; }
  .group .head { display: flex; align-items: center; gap: 6px; }
  .group .swatch { width: 12px; height: 12px; border: 1px solid #0006;
                   border-radius: 2px; flex: none; }
  .group label { flex: 1; cursor: pointer; font-weight: 600;
                 overflow: hidden; text-overflow: ellipsis;
                 white-space: nowrap; }
  .group .cnt { color: #666; font-weight: 400; font-size: 11px; }
  .group input[type=range] { width: 100%; margin: 6px 0 0; }
  .zgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px;
           margin-top: 6px; }
  .zrow { display: flex; align-items: flex-start; gap: 4px;
          font-size: 10.5px; cursor: pointer; user-select: none;
          color: #444; line-height: 1.3; padding: 1px 2px;
          border-radius: 3px; }
  .zrow:hover { background: #eee; }
  .zrow.off { opacity: 0.35; }
  .zsw { width: 9px; height: 9px; margin-top: 2px; flex: none;
         border: 1px solid #0004; border-radius: 2px; display: inline-block; }
  /* collapse the zone grid to one column in a narrow panel */
  @container (max-width: 280px) {
    .zgrid { grid-template-columns: 1fr; }
  }
  .group .hint { color: #777; font-size: 11px; margin-top: 2px; }
  .group .gtitle { color: #333; font-size: 11.5px; margin: 3px 0 2px;
                   line-height: 1.4; white-space: normal; }
  .group details.gdetails { margin-top: 4px; font-size: 11px; }
  .group details.gdetails summary { cursor: pointer; color: #0366d6;
                                    user-select: none; }
  .group details.gdetails div { color: #555; margin-top: 4px;
                                line-height: 1.5; white-space: normal; }
  .group .desc { color: #555; font-size: 11px; margin-top: 4px;
                 white-space: normal; line-height: 1.4; }
  .btns button { margin: 3px 0; padding: 5px 8px; font-size: 12px;
                 width: 100%; cursor: pointer; }
  #panel a { color: #0366d6; font-size: 12px; display: block; margin: 10px 0; }
  .src { color: #777; font-size: 11px; margin: -6px 0 8px;
         word-break: break-word; }
  .lang { margin: -4px 0 8px; font-size: 12px; }
  #langsel a { color: #0366d6; margin: 0 10px 0 0; font-weight: 600;
               display: inline-block; }
  #langsel a.cur { color: #000; pointer-events: none; }
  .plabel { color: #555; font-size: 10.5px; text-transform: uppercase;
            letter-spacing: 0.04em; }
  .lang .plabel { margin-right: 8px; }
  .plinks .plabel { display: block; margin-bottom: 3px; }

  .sechead { margin: 14px 0 6px; font-size: 11px; text-transform: uppercase;
             letter-spacing: 0.04em; color: #555;
             border-bottom: 1px solid #ddd; padding-bottom: 3px; }
  .sechead input { margin: 0 5px 0 0; vertical-align: middle; }
  .plinks { margin: 0 0 8px; font-size: 12px; }
  #plinks a { color: #0366d6; display: inline-block; margin: 0 10px 4px 0; }
  .note { margin: 0 0 12px; font-size: 12px; color: #444; }
  .note summary { cursor: pointer; color: #0366d6; font-weight: 600; }
  .note div { margin-top: 6px; line-height: 1.5; white-space: normal; }
  #info { position: fixed; background: #fff; border: 1px solid #999;
          border-radius: 4px; padding: 6px 9px; font-size: 12px;
          pointer-events: none; display: none; z-index: 10;
          max-width: 280px; white-space: normal;
          box-shadow: 2px 2px 6px #0003; }
  #info .desc { color: #555; margin-top: 3px; display: block; }
  /* small screens: the panel overlays the map instead of squeezing it */
  @media (max-width: 700px) {
    #topbar { padding: 6px 10px; }
    #topbar h1 { font-size: 13px; }
    #psubtitle { font-size: 11px; }
    #wrap { position: relative; }
    #resizer { display: none; }
    #paneltoggle { position: absolute; top: 0; right: 0; bottom: 0;
                   z-index: 6; }
    #panel { position: absolute; top: 0; right: 15px; bottom: 0;
             z-index: 5; max-width: calc(85vw - 15px);
             box-shadow: -2px 0 10px #0003; }
    .zrow { padding: 5px 3px; }
    .group .head input[type=checkbox] { width: 16px; height: 16px; }
    .btns button { padding: 8px 6px; }
  }
</style>
</head>
<body>
<div id="topbar">
  <div id="titles">
    <h1 id="ptitle">Loading...</h1>
    <div id="psubtitle" style="display:none"></div>
  </div>
</div>
<div id="wrap">
  <canvas id="canvas"></canvas>
  <div id="resizer" title="drag to resize panel"></div>
  <button id="paneltoggle" title="toggle panel"><svg viewBox="0 0 8 12"><path d="M1 1l6 5-6 5"/></svg></button>
  <div id="panel">
    <div class="lang" id="langsel"></div>
    <div class="src" id="psrc"></div>
    <div class="plinks" id="plinks"></div>
    <details id="pnote" class="note" style="display:none">
      <summary id="notesum">Explanation</summary>
      <div id="notetext"></div>
    </details>
    <div id="groups"></div>
    <div class="btns">
      <button id="zoomin"></button>
      <button id="zoomout"></button>
      <button id="fitbtn"></button>
      <button id="png"></button>
    </div>
    __CLASSIC_LINK__
  </div>
</div>
<div id="info"></div>
<script>
"use strict";
// language from the URL path (/en/ or /pl/); otherwise Polish, except
// for browsers reporting an English locale
const langMatch = location.pathname.match(/\/(en|pl)(\/|$)/);
const LANG = langMatch ? langMatch[1]
  : ((navigator.language || 'pl').toLowerCase().startsWith('en') ? 'en' : 'pl');
const MAPDATA_URL = (langMatch ? '../' : '') + 'mapdata.json';
// UI labels: injected at export time from the built-in EN/PL set,
// optionally overridden via --i18n (see i18n.json)
const I18N = __I18N__;
const L = I18N[LANG] || I18N.en;
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const info = document.getElementById('info');
let DATA = null, paths = [], streets = [], groups = {};
let streetsPath = null;  // all streets merged into one Path2D
const state = {};   // group name -> {on, alpha}
const view = {s: 1, tx: 0, ty: 0};
let dpr = 1;
// hatch configuration for overlay groups: app-level only (from mapdata),
// no UI. width/spacing in CSS px; fill = opacity of the solid color
// between the hatch lines (0 = transparent).
let HATCH = {width: 2.5, spacing: 16, fill: 0};

function esc(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
function darkenHex(h) {
  h = h.replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  const f = c => Math.round(parseInt(c, 16) * 0.6);
  return 'rgb(' + f(h.slice(0, 2)) + ',' + f(h.slice(2, 4)) + ',' + f(h.slice(4, 6)) + ')';
}
// 45-degree hatch patterns for group overlays: colored "/" lines on a
// transparent background. Line thickness and spacing (CSS px) come from
// the app configuration (HATCH); tile spacing is spacing*sqrt(2) so the
// line distance equals the configured value. Anchored to the screen via
// the inverse of the current view transform, so line width and spacing
// stay constant while panning and zooming.
const hatchCache = {};
function hatchPattern(color, widthPx, spacingPx) {
  const key = color + '|' + widthPx + '|' + spacingPx + '|' + dpr;
  let pat = hatchCache[key];
  if (!pat) {
    const s = Math.max(8, Math.round(spacingPx * Math.SQRT2 * dpr));
    const tile = document.createElement('canvas');
    tile.width = tile.height = s;
    const t = tile.getContext('2d');
    t.strokeStyle = color;
    t.lineWidth = Math.max(1, widthPx * dpr);
    t.beginPath();
    // seamless family of lines x + y = s/2 + n*s: two segments per tile
    t.moveTo(-2, s / 2 + 2); t.lineTo(s / 2 + 2, -2);
    t.moveTo(s / 2 - 2, s + 2); t.lineTo(s + 2, s / 2 - 2);
    t.stroke();
    pat = ctx.createPattern(tile, 'repeat');
    hatchCache[key] = pat;
  }
  pat.setTransform(ctx.getTransform().inverse());
  return pat;
}
// --- shareable view state in the URL --------------------------------
// Serializes group/zone toggles and opacities into the ?s= query
// parameter so a view can be shared by copying the URL. A query
// parameter survives social-platform link handling (Instagram etc.
// can strip #fragments); replaceState avoids history spam.
let saveTimer = null;
function saveState() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const out = {};
    for (const name in state) {
      const s = state[name];
      const e = {on: s.on ? 1 : 0, a: s.alpha};
      if (s.zones) {  // list only the disabled zone types
        const off = Object.keys(s.zones).filter(k => !s.zones[k]);
        e.z = off.join(',');
      }
      out[name] = e;
    }
    history.replaceState(null, '',
      '?s=' + encodeURIComponent(JSON.stringify(out)));
  }, 200);
}
function loadState() {
  // accept the state from ?s=... or the legacy #s=... fragment
  let raw = new URLSearchParams(location.search).get('s');
  if (!raw) {
    const m = location.hash.match(/^[#&]s=([^&]+)/);
    if (m) raw = decodeURIComponent(m[1]);
  }
  if (!raw) return;
  let data = null;
  try { data = JSON.parse(raw); } catch (err) {}
  if (!data) {  // tolerate double-encoded values from link wrappers
    try { data = JSON.parse(decodeURIComponent(raw)); } catch (err) {}
  }
  if (!data) return;
  for (const name in data) {
    const s = state[name], d = data[name];
    if (!s || typeof d !== 'object') continue;
    if (typeof d.on === 'number') s.on = !!d.on;
    if (typeof d.a === 'number' && d.a >= 0.05 && d.a <= 1) s.alpha = d.a;
    if (s.zones && typeof d.z === 'string') {
      const off = d.z ? d.z.split(',') : [];
      for (const k in s.zones) s.zones[k] = !off.includes(k);
    }
  }
}
function initGroups() {
  for (const g of DATA.groups) {
    groups[g.name] = g;
    const s = {on: g.on !== false, alpha: g.alpha || 0.62};
    if (g.zones) {  // per-zone-type on/off via the panel zone rows;
      s.zones = {};  // they start consistent with the layer's state
      for (const z of g.zones) s.zones[z.sym] = g.on !== false;
    }
    state[g.name] = s;
  }
}
function makePath(f) {
  const entry = {g: f.g, bc: f.bc, be: f.be || null, bg: f.bg,
                 layer: f.layer, ozn: f.ozn,
                 sym: f.sym, t: f.t, b: null};
  if (f.t === 'pt') { entry.x = f.x; entry.y = f.y; entry.b = [f.x, f.y, f.x, f.y]; return entry; }
  const p = new Path2D();
  let minx = 1e18, miny = 1e18, maxx = -1e18, maxy = -1e18;
  const upd = (x, y) => { if (x < minx) minx = x; if (y < miny) miny = y;
                           if (x > maxx) maxx = x; if (y > maxy) maxy = y; };
  if (f.t === 'p') {
    for (const part of f.parts) {
      for (let ri = 0; ri < part.length; ri++) {
        const r = part[ri];
        p.moveTo(r[0], r[1]); upd(r[0], r[1]);
        for (let i = 2; i < r.length; i += 2) { p.lineTo(r[i], r[i+1]); upd(r[i], r[i+1]); }
        p.closePath();
      }
    }
  } else {
    const r = f.parts[0][0];
    p.moveTo(r[0], r[1]); upd(r[0], r[1]);
    for (let i = 2; i < r.length; i += 2) { p.lineTo(r[i], r[i+1]); upd(r[i], r[i+1]); }
  }
  entry.p = p; entry.b = [minx, miny, maxx, maxy];
  return entry;
}
function resize() {
  // cap the pixel ratio: dpr 3 phones triple the fill cost for no gain
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(canvas.clientWidth * dpr);
  canvas.height = Math.round(canvas.clientHeight * dpr);
  if (DATA) draw();
}
function fit() {
  const [minx, miny, maxx, maxy] = DATA.bounds;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  const s = Math.min(w / (maxx - minx), h / (maxy - miny)) * 0.95;
  view.s = s;
  view.tx = (w - s * (minx + maxx)) / 2;
  view.ty = (h + s * (miny + maxy)) / 2;
}
function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(view.s * dpr, 0, 0, -view.s * dpr, view.tx * dpr, view.ty * dpr);
  ctx.lineJoin = 'round';
  // viewport culling: only draw features intersecting the visible world rect
  const vw = canvas.width / dpr, vh = canvas.height / dpr;
  const vx0 = -view.tx / view.s, vx1 = (vw - view.tx) / view.s;
  const vy0 = (view.ty - vh) / view.s, vy1 = view.ty / view.s;
  const visible = b =>
    b[2] >= vx0 && b[0] <= vx1 && b[3] >= vy0 && b[1] <= vy1;
  // base pass: every feature in its base color, controlled by its base group
  for (const pf of paths) {
    const st = state[pf.bg];
    if (!st || !st.on) continue;
    if (st.zones && pf.sym && st.zones[pf.sym] === false) continue;
    if (!visible(pf.b)) continue;
    if (pf.t === 'p') {
      // pf.ba: zone-definition initial fill transparency; the group's
      // opacity slider scales this initial level
      ctx.globalAlpha = st.alpha * (pf.ba === undefined ? 1 : pf.ba);
      ctx.fillStyle = pf.bc;
      ctx.fill(pf.p, 'evenodd');
      if (!pf.be) {  // zone borders are stroked in a separate top pass
        ctx.globalAlpha = Math.min(1, st.alpha + 0.2);
        ctx.strokeStyle = darkenHex(pf.bc);
        ctx.lineWidth = 1 / view.s;
        ctx.stroke(pf.p);
      }
    } else if (pf.t === 'l') {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = pf.be || darkenHex(pf.bc);
      ctx.lineWidth = 1.4 / view.s;
      ctx.stroke(pf.p);
    } else {
      ctx.globalAlpha = 1;
      ctx.fillStyle = pf.bc;
      ctx.strokeStyle = pf.be || darkenHex(pf.bc);
      ctx.lineWidth = 1 / view.s;
      ctx.beginPath();
      ctx.arc(pf.x, pf.y, 6 / view.s, 0, 2 * Math.PI);
      ctx.fill(); ctx.stroke();
    }
  }
  // overlay pass: group overlays painted on top of the base rendering;
  // polygons are hatched with the group color (app-configured width,
  // spacing and fill). The per-group opacity slider is the group's total
  // opacity: it scales fill, hatch lines and edge together (base 1).
  for (const pf of paths) {
    if (!pf.g) continue;
    const st = state[pf.g];
    if (!st || !st.on) continue;
    if (!visible(pf.b)) continue;
    const gr = groups[pf.g];
    if (pf.t === 'p') {
      if (HATCH.fill > 0) {  // optional solid fill between the lines
        ctx.globalAlpha = HATCH.fill * st.alpha;
        ctx.fillStyle = gr.color;
        ctx.fill(pf.p, 'evenodd');
      }
      ctx.globalAlpha = st.alpha;
      ctx.fillStyle = hatchPattern(gr.color, HATCH.width, HATCH.spacing);
      ctx.fill(pf.p, 'evenodd');
      ctx.globalAlpha = st.alpha;
      ctx.strokeStyle = gr.edge;
      ctx.lineWidth = 1 / view.s;
      ctx.stroke(pf.p);
    } else if (pf.t === 'l') {
      ctx.globalAlpha = st.alpha;
      ctx.strokeStyle = gr.edge;
      ctx.lineWidth = 1.4 / view.s;
      ctx.stroke(pf.p);
    } else {
      ctx.globalAlpha = st.alpha;
      ctx.fillStyle = gr.color;
      ctx.strokeStyle = gr.edge;
      ctx.lineWidth = 1 / view.s;
      ctx.beginPath();
      ctx.arc(pf.x, pf.y, 6 / view.s, 0, 2 * Math.PI);
      ctx.fill(); ctx.stroke();
    }
  }
  // zone borders: stroked on top of overlays so they stay visible
  for (const pf of paths) {
    if (!pf.be || pf.t !== 'p') continue;
    const st = state[pf.bg];
    if (!st || !st.on) continue;
    if (st.zones && pf.sym && st.zones[pf.sym] === false) continue;
    if (!visible(pf.b)) continue;
    ctx.globalAlpha = 1;
    ctx.strokeStyle = pf.be;
    ctx.lineWidth = 1.2 / view.s;
    ctx.stroke(pf.p);
  }
  const stS = state['streets'];
  if (stS && stS.on && streetsPath) {
    ctx.globalAlpha = stS.alpha;
    ctx.strokeStyle = groups['streets'].edge;
    ctx.lineWidth = 1.1 / view.s;
    ctx.stroke(streetsPath);
  }
  ctx.globalAlpha = 1;
  if (stS && stS.on) drawStreetLabels(visible);
}
function drawStreetLabels(visible) {
  // draw in CSS pixels: scale the backing store by dpr (devicePixelRatio)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.font = '10px system-ui, sans-serif';
  for (const s of streets) {
    if (!visible(s.b)) continue;
    if (s.len * view.s < 90) continue;  // too short at this zoom
    const ax = view.tx + view.s * s.lab[0], ay = view.ty - view.s * s.lab[1];
    const bx = view.tx + view.s * s.lab[2], by = view.ty - view.s * s.lab[3];
    let ang = Math.atan2(by - ay, bx - ax);
    if (ang > Math.PI / 2) ang -= Math.PI;
    else if (ang < -Math.PI / 2) ang += Math.PI;
    ctx.save();
    ctx.translate((ax + bx) / 2, (ay + by) / 2);
    ctx.rotate(ang);
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.strokeText(s.name, 0, -3);
    ctx.fillStyle = '#222';
    ctx.fillText(s.name, 0, -3);
    ctx.restore();
  }
}
function zoomAt(mx, my, factor) {
  view.tx = mx - (mx - view.tx) * factor;
  view.ty = my - (my - view.ty) * factor;
  view.s *= factor;
  draw();
}
function identify(mx, my) {
  const wx = (mx - view.tx) / view.s;
  const wy = (view.ty - my) / view.s;
  ctx.setTransform(view.s * dpr, 0, 0, -view.s * dpr, view.tx * dpr, view.ty * dpr);
  for (let i = paths.length - 1; i >= 0; i--) {
    const pf = paths[i];
    const st = state[pf.bg];
    if (!st || !st.on || pf.t !== 'p') continue;
    if (st.zones && pf.sym && st.zones[pf.sym] === false) continue;
    if (wx < pf.b[0] || wy < pf.b[1] || wx > pf.b[2] || wy > pf.b[3]) continue;
    if (ctx.isPointInPath(pf.p, wx, wy)) {
      const g = pf.g ? groups[pf.g] : null;
      let html = '<b>' + esc(pf.ozn || pf.layer) + '</b>' +
        '<br>' + L.layer + ': ' + esc(pf.layer);
      if (pf.g) html += '<br>' + L.group + ': ' + esc(pf.g);
      if (pf.sym) html += '<br>' + L.symbol + ': ' + esc(pf.sym);
      if (g) {
        const t = g.desc_title || g.desc;
        if (t) {
          const short = t.length > 140 ? t.slice(0, 140) + '...' : t;
          html += '<span class="desc">' + esc(short) + '</span>';
        }
      }
      info.innerHTML = html;
      info.style.display = 'block';
      info.style.left = Math.max(0, Math.min(mx + 14, window.innerWidth - 290)) + 'px';
      info.style.top = (my + 14) + 'px';
      return true;
    }
  }
  info.style.display = 'none';
  return false;
}
function swatchBackground(g) {
  // preview the group's 45-degree hatch (configured width + spacing)
  return g.kind === 'group'
    ? 'repeating-linear-gradient(135deg,' + g.color + ' 0 ' + HATCH.width + 'px,' +
      'transparent ' + HATCH.width + 'px ' + (HATCH.width + HATCH.spacing) + 'px)'
    : g.color;
}
function groupBlock(g, counts) {
  const st = state[g.name];
  const on = st.on;
  if (g.name === 'streets') counts[g.name] = streets.length;
  const range = (attr, label, min, max, step, val) =>
    '<input type="range" min="' + min + '" max="' + max + '" step="' + step +
    '" value="' + val + '" data-' + attr + '="' + esc(g.name) +
    '" data-label="' + esc(label) + '">' +
    '<div class="hint">' + label + ' ' + val + '</div>';
  let html = '<div class="group' + (on ? '' : ' off') + '" id="grp-' + esc(g.name) + '" title="' + esc(g.name) + '">' +
    '<div class="head">' +
    '<input type="checkbox"' + (on ? ' checked' : '') + ' data-toggle="' + esc(g.name) + '">' +
    '<span class="swatch" style="background:' + swatchBackground(g) + '"></span>' +
    '<label>' + esc(g.kind === 'streets' ? L.secStreets : (g.label || g.name)) +
    ' <span class="cnt">' + (counts[g.name] || 0) + '</span></label></div>' +
    (g.desc_title ? '<div class="gtitle">' + esc(g.desc_title) + '</div>' : '') +
    // zone-type toggles: full names in a two-column grid, color-coded
    (g.zones && g.zones.length ? '<div class="zgrid">' +
      g.zones.map(z => '<span class="zrow' +
        (st.zones[z.sym] === false ? ' off' : '') +
        '" data-zone="' + esc(z.sym) + '" data-group="' + esc(g.name) +
        '"><i class="zsw" style="background:' + z.color + '"></i>' +
        esc(z.title) + '</span>').join('') + '</div>' : '') +
    // streets are toggle-only; everything else keeps the opacity slider
    (g.kind === 'streets' ? '' :
      range('alpha', L.opacity, '0.05', '1', '0.01', st.alpha)) +
    (g.desc ? '<details class="gdetails"><summary>' + L.details + '</summary><div>' +
      esc(g.desc) + '</div></details>' : '') +
    '</div>';
  return html;
}

function buildPanel() {
  const counts = {};
  for (const pf of paths) {
    if (pf.g) counts[pf.g] = (counts[pf.g] || 0) + 1;
    if (pf.bg && pf.bg !== pf.g) counts[pf.bg] = (counts[pf.bg] || 0) + 1;
  }
  const secs = { layer: [], group: [], streets: [] };
  for (const g of DATA.groups) secs[g.kind || 'group'].push(g);
  let html = '';
  // sections: environmental impact on top, then GML layers, streets last
  for (const sec of [[L.secGroups, secs.group, 'group'],
                     [L.secLayers, secs.layer, 'layer'],
                     [L.secStreets, secs.streets, 'streets']]) {
    if (!sec[1].length) continue;
    html += '<h4 class="sechead">';
    if (sec[2] === 'group') {  // master switch for all impact groups
      html += '<input type="checkbox" data-secmaster="group">';
    }
    html += esc(sec[0]) + '</h4><div class="secbody" data-sec="' + sec[2] + '">';
    for (const g of sec[1]) html += groupBlock(g, counts);
    html += '</div>';
  }
  document.getElementById('groups').innerHTML = html;
  document.querySelectorAll('[data-toggle]').forEach(el => {
    el.addEventListener('change', () => {
      const s = state[el.dataset.toggle];
      s.on = el.checked;
      if (s.zones) {  // zone layers: master selects/deselects every zone
        for (const k in s.zones) s.zones[k] = el.checked;
        el.closest('.group').querySelectorAll('[data-zone]').forEach(z =>
          z.classList.toggle('off', !el.checked));
      }
      document.getElementById('grp-' + el.dataset.toggle).classList.toggle('off', !el.checked);
      draw();
      saveState();
    });
  });
  document.querySelectorAll('[data-zone]').forEach(el => {
    el.addEventListener('click', () => {
      const s = state[el.dataset.group];
      s.zones[el.dataset.zone] = !s.zones[el.dataset.zone];
      el.classList.toggle('off', !s.zones[el.dataset.zone]);
      // tri-state master checkbox: "-" (indeterminate) while the zone
      // selection is mixed; all-on checks it, all-off unchecks it
      const vals = Object.values(s.zones);
      const all = vals.every(Boolean), none = vals.every(v => !v);
      const card = el.closest('.group');
      const master = card.querySelector('[data-toggle]');
      s.on = !none;
      master.checked = all;
      master.indeterminate = !all && !none;
      card.classList.toggle('off', none);
      draw();
      saveState();
    });
  });
  // section master: tri-state switch for all impact groups, mirroring
  // the zone master ("-" = mixed selection, click to enable all)
  const secMaster = document.querySelector('[data-secmaster]');
  if (secMaster) {
    const groupToggles = () =>
      document.querySelectorAll('[data-sec="group"] [data-toggle]');
    const syncMaster = () => {
      const states = [...groupToggles()].map(el => state[el.dataset.toggle].on);
      secMaster.checked = states.every(Boolean);
      secMaster.indeterminate =
        !secMaster.checked && !states.every(v => !v);
    };
    secMaster.addEventListener('change', () => {
      groupToggles().forEach(el => {
        state[el.dataset.toggle].on = secMaster.checked;
        el.checked = secMaster.checked;
        document.getElementById('grp-' + el.dataset.toggle)
          .classList.toggle('off', !secMaster.checked);
      });
      draw();
      saveState();
    });
    groupToggles().forEach(el =>
      el.addEventListener('change', syncMaster));
    syncMaster();
  }
  // zone-layer master checkboxes start consistent with their zone states
  // (covers both fresh loads and views restored from the URL hash)
  document.querySelectorAll('[data-toggle]').forEach(el => {
    const s = state[el.dataset.toggle];
    if (s && s.zones) {
      const vals = Object.values(s.zones);
      const all = vals.every(Boolean), none = vals.every(v => !v);
      el.checked = all;
      el.indeterminate = !all && !none;
    }
  });
  document.querySelectorAll('[data-alpha]').forEach(el => {
    el.addEventListener('input', () => {
      state[el.dataset.alpha].alpha = parseFloat(el.value);
      el.parentElement.querySelector('.hint').textContent =
        el.dataset.label + ' ' + el.value;
      draw();
      saveState();
    });
  });
}
async function load() {
  let res;
  try {
    res = await fetch(MAPDATA_URL);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    DATA = await res.json();
  } catch (err) {
    // surface load failures instead of a silent white page
    document.getElementById('ptitle').textContent =
      L.loadError + MAPDATA_URL;
    return;
  }
  if (DATA.hatch) HATCH = Object.assign(HATCH, DATA.hatch);
  document.title = DATA.page_title || DATA.title;
  document.getElementById('ptitle').textContent = DATA.page_title || DATA.title;
  const pst = DATA.page_subtitle || '';
  const psub = document.getElementById('psubtitle');
  psub.textContent = pst;
  psub.style.display = pst ? 'block' : 'none';
  document.getElementById('zoomin').textContent = L.zoomIn;
  document.getElementById('zoomout').textContent = L.zoomOut;
  document.getElementById('fitbtn').textContent = L.reset;
  document.getElementById('png').textContent = L.png;
  document.getElementById('notesum').textContent = L.explanation;
  const ls = document.getElementById('langsel');
  const lb = langMatch ? '../' : '';
  ls.innerHTML = '<span class="plabel">' + esc(L.language) + '</span>' +
    '<a href="' + lb + 'en/"' +
    (LANG === 'en' ? ' class="cur"' : '') + '>EN</a>' +
    '<a href="' + lb + 'pl/"' + (LANG === 'pl' ? ' class="cur"' : '') + '>PL</a>';
  if (DATA.src) {
    document.getElementById('psrc').textContent = L.data + DATA.src;
  }
  if (DATA.links && DATA.links.length) {
    document.getElementById('plinks').innerHTML =
      '<span class="plabel">' + esc(L.links) + '</span>' +
      DATA.links.map(l => '<a href="' + esc(l.url) +
        '" target="_blank" rel="noopener">' +
        esc(L['link.' + l.name] || l.name) + '</a>').join('');
  }
  if (DATA.note) {
    document.getElementById('pnote').style.display = 'block';
    document.getElementById('notetext').textContent = DATA.note;
  }
  initGroups();
  loadState();  // restore a shared view from the URL hash, if any
  // build Path2D geometry in chunks, yielding between chunks: keeps the
  // page responsive on memory-constrained in-app browsers
  const feats = DATA.features;
  for (let i = 0; i < feats.length; i += 200) {
    const end = Math.min(i + 200, feats.length);
    for (let j = i; j < end; j++) paths.push(makePath(feats[j]));
    await new Promise(r => setTimeout(r, 0));
  }
  if (DATA.streets) {
    // every street shares one stroke style, so merge them all into a
    // single Path2D instead of one object per street (memory + draw
    // calls); labels keep their own per-street metadata
    const sp = new Path2D();
    for (const s of DATA.streets) {
      const r = s.parts[0];
      sp.moveTo(r[0], r[1]);
      let minx = 1e18, miny = 1e18, maxx = -1e18, maxy = -1e18;
      const up = (x, y) => { if (x < minx) minx = x; if (y < miny) miny = y;
                             if (x > maxx) maxx = x; if (y > maxy) maxy = y; };
      up(r[0], r[1]);
      for (let i = 2; i < r.length; i += 2) { sp.lineTo(r[i], r[i + 1]); up(r[i], r[i + 1]); }
      streets.push({name: s.name, len: s.len, lab: s.lab,
                    b: [minx, miny, maxx, maxy]});
    }
    streetsPath = sp;
  }
  // the parsed payload is not needed past this point: free it for GC
  DATA.features = null;
  DATA.streets = null;
  buildPanel();
  resize(); fit(); draw();
}

// --- pointer input: mouse drag/hover/click plus touch pan, pinch zoom
// and tap-to-pin. Pointer events fire for mouse and touch alike.
let drag = null, pinned = false, hoverRaf = null;
let lastHover = {x: 0, y: 0};
const activePtrs = new Map();  // canvas pointerId -> {x, y}
let pinch = null;              // two-finger distance at the previous step
function canvasPos(e) {
  const r = canvas.getBoundingClientRect();
  return {x: e.clientX - r.left, y: e.clientY - r.top};
}
canvas.addEventListener('pointerdown', e => {
  activePtrs.set(e.pointerId, {x: e.clientX, y: e.clientY});
  try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
  if (activePtrs.size === 1) {
    drag = {x: e.clientX, y: e.clientY, moved: false};
    canvas.classList.add('dragging');
  } else {  // second finger: pinch zoom instead of pan
    drag = null;
    pinch = null;
    canvas.classList.remove('dragging');
  }
});
canvas.addEventListener('pointermove', e => {
  if (!DATA) return;
  const p = activePtrs.get(e.pointerId);
  if (p) { p.x = e.clientX; p.y = e.clientY; }
  if (activePtrs.size >= 2) {  // pinch zoom around the finger midpoint
    const pts = [...activePtrs.values()];
    const d = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    if (pinch !== null && d > 0 && pinch > 0) {
      const r = canvas.getBoundingClientRect();
      zoomAt((pts[0].x + pts[1].x) / 2 - r.left,
             (pts[0].y + pts[1].y) / 2 - r.top, d / pinch);
    }
    pinch = d;
    return;
  }
  if (drag) {  // one-pointer pan
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
    if (drag.moved) {
      view.tx += e.clientX - drag.x;
      view.ty += e.clientY - drag.y;
      drag.x = e.clientX; drag.y = e.clientY;
      draw();
    }
    return;
  }
  if (e.pointerType === 'mouse' && !pinned) {  // hover tooltip (mouse)
    lastHover = canvasPos(e);
    if (!hoverRaf) {
      hoverRaf = requestAnimationFrame(() => {
        hoverRaf = null;
        identify(lastHover.x, lastHover.y);
      });
    }
  }
});
canvas.addEventListener('pointerup', e => {
  activePtrs.delete(e.pointerId);
  pinch = null;
  if (drag) {
    const moved = drag.moved;
    drag = null;
    canvas.classList.remove('dragging');
    if (!moved) {
      // click or tap pins/unpins the details shown on hover
      const cp = canvasPos(e);
      if (pinned) {
        pinned = false;
        info.style.display = 'none';
      } else {
        pinned = identify(cp.x, cp.y);
      }
    }
  }
});
canvas.addEventListener('pointercancel', e => {
  activePtrs.delete(e.pointerId);
  pinch = null;
  drag = null;
  canvas.classList.remove('dragging');
});
canvas.addEventListener('pointerleave', () => {
  if (!pinned) info.style.display = 'none';
});
window.addEventListener('mousemove', e => {
  if (resizing) {  // panel width drag (desktop; hidden on touch layouts)
    const w = Math.min(600, Math.max(200,
      resizing.w - (e.clientX - resizing.x)));  // panel is right-anchored
    panel.style.width = w + 'px';
    if (!sizeRaf) {
      sizeRaf = requestAnimationFrame(() => { sizeRaf = null; resize(); });
    }
  }
});
window.addEventListener('mouseup', () => {
  if (resizing) {
    resizing = null;
    resizer.classList.remove('active');
    document.body.style.cursor = '';
    try { localStorage.setItem('panelWidth', panel.offsetWidth); } catch (err) {}
  }
});

// panel resizing
const panel = document.getElementById('panel');
const resizer = document.getElementById('resizer');
let resizing = null, sizeRaf = null;
// collapsible panel: the toggle sits on the panel's left edge and
// stays visible when the panel is hidden
const panelToggle = document.getElementById('paneltoggle');
panelToggle.addEventListener('click', () => {
  const show = panel.style.display === 'none';
  panel.style.display = show ? '' : 'none';
  resizer.style.display = show ? '' : 'none';
  panelToggle.classList.toggle('closed', !show);
  resize();
});
try {
  const saved = localStorage.getItem('panelWidth');
  if (saved) panel.style.width = Math.min(600, Math.max(200, +saved)) + 'px';
} catch (err) {}
resizer.addEventListener('mousedown', e => {
  resizing = {x: e.clientX, w: panel.offsetWidth};
  resizer.classList.add('active');
  document.body.style.cursor = 'col-resize';
  e.preventDefault();
});
window.addEventListener('keydown', e => { if (e.key === 'Escape') { pinned = false; info.style.display = 'none'; } });
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const f = e.deltaY < 0 ? 1.2 : 1 / 1.2;
  zoomAt(e.offsetX, e.offsetY, f);
}, {passive: false});
document.getElementById('fitbtn').onclick = () => { fit(); draw(); };
document.getElementById('zoomin').onclick = () => zoomAt(canvas.clientWidth / 2, canvas.clientHeight / 2, 1.3);
document.getElementById('zoomout').onclick = () => zoomAt(canvas.clientWidth / 2, canvas.clientHeight / 2, 1 / 1.3);
document.getElementById('png').onclick = () => {
  const off = document.createElement('canvas');
  off.width = canvas.width; off.height = canvas.height;
  const octx = off.getContext('2d');
  octx.fillStyle = '#fff'; octx.fillRect(0, 0, off.width, off.height);
  octx.drawImage(canvas, 0, 0);
  const a = document.createElement('a');
  a.download = 'map.png';
  a.href = off.toDataURL('image/png');
  a.click();
};
window.addEventListener('resize', resize);
load();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# interactive canvas viewer payload
# ---------------------------------------------------------------------------

def _darken(color):
    r, g, b = to_rgb(color)
    return "#{:02x}{:02x}{:02x}".format(int(r * 153), int(g * 153), int(b * 153))


def _flat_ring(ring):
    out = []
    for x, y in ring.coords:
        out.append(round(x, 2))
        out.append(round(y, 2))
    return out


def _kind_of(geom: BaseGeometry) -> str:
    t = geom.geom_type
    if "Point" in t:
        return "pt"
    if "Line" in t or "Curve" in t:
        return "l"
    return "p"


def _flatten_geom(geom: BaseGeometry):
    if hasattr(geom, "geoms"):
        for p in geom.geoms:
            yield from _flatten_geom(p)
    else:
        yield geom


def build_map_payload(features, schema, prop, zone_mapping,
                      title, srs=None, resolve_key=None, streets=None,
                      overlay=False, descriptions=None,
                      page_title=None, page_subtitle=None, note=None,
                      links=None, src=None,
                      default_off=None, zone_definition=None, hatch=None,
                      default_alpha=None, layer_names=None,
                      street_tolerance=None):
    """Build the JSON payload for the interactive canvas viewer.

    `resolve_key(value) -> schema key or None` decides the group of a feature
    (same logic as the CLI color matching); required.
    `streets`: list of {"coords": [(x, y), ...], "name", "highway"} overlays.
    `overlay`: if True, features keep their original per-layer colors as
    individually controllable base layers and groups are painted on top;
    if False, groups replace the colors.
    `descriptions`: optional {group name: description text} shown in the UI.
    `default_alpha`: optional {group/layer name: opacity 0..1} setting
    the initial position of the per-group opacity slider.
    `layer_names`: optional {raw layer name: display name}; the key order
    sets the display order of the layer controls in the viewer panel.
    `street_tolerance`: optional Douglas-Peucker tolerance (CRS units)
    simplifying street geometry in the payload; trims its size and the
    memory needed to load it in the browser.
    `hatch`: app-level hatch config for overlay groups (no UI control):
    {"width": line thickness in px, "spacing": line distance in px,
    "fill": opacity 0..1 of the solid color between the lines}. Defaults
    to the reserved "global_hatch" entry of `schema` (the group-definitions
    file), which names the fill opacity "alpha".
    """
    if resolve_key is None:
        raise ValueError("resolve_key callback is required")

    hcfg = hatch or (schema or {}).get("global_hatch") or {}
    hatch = {
        "width": float(hcfg.get("width", 2.5)),
        "spacing": float(hcfg.get("spacing", 16.0)),
        "fill": float(hcfg.get("alpha", hcfg.get("fill", 0.0))),
    }
    if hatch["width"] <= 0 or hatch["spacing"] <= 0:
        raise ValueError("hatch width and spacing must be positive")
    if not 0 <= hatch["fill"] <= 1:
        raise ValueError("hatch fill must be a number in [0, 1]")

    if overlay:
        # the original per-layer colors form individually controllable
        # base layers; groups are painted on top as overlays
        cmap = mpl.colormaps["tab20"]
        raw = sorted({f.layer for f in features}, key=str.lower)
        lname = layer_names or {}
        # mapped layers first, in the file's key order; the rest after
        layer_order = [n for n in lname if n in raw] + \
                      [n for n in raw if n not in lname]
        base_color = {n: mpl.colors.to_hex(cmap(i % 20))
                      for i, n in enumerate(layer_order)}
        dalpha = default_alpha or {}
        groups = [{"name": n, "label": lname.get(n, n),
                   "color": base_color[n],
                   "edge": _darken(base_color[n]),
                   "alpha": dalpha.get(n, 0.62), "kind": "layer"}
                  for n in layer_order]
        groups += [{"name": k, "color": v, "edge": _darken(v),
                    "alpha": dalpha.get(k, 1.0), "kind": "group"}
                   for k, v in schema.items()
                   if k not in ("_default", "global_hatch")]
        color_by_group = {g["name"]: g["color"] for g in groups}
    else:
        dalpha = default_alpha or {}
        groups = [{"name": k, "color": v, "edge": _darken(v),
                   "alpha": dalpha.get(k, 0.62), "kind": "group"}
                   for k, v in schema.items()
                   if k not in ("_default", "global_hatch")]
        default_color = schema.get("_default", "#dddddd")
        groups.append({"name": "other", "color": default_color,
                       "edge": _darken(default_color), "alpha": 0.62,
                       "kind": "group"})
        color_by_group = {g["name"]: g["color"] for g in groups}
    if descriptions:
        for g in groups:
            d = descriptions.get(g["name"])
            if not d:
                continue
            if isinstance(d, dict):  # {"title": ..., "details": ...}
                if d.get("title"):
                    g["desc_title"] = str(d["title"]).strip()
                if d.get("details"):
                    g["desc"] = str(d["details"]).strip()
            elif str(d).strip():     # legacy: plain description string
                g["desc"] = str(d).strip()
    group_rank = {g["name"]: i for i, g in enumerate(groups)}
    kind_rank = {"p": 0, "l": 1, "pt": 2}

    entries = []
    zones_by_layer = {}  # layer -> {sym: {sym, title, color}} for the UI chips
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    for f in features:
        key = resolve_key(f.props.get(prop))
        if overlay:
            group = key if key in group_rank else None
            bc = base_color.get(f.layer, "#cccccc")
            bg = f.layer
        else:
            group = key if key in group_rank else "other"
            bc = color_by_group.get(group, "#dddddd")
            bg = group
        be = None
        sym = (f.props.get("symbol") or "").strip()
        zdef = (zone_definition or {}).get(sym)
        if zdef:
            # zone-type feature: definition color + explicit stroke; the
            # optional "alpha" is its initial fill transparency (the UI
            # opacity slider scales this level)
            bc = zdef["color"]
            be = zdef.get("stroke", "#191919")
        base = {
            "g": group,
            "bc": bc,
            "be": be,
            "bg": bg,
            "layer": f.layer,
            "ozn": (f.props.get(prop) or "").strip(),
            "sym": f.props.get("symbol", ""),
        }
        if zdef:
            base["ba"] = round(float(zdef.get("alpha", 1.0)), 3)
            zl = zones_by_layer.setdefault(f.layer, {})
            if sym not in zl:
                zl[sym] = {"sym": sym, "title": zdef["title"],
                           "color": zdef["color"]}
        for g in _flatten_geom(f.geom):
            kind = _kind_of(g)
            if kind == "p":
                if g.exterior is None:
                    continue
                part = [_flat_ring(g.exterior)]
                part.extend(_flat_ring(r) for r in g.interiors)
                entry = dict(base, t="p", parts=[part])
            elif kind == "l":
                entry = dict(base, t="l", parts=[[_flat_ring(g)]])
            else:
                entry = dict(base, t="pt", x=round(g.x, 2), y=round(g.y, 2))
            b = g.bounds
            if b and all(v == v for v in b):  # non-empty
                xmin, ymin = min(xmin, b[0]), min(ymin, b[1])
                xmax, ymax = max(xmax, b[2]), max(ymax, b[3])
            entries.append(entry)

    entries.sort(key=lambda e: (group_rank[e["bg"]],
                                kind_rank[e["t"]]))

    # per-zone-type on/off chips for layer groups containing zone features
    for g in groups:
        zl = zones_by_layer.get(g["name"])
        if zl and g.get("kind") == "layer":
            g["zones"] = [zl[k] for k in sorted(zl)]

    payload = {
        "title": title,
        "crs": srs or "",
        "bounds": [xmin, ymin, xmax, ymax],
        "groups": groups,
        "features": entries,
        "hatch": hatch,
    }
    if streets:
        # streets are not a color group feature; add their group for the UI
        payload["groups"].append({"name": "streets", "label": "Streets",
                                  "color": "#5a5a5a",
                                  "edge": "#3a3a3a", "alpha": 0.85,
                                  "kind": "streets"})
        web_streets = []
        for s in streets:
            pts = s["coords"]
            if len(pts) < 2:
                continue
            if street_tolerance:  # simplify street geometry (memory)
                pts = list(LineString(pts).simplify(
                    street_tolerance, preserve_topology=False).coords)
                if len(pts) < 2:
                    continue
            flat = []
            length = 0.0
            best = None  # longest segment for the label
            for i, (x, y) in enumerate(pts):
                flat.append(round(x, 2))
                flat.append(round(y, 2))
                if i:
                    dx, dy = x - pts[i - 1][0], y - pts[i - 1][1]
                    d = (dx * dx + dy * dy) ** 0.5
                    length += d
                    if best is None or d > best[0]:
                        best = (d, pts[i - 1][0], pts[i - 1][1], x, y)
            web_streets.append({
                "parts": [flat],
                "name": s.get("name", ""),
                "hw": s.get("highway", ""),
                "len": round(length, 1),
                "lab": [best[1], best[2], best[3], best[4]],
            })
        payload["streets"] = web_streets
        for s in web_streets:  # include streets in the rebase extent
            r = s["parts"][0]
            for i in range(0, len(r), 2):
                xmin, ymin = min(xmin, r[i]), min(ymin, r[i + 1])
                xmax, ymax = max(xmax, r[i]), max(ymax, r[i + 1])

    # Rebase all coordinates to a local origin. Browsers store canvas
    # path points as 32-bit floats, so absolute coordinates of millions
    # of meters lose precision and visibly drift at deep zoom-out.
    ox, oy = xmin, ymin

    def _shift_ring(r):
        for i in range(0, len(r), 2):
            r[i] = round(r[i] - ox, 2)
            r[i + 1] = round(r[i + 1] - oy, 2)

    for e in entries:
        if e["t"] == "pt":
            e["x"] = round(e["x"] - ox, 2)
            e["y"] = round(e["y"] - oy, 2)
        else:
            for part in e["parts"]:
                if e["t"] == "p":
                    for ring in part:
                        _shift_ring(ring)
                else:
                    _shift_ring(part[0])
    if payload.get("streets"):
        for s in payload["streets"]:
            _shift_ring(s["parts"][0])
            s["lab"] = [round(v - (ox if i % 2 == 0 else oy), 2)
                        for i, v in enumerate(s["lab"])]

    payload["bounds"] = [0, 0, round(xmax - ox, 2), round(ymax - oy, 2)]
    payload["page_title"] = page_title or title
    payload["page_subtitle"] = page_subtitle or ""
    payload["src"] = src or title
    payload["note"] = note or ""
    payload["links"] = links or []
    if default_off:
        for g in payload["groups"]:
            g["on"] = g["name"] not in default_off
    return payload


# Built-in UI labels for the viewer page (the keys the page script looks
# up); --i18n (see i18n.json) layers overrides on top of this set.
DEFAULT_I18N = {
    "en": {
        "secLayers": "GML layers",
        "secGroups": "Environmental impact",
        "secStreets": "Streets",
        "opacity": "opacity",
        "details": "details",
        "language": "Language",
        "links": "Links",
        "zoomIn": "Zoom in",
        "zoomOut": "Zoom out",
        "reset": "Reset view",
        "png": "Download PNG",
        "explanation": "Explanation",
        "loadError": "Failed to load map data from ",
        "layer": "layer",
        "group": "group",
        "symbol": "symbol",
        "data": "data: ",
    },
    "pl": {
        "secLayers": "Warstwy GML",
        "secGroups": "Oddziaływanie na środowisko",
        "secStreets": "Ulice",
        "opacity": "przezroczystość",
        "details": "szczegóły",
        "language": "Język",
        "links": "Linki",
        "zoomIn": "Przybliż",
        "zoomOut": "Oddal",
        "reset": "Resetuj widok",
        "png": "Pobierz PNG",
        "explanation": "Wyjaśnienie",
        "loadError": "Nie udało się wczytać danych mapy z ",
        "layer": "warstwa",
        "group": "grupa",
        "symbol": "symbol",
        "data": "dane: ",
    },
}


def merged_i18n(override=None):
    """DEFAULT_I18N updated with {lang: {key: text}} entries of `override`."""
    i18n = {lang: dict(labels) for lang, labels in DEFAULT_I18N.items()}
    for lang, labels in (override or {}).items():
        i18n.setdefault(lang, {}).update(labels)
    return i18n


def interactive_page_html(i18n=None):
    """The interactive viewer page for the static export.

    `i18n`: optional {lang: {key: text}} UI labels layered over the
    built-in EN/PL set; embedded into the page as JSON.
    The mapdata URL and the language are computed client-side from the page
    URL, so the same HTML works at any path (incl. /en/ and /pl/ subpaths).
    """
    html = _INTERACTIVE_HTML.replace(
        "__I18N__", json.dumps(merged_i18n(i18n), ensure_ascii=False))
    return html.replace("__CLASSIC_LINK__", "")


def export_static(payload, out_dir, i18n=None):
    """Write a fully static copy of the interactive viewer to `out_dir`.

    Produces index.html (auto language) plus en/ and pl/ copies, and
    mapdata.json; hostable on any static file server (nginx, GitHub Pages,
    S3, ...). `i18n` overrides the built-in UI labels ({lang: {key: text}},
    see i18n.json). No Python is needed at serving time.
    Returns the index.html path.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html = interactive_page_html(i18n)
    (out / "index.html").write_text(html, encoding="utf-8")
    for lang in ("en", "pl"):
        sub = out / lang
        sub.mkdir(exist_ok=True)
        (sub / "index.html").write_text(html, encoding="utf-8")
    (out / "mapdata.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out / "index.html"
