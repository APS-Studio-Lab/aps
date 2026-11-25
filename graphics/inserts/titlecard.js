// where the type sits: the dark side of the clip (D.place: "right" | "left" | "center")
function placeStack(stack, shade) {
  const p = V ? "center" : (D.place || "right");
  if (p === "center") { stack.style.left = "18%"; stack.style.width = "64%";
    shade.style.background = "radial-gradient(ellipse 60% 55% at 50% 50%,rgba(0,0,0,.35),rgba(0,0,0,0) 75%)"; }
  else { stack.style[p] = "4%";
    shade.style.background = `linear-gradient(${p === "right" ? "270deg" : "90deg"},rgba(0,0,0,.5) 0%,rgba(0,0,0,.28) 38%,rgba(0,0,0,0) 62%)`; }
}
// words ink in: from a soft blur to sharp, one after another
function inkWords(e, t, t0, per = .14) {
  if (!e._w) { e.innerHTML = e.textContent.trim().split(/\s+/).map((w) => `<span class="w">${w}</span>`).join(" ");
               e._w = [...e.querySelectorAll(".w")]; }
  e._w.forEach((w, i) => { const k = eOut(seg(t, t0 + i * per, t0 + i * per + .45));
    w.style.opacity = k; w.style.transform = `translateY(${(1 - k) * 8 * U}px)`; });
}
// typewriter: letters one by one (only for Latin/typewriter lines and short Arabic kickers)
function typeOn(e, t, t0, per = .05) {
  if (e._full === undefined) e._full = e.textContent;
  e.textContent = e._full.slice(0, Math.max(0, Math.floor((t - t0) / per)));
}
// dust drifting in the light
function dustLayer(n, seed) {
  const r = rng(seed), m = [];
  for (let i = 0; i < n; i++) { const d = el("div", "dust", document.body), s = (1.4 + r() * 3.2) * U;
    d.style.width = d.style.height = s + "px";
    m.push({ d, x: r() * innerWidth, y: r() * innerHeight, vx: (r() - .5) * 7, vy: -3 - r() * 9, a: .15 + r() * .45 }); }
  return (t) => m.forEach((p) => { p.d.style.transform = `translate(${(p.x + p.vx * t * U * 3 + innerWidth * 4) % innerWidth}px,${(p.y + p.vy * t * U * 3 + innerHeight * 4) % innerHeight}px)`;
                                   p.d.style.opacity = p.a * (0.6 + 0.4 * Math.sin(t * 2 + p.x)); });
}
