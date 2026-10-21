"use strict";
// language from the URL path (/en/ or /pl/); otherwise Polish, except
// for browsers reporting an English locale
const langMatch = location.pathname.match(/\/(en|pl)(\/|$)/);
const LANG = langMatch ? langMatch[1]
  : ((navigator.language || 'pl').toLowerCase().startsWith('en') ? 'en' : 'pl');
const MAPDATA_URL = (langMatch ? '../' : '') + 'mapdata.json';
// the greens layer downloads on demand, only when toggled on
const GREENS_URL = (langMatch ? '../' : '') + 'greens.json';
// UI labels: injected at export time from the i18n JSON file
// (--i18n, the single source of truth; see i18n.json)
const I18N = window.I18N;
const L = I18N[LANG] || I18N.en;
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const info = document.getElementById('info');
let DATA = null, paths = [], streets = [], groups = {};
let streetsPath = null;  // all streets merged into one Path2D
let greensPaths = null;  // zone-type x green-class merged Path2Ds
let greenStats = null;   // per-zone overlap stats for the tooltip
let greensFailed = false;
let greenCount = 0;
// openstreetmap-carto landcover palette (osm.org standard style)
const GREEN_COLORS = {forest: '#add19e', meadow: '#cdebb0',
                      park: '#c8facc', scrub: '#adde8b',
                      wetland: '#b6d5c0'};
let greenRate = 0.2;  // texture growth rate with zoom, established by
                      // tuning: 0 = constant on-screen size, 0.5 = grows
                      // with the square root of the zoom
let greenMin = 64;    // texture tile size (px) at the fit zoom - also the
                      // floor when zoomed out
let greenMax = 256;   // texture tile size (px) cap at deep zoom
let fitScale = 1;     // view.s at the fit zoom: the texture reference
let greenAnchor = {x: 0, y: 0};  // world point the greens tile grid is
                                 // pinned to: kept across pans (their
                                 // phase must not change), re-pinned to
                                 // the screen center on zoom changes
