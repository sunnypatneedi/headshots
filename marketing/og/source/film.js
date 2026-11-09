// headshots og:video v4 — darkroom contact sheet on a light table. Copy from briefs/headshots.md only.
// Faces: the kit's AI-generated synthetic demo portraits (films/_og/assets/hs/p-*.jpg). No real people.
const { el, add, rnd, onSeek, end, stage } = K;
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const pr = (t, t0, d) => cl((t - t0) / d);
const oc = (p) => 1 - Math.pow(1 - p, 3);
const io = (p) => (p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
const ob = (p, s = 2.2) => 1 + (s + 1) * Math.pow(p - 1, 3) + s * Math.pow(p - 1, 2);
const lerp = (a, b, p) => a + (b - a) * p;
const R = (a, b) => a + (b - a) * rnd();
const wob = (t, t0, amp, f = 38, k = 13) => (t < t0 ? 0 : amp * Math.exp(-k * (t - t0)) * Math.sin(f * (t - t0)));
const kf = (keys, t) => { if (t <= keys[0][0]) return keys[0].slice(1); for (let i = 1; i < keys.length; i++) if (t <= keys[i][0]) { const a = keys[i - 1], b = keys[i], p = io((t - a[0]) / (b[0] - a[0])); return a.slice(1).map((v, j) => lerp(v, b[j + 1], p)); } return keys[keys.length - 1].slice(1); };
const grainURL = (() => { const n = 160, c = document.createElement('canvas'); c.width = c.height = n; const g = c.getContext('2d'), d = g.createImageData(n, n); for (let i = 0; i < n * n; i++) { d.data[i * 4 + 3] = rnd() < .35 ? rnd() * 26 : 0; } g.putImageData(d, 0, 0); return c.toDataURL(); })();

const table = add(stage, el(`<div class="full" id="table"><div class="gr" style="background-image:url(${grainURL})"></div></div>`));
// pencilled rule + ticks on the table
add(table, el('<div class="pl" style="left:36px;right:36px;top:612px;height:1.5px"></div>'));
for (let i = 0; i <= 56; i++) add(table, el(`<div class="pl" style="left:${40 + i * 20}px;top:${i % 5 ? 604 : 596}px;width:1.5px;height:${i % 5 ? 8 : 16}px"></div>`));
const lab = add(stage, el('<div class="cp" style="left:56px;top:38px;font-size:20px">Example · AI-generated demo portraits</div>'));

const grp = add(stage, el('<div class="full"></div>'));
const FACES = ['a', 'd', 'c', 'e', 'b', 'f'], EYE = { a: 0, d: 0, c: 0, e: 0, b: 0, f: 0 };
const RAW = [[1.5, 20, 35], [1.3, -10, -25], [1.9, -40, -60], [1.25, 15, 18], [2.1, 30, 70], [1.12, -8, -12]];
const PX = (i) => 52 + i * 370, PY = 157, LINE = PY + 44 + 198 * .415;
const P0 = [[-18, -58, -5], [8, 50, 3.6], [24, -24, -2.6]], LANDP = [0.2, 0.42, 0.3], FROM = [[-900, 120, -16], [40, -700, 13], [1000, -60, 12]], SNAPP = [1.64, 1.74, 1.82];
const SNAPF = [1.96, 2.04, 2.15, 2.21, 2.33, 2.39];
const pieces = [0, 1, 2].map((i) => {
  const p = add(grp, el(`<div class="piece"><div class="sh"></div><div class="spr" style="top:9px"></div><div class="spr" style="bottom:9px"></div></div>`));
  p.frames = [0, 1].map((j) => { const f = i * 2 + j, k = FACES[f]; const fr = add(p, el(`<div class="fr" style="left:${14 + j * 170}px"><div class="ph" style="background-image:url(/films/_og/assets/hs/p-${k}.jpg);background-position:50% ${EYE[k]}px"></div></div>`));
    add(p, el(`<div class="fn" style="left:${20 + j * 170}px">${f + 3}</div>`)); add(p, el(`<div class="fn" style="left:${118 + j * 170}px">${f + 3}A</div>`)); fr.ph = fr.firstChild; fr.f = f; return fr; });
  return p;
});
const FX = (f) => PX(Math.floor(f / 2)) + 14 + (f % 2) * 170 + 79;
const svg = add(grp, el('<svg class="ink" width="1200" height="630" viewBox="0 0 1200 630"></svg>'));
const path = (par, pts, w, op = 1) => { const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join('')); p.setAttribute('pathLength', 1); p.setAttribute('stroke-width', w); p.setAttribute('stroke-dasharray', '1 1'); p.setAttribute('stroke-dashoffset', 1); p.setAttribute('opacity', op); par.appendChild(p); return p; };
const wl = (x0, y0, x1, y1, a, n = 10) => Array.from({ length: n + 1 }, (_, i) => [lerp(x0, x1, i / n), lerp(y0, y1, i / n) + (i && i < n ? R(-a, a) : 0)]);
const draw = (ps, p, on = true) => ps.forEach((q, i) => { const pp = cl(p * 1.1 - i * .05); q.setAttribute('stroke-dashoffset', (1 - pp).toFixed(4)); q.style.visibility = on && pp > 0 ? 'visible' : 'hidden'; });
const eyeLine = [path(svg, wl(26, LINE, 1174, LINE, 1.2, 40), 7, .92), path(svg, wl(30, LINE + 3, 1170, LINE + 2.5, 1.5, 40), 3, .6), path(svg, wl(28, LINE - 3, 1172, LINE - 3, 1.2, 40), 2, .5)];
const ticks = SNAPF.map((_, f) => { const x = FX(f) + R(-2, 2); return [path(svg, wl(x, LINE - 15, x + R(-2, 2), LINE + 15, 0, 2), 5, .95)]; });
// marks layer (stays on the table, not in the moving group)
const svg2 = add(stage, el('<svg class="ink" width="1200" height="630" viewBox="0 0 1200 630"></svg>'));
const NOTES = [['same head size', 58, 84, -2], ['same eye line', 452, 90, 1.5], ['same finish', 846, 82, -1.5]].map(([s, x, y, r]) => { const n = add(stage, el(`<div class="mk" style="left:${x}px;top:${y}px;font-size:40px;transform:rotate(${r}deg)">${s}</div>`)); return n; });
const GR = ['PASS', 'PASS', 'PASS', 'PASS', 'REVIEW', 'PASS'], GT = [3.1, 3.22, 3.42, 3.52, 4.02, 3.68];
const grades = GR.map((s, f) => add(stage, el(`<div class="mk" style="left:${FX(f) - (s === 'PASS' ? 44 : 70)}px;top:${452 + (f % 2) * 4}px;font-size:36px;transform:rotate(${R(-5, 3).toFixed(1)}deg)">${s}</div>`)));
const circ = [path(svg2, Array.from({ length: 40 }, (_, i) => { const a = -2.2 + i / 35 * 6.283; return [FX(4) + Math.cos(a) * (104 + i * .4) + R(-2, 2), PY + 143 + Math.sin(a) * (128 + i * .3) + R(-2, 2)]; }), 7, .92)];
const L1 = 'you are not eyeballing 200 photos, you are reading', L2 = 'the 13 the tool is unsure about.';
const ty1 = add(stage, el('<div class="cp" style="left:56px;top:520px;font-size:25px"></div>')), ty2 = add(stage, el('<div class="cp" style="left:56px;top:554px;font-size:25px"></div>'));
const pencil = add(stage, el('<div id="pencil"><div class="psh"></div><div class="pb"></div><div class="pp"></div><div class="pt"></div></div>'));
const PK = [[0.8, 1260, 760, 60], [1.15, 26, LINE, 42], [1.5, 1174, LINE, 30], [1.9, 1010, 560, 8], [3.7, 1010, 560, 8], [3.84, FX(4) - 62, PY + 40, 48], [4.12, FX(4) - 62, PY + 40, 48], [4.5, 1010, 566, 6], [5.7, 1010, 566, 6], [5.95, 1320, 700, 20]];
// end card
const band = add(stage, el('<div id="band"><div class="spr" style="top:8px"></div><div class="spr" style="bottom:8px"></div><div class="ttl">headshots</div><div class="ai">AI-generated demo portraits</div></div>'));
const e1 = add(stage, el('<div class="cp" style="left:56px;top:442px;font-size:27px;font-weight:700">Turn a folder of phone photos into a matched set of portraits —</div>'));
const e2 = add(stage, el('<div class="cp" style="left:56px;top:478px;font-size:27px;font-weight:700">same head size, same eye line, same finish</div>'));
const e3 = add(stage, el('<div class="cp" style="left:56px;top:566px;font-size:20px">It runs on your machine. No account, no upload, no telemetry.</div>'));
const e4 = add(stage, el('<div class="cp" style="right:56px;top:566px;font-size:20px">Built by Sunny Patneedi</div>'));
const eu = [path(svg2, wl(54, 514, 740, 509, 2.5), 5.5, .92), path(svg2, wl(62, 520, 728, 516, 2), 2.5, .6)];
const vis = (n, on) => (n.style.visibility = on ? 'visible' : 'hidden');

