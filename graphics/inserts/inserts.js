// Archive inserts: shared camera, light, paper and ink. Every frame is a pure function of t (deterministic).
const PLATES = "../../00_Brand/archive/";
const clamp = (x) => Math.max(0, Math.min(1, x));
const seg = (t, a, b) => clamp((t - a) / (b - a));
const eOut = (x) => 1 - Math.pow(1 - x, 3);
const eInOut = (x) => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const $ = (id) => document.getElementById(id);
const FPS = 30;
const D = window.D || {};
const DUR = D.seconds || 5;
const V = innerHeight > innerWidth;               // vertical (9:16) render
const U = Math.min(innerWidth, innerHeight) / 1000;

function rng(seed) {                               // mulberry32
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function el(tag, cls, parent, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  (parent || document.body).appendChild(e);
  return e;
}

// ---------- ink / paper filters (also used by overlays, which have no Scene) ----------
function installFilters() {
  document.body.insertAdjacentHTML("afterbegin", `
      <svg width="0" height="0" style="position:absolute">
        <filter id="rough"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4"/>
          <feDisplacementMap in="SourceGraphic" scale="${3 * U}"/></filter>
        <filter id="stampink"><feTurbulence type="fractalNoise" baseFrequency="0.55" numOctaves="3" seed="9" result="n"/>
          <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.2 1.35" result="m"/>
          <feComposite in="SourceGraphic" in2="m" operator="in"/></filter>
        <filter id="oldink" x="-4%" y="-4%" width="108%" height="108%" color-interpolation-filters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="3" result="fine"/>
          <feTurbulence type="fractalNoise" baseFrequency="0.011" numOctaves="2" seed="8" result="coarse"/>
          <feDisplacementMap in="SourceGraphic" in2="fine" scale="${2.4 * Math.max(1, U)}" xChannelSelector="R" yChannelSelector="G" result="rough"/>
          <feGaussianBlur in="rough" stdDeviation="${0.55 * Math.max(1, U)}" result="bleed"/>
          <feColorMatrix in="fine" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  2.6 0 0 0 -0.55" result="speck"/>
          <feComposite in="bleed" in2="speck" operator="in" result="specked"/>
          <feColorMatrix in="coarse" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  1.4 0 0 0 0.12" result="wear"/>
          <feComposite in="specked" in2="wear" operator="in"/></filter>
      </svg>`);
}

// ---------- scene: plate + lamp + vignette + grain + dust ----------
const Scene = {
  build(plate, opts = {}) {
    installFilters();
    this.cam = el("div", "", document.body); this.cam.id = "cam";
    const p = el("div", "plate", this.cam);
    p.style.backgroundImage = `url('${plate.includes(":") ? plate : PLATES + plate}')`;
    this.plate = p;
    this.posX = opts.posX ?? 0.5;
    p.style.backgroundPosition = `${this.posX * 100}% 50%`;
    this.stage = el("div", "", this.cam); this.stage.style.cssText = "position:absolute;inset:0";
    el("div", "lamp", this.cam);
    el("div", "vignette", document.body);
    this.dust = [];
    const r = rng(11);
    for (let i = 0; i < 26; i++) {
      const d = el("div", "dust", document.body);
      const s = (1.5 + r() * 3.5) * U;
      d.style.width = d.style.height = s + "px";
      this.dust.push({ d, x: r() * innerWidth, y: r() * innerHeight, vx: (r() - .5) * 8, vy: -4 - r() * 10, a: .2 + r() * .5 });
    }
    this.grain = el("canvas", "grain", document.body);
    this.grain.width = Math.round(innerWidth / 3); this.grain.height = Math.round(innerHeight / 3);
    this.push = opts.push ?? 0.06; this.panX = opts.panX ?? 0; this.panY = opts.panY ?? 0;
  },
  frame(t) {
    // camera: slow push-in with a hint of drift; rack focus in at the start
    const k = eInOut(seg(t, 0, DUR));
    const s = 1.02 + this.push * k;
    const x = this.panX * k * innerWidth, y = this.panY * k * innerHeight;
    const blur = 7 * (1 - eOut(seg(t, 0, .45))) * U;
    this.cam.style.transform = `translate(${x}px,${y}px) scale(${s})`;
    this.cam.style.filter = blur > .05 ? `blur(${blur}px)` : "none";
    for (const p of this.dust) {
      const xx = (p.x + p.vx * t * U * 3 + innerWidth) % innerWidth;
      const yy = (p.y + p.vy * t * U * 3 + innerHeight * 4) % innerHeight;
      p.d.style.transform = `translate(${xx}px,${yy}px)`;
      p.d.style.opacity = p.a * (0.6 + 0.4 * Math.sin(t * 2 + p.x));
    }
    const g = this.grain.getContext("2d"), w = this.grain.width, h = this.grain.height;
    const img = g.createImageData(w, h), r = rng(1 + Math.round(t * FPS));
    for (let i = 0; i < img.data.length; i += 4) {
      const v = 110 + r() * 100; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  },
};

// ---------- printing on a real surface in a plate ----------
function homography(src, dst) {               // 3x3 projective map src -> dst, as a CSS matrix3d
  const A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  for (let c = 0; c < 8; c++) {
    let p = c; for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]]; [b[c], b[p]] = [b[p], b[c]];
    for (let r = 0; r < 8; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k]; b[r] -= f * b[c]; }
  }
  const h = b.map((v, i) => v / A[i][i]);
  return [h[0], h[3], 0, h[6], h[1], h[4], 0, h[7], 0, 0, 1, 0, h[2], h[5], 0, 1];
}
// plate pixel (in the 1376 x 768 plate) -> screen pixel, for the .plate layer (cover, inset -4%)
function plateToScreen(px, py, posX = 0.5) {
  const bw = innerWidth * 1.08, bh = innerHeight * 1.08, sc = Math.max(bw / 1376, bh / 768);
  return [-innerWidth * .04 + (bw - 1376 * sc) * posX + px * sc, -innerHeight * .04 + (bh - 768 * sc) / 2 + py * sc];
}
// a polyline through plate points, sampled at t in 0..1 by arc length
function along(pts, t) {
  const L = [0]; for (let i = 1; i < pts.length; i++) L.push(L[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const d = t * L[L.length - 1]; let i = 1; while (i < pts.length - 1 && L[i] < d) i++;
  const k = (d - L[i - 1]) / ((L[i] - L[i - 1]) || 1);
  return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * k, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * k];
}
// Print `content` (an element sized CW x CH) onto a surface P(u,v) -> screen [x,y], u,v in 0..1.
// The surface is cut into a mesh of tiles, each with its own perspective map, so text follows curves.
function printOnSurface(parent, content, CW, CH, P, nu = 10, nv = 8) {
  const holder = el("div", "", parent);
  holder.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;mix-blend-mode:multiply";
  const tiles = [];
  for (let i = 0; i < nu; i++) for (let j = 0; j < nv; j++) {
    const x0 = CW * i / nu, x1 = CW * (i + 1) / nu, y0 = CH * j / nv, y1 = CH * (j + 1) / nv;
    const c = content.cloneNode(true);
    c.style.position = "absolute"; c.style.left = "0"; c.style.top = "0";
    c.style.width = CW + "px"; c.style.height = CH + "px"; c.style.transformOrigin = "0 0";
    const e = 1.6;  // overlap a little so no seams show
    c.style.clipPath = `polygon(${x0 - e}px ${y0 - e}px,${x1 + e}px ${y0 - e}px,${x1 + e}px ${y1 + e}px,${x0 - e}px ${y1 + e}px)`;
    const q = [P(i / nu, j / nv), P((i + 1) / nu, j / nv), P((i + 1) / nu, (j + 1) / nv), P(i / nu, (j + 1) / nv)];
    c.style.transform = `matrix3d(${homography([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], q).join(",")})`;
    holder.appendChild(c); tiles.push(c);
  }
  content.remove();
  return { holder, tiles };
}

// ---------- paper ----------
function deckle(sheet, seed, rough = 0.6) {
  // a torn / deckled outline: jittered points along each edge
  const r = rng(seed), pts = [], n = 34, j = rough;
  for (let i = 0; i <= n; i++) pts.push([i / n * 100, r() * j]);
  for (let i = 0; i <= n; i++) pts.push([100 - r() * j, i / n * 100]);
  for (let i = n; i >= 0; i--) pts.push([i / n * 100, 100 - r() * j]);
  for (let i = n; i >= 0; i--) pts.push([r() * j, i / n * 100]);
  sheet.style.clipPath = "polygon(" + pts.map(([x, y]) => `${x.toFixed(2)}% ${y.toFixed(2)}%`).join(",") + ")";
}

function makeSheet(parent, { w, h, x, y, rot = -2, paper = "newsprint_blank.jpeg", seed = 3, rough = 0.6, tint = 0 }) {
  const holder = el("div", "sheet-holder", parent);
  holder.style.cssText += `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
  const sheet = el("div", "sheet", holder);
  sheet.style.cssText += `width:100%;height:100%;background-image:url(${PLATES}${paper})`;
  if (tint) sheet.style.filter = `sepia(${tint})`;
  deckle(sheet, seed, rough);
  return { holder, sheet, rot, x, y };
}

// a sheet placed by hand: slides in, settles, shadow tightens as it lands
function placeSheet(s, t, t0, { from = [-0.35, 0.25], dur = .75, startRot = -9 } = {}) {
  const p = eOut(seg(t, t0, t0 + dur));
  const settle = Math.sin(seg(t, t0 + dur * .8, t0 + dur * 1.35) * Math.PI) * 0.6;
  const dx = (1 - p) * from[0] * innerWidth, dy = (1 - p) * from[1] * innerHeight;
  const rot = s.rot + (1 - p) * (startRot - s.rot) + settle * 0.4;
  const lift = 1 + (1 - p) * 0.06;
  s.holder.style.transform = `translate(${dx}px,${dy}px) rotate(${rot}deg) scale(${lift})`;
  const blur = (6 + 26 * (1 - p)) * U, off = (5 + 30 * (1 - p)) * U;
  s.holder.style.filter = `drop-shadow(${off * .4}px ${off}px ${blur}px rgba(0,0,0,${.55 - .15 * (1 - p)}))`;
  s.holder.style.opacity = t < t0 ? 0 : 1;
}

// highlighter stroke grows right-to-left (Arabic reading direction) or left-to-right
function stroke(e, t, t0, dur = .5, rtl = true) {
  const p = eOut(seg(t, t0, t0 + dur));
  e.style.transformOrigin = rtl ? "100% 50%" : "0% 50%";
  e.style.transform = `scaleX(${p})`;
  e.style.opacity = p > 0 ? 1 : 0;
}

// pen/pencil SVG path drawn over time
function drawPath(path, t, t0, dur = .8) {
  const L = path.getTotalLength();
  path.style.strokeDasharray = L;
  path.style.strokeDashoffset = L * (1 - eInOut(seg(t, t0, t0 + dur)));
  path.style.opacity = t >= t0 ? 1 : 0;
}

// rubber stamp: thump down with a little overshoot
function thump(e, t, t0, rot = -8) {
  const p = seg(t, t0, t0 + .18);
  const s = t < t0 ? 1.6 : 1 + 0.6 * Math.pow(1 - p, 2);
  e.style.opacity = t < t0 ? 0 : (0.25 + 0.7 * p);
  e.style.transform = `rotate(${rot}deg) scale(${s})`;
}

// type appears as if set word by word (for Arabic, whole words: letters must stay joined)
function setWords(e, t, t0, perWord = .09) {
  if (!e._words) {
    const words = e.textContent.trim().split(/\s+/);
    e.innerHTML = words.map((w) => `<span>${w}</span>`).join(" ");
    e._words = [...e.querySelectorAll("span")];
  }
  e._words.forEach((w, i) => { w.style.opacity = clamp((t - t0 - i * perWord) / .12); });
}

function bindRender(fn) {
  window.render = (t) => { Scene.frame(t); fn(t); };
}