let greenAnchorS = null;         // view.s the anchor was pinned at
const greenPatternCache = {};  // cls -> pattern (one raster size at a time)
const greenPatternT = {};      // cls -> raster px the pattern was built at
function greenPattern(cls) {
  // One ground-anchored tile per class: the pattern transform maps
  // pattern pixels to world units (the negative y undoes the world
  // transform's y-flip), so the texture sticks to the ground while
  // panning. Its on-screen size grows with zoom at rate greenRate,
  // from greenMin px at the fit zoom - never below it, so zooming
  // out never gets denser than that - up to the greenMax cap:
  //   T = greenMin * (view.s / fitScale)^greenRate
  // The raster is drawn once at the greenMax cap, so the tile is
  // only ever downscaled on screen: crisp at every size. ~10
  // elements per tile: the density of the OSM standard style at
  // high zoom.
  const T = Math.min(greenMax,
    greenMin * Math.max(1, Math.pow(view.s / fitScale, greenRate)));
  const t = Math.round(greenMax * dpr);
  let pat = greenPatternCache[cls];
  if (!pat || greenPatternT[cls] !== t) {
    const cv = document.createElement('canvas');
    cv.width = cv.height = t;
    const c = cv.getContext('2d');
    c.fillStyle = GREEN_COLORS[cls] || '#cdebb0';
    c.fillRect(0, 0, t, t);
    const r = t / 32;
    if (cls === 'forest') {  // dark tree silhouettes, like osm.org woods
      c.fillStyle = '#4f804d';
      for (const [x, y] of [[5, 4], [14, 3], [23, 6], [9, 13], [19, 11],
                           [5, 21], [14, 19], [23, 22], [9, 29], [19, 27]]) {
        c.beginPath();
        c.arc(x * r, y * r, 1.6 * r, 0, 2 * Math.PI);
        c.fill();
        c.fillRect((x - 0.35) * r, (y + 1.1) * r, 0.7 * r, 1.3 * r);
      }
    } else if (cls === 'meadow') {  // sparse grass tufts
      c.strokeStyle = '#9cc178';
      c.lineWidth = 0.55 * r; c.lineCap = 'round';
      for (const [x, y] of [[8, 6], [17, 4], [26, 7], [12, 14], [22, 12],
                           [8, 22], [17, 20], [26, 23], [12, 30], [22, 28]]) {
        c.beginPath();
        c.moveTo((x - 1.5) * r, (y + 1.5) * r);
        c.lineTo(x * r, (y - 1.5) * r);
        c.lineTo((x + 1.5) * r, (y + 1.5) * r);
        c.stroke();
      }
    } else if (cls === 'scrub') {  // small shrubs, one blob each
      c.fillStyle = '#6fa15f';
      for (const [x, y] of [[3, 8], [12, 6], [21, 9], [7, 17], [17, 15],
                            [3, 24], [12, 22], [21, 25], [7, 30], [17, 28]]) {
        c.beginPath();
        c.arc(x * r, y * r, 1.5 * r, 0, 2 * Math.PI);
        c.fill();
      }
    } else if (cls === 'wetland') {  // horizontal reed dashes in rows
      c.strokeStyle = '#4e8a72';
      c.lineWidth = 0.65 * r; c.lineCap = 'round';
      for (const [x, y] of [[6, 5], [15, 4], [24, 6], [10, 13], [20, 11],
                            [6, 20], [15, 19], [24, 21], [10, 28], [20, 26]]) {
        c.beginPath();
        c.moveTo((x - 2) * r, y * r);
        c.lineTo((x + 2) * r, y * r);
        c.stroke();
      }
    }  // park: plain pastel fill, like osm.org parks
    pat = ctx.createPattern(cv, 'repeat');
    greenPatternCache[cls] = pat;
    greenPatternT[cls] = t;
  }
  // map pattern px into the space the engine actually uses, so the tile
  // always covers T screen px. Spec engines: cancel the world transform
  // (the negative y mirrors its y-flip) and pin the tile grid to the
  // world anchor; device-space engines: map straight to device pixels,
  // pinned to the anchor's on-screen position (no y-flip to mirror)
  const m = T / (t * view.s);
  pat.setTransform(patternsInDeviceSpace()
    ? new DOMMatrix([m * view.s * dpr, 0, 0, m * view.s * dpr,
                     (greenAnchor.x * view.s + view.tx) * dpr,
                     (view.ty - greenAnchor.y * view.s) * dpr])
    : new DOMMatrix([m, 0, 0, -m, greenAnchor.x, greenAnchor.y]));
  return pat;
}
const zoneTitles = {};   // zone symbol -> full title (e.g. SI -> Strefa ...)
let hoverPf = null;       // feature under the cursor (or pinned): outlined
let tooltipOn = true;      // on-hover details tooltip on/off (sidebar switch)
try {  // remembered across visits, like the panel width
  if (localStorage.getItem('hoverDetails') === '0') tooltipOn = false;
} catch (err) {}
const state = {};   // group name -> {on, alpha}
const view = {s: 1, tx: 0, ty: 0};
let dpr = 1;
// hatch configuration for overlay groups: app-level only (from mapdata),
// no UI. width/spacing in CSS px; fill = opacity of the solid color
// between the hatch lines (0 = transparent).
let HATCH = {width: 2.5, spacing: 16, fill: 0};
// hovered-zone outline style: app-level only (from mapdata), no UI.
// color, width/dash segments in CSS px; dash is an on/off pattern.
// built-in highlight fallback for deployments whose settings define no
// highlight section; the app's live values come from settings.json (the
// single config source) and merge over these
let HIGHLIGHT = {color: '#111', width: 3.5, dash: [16, 12]};

