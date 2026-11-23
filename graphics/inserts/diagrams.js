// Explainer diagrams, drawn by hand on the layout sheet. Each returns timed steps in viewBox units.
// Our own drawings of well-known concepts; the idea's author is credited on the sheet (D.credit).
// Labels are Egyptian business Ammia; English terms stay as business people say them.

function credit(W, H, D, t) {
  return D.credit ? [{ k: "text", x: W - 40, y: H - 30, s: D.credit, size: 24, font: "Typewriter", bold: false, anchor: "end", t }] : [];
}

const DIAGRAMS = {
  // Hub-and-Spoke vs Point-to-Point
  hub_vs_p2p(W, H, V, D) {
    const S = [];
    const panel = (cx, cy, r, title, en, t) => [
      { k: "text", x: cx, y: cy - r - 90, s: title, size: V ? 50 : 48, t },
      { k: "text", x: cx, y: cy - r - 45, s: en, size: 28, font: "Courier", t: t + .15 },
    ];
    const c1 = V ? [W / 2, 470] : [W * 0.27, 520], c2 = V ? [W / 2, 1150] : [W * 0.73, 520], r = V ? 220 : 250;
    // left: one hub, every route passes through it
    S.push(...panel(...c1, r, "المحطة المركزية", "Hub-and-Spoke", 0.2));
    const cities = [0, 1, 2, 3, 4, 5].map((i) => [c1[0] + r * Math.cos(i / 6 * 6.283 - 1.2), c1[1] + r * Math.sin(i / 6 * 6.283 - 1.2)]);
    S.push({ k: "circle", c: c1, r: 34, t: .5, dur: .5, w: 6 });
    cities.forEach((p, i) => {
      S.push({ k: "line", p: [c1[0], c1[1], p[0], p[1]], t: .8 + i * .12, dur: .35 });
      S.push({ k: "dot", c: p, r: 13, t: .8 + i * .12 + .3 });
    });
    S.push({ k: "text", x: c1[0], y: c1[1] + r + 70, s: "كل رحلة لازم تعدّي على المطار الكبير", size: V ? 34 : 32, bold: false, font: "AmiriR", t: 1.9 });
    // right: the triangle, direct routes only
    S.push(...panel(...c2, r, "من النقطة للنقطة", "Point-to-Point", 2.3));
    const tri = [[c2[0], c2[1] - r * .85], [c2[0] + r * .95, c2[1] + r * .6], [c2[0] - r * .95, c2[1] + r * .6]];
    const names = ["دالاس", "هيوستن", "سان أنطونيو"];
    tri.forEach((p, i) => {
      const q = tri[(i + 1) % 3];
      S.push({ k: "line", p: [p[0], p[1], q[0], q[1]], t: 2.6 + i * .35, dur: .4, red: true, w: 7 });
    });
    tri.forEach((p, i) => {
      S.push({ k: "dot", c: p, r: 15, t: 2.6 + i * .2 });
      S.push({ k: "text", x: p[0], y: p[1] + (i === 0 ? -32 : 58), s: names[i], size: V ? 38 : 36, t: 2.75 + i * .2 });
    });
    S.push({ k: "text", x: c2[0], y: c2[1] + r + 70, s: "طيران مباشر.. من غير ترانزيت", size: V ? 34 : 32, bold: false, font: "AmiriR", t: 3.8 });
    if (!V) S.push({ k: "line", p: [W / 2, 160, W / 2, H - 90], t: 2.1, dur: .5, w: 2.5 });
    return S.concat(credit(W, H, D, 4.2));
  },

  // the Flywheel: each step feeds the next
  flywheel(W, H, V, D) {
    const S = [];
    const steps = D.steps || ["نوع واحد من الطيارات", "صيانة أسرع وأرخص", "الطيارة تطير أكتر", "تكلفة الكرسي تقل", "سعر أقل", "زباين أكتر"];
    const cx = W / 2, cy = V ? 820 : 525, R = V ? 270 : 255;
    S.push({ k: "text", x: cx, y: V ? 330 : 84, s: D.title || "العجلة اللي بتلف لوحدها", size: V ? 54 : 50, t: .1 });
    S.push({ k: "text", x: cx, y: V ? 380 : 120, s: "The Flywheel", size: 28, font: "Courier", t: .25 });
    const n = steps.length, pts = steps.map((_, i) => {
      const a = -Math.PI / 2 + i / n * 2 * Math.PI;
      return [cx + R * Math.cos(a), cy + R * Math.sin(a), a];
    });
    pts.forEach(([x, y, a], i) => {
      const t = .5 + i * .5;
      const lx = x + Math.cos(a) * (V ? 34 : 44), ly = y + Math.sin(a) * 52 + 12;
      const anchor = Math.abs(Math.cos(a)) < .3 ? "middle" : (Math.cos(a) > 0 ? "start" : "end");
      S.push({ k: "dot", c: [x, y], r: 14, t });
      S.push({ k: "text", x: lx, y: ly, s: steps[i], size: V ? 32 : 34, anchor, t: t + .05 });
      const [x2, y2, a2] = pts[(i + 1) % n];
      const am = (a + (a2 < a ? a2 + 2 * Math.PI : a2)) / 2, rr = R * .78;
      // curved arrow along the inside of the wheel
      const sx = cx + rr * Math.cos(a + .2), sy = cy + rr * Math.sin(a + .2);
      const ex = cx + rr * Math.cos((a2 < a ? a2 + 2 * Math.PI : a2) - .2), ey = cy + rr * Math.sin((a2 < a ? a2 + 2 * Math.PI : a2) - .2);
      const mx = cx + rr * 1.06 * Math.cos(am), my = cy + rr * 1.06 * Math.sin(am);
      const ah = Math.atan2(ey - my, ex - mx), h = 18;
      S.push({ k: "path", path: `M${sx} ${sy} Q${mx} ${my} ${ex} ${ey} M${ex - h * Math.cos(ah - .5)} ${ey - h * Math.sin(ah - .5)} L${ex} ${ey} L${ex - h * Math.cos(ah + .5)} ${ey - h * Math.sin(ah + .5)}`,
               t: t + .25, dur: .35, red: true, w: 6 });
    });
    S.push({ k: "circle", c: [cx, cy], r: 70, t: .5 + n * .5, dur: .5, red: true, w: 6 });
    S.push({ k: "text", x: cx, y: cy + 14, s: D.center || "بتلف أسرع", size: 34, red: true, t: .7 + n * .5 });
    return S.concat(credit(W, H, D, .9 + n * .5));
  },

  // Trade-offs: what Southwest said "no" to
  trade_offs(W, H, V, D) {
    const S = [];
    const rows = D.rows || [["وجبات؟", "تسالي بس"], ["كراسي محجوزة؟", "اللي ييجي الأول يقعد الأول"],
                            ["مطارات كبيرة؟", "مطارات جانبية فاضية"], ["درجة أولى؟", "كله درجة واحدة"]];
    S.push({ k: "text", x: W / 2, y: V ? 190 : 100, s: D.title || "ساوث ويست قالت «لأ»", size: V ? 56 : 52, t: .1 });
    S.push({ k: "text", x: W / 2, y: V ? 240 : 145, s: "Trade-offs", size: 28, font: "Courier", t: .25 });
    const top = V ? 400 : 240, gap = V ? 250 : 150, xr = V ? W - 140 : W * 0.66, xs = V ? W - 140 : W * 0.44;
    rows.forEach(([q, a], i) => {
      const y = top + i * gap, t = .5 + i * .7;
      S.push({ k: "text", x: xr, y, s: q, size: V ? 46 : 44, anchor: "end", t });
      const w = q.length * (V ? 22 : 21) + 20;
      S.push({ k: "line", p: [xr - w, y - 14, xr + 10, y - 14], t: t + .25, dur: .3, red: true, w: 7, amp: 2 });
      const la = V ? 150 : Math.min(xr - w - 70, W * 0.52);
      S.push({ k: "text", x: la, y, s: "لأ", size: 58, red: true, anchor: "middle", t: t + .4 });
      S.push({ k: "text", x: V ? xr : la - 60, y: V ? y + 72 : y, s: a, size: V ? 36 : 36, bold: false, font: "AmiriR", anchor: "end", t: t + .5 });
    });
    return S.concat(credit(W, H, D, .9 + rows.length * .7));
  },

  // Straddling: trying to stand on two ropes
  straddling(W, H, V, D) {
    const S = [];
    S.push({ k: "text", x: W / 2, y: V ? 190 : 95, s: "الوقوف على حبلين", size: V ? 58 : 54, t: .1 });
    S.push({ k: "text", x: W / 2, y: V ? 240 : 140, s: "Straddling", size: 28, font: "Courier", t: .25 });
    const L = V ? [W * .22, 560] : [W * .2, 420], R = V ? [W * .78, 560] : [W * .8, 420], M = V ? [W / 2, 860] : [W / 2, 600];
    S.push({ k: "circle", c: L, r: V ? 130 : 130, t: .5, dur: .5 });
    S.push({ k: "text", x: L[0], y: L[1] - 6, s: "فخامة", size: 46, t: .8 });
    S.push({ k: "text", x: L[0], y: L[1] + 40, s: "Full Service", size: 24, font: "Courier", t: .9 });
    S.push({ k: "circle", c: R, r: V ? 130 : 130, t: 1.0, dur: .5 });
    S.push({ k: "text", x: R[0], y: R[1] - 6, s: "سعر رخيص", size: 44, t: 1.3 });
    S.push({ k: "text", x: R[0], y: R[1] + 40, s: "Low Cost", size: 24, font: "Courier", t: 1.4 });
    S.push({ k: "arrow", p: [M[0] - 40, M[1] - 60, L[0] + 80, L[1] + 110], t: 1.6, dur: .4 });
    S.push({ k: "arrow", p: [M[0] + 40, M[1] - 60, R[0] - 80, R[1] + 110], t: 1.8, dur: .4 });
    S.push({ k: "text", x: M[0], y: M[1] + 10, s: "Continental Lite", size: 36, font: "Courier", t: 2.1 });
    S.push({ k: "text", x: M[0], y: M[1] + 58, s: "Ted (United)", size: 34, font: "Courier", t: 2.25 });
    const y2 = V ? 1150 : 790;
    S.push({ k: "line", p: [W * .18, y2 - 60, W * .82, y2 - 60], t: 2.6, dur: .4, w: 2.5 });
    S.push({ k: "text", x: W / 2, y: y2, s: "النتيجة: خدمة وحشة.. وسعر لسه غالي", size: V ? 44 : 44, red: true, t: 2.9 });
    return S.concat(credit(W, H, D, 3.2));
  },
};
