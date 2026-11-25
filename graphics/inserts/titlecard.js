// worn letterpress edges for light type on dark footage
document.body.insertAdjacentHTML("afterbegin", `<svg width="0" height="0" style="position:absolute"><defs>
  <filter id="worn" x="-5%" y="-5%" width="110%" height="110%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4" result="n"/>
    <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -1.6 1.25" result="holes"/>
    <feComposite in="SourceGraphic" in2="holes" operator="in" result="worn"/>
    <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="9" result="w"/>
    <feDisplacementMap in="worn" in2="w" scale="2.2" xChannelSelector="R" yChannelSelector="G"/>
  </filter></defs></svg>`);
// words ink in: from a soft blur to sharp, one after another
function inkWords(e, t, t0, per = .14) {
  if (!e._w) { e.innerHTML = e.textContent.trim().split(/\s+/).map((w) => `<span class="w">${w}</span>`).join(" ");
               e._w = [...e.querySelectorAll(".w")]; }
  e._w.forEach((w, i) => { const k = eOut(seg(t, t0 + i * per, t0 + i * per + .45));
    w.style.opacity = k; w.style.filter = `blur(${(1 - k) * 7 * U}px)`; w.style.transform = `translateY(${(1 - k) * 10 * U}px)`; });
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
