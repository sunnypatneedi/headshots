/* Interactive mirror of the SwiftUI shell for visual QA on non-Mac hosts. */

const params = new URLSearchParams(location.search);
const screenSelect = document.getElementById("screen");
const themeSelect = document.getElementById("theme");
const pane = document.getElementById("pane");
const actionBar = document.getElementById("action-bar");
const steps = [...document.querySelectorAll("#steps li")];

const SCREENS = {
  welcome: { step: 1, render: renderWelcome, actions: () => emptyActions() },
  check: { step: 2, render: renderCheck, actions: () => backAndPrimary("Continue") },
  finish: { step: 3, render: renderFinish, actions: () => backAndPrimary("Make Headshots") },
  processing: { step: 3, render: renderProcessing, actions: () => stopOnly() },
  results: { step: 4, render: renderResults, actions: () => resultsActions() },
  empty: { step: 2, render: renderEmpty, actions: () => backOnly() },
  error: { step: 3, render: renderError, actions: () => backAndPrimary("Make Headshots") },
};

function setStep(n) {
  steps.forEach((el) => {
    const i = Number(el.dataset.step);
    el.removeAttribute("aria-current");
    el.classList.toggle("is-done", i < n);
    if (i === n) el.setAttribute("aria-current", "step");
    const badge = el.querySelector(".badge");
    badge.textContent = i < n ? "✓" : String(i);
  });
}

function btn(label, { primary = false, disabled = false } = {}) {
  return `<button class="btn ${primary ? "btn-primary" : "btn-secondary"}" ${disabled ? "disabled" : ""} type="button">${label}</button>`;
}

function emptyActions() {
  actionBar.innerHTML = `<span class="btn-spacer"></span><span class="muted" style="font-size:12px">Choose a folder to continue</span>`;
}
function backOnly() {
  actionBar.innerHTML = `${btn("Back")}<span class="btn-spacer"></span>`;
}
function backAndPrimary(label) {
  actionBar.innerHTML = `${btn("Back")}<span class="btn-spacer"></span>${btn(label, { primary: true })}`;
}
function stopOnly() {
  actionBar.innerHTML = `<span class="btn-spacer"></span>${btn("Stop")}`;
}
function resultsActions() {
  actionBar.innerHTML = `${btn("Back")}<span class="btn-spacer"></span>${btn("Show in Finder")}${btn("Open contact sheet")}${btn("Polish again", { primary: true })}`;
}

function renderWelcome() {
  pane.innerHTML = `
    <div class="stack">
      <div class="drop" tabindex="0" role="button" aria-label="Drop photos or a folder here">
        <div>
          <div class="portraits" aria-hidden="true"><span></span><span></span><span></span></div>
          <div class="drop-arrow" aria-hidden="true">↓</div>
          <h1>Drop photos or a folder here</h1>
          <p class="sub">We’ll turn them into clean, matching headshots.</p>
          <div class="row" style="justify-content:center;margin-top:16px">
            ${btn("Choose Photos", { primary: true })}
            ${btn("Choose a Folder")}
          </div>
        </div>
      </div>
      <div class="lockline"><span class="lock-icon" aria-hidden="true"></span> Everything stays on your Mac. Nothing is uploaded.</div>
    </div>`;
}

function renderCheck() {
  pane.innerHTML = `
    <div class="stack">
      <div>
        <h1>Ready to polish</h1>
        <p class="sub" style="font-weight:650;color:var(--ink)">cast-shoot</p>
        <p class="sub">24 photos at the top level. Originals stay untouched.</p>
      </div>
      <div class="row">
        ${btn("Choose another folder")}
        ${btn("Continue to Finish", { primary: true })}
      </div>
    </div>`;
}

function renderFinish() {
  pane.innerHTML = `
    <div class="stack">
      <div style="text-align:center">
        <h1>How should we finish them?</h1>
        <div class="recommend">These are our recommended settings. Just press Make Headshots.</div>
      </div>
      <section>
        <div class="section-label">Framing</div>
        <div class="cards">
          ${framingCard("Head & shoulders", "Best for most uses", true, true)}
          ${framingCard("Close-up", "Face fills the frame", false, false)}
          ${framingCard("Half body", "More of the outfit", false, false)}
        </div>
      </section>
      <div class="split">
        <section>
          <div class="section-label">Color</div>
          <div class="stack" style="gap:8px">
            ${choice("Color", true, "var(--accent)")}
            ${choice("Black & White", false, "var(--ink-secondary)")}
          </div>
        </section>
        <section>
          <div class="section-label">Background</div>
          <div class="stack" style="gap:8px">
            ${choice("Soft studio", true, "var(--surface-muted)")}
            ${choice("Keep original", false, "var(--warning)")}
          </div>
        </section>
      </div>
      <div class="group-row">
        <div class="group-icon" aria-hidden="true">▾▾</div>
        <div>
          <strong>Group by person</strong>
          <div class="muted" style="font-size:12px">Puts photos of the same person together.</div>
        </div>
        <div class="toggle" role="switch" aria-checked="true" aria-label="Group by person"></div>
      </div>
    </div>`;
}

