// Explainer diagrams, drawn by a pen over the dimmed archive clip. Each returns timed steps in viewBox units.
// Our own drawings of well-known concepts; the idea's author is credited on the frame (D.credit).
// Labels are Egyptian business Ammia; English terms stay as business people say them.
// Timing: every step that illustrates a spoken word reads its time with T(D, key, default); the pipeline fills
// D.beats from the transcript so nothing appears before the presenter says it. Defaults are for previews only.

function T(D, k, d) { return D.beats && D.beats[k] != null ? +D.beats[k] : d; }
function credit(W, H, D, t) {
  return D.credit ? [{ k: "text", x: W - 40, y: H - 30, s: D.credit, size: 22, font: "Typewriter", bold: false, anchor: "end", dim: true, t }] : [];
}
function needCredit(D, what) { if (!D.credit) throw new Error(`${what}: shows a figure, needs data.credit (its source)`); }
function heading(W, V, D, ar, en, t, y) {
  return [{ k: "text", x: W / 2, y: y ?? (V ? 200 : 100), s: D.title || ar, size: V ? 56 : 52, t },
          { k: "text", x: W / 2, y: (y ?? (V ? 200 : 100)) + (V ? 50 : 46), s: en, size: 26, font: "Typewriter", bold: false, dim: true, t: t + .15 }];
}