onSeek.push((t) => {
  const t12 = Math.floor(t * 12) / 12;
  pieces.forEach((p, i) => {
    const a = pr(t, LANDP[i] - .5, .5), e = oc(a), zs = lerp(2.3, 1, io(a)) + wob(t, LANDP[i], .03), s = pr(t, SNAPP[i], .09), se = ob(s, 2.6);
    const x0 = PX(i) + P0[i][0] + (1 - e) * FROM[i][0] + wob(t, LANDP[i], i === 1 ? 0 : 7), y0 = PY + P0[i][1] + (1 - e) * FROM[i][1] + wob(t, LANDP[i], i === 1 ? 8 : 0), r0 = P0[i][2] + (1 - e) * FROM[i][2] + wob(t, LANDP[i], 1.4);
    p.style.visibility = a > 0 ? 'visible' : 'hidden';
    p.style.transform = `translate(${lerp(x0, PX(i), se).toFixed(2)}px,${lerp(y0, PY, se).toFixed(2)}px) rotate(${lerp(r0, 0, se).toFixed(3)}deg) scale(${zs.toFixed(4)})`;
    p.firstChild.style.transform = `translate(${(4 + (zs - 1) * 12).toFixed(1)}px,${(5 + (zs - 1) * 15).toFixed(1)}px)`;
    p.frames.forEach((fr) => { const [sc, ox, oy] = RAW[fr.f], q = ob(pr(t, SNAPF[fr.f], .08), 2); fr.ph.style.transform = `translate(${lerp(ox, 0, q).toFixed(2)}px,${lerp(oy, 0, q).toFixed(2)}px) scale(${lerp(sc, 1, q).toFixed(4)})`; });
  });
  draw(eyeLine, pr(t, 1.15, .35));
  ticks.forEach((k, f) => draw(k, t >= SNAPF[f] + .06 ? 1 : 0));
  NOTES.forEach((n, i) => { const p = Math.floor(pr(t, 2.46 + i * .17, .2) * 5) / 5; n.style.clipPath = `inset(-10px ${(100 - p * 104).toFixed(1)}% -10px -4px)`; vis(n, p > 0 && t < 5.76); });
  grades.forEach((n, f) => { const p = Math.floor(pr(t, GT[f], .12) * 3) / 3; n.style.clipPath = `inset(-10px ${(100 - p * 106).toFixed(1)}% -10px -4px)`; vis(n, p > 0 && t < 5.76); });
  const cp = pr(t, 3.84, .28); draw(circ, cp, t < 5.76);
  const ty = (n, s, t0, d) => { n.textContent = s.slice(0, Math.round(cl((t12 - t0) / d) * s.length)); vis(n, t < 5.76); };
  ty(ty1, L1, 4.4, .6); ty(ty2, L2, 5.0, .4);
  vis(lab, t < 5.76);
  let [px, py, pa] = kf(PK, t);
  if (t > 3.84 && t < 4.12) { const a = -2.2 + cp * 6.283 * 39 / 35; px = FX(4) + Math.cos(a) * 110; py = PY + 143 + Math.sin(a) * 134; }
  pencil.style.transform = `translate(${px.toFixed(1)}px,${py.toFixed(1)}px) rotate(${pa.toFixed(2)}deg)`;
  // end: sheet slides up, title band slaps in
  const up = ob(pr(t, 5.78, .2), 1.6); grp.style.transform = `translateY(${(-187 * up).toFixed(2)}px)`;
  const bp = pr(t, 5.98, .15), be = oc(bp); vis(band, bp > 0); band.style.transform = `translate(${((1 - be) * 1300 + wob(t, 6.13, 9, 40, 14)).toFixed(1)}px,0) rotate(${wob(t, 6.13, .5).toFixed(2)}deg)`;
  vis(e1, t >= 6.3); vis(e2, t >= 6.42); vis(e3, t >= 6.6); vis(e4, t >= 6.6); draw(eu, pr(t, 6.72, .2));
});
end();