function framingCard(title, detail, selected, recommended) {
  return `<button class="card" type="button" aria-pressed="${selected}">
    <div class="card-art">
      ${recommended ? '<span class="pill">Recommended</span>' : ""}
      ${selected ? '<span class="check">✓</span>' : ""}
      ◻
    </div>
    <h3>${title}</h3>
    <p>${detail}</p>
  </button>`;
}

function choice(title, selected, swatch) {
  return `<button class="choice" type="button" aria-pressed="${selected}">
    <span class="swatch" style="background:${swatch}"></span>
    <strong>${title}</strong>
    <span class="mark">${selected ? "●" : "○"}</span>
  </button>`;
}

function renderProcessing() {
  pane.innerHTML = `
    <div class="stack">
      <div>
        <h1>Making headshots…</h1>
        <p class="sub">10 of 24 — tiles fill in as each one finishes.</p>
      </div>
      <div class="progress" role="progressbar" aria-valuenow="10" aria-valuemin="0" aria-valuemax="24"><i></i></div>
      <div class="grade-list">
        ${grade("PASS", "IMG_0418.JPG", "eyes at 42%")}
        ${grade("PASS", "IMG_0419.JPG", "")}
        ${grade("REVIEW", "IMG_0420.JPG", "eyes at 51% from the top, not 42%", true)}
      </div>
    </div>`;
}

function grade(label, file, why, review = false) {
  return `<div class="grade-row">
    <span class="dot ${review ? "review" : ""}"></span>
    <strong style="color:${review ? "var(--warning)" : "var(--success)"}">${label}</strong>
    <span class="mono">${file}</span>
    <span class="muted why">${why}</span>
  </div>`;
}

function renderResults() {
  pane.innerHTML = `
    <div class="stack">
      <div class="success-head">
        <div class="success-mark" aria-hidden="true">✓</div>
        <div>
          <h1>Your headshots are ready</h1>
          <p class="sub">24 polished, 0 unchanged — 21 pass, 3 review</p>
          <p class="sub" style="font-size:12px">5 people across 24 photos — grouped at cosine 0.55</p>
        </div>
      </div>
      <div class="grade-list">
        ${grade("PASS", "IMG_0418.JPG", "eyes at 42%")}
        ${grade("PASS", "IMG_0419.JPG", "")}
        ${grade("REVIEW", "IMG_0420.JPG", "eyes at 51% from the top, not 42%", true)}
        ${grade("PASS", "IMG_0421.JPG", "")}
      </div>
    </div>`;
}

function renderEmpty() {
  pane.innerHTML = `
    <div class="empty">
      <div style="font-size:28px;color:var(--ink-secondary)">▣</div>
      <h1 style="font-size:15px">No photos in this folder</h1>
      <p class="sub">Pick a folder with JPEGs, HEICs or PNGs at the top level. Subfolders are ignored.</p>
      ${btn("Choose another folder", { primary: true })}
    </div>`;
}

function renderError() {
  pane.innerHTML = `
    <div class="stack">
      <h1>How should we finish them?</h1>
      <div class="error" role="alert">
        <strong>Something stopped the run</strong>
        <div class="muted" style="margin:6px 0 12px">The headshots command is missing from this app. Build it with make app, or install it with pipx install headshots.</div>
        ${btn("Dismiss")}
      </div>
    </div>`;
}

function apply() {
  const screen = screenSelect.value;
  const theme = themeSelect.value;
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.screen = screen;
  const conf = SCREENS[screen];
  setStep(conf.step);
  conf.render();
  conf.actions();
  const url = new URL(location.href);
  url.searchParams.set("screen", screen);
  url.searchParams.set("theme", theme);
  history.replaceState(null, "", url);
}

if (params.get("chrome") === "0") document.body.classList.add("hide-chrome");
screenSelect.value = params.get("screen") || "welcome";
themeSelect.value = params.get("theme") || "light";
screenSelect.addEventListener("change", apply);
themeSelect.addEventListener("change", apply);
apply();