function esc(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}
// minimal markdown for the sidebar changelog: #-headings, lists, **bold**
function mdLite(src) {
  const out = [];
  let list = false;
  for (let line of String(src).split(/\r?\n/)) {
    line = esc(line);
    if (/^[-*] /.test(line)) {
      if (!list) { out.push('<ul>'); list = true; }
      out.push('<li>' + line.replace(/^[-*] /, '') + '</li>');
    } else {
      if (list) { out.push('</ul>'); list = false; }
      if (/^#{1,6} /.test(line))
        out.push('<div class="md-h">' + line.replace(/^#+ /, '') + '</div>');
      else if (line.trim())
        out.push('<p>' + line + '</p>');
    }
  }
  if (list) out.push('</ul>');
  return out.join('').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}
function darkenHex(h) {
  h = h.replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  const f = c => Math.round(parseInt(c, 16) * 0.6);
  return 'rgb(' + f(h.slice(0, 2)) + ',' + f(h.slice(2, 4)) + ',' + f(h.slice(4, 6)) + ')';
}
// --- pattern-transform semantics -------------------------------------
// Per spec, CanvasPattern.setTransform maps pattern pixels into user
// space, composed with the CTM at fill time. Some engines (WebKit)
// instead apply it directly in device space. The hatch and greens
// patterns depend on the exact placement, so detect the behavior once
// and adapt: spec engines get transforms that cancel the drawing CTM,
// device-space engines get plain device-space mappings.
let PATTERNS_DEVICE = null;
function patternsInDeviceSpace() {
  if (PATTERNS_DEVICE !== null) return PATTERNS_DEVICE;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 4;
  const c2 = cv.getContext('2d');
  const tile = document.createElement('canvas');
  tile.width = tile.height = 2;
  const t2 = tile.getContext('2d');
  t2.fillStyle = '#000';
  t2.fillRect(0, 0, 1, 1);
  c2.setTransform(2, 0, 0, 2, 0, 0);  // user space is half the device
  c2.fillStyle = c2.createPattern(tile, 'repeat');
  c2.fillRect(0, 0, 2, 2);
  // spec: the black user cell covers device pixels (0..2, 0..2);
  // device semantics: it stays a single device pixel
  PATTERNS_DEVICE = c2.getImageData(1, 1, 1, 1).data[3] === 0;
  return PATTERNS_DEVICE;
}
// 45-degree hatch patterns for group overlays: colored "/" lines on a
// transparent background. Line thickness and spacing (CSS px) come from
// the app configuration (HATCH); tile spacing is spacing*sqrt(2) so the
// line distance equals the configured value. Anchored to the screen via
// the inverse of the *drawing context's* current view transform, so line
// width and spacing stay constant while panning and zooming.
const hatchCache = {};
function hatchPattern(c, color, widthPx, spacingPx) {
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
    pat = c.createPattern(tile, 'repeat');
    hatchCache[key] = pat;
  }
  // cancel the drawing context's world transform under spec semantics;
  // device-space engines already place the pattern in device space
  pat.setTransform(patternsInDeviceSpace()
    ? new DOMMatrix()
    : c.getTransform().inverse());
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
let greensLoading = false;
async function fetchGreens() {
  // download the greens layer on first use: default off, so visitors who
  // never toggle it never pay for the extra ~1 MB (gzipped) download
  if (greensPaths || greensLoading) return;
  greensLoading = true;
  const cnt = document.querySelector('#grp-greens .cnt');
  if (cnt) cnt.textContent = '...';
  try {
    const res = await fetch(GREENS_URL);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const feats = Array.isArray(data) ? data : (data.greens || []);
    greenStats = Array.isArray(data) ? null : (data.stats || null);
    // one Path2D per (zone type, green class): few fill calls per frame,
    // and the zone-type toggles can still filter whole patches out
    greensPaths = {};
    greenCount = feats.length;
    for (const g of feats) {
      const key = g.sym + '|' + g.c;
      let e = greensPaths[key];
      if (!e) e = greensPaths[key] =
        {p: new Path2D(), b: [1e18, 1e18, -1e18, -1e18], sym: g.sym, c: g.c};
      for (const ring of g.parts[0]) {
        if (ring.length < 8) continue;
        e.p.moveTo(ring[0], ring[1]);
        for (let i = 2; i < ring.length; i += 2) e.p.lineTo(ring[i], ring[i + 1]);
        e.p.closePath();
        for (let i = 0; i < ring.length; i += 2) {
          if (ring[i] < e.b[0]) e.b[0] = ring[i];
          if (ring[i + 1] < e.b[1]) e.b[1] = ring[i + 1];
          if (ring[i] > e.b[2]) e.b[2] = ring[i];
          if (ring[i + 1] > e.b[3]) e.b[3] = ring[i + 1];
        }
      }
    }
    if (cnt) cnt.textContent = greenCount;
    draw();
    // a tooltip opened before the download finished shows no stats yet:
    // refresh it if it is still on screen
    if (info.style.display !== 'none' && hoverPf)
      showTooltip(hoverPf, lastHover.x, lastHover.y);
  } catch (err) {
    console.error('greens layer:', err);
    greensFailed = true;  // do not retry on every tooltip; the layer
                          // toggle can still trigger a fresh attempt
    // revert the toggle so the panel reflects what actually rendered
    const s = state['greens'];
    if (s) s.on = false;
    const el = document.querySelector('#grp-greens [data-toggle]');
    if (el) el.checked = false;
    const grp = document.getElementById('grp-greens');
    if (grp) { grp.classList.add('off');
               grp.title = L.loadError + GREENS_URL; }
    if (cnt) cnt.textContent = '!';
    saveState();
  } finally {
    greensLoading = false;
  }
}
function initGroups() {
  for (const g of DATA.groups) {
    groups[g.name] = g;
    const s = {on: g.on !== false, alpha: g.alpha || 0.62};
    if (g.zones) {  // per-zone-type on/off via the panel zone rows;
      s.zones = {};  // they start consistent with the layer's state
      for (const z of g.zones) {
        s.zones[z.sym] = g.on !== false;
        if (z.title) zoneTitles[z.sym] = z.title;
      }
    }
    state[g.name] = s;
  }
}
function simplifyRing(r, tol) {
  // Douglas-Peucker on a flat [x0, y0, x1, y1, ...] ring, kept closed;
  // returns the input unchanged when the result would degenerate
  const n = r.length / 2;
  if (n < 4) return r;
  const keep = new Uint8Array(n);
  keep[0] = keep[n - 1] = 1;
  const stack = [[0, n - 1]];
  while (stack.length) {
    const seg = stack.pop(), i0 = seg[0], i1 = seg[1];
    const x0 = r[2 * i0], y0 = r[2 * i0 + 1];
    const dx = r[2 * i1] - x0, dy = r[2 * i1 + 1] - y0;
    const len = Math.hypot(dx, dy) || 1e-12;
    let dmax = -1, imax = -1;
    for (let i = i0 + 1; i < i1; i++) {
      const d = Math.abs(dy * (r[2 * i] - x0) -
                         dx * (r[2 * i + 1] - y0)) / len;
      if (d > dmax) { dmax = d; imax = i; }
    }
    if (dmax > tol) {
      keep[imax] = 1;
      stack.push([i0, imax], [imax, i1]);
    }
  }
  const out = [];
  for (let i = 0; i < n; i++)
    if (keep[i]) { out.push(r[2 * i], r[2 * i + 1]); }
  if (out.length >= 6 && (out[0] !== out[out.length - 2] ||
                          out[1] !== out[out.length - 1]))
    out.push(out[0], out[1]);
  return out.length >= 6 ? out : r;
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
  if (f.t !== 'pt' && DATA.bounds) {
    // zoom-dependent LOD: two precomputed simplifications, used by the
    // renderer while their worst-case screen error stays under a pixel
    // (see lodPath); hover outlines and hit-testing keep the exact path
    const diag = Math.max(DATA.bounds[2], DATA.bounds[3]) || 1;
    entry.lods = [];
    for (const tol of [diag / 4000, diag / 500]) {
      const lp = new Path2D();
      let any = false;
      if (f.t === 'p') {
        for (const part of f.parts) {
          for (let ri = 0; ri < part.length; ri++) {
            const r = simplifyRing(part[ri], tol);
            if (r.length < 6) continue;
            lp.moveTo(r[0], r[1]);
            for (let i = 2; i < r.length; i += 2) lp.lineTo(r[i], r[i+1]);
            lp.closePath();
            any = true;
          }
        }
      } else {
        const r = simplifyRing(f.parts[0][0], tol);
        if (r.length >= 4) {
          lp.moveTo(r[0], r[1]);
          for (let i = 2; i < r.length; i += 2) lp.lineTo(r[i], r[i+1]);
          any = true;
        }
      }
      if (any) entry.lods.push({tol: tol, p: lp});
    }
  }
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
  fitScale = s;  // greens texture reference zoom (see greenPattern)
  view.tx = (w - s * (minx + maxx)) / 2;
  view.ty = (h + s * (miny + maxy)) / 2;
  offView = null;  // fit is a view jump: render the next frame crisp
}
function zoneTypeOff(sym) {
  // a zone type counts as off when a *visible* zone-toggle group (the
  // zone-type chips, e.g. under StrefaPlanistyczna) disables it. A hidden
  // zone layer does not filter the greens: turning that layer off bulk
  // deselects its chips, which must not blank the greens layer too
  if (!sym) return false;
  for (const name in state) {
    const s = state[name];
    if (s.zones && s.on && s.zones[sym] === false) return true;
  }
  return false;
}
function visibleRect() {
  // viewport culling: only draw features intersecting the visible world rect
  const vw = canvas.width / dpr, vh = canvas.height / dpr;
  const vx0 = -view.tx / view.s, vx1 = (vw - view.tx) / view.s;
  const vy0 = (view.ty - vh) / view.s, vy1 = view.ty / view.s;
  return b => b[2] >= vx0 && b[0] <= vx1 && b[3] >= vy0 && b[1] <= vy1;
}
function lodPath(pf) {
  // coarsest precomputed simplification (see makePath) whose worst-case
  // screen error stays under ~0.75 px; the exact path once zoomed in
  const lods = pf.lods;
  if (!lods) return pf.p;
  for (let i = lods.length - 1; i >= 0; i--)
    if (lods[i].tol * view.s <= 0.75) return lods[i].p;
  return pf.p;
}
// --- offscreen scene cache --------------------------------------------
// Zone fills, hatches, greens, borders and streets are expensive to
// rasterize but static between gestures: they render into an offscreen
// canvas at rest and every frame just blits it. A content change
// (toggle/alpha/data) re-renders at once; a view change mid-gesture
// blits the cached frame shifted/scaled and re-renders crisp once the
// view settles (~120 ms after the last change). A hover frame with the
// view at rest costs a 1:1 blit plus the dashed outline and labels.
let offCv = null;        // offscreen canvas holding the static scene
let offView = null;      // {s, tx, ty} the cache was rendered with
let offSig = null;       // scene fingerprint the cache was rendered with
let settleTimer = null;  // crisp re-render once a gesture pauses
function sceneSig() {
  return JSON.stringify(state) + (greensPaths ? '|g' : '');
}
function renderStatic(c, visible) {
  const ctx = c;  // the passes below draw into the offscreen canvas
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
      ctx.fill(lodPath(pf), 'evenodd');
      if (!pf.be) {  // zone borders are stroked in a separate top pass
        ctx.globalAlpha = Math.min(1, st.alpha + 0.2);
        ctx.strokeStyle = darkenHex(pf.bc);
        ctx.lineWidth = 1 / view.s;
        ctx.stroke(lodPath(pf));
      }
    } else if (pf.t === 'l') {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = pf.be || darkenHex(pf.bc);
      ctx.lineWidth = 1.4 / view.s;
      ctx.stroke(lodPath(pf));
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
        ctx.fill(lodPath(pf), 'evenodd');
      }
      ctx.globalAlpha = st.alpha;
      ctx.fillStyle = hatchPattern(ctx, gr.color, HATCH.width, HATCH.spacing);
      ctx.fill(lodPath(pf), 'evenodd');
      ctx.globalAlpha = st.alpha;
      ctx.strokeStyle = gr.edge;
      ctx.lineWidth = 1 / view.s;
      ctx.stroke(lodPath(pf));
    } else if (pf.t === 'l') {
      ctx.globalAlpha = st.alpha;
      ctx.strokeStyle = gr.edge;
      ctx.lineWidth = 1.4 / view.s;
      ctx.stroke(lodPath(pf));
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
  // greens overlap layer: the green x zone intersection patches, on top
  // of the overlays. Visibility follows the layer toggle plus the same
  // zone-type chips that control the plan zones (e.g. StrefaPlanistyczna)
  const stGr = state['greens'];
  if (stGr && stGr.on && greensPaths) {
    // OSM-style landcover texture: ground-anchored and growing with
    // zoom at rate greenRate, from the fit-zoom reference density
    // (never denser than that; see greenPattern)
    for (const k in greensPaths) {
      const gp = greensPaths[k];
      if (zoneTypeOff(gp.sym)) continue;
      if (!visible(gp.b)) continue;
      ctx.globalAlpha = stGr.alpha;
      ctx.fillStyle = greenPattern(gp.c);
      ctx.fill(gp.p, 'evenodd');
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
    ctx.lineWidth = 0.6 / view.s;
    ctx.stroke(lodPath(pf));
  }
  const stS = state['streets'];
  if (stS && stS.on && streetsPath) {
    ctx.globalAlpha = stS.alpha;
    ctx.strokeStyle = groups['streets'].edge;
    ctx.lineWidth = 1.1 / view.s;
    ctx.stroke(streetsPath);
  }
  ctx.globalAlpha = 1;
}
function renderScene() {
  // full re-render of the static scene into the cache, at the view now
  // pin the greens tile grid: kept across pans (a pan re-render must
  // not shift the texture phase), but re-pinned to the screen center
  // whenever the zoom changes - with a growth rate below 1 the tile's
  // ground size changes per zoom step, and pinning that rescale to the
  // middle of the view keeps the drift near zero where the user looks
  // instead of sliding relative to the distant map origin
  if (greenAnchorS !== view.s) {
    greenAnchorS = view.s;
    greenAnchor = {
      x: (canvas.clientWidth / 2 - view.tx) / view.s,
      y: (view.ty - canvas.clientHeight / 2) / view.s};
  }
  const c = offCv.getContext('2d');
  c.setTransform(1, 0, 0, 1, 0, 0);
  c.clearRect(0, 0, offCv.width, offCv.height);
  c.setTransform(view.s * dpr, 0, 0, -view.s * dpr, view.tx * dpr, view.ty * dpr);
  renderStatic(c, visibleRect());
  offView = {s: view.s, tx: view.tx, ty: view.ty};
  offSig = sceneSig();
}
function draw() {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!offCv || offCv.width !== canvas.width ||
      offCv.height !== canvas.height) {
    offCv = document.createElement('canvas');
    offCv.width = canvas.width;
    offCv.height = canvas.height;
    offView = null;  // fresh cache: force a crisp render below
  }
  if (offView === null || offSig !== sceneSig()) {
    renderScene();  // content or canvas size changed: render crisp now
  } else if (view.s !== offView.s || view.tx !== offView.tx ||
             view.ty !== offView.ty) {
    // mid-gesture: the blit below keeps the frame cheap, but it scales
    // the whole cached frame, while the hatch and greens render at their
    // own scale (screen-space / gentle growth) - so a far-drifted blit
    // visibly diverges from a crisp render and then snaps back. Re-render
    // as soon as the zoom drifts past ~25%, else once the gesture pauses
    const k = view.s / offView.s;
    if (k > 1.25 || k < 0.8) {
      renderScene();
    } else {
      clearTimeout(settleTimer);
      settleTimer = setTimeout(() => {
        settleTimer = null;
        renderScene();
        draw();
      }, 60);
    }
  }
  // blit the cached scene under the current view (device pixel space);
  // k/ax/ay map the cached frame's pixels onto the current transform
  // (note the minus on ay: the world transform flips y)
  const k = view.s / offView.s;
  const ax = view.tx - k * offView.tx;
  const ay = view.ty - k * offView.ty;
  ctx.drawImage(offCv, ax * dpr, ay * dpr, offCv.width * k, offCv.height * k);
  // dynamic on top of the cached scene: the dashed hover/pinned outline
  // and street labels, which track the view on every frame
  const visible = visibleRect();
  ctx.setTransform(view.s * dpr, 0, 0, -view.s * dpr, view.tx * dpr, view.ty * dpr);
  ctx.lineJoin = 'round';
  if (hoverPf && visible(hoverPf.b)) {
    ctx.globalAlpha = 1;
    ctx.strokeStyle = HIGHLIGHT.color;
    ctx.lineWidth = HIGHLIGHT.width / view.s;
    // screen-space dash (configured on/off px) regardless of zoom
    ctx.setLineDash(HIGHLIGHT.dash.map(v => v / view.s));
    ctx.stroke(hoverPf.p);
    ctx.setLineDash([]);
  }
  const stS = state['streets'];
  ctx.globalAlpha = (stS && stS.on) ? stS.alpha : 1;
  if (stS && stS.on) drawStreetLabels(visible);
  ctx.globalAlpha = 1;
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
function hitTest(mx, my) {
  const wx = (mx - view.tx) / view.s;
  const wy = (view.ty - my) / view.s;
  ctx.setTransform(view.s * dpr, 0, 0, -view.s * dpr, view.tx * dpr, view.ty * dpr);
  for (let i = paths.length - 1; i >= 0; i--) {
    const pf = paths[i];
    const st = state[pf.bg];
    if (!st || !st.on || pf.t !== 'p') continue;
    if (st.zones && pf.sym && st.zones[pf.sym] === false) continue;
    if (wx < pf.b[0] || wy < pf.b[1] || wx > pf.b[2] || wy > pf.b[3]) continue;
    // isPointInPath tests the point AS GIVEN (canvas pixel space,
    // unaffected by the CTM) against the CTM-transformed path, so pass
    // the mouse position in device pixels, not world coordinates
    if (ctx.isPointInPath(pf.p, mx * dpr, my * dpr)) return pf;
  }
  return null;
}
function tooltipHtml(pf) {
  const g = pf.g ? groups[pf.g] : null;
  const zt = pf.sym ? zoneTitles[pf.sym] : null;
  let html = '<b>' + esc(pf.ozn || pf.layer) + '</b>';
  if (zt) html += '<br>' + esc(zt);
  html += '<br>' + L.layer + ': ' + esc(pf.layer);
  if (pf.g) html += '<br>' + L.group + ': ' + esc(pf.g);
  if (pf.sym && !zt) html += '<br>' + L.symbol + ': ' + esc(pf.sym);
  if (g) {
    const t = g.desc_title || g.desc;
    if (t) {
      const short = t.length > 140 ? t.slice(0, 140) + '...' : t;
      html += '<span class="desc">' + esc(short) + '</span>';
    }
  }
  // green overlap stats for the hovered zone (needs the greens download)
  if (greenStats && pf.ozn && greenStats[pf.ozn]) {
    const s = greenStats[pf.ozn];
    html += '<span class="desc"><b>' + esc(L.greens) + ':</b> ' +
      s.pct + '% (' + s.green + ' ha / ' + s.ha + ' ha)';
    const parts = [];
    for (const c in (s.by || {}))
      parts.push(esc(L['gc.' + c] || c) + ' ' + s.by[c] + '%');
    if (parts.length) html += '<br>' + parts.join(' &middot; ');
    html += '</span>';
  }
  return html;
}
function showTooltip(pf, mx, my) {
  // asking for a zone's green overlap (the tooltip) downloads the greens
  // data too - the same single file the layer toggle fetches
  if (pf.ozn && !greenStats && !greensLoading && !greensFailed)
    fetchGreens();
  info.innerHTML = tooltipHtml(pf);
  info.style.display = 'block';
  info.style.left = Math.max(0, Math.min(mx + 14, window.innerWidth - 290)) + 'px';
  info.style.top = (my + 14) + 'px';
}
// click/tap-to-pin: highlight and tooltip at once, no hover delay
function identify(mx, my) {
  const pf = hitTest(mx, my);
  if (pf) {
    showTooltip(pf, mx, my);
    if (hoverPf !== pf) {
      hoverPf = pf;
      draw();
    }
    return true;
  }
  info.style.display = 'none';
  if (hoverPf) { hoverPf = null; draw(); }
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
  if (g.name === 'greens') counts[g.name] = greenCount;
  const range = (attr, label, min, max, step, val) =>
    '<input type="range" min="' + min + '" max="' + max + '" step="' + step +
    '" value="' + val + '" data-' + attr + '="' + esc(g.name) +
    '" data-label="' + esc(label) + '">' +
    '<div class="hint">' + label + ' ' + val + '</div>';
  let html = '<div class="group' + (on ? '' : ' off') + '" id="grp-' + esc(g.name) + '" title="' + esc(g.name) + '">' +
    '<div class="head">' +
    '<input type="checkbox"' + (on ? ' checked' : '') + ' data-toggle="' + esc(g.name) + '">' +
    '<span class="swatch" style="background:' + swatchBackground(g) + '"></span>' +
    '<label>' + esc(g.kind === 'streets' ? L.secStreets :
      (g.i18n ? (L[g.i18n] || g.label || g.name) : (g.label || g.name))) +
    ' <span class="cnt">' + (counts[g.name] || 0) + '</span></label></div>' +
    (g.desc_title ? '<div class="gtitle">' + esc(g.desc_title) + '</div>' : '') +
    // data attribution: always visible, unlike desc (Details block)
    (g.attrib ? '<div class="attrib">' + esc(g.attrib) + '</div>' : '') +
    // zone-type toggles: full names in a two-column grid, color-coded
    (g.zones && g.zones.length ? '<div class="zgrid">' +
      g.zones.map(z => '<span class="zrow' +
        (st.zones[z.sym] === false ? ' off' : '') +
        '" data-zone="' + esc(z.sym) + '" data-group="' + esc(g.name) +
        '"><i class="zsw" style="background:' + z.color + '"></i>' +
        esc(z.title) + '</span>').join('') + '</div>' : '') +
    range('alpha', L.opacity, '0.05', '1', '0.01', st.alpha) +
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
    html += esc(sec[0]) + '</h4>';
    if (sec[2] === 'layer') {  // hover-details switch under the layers head
      html += '<label class="hoveropt"><input type="checkbox"' +
        (tooltipOn ? ' checked' : '') + ' data-hoveropt> ' +
        esc(L.hoverDetails) + '</label>';
    }
    html += '<div class="secbody" data-sec="' + sec[2] + '">';
    for (const g of sec[1]) html += groupBlock(g, counts);
    html += '</div>';
  }
  document.getElementById('groups').innerHTML = html;
  document.querySelectorAll('[data-toggle]').forEach(el => {
    el.addEventListener('change', () => {
      const s = state[el.dataset.toggle];
      s.on = el.checked;
      // the greens layer ships in a separate file, fetched on first enable
      if (el.dataset.toggle === 'greens' && el.checked) fetchGreens();
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
  // on-hover details switch (under the "GML layers" section header):
  // it gates only the tooltip - the zone outline keeps working
  const hopt = document.querySelector('[data-hoveropt]');
  if (hopt) hopt.addEventListener('change', () => {
    tooltipOn = hopt.checked;
    try { localStorage.setItem('hoverDetails', tooltipOn ? '1' : '0'); } catch (err) {}
    if (!tooltipOn) {  // hide the live tooltip; a pinned one stays until unpinned
      clearTimeout(tooltipTimer);
      if (!pinned) info.style.display = 'none';
    }
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
  if (DATA.highlight) HIGHLIGHT = Object.assign(HIGHLIGHT, DATA.highlight);
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
  // changelog: collapsed by default; deliberately not part of the
  // shareable URL state (unlike toggles/zones/opacity)
  document.getElementById('changelogsum').textContent = L.changelog;
  if (DATA.changelog) {
    document.getElementById('pchangelog').style.display = 'block';
    document.getElementById('changelogtext').innerHTML =
      mdLite(DATA.changelog);
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
  // a shared view may restore the greens layer as enabled: honor it by
  // downloading the data right away (normally it loads on first toggle)
  if (state['greens'] && state['greens'].on) fetchGreens();
  // the parsed payload is not needed past this point: free it for GC
  DATA.features = null;
  DATA.streets = null;
  buildPanel();
  resize(); fit(); draw();
}

// --- pointer input: mouse drag/hover/click plus touch pan, pinch zoom
// and tap-to-pin. Pointer events fire for mouse and touch alike.
let drag = null, pinned = false;
let lastHover = {x: 0, y: 0};
// hover: the zone outline reacts instantly (RAF-throttled); the details
// tooltip is delayed: it shows only once the pointer rests for
// TOOLTIP_DELAY ms, so quick pass-overs and panning do not trigger it
const TOOLTIP_DELAY = 200;
let hoverRaf = null;         // pending highlight update (requestAnimationFrame)
let tooltipTimer = null;     // pending tooltip timeout
function hoverUpdate() {
  const pf = hitTest(lastHover.x, lastHover.y);
  if (hoverPf !== pf) {  // instant outline, no delay
    hoverPf = pf;
    if (!pinned) info.style.display = 'none';  // stale tooltip outlives its zone
    draw();
  }
  scheduleTooltip();
}
function scheduleTooltip() {
  clearTimeout(tooltipTimer);
  tooltipTimer = setTimeout(() => {
    tooltipTimer = null;
    if (tooltipOn && !pinned && hoverPf)
      showTooltip(hoverPf, lastHover.x, lastHover.y);
  }, TOOLTIP_DELAY);
}
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
    clearTimeout(tooltipTimer);  // a drag/click cancels the pending tooltip
    if (hoverRaf) { cancelAnimationFrame(hoverRaf); hoverRaf = null; }
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
  if (e.pointerType === 'mouse' && !pinned) {  // hover: outline + tooltip
    lastHover = canvasPos(e);
    if (!hoverRaf) {  // instant highlight, throttled to one per frame
      hoverRaf = requestAnimationFrame(() => {
        hoverRaf = null;
        hoverUpdate();
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
        if (hoverPf) { hoverPf = null; draw(); }
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
  clearTimeout(tooltipTimer);  // leaving the canvas cancels the tooltip
  if (hoverRaf) { cancelAnimationFrame(hoverRaf); hoverRaf = null; }
  if (!pinned) {
    info.style.display = 'none';
    if (hoverPf) { hoverPf = null; draw(); }
  }
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
window.addEventListener('keydown', e => { if (e.key === 'Escape') { pinned = false; info.style.display = 'none'; if (hoverPf) { hoverPf = null; draw(); } } });
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