const DIAGRAMS = {
  // The napkin: a triangle between three cities (rows: «رسم مثلث», then each city as it is named)
  napkin(W, H, V, D) {
    const S = [], c = V ? [W / 2, 760] : [W / 2, 500], r = V ? 300 : 300;
    const tri = [[c[0], c[1] - r * .9], [c[0] + r * 1.05, c[1] + r * .62], [c[0] - r * 1.05, c[1] + r * .62]];
    const names = D.cities || ["دالاس", "هيوستن", "سان أنطونيو"], keys = ["city0", "city1", "city2"];
    const tt = T(D, "triangle", .4);
    tri.forEach((p, i) => { const q = tri[(i + 1) % 3]; S.push({ k: "line", p: [...p, ...q], t: tt + i * .3, dur: .35, w: 5 }); });
    tri.forEach((p, i) => {
      const t = Math.max(T(D, keys[i], tt + 1.2 + i * .5), tt + .9);
      S.push({ k: "dot", c: p, r: 14, red: true, t });
      S.push({ k: "text", x: p[0] + (i === 1 ? 30 : i === 2 ? -30 : 0), y: p[1] + (i === 0 ? -40 : 72), s: names[i], size: V ? 46 : 46,
               anchor: i === 1 ? "start" : i === 2 ? "end" : "middle", t });
    });
    if (D.caption) S.push({ k: "text", x: c[0], y: V ? 1260 : H - 70, s: D.caption, size: 34, bold: false, font: "AmiriR", dim: true, t: T(D, "caption", tt + 3) });
    return S.concat(credit(W, H, D, tt + .5));
  },

  // Not other airlines: «شركات الطيران» struck, then the real rivals written under it
  rivals(W, H, V, D) {
    const S = [], y1 = V ? 620 : 380, y2 = V ? 900 : 600;
    S.push({ k: "text", x: W / 2, y: V ? 330 : 170, s: D.title || "هننافس مين؟", size: V ? 52 : 48, dim: true, t: .2 });
    S.push({ k: "text", id: "air", x: W / 2, y: y1, s: D.not || "شركات الطيران", size: V ? 76 : 80, t: T(D, "airlines", .5) });
    S.push({ k: "strike", of: "air", t: T(D, "no", 1.3), dur: .4 });
    S.push({ k: "text", x: W / 2, y: y2, s: D.yes || "الأتوبيس والعربية", size: V ? 76 : 80, red: true, t: T(D, "rivals", 2.0) });
    S.push({ k: "line", p: [W / 2 - 170, y2 + 40, W / 2 + 170, y2 + 40], t: T(D, "rivals", 2.0) + .3, dur: .4, red: true, w: 5 });
    return S.concat(credit(W, H, D, 1));
  },

  // Trade-offs: each «لأ» lands only when it is said (beats q0..q3 for the item, no0..no3 for its «لأ»)
  trade_offs(W, H, V, D) {
    const S = [];
    const rows = D.rows || [["وجبات؟", "تسالي بس"], ["كراسي محجوزة؟", "اللي ييجي الأول يقعد الأول"],
                            ["مطارات كبيرة؟", "مطارات جانبية"], ["درجة أولى؟", "كله درجة واحدة"]];
    S.push(...heading(W, V, D, "ساوث ويست قالت «لأ»", "Trade-offs", .1));
    const top = V ? 420 : 270, gap = V ? 250 : 155, xr = V ? W - 120 : W * 0.68, xn = V ? 150 : W * 0.40;
    rows.forEach(([q, a], i) => {
      const y = top + i * gap, tq = T(D, `q${i}`, .6 + i * 1.2), tn = Math.max(T(D, `no${i}`, tq + .6), tq + .15);
      S.push({ k: "text", id: `q${i}`, x: xr, y, s: q, size: V ? 48 : 46, anchor: "end", t: tq });
      S.push({ k: "strike", of: `q${i}`, t: tn, dur: .3 });
      S.push({ k: "text", x: xn, y, s: "لأ", size: 62, red: true, t: tn + .05 });
      if (a) S.push({ k: "text", x: V ? xr : xn - 70, y: V ? y + 74 : y, s: a, size: 34, bold: false, font: "AmiriR", dim: true,
                      anchor: "end", t: T(D, `a${i}`, tn + .4) });
    });
    return S.concat(credit(W, H, D, .5));
  },

  // The 10-minute turn: a clock face, each step on its words, then the stamp
  clock10(W, H, V, D) {
    needCredit(D, "clock10");
    const S = [], c = V ? [W / 2, 620] : [W * .5, 500], R = V ? 230 : 250;
    const steps = D.steps || ["الركاب ينزلوا", "الشنط", "التنضيف", "ركاب جداد", "إقلاع"];
    S.push(...heading(W, V, D, "الطيارة على الأرض", "10-minute turn", .1, V ? 220 : 70));
    const t0 = T(D, "clock", .4);
    S.push({ k: "circle", c, r: R, t: t0, dur: .6, w: 5 });
    for (let i = 0; i < 12; i++) {           // hour ticks
      const a = i / 12 * 6.283;
      S.push({ k: "line", p: [c[0] + Math.sin(a) * R * .88, c[1] - Math.cos(a) * R * .88, c[0] + Math.sin(a) * R * .96, c[1] - Math.cos(a) * R * .96], t: t0 + .4, dur: .2, w: 3, amp: 0 });
    }
    // the 10 minutes: a red wedge from 12 to 2, drawn as each step is said
    steps.forEach((s, i) => {
      const t = T(D, `s${i}`, t0 + .9 + i * .7);
      // the list of steps: right of the clock (16:9) or under it (9:16)
      const tx = V ? W / 2 + 200 : c[0] - R - 90, ty = V ? c[1] + R + 110 + i * 62 : c[1] - R + 60 + i * 92;
      S.push({ k: "text", x: tx, y: ty, s: `${"١٢٣٤٥٦٧٨"[i]}. ${s}`, size: V ? 34 : 38, anchor: "end", t });
      // the 10 minutes fill in on the dial, one slice per step
      const a1 = i / steps.length * (Math.PI / 3), a2 = (i + 1) / steps.length * (Math.PI / 3), rr = R * .72;
      S.push({ k: "path", path: `M${c[0] + Math.sin(a1) * rr} ${c[1] - Math.cos(a1) * rr} A${rr} ${rr} 0 0 1 ${c[0] + Math.sin(a2) * rr} ${c[1] - Math.cos(a2) * rr}`,
               t, dur: .4, red: true, w: 18 });
    });
    const ts = T(D, "ten", t0 + .9 + steps.length * .7);
    S.push({ k: "line", p: [c[0], c[1], c[0], c[1] - R * .72], t: t0 + .3, dur: .3, w: 5, amp: 0 });
    S.push({ k: "line", p: [c[0], c[1], c[0] + Math.sin(Math.PI / 3) * R * .6, c[1] - Math.cos(Math.PI / 3) * R * .6], t: ts - .3, dur: .3, red: true, w: 6, amp: 0 });
    S.push({ k: "text", x: V ? c[0] : c[0] + R + 70, y: V ? c[1] - R - 60 : c[1] - 10, s: D.stamp || "١٠ دقايق", size: V ? 70 : 76, red: true, anchor: V ? "middle" : "start", t: ts });
    if (D.others !== false) S.push({ k: "text", x: V ? c[0] : c[0] + R + 70, y: V ? c[1] + R + 450 : c[1] + 70, s: D.others || "الباقيين: ساعة على الأقل", size: 34, bold: false, font: "AmiriR", dim: true,
                                     anchor: V ? "middle" : "start", t: T(D, "others", ts + 1) });
    return S.concat(credit(W, H, D, t0 + .5));
  },

  // One plane type: a 737 outline, then the same plane again and again
  fleet737(W, H, V, D) {
    const S = [];
    const plane = (x, y, s) =>   // side view, nose to the left
      `M${x - 150 * s} ${y} Q${x - 165 * s} ${y - 14 * s} ${x - 130 * s} ${y - 20 * s} L${x + 120 * s} ${y - 22 * s} L${x + 160 * s} ${y - 70 * s} L${x + 180 * s} ${y - 70 * s} ` +
      `L${x + 170 * s} ${y - 18 * s} L${x + 175 * s} ${y + 2 * s} L${x - 140 * s} ${y + 10 * s} Q${x - 160 * s} ${y + 6 * s} ${x - 150 * s} ${y} ` +
      `M${x - 20 * s} ${y + 2 * s} L${x + 40 * s} ${y + 40 * s} L${x + 62 * s} ${y + 40 * s} L${x + 40 * s} ${y + 4 * s}`;
    const t0 = T(D, "plane", .3), cy = V ? 600 : 380;
    S.push({ k: "path", path: plane(W / 2, cy, V ? 2.0 : 2.2), t: t0, dur: 1.0, w: 5 });
    S.push({ k: "text", x: W / 2, y: cy + (V ? 170 : 170), s: D.label || "Boeing 737", size: V ? 54 : 56, font: "Typewriter", bold: false, t: t0 + .6 });
    const n = V ? 6 : 8, tc = T(D, "copies", t0 + 1.6), y2 = V ? 1060 : 700;
    for (let i = 0; i < n; i++) {
      const col = V ? i % 3 : i, row = V ? Math.floor(i / 3) : 0;
      const x = V ? W * (.2 + col * .3) : W * (.08 + col * .12);
      S.push({ k: "path", path: plane(x, y2 + row * 170, V ? .55 : .45), t: tc + i * .12, dur: .35, w: 3, red: i === 0 });
    }
    if (D.caption) S.push({ k: "text", x: W / 2, y: V ? 1420 : H - 60, s: D.caption, size: 34, bold: false, font: "AmiriR", dim: true, t: tc + n * .12 + .2 });
    return S.concat(credit(W, H, D, t0 + .5));
  },

  // Hub-and-Spoke vs Point-to-Point (beats: hub, transit, p2p, storm)
  hub_vs_p2p(W, H, V, D) {
    const S = [];
    const panel = (cx, cy, r, title, en, t) => [
      { k: "text", x: cx, y: cy - r - 130, s: title, size: V ? 50 : 46, t },
      { k: "text", x: cx, y: cy - r - 86, s: en, size: 26, font: "Typewriter", bold: false, dim: true, t: t + .15 },
    ];
    const c1 = V ? [W / 2, 470] : [W * 0.27, 520], c2 = V ? [W / 2, 1150] : [W * 0.73, 520], r = V ? 220 : 240;
    const th = T(D, "hub", .2);
    S.push(...panel(...c1, r, "المطار المحوري", "Hub-and-Spoke", th));
    const cities = [0, 1, 2, 3, 4, 5].map((i) => [c1[0] + r * Math.cos(i / 6 * 6.283 - 1.2), c1[1] + r * Math.sin(i / 6 * 6.283 - 1.2)]);
    S.push({ k: "circle", c: c1, r: 34, t: th + .3, dur: .5, w: 5 });
    cities.forEach((p, i) => {
      S.push({ k: "line", p: [c1[0], c1[1], p[0], p[1]], t: th + .6 + i * .1, dur: .3 });
      S.push({ k: "dot", c: p, r: 12, t: th + .85 + i * .1 });
    });
    const tt = T(D, "transit", th + 1.8);   // one trip: city -> hub -> city
    S.push({ k: "path", path: `M${cities[1][0]} ${cities[1][1]} L${c1[0]} ${c1[1]} L${cities[4][0]} ${cities[4][1]}`, t: tt, dur: .7, red: true, w: 6 });
    S.push({ k: "text", x: c1[0], y: c1[1] + r + 70, s: "ترانزيت.. وانتظار", size: 32, bold: false, font: "AmiriR", dim: true, t: tt + .3 });
    const ts = T(D, "storm", -1);
    if (ts >= 0) S.push({ k: "circle", c: c1, r: 70, t: ts, dur: .5, red: true, w: 6 },
                        { k: "text", x: c1[0], y: c1[1] + r + 125, s: "عاصفة في المحور = كله يقف", size: 32, red: true, t: ts + .3 });
    const tp = T(D, "p2p", tt + 1.2);
    S.push(...panel(...c2, r, "من نقطة لنقطة", "Point-to-Point", tp));
    const tri = [[c2[0], c2[1] - r * .85], [c2[0] + r * .95, c2[1] + r * .6], [c2[0] - r * .95, c2[1] + r * .6]];
    const names = D.cities || ["دالاس", "هيوستن", "سان أنطونيو"];
    tri.forEach((p, i) => { const q = tri[(i + 1) % 3]; S.push({ k: "line", p: [...p, ...q], t: tp + .3 + i * .3, dur: .35, red: true, w: 6 }); });
    tri.forEach((p, i) => {
      S.push({ k: "dot", c: p, r: 14, t: tp + .3 + i * .2 });
      S.push({ k: "text", x: p[0], y: p[1] + (i === 0 ? -32 : 58), s: names[i], size: V ? 36 : 34, t: tp + .45 + i * .2 });
    });
    S.push({ k: "text", x: c2[0], y: c2[1] + r + 70, s: "طيران مباشر.. من غير ترانزيت", size: 32, bold: false, font: "AmiriR", dim: true, t: tp + 1.3 });
    if (!V) S.push({ k: "line", p: [W / 2, 160, W / 2, H - 90], t: tp - .2, dur: .5, w: 2 });
    return S.concat(credit(W, H, D, th + .5));
  },

  // the Flywheel: each link appears as it is said (beats step0..), «هتقف» jams it
  flywheel(W, H, V, D) {
    const S = [];
    const steps = D.steps || ["نوع واحد من الطيارات", "صيانة أسرع وأرخص", "الطيارة تطير أكتر", "تكلفة الكرسي تقل", "سعر أقل", "زباين أكتر"];
    const cx = W / 2, cy = V ? 820 : 515, R = V ? 270 : 250;
    S.push({ k: "text", x: cx, y: V ? 330 : 70, s: D.title || "العجلة", size: V ? 54 : 48, t: .1 });
    S.push({ k: "text", x: cx, y: V ? 380 : 112, s: "The Flywheel", size: 26, font: "Typewriter", bold: false, dim: true, t: .25 });
    const n = steps.length, pts = steps.map((_, i) => {
      const a = -Math.PI / 2 + i / n * 2 * Math.PI;
      return [cx + R * Math.cos(a), cy + R * Math.sin(a), a];
    });
    let last = .5;
    pts.forEach(([x, y, a], i) => {
      const t = Math.max(T(D, `step${i}`, .5 + i * .9), last); last = t + .2;
      const lx = x + Math.cos(a) * (V ? 34 : 44), ly = y + Math.sin(a) * 52 + 12;
      const anchor = Math.abs(Math.cos(a)) < .3 ? "middle" : (Math.cos(a) > 0 ? "start" : "end");
      S.push({ k: "dot", c: [x, y], r: 13, t });
      S.push({ k: "text", x: lx, y: ly, s: steps[i], size: V ? 32 : 32, anchor, t: t + .05 });
      const [, , a2r] = pts[(i + 1) % n], a2 = a2r < a ? a2r + 2 * Math.PI : a2r;
      const am = (a + a2) / 2, rr = R * .78;
      const sx = cx + rr * Math.cos(a + .2), sy = cy + rr * Math.sin(a + .2);
      const ex = cx + rr * Math.cos(a2 - .2), ey = cy + rr * Math.sin(a2 - .2);
      const mx = cx + rr * 1.06 * Math.cos(am), my = cy + rr * 1.06 * Math.sin(am);
      const ah = Math.atan2(ey - my, ex - mx), h = 18;
      S.push({ k: "path", path: `M${sx} ${sy} Q${mx} ${my} ${ex} ${ey} M${ex - h * Math.cos(ah - .5)} ${ey - h * Math.sin(ah - .5)} L${ex} ${ey} L${ex - h * Math.cos(ah + .5)} ${ey - h * Math.sin(ah + .5)}`,
               t: t + .25, dur: .35, red: true, w: 5 });
    });
    S.push({ k: "circle", c: [cx, cy], r: 66, t: last + .2, dur: .5, red: true, w: 5 });
    S.push({ k: "text", x: cx, y: cy + 14, s: D.center || "بتلف أسرع", size: 32, red: true, t: last + .4 });
    const tj = T(D, "jam", -1);
    if (tj >= 0) S.push({ k: "line", p: [cx - R * .55, cy - R * .55, cx + R * .55, cy + R * .55], t: tj, dur: .3, red: true, w: 9 },
                        { k: "text", x: cx, y: V ? cy + R + 140 : H - 18, s: D.jam || "لو بطّلت واحدة.. العجلة تقف", size: 38, red: true, t: tj + .2 });
    return S.concat(credit(W, H, D, .5));
  },

  // Straddling: trying to stand in two places at once (beats: full, low, lite, ted, fail)
  straddling(W, H, V, D) {
    const S = [];
    S.push(...heading(W, V, D, "الوقوف على حبلين", "Straddling", .1, V ? 190 : 95));
    const L = V ? [W * .25, 560] : [W * .22, 420], R = V ? [W * .75, 560] : [W * .78, 420], M = V ? [W / 2, 880] : [W / 2, 610];
    const tf = T(D, "full", .5), tl = T(D, "low", tf + .5);
    S.push({ k: "circle", c: L, r: 130, t: tf, dur: .5 });
    S.push({ k: "text", x: L[0], y: L[1] - 6, s: "خدمة كاملة", size: 42, t: tf + .3 });
    S.push({ k: "text", x: L[0], y: L[1] + 40, s: "Full Service", size: 22, font: "Typewriter", bold: false, dim: true, t: tf + .4 });
    S.push({ k: "circle", c: R, r: 130, t: tl, dur: .5 });
    S.push({ k: "text", x: R[0], y: R[1] - 6, s: "سعر رخيص", size: 42, t: tl + .3 });
    S.push({ k: "text", x: R[0], y: R[1] + 40, s: "Low Cost", size: 22, font: "Typewriter", bold: false, dim: true, t: tl + .4 });
    const t1 = T(D, "lite", tl + .9), t2 = T(D, "ted", t1 + .6);
    S.push({ k: "arrow", p: [M[0] - 40, M[1] - 60, L[0] + 80, L[1] + 110], t: t1, dur: .4 });
    S.push({ k: "arrow", p: [M[0] + 40, M[1] - 60, R[0] - 80, R[1] + 110], t: t1 + .2, dur: .4 });
    S.push({ k: "text", id: "lite", x: M[0], y: M[1] + 10, s: "Continental Lite", size: 34, font: "Typewriter", bold: false, t: t1 });
    S.push({ k: "text", id: "ted", x: M[0], y: M[1] + 60, s: "Ted (United)", size: 32, font: "Typewriter", bold: false, t: t2 });
    const tx = T(D, "fail", t2 + .8);
    S.push({ k: "strike", of: "lite", t: tx, dur: .3 }, { k: "strike", of: "ted", t: tx + .2, dur: .3 });
    S.push({ k: "text", x: W / 2, y: V ? 1180 : 800, s: D.result || "فشل", size: V ? 60 : 58, red: true, t: tx + .3 });
    return S.concat(credit(W, H, D, .5));
  },
};
