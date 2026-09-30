/*
  Pastie's window. It draws what the presenter decided and does nothing clever
  (docs/UI-SPEC.md 5.5): every word, every fact and every rule comes from
  Python through window.pywebview.api. This file only arranges it.

  Everything shown is escaped. Sections are redrawn only when their data
  changes, so a status poll never throws away a choice somebody is making.
*/
"use strict";

const api = () => window.pywebview.api;
const $ = (id) => document.getElementById(id);
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

const RING = 2 * Math.PI * 54;
const POLL_MS = 3000;
const POLL_FAST_MS = 1000;
const STOP_CONFIRM_MS = 5000;

let poses = {};
let screen = null;
let view = "home";
let timer = null;
const drawn = {};                 // section id -> JSON last drawn
const choices = {};               // appliance id -> { programme, options }
let stopArmedUntil = 0;
let pokeClicks = [];
let shownPose = null;               // for the 200 ms crossfade between poses
let poked = null;

// ================================================================ start up

window.addEventListener("pywebviewready", async () => {
  poses = await api().poses();
  bindRail();
  bindWhy();
  await applyAppearance();
  const first = await api().onboarding();
  if (first.needed) startOnboarding(first.asides);
  tick();
});

async function tick() {
  try {
    screen = await api().screen();
    render();
  } catch (error) {
    console.error("screen failed", error);
  }
  clearTimeout(timer);
  const waiting = screen && screen.trail && ["requested", "accepted"].includes(screen.trail.outcome);
  timer = setTimeout(tick, waiting ? POLL_FAST_MS : POLL_MS);
}

function once(section, data, draw) {
  const json = JSON.stringify(data);
  if (drawn[section] === json) return;
  drawn[section] = json;
  draw();
}

// ================================================================ header and rail

function render() {
  const h = screen.header;
  const health = $("health");
  health.className = `health ${h.tone}`;
  health.querySelector(".words").textContent = h.words;
  $("guide-dot").hidden = !screen.guide_new;
  if (view === "home") renderHome();
  announce();
}

// One announcement per real change of state, from a node that is never redrawn.
let announced = "";
function announce() {
  const hero = screen && screen.hero;
  const text = hero ? `${hero.name}: ${hero.state_word}` : (screen && screen.connecting ? screen.connecting.line : "");
  if (text && text !== announced) {
    announced = text;
    $("live").textContent = text;
  }
}

function bindRail() {
  document.querySelectorAll(".rail-btn").forEach((button) => {
    button.addEventListener("click", () => show(button.dataset.view));
  });
}

async function show(name) {
  view = name;
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== `view-${name}`; });
  if (name === "home") { Object.keys(drawn).forEach((k) => delete drawn[k]); renderHome(); }
  if (name === "history") renderHistory(await api().history());
  if (name === "guide") renderGuide(await api().guide());
  if (name === "settings") renderSettings();
  if (name === "about") renderAbout(await api().about());
  if (name === "diagnostics") renderDiagnostics(await api().diagnostics());
}

// ================================================================ home

function renderHome() {
  if (!screen) return;
  const heading = $("caseload-heading");
  heading.hidden = !screen.caseload_heading || Boolean(screen.where);
  heading.textContent = screen.caseload_heading || "";

  once("caseload", screen.caseload, () => {
    const chips = screen.where ? [] : screen.caseload;  // one appliance is still one chip
    $("caseload").innerHTML = chips.map((c) => `
      <button class="chip ${c.state === "fault" ? "needs" : ""}" role="tab" aria-selected="${c.selected}" data-id="${esc(c.id)}">
        <img src="${esc(poses[c.pose] || "")}" alt="">
        <span>${esc(c.name)}</span>
        <span class="chip-state">${esc(c.state_word)}</span>
        ${c.unverified ? '<span class="stamp plainstamp">unverified</span>' : ""}
      </button>`).join("");
    $("caseload").querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", async () => { await api().pin(chip.dataset.id); tick(); });
    });
  });

  const home = $("home");
  if (screen.where) {
    once("home", { where: screen.where }, () => { home.innerHTML = whereHtml(screen.where); });
    return;
  }
  if (!screen.hero) {
    const c = screen.connecting || { line: "Connecting…", pose: "waiting" };
    once("home", { connecting: c }, () => {
      const image = c.crest ? "brand/crest.png" : (poses[c.pose] || "");
      home.innerHTML = `<div class="connecting"><img class="${c.crest ? "crest" : ""}" src="${esc(image)}" alt=""><p>${esc(c.line)}</p></div>`;
    });
    return;
  }
  if (drawn.home && !drawn.home.startsWith('{"hero"')) {
    home.innerHTML = "";
  }
  if (!home.querySelector("#hero-card")) {
    home.innerHTML = `
      <div id="connecting-line"></div>
      <div class="card" id="hero-card"><div id="hero-top"></div><div id="hero-actions" class="actions"></div></div>
      <div id="trail"></div>`;
    ["hero-top", "hero-actions", "trail", "connecting-line"].forEach((k) => delete drawn[k]);
  }
  drawn.home = '{"hero"}';
  const hero = screen.hero;
  once("connecting-line", screen.connecting, () => {
    $("connecting-line").innerHTML = screen.connecting ? `<p class="note">${esc(screen.connecting.line)}</p>` : "";
  });
  once("hero-top", { hero: { ...hero, actions: null }, poked }, () => { $("hero-top").innerHTML = heroHtml(hero); bindHero(hero); });
  once("hero-actions", { a: hero.actions, id: hero.id, state: hero.state }, () => { renderActions(hero); });
  once("trail", screen.trail, () => { $("trail").innerHTML = screen.trail ? trailHtml(screen.trail) : ""; });
}

function ringHtml(hero) {
  const progress = hero.facts.progress;
  const known = progress !== null && progress !== undefined;
  const offset = known ? RING * (1 - progress / 100) : 0;
  const state = !known && hero.state === "running" ? "unknown" : hero.state;
  return `
    <div class="ring ${esc(state)}">
      <svg viewBox="0 0 132 132" aria-hidden="true">
        <circle class="track" cx="66" cy="66" r="54"/>
        <circle class="fill" cx="66" cy="66" r="54" stroke-dasharray="${RING}" stroke-dashoffset="${known ? offset : RING}"/>
        ${known && hero.state === "running" ? `<circle class="glint" cx="66" cy="66" r="54" stroke-dasharray="6 ${RING}" stroke-dashoffset="${offset}"/>` : ""}
      </svg>
      <img class="pose" id="pose" src="${esc(poses[hero.pose] || "")}" alt="Pastie, ${esc(hero.pose)}">
    </div>`;
}

function heroHtml(hero) {
  const f = hero.facts;
  const known = f.progress !== null && f.progress !== undefined;
  const why = (key) => (hero.why && hero.why[key] ? `<button class="q" data-why="${key}" aria-label="Why does Pastie say this?">?</button>` : "");
  const lines = [];
  if (f.programme) lines.push(`<div>${esc(f.programme)}</div>`);
  if (f.completion) lines.push(`<div>Estimated completion ${esc(f.completion)} · ${esc(f.remaining)} · ${esc(f.confidence)}${why("remaining")}</div>`);
  else if (f.remaining) lines.push(`<div>${esc(f.remaining)} · ${esc(f.confidence)}${why("remaining")}</div>`);
  else if (f.confidence) lines.push(`<div>Still estimating</div>`);
  if (f.finished_at) lines.push(`<div>Finished at ${esc(f.finished_at)}${why("finished")}</div>`);
  else if (hero.why && hero.why.finished) lines.push(`<div>Finished${why("finished")}</div>`);
  const severe = ["warning", "error"].includes(hero.severity);
  for (const line of f.lines || []) lines.push(`<div class="plain ${severe ? "warn" : ""}">${esc(line)}${line.startsWith("State unknown") ? why("state") : ""}</div>`);
  for (const line of f.maintenance || []) lines.push(`<div class="muted">${esc(line)}</div>`);
  const meters = (hero.meters || []).map((m) => `
    <span class="m-label">${esc(m.label)}</span>
    <span class="m-bar"><span style="width:${Number(m.value)}%"></span></span>
    <span class="m-value">${Number(m.value)}</span>`).join("");
  return `
    <div class="hero">
      ${ringHtml(hero)}
      <div>
        <div class="${known ? "big" : "big unknown"}">${known ? `${Number(f.progress)}%` : (hero.state === "running" ? "Still estimating" : "")}</div>
      </div>
    </div>
    <p class="hero-name">${esc(hero.name)}<span class="stamps">${(hero.stamps || []).map((s) => `<span class="stamp plainstamp">${esc(s)}</span>`).join("")}</span></p>
    <div class="hero-model">${esc(hero.model)}</div>
    <div class="state-word state-${esc(hero.state)}">${esc(hero.state_word)}</div>
    <div class="facts">${lines.join("")}</div>
    ${hero.aside ? `<p class="aside">${esc(hero.aside)}</p>` : ""}
    ${poked ? `<p class="poked">${esc(poked)}</p>` : ""}
    ${meters ? `<div class="meters">${meters}</div>` : ""}`;
}

function bindHero(hero) {
  $("hero-top").querySelectorAll("[data-why]").forEach((b) => {
    b.addEventListener("click", () => openWhy(hero.why[b.dataset.why]));
  });
  const pose = $("pose");
  if (!pose) return;
  pose.addEventListener("click", onPoke);
  // A pose change is a 200 ms fade and nothing more (UI-SPEC 6.2).
  if (shownPose !== null && shownPose !== hero.pose) {
    pose.style.opacity = "0";
    requestAnimationFrame(() => requestAnimationFrame(() => { pose.style.opacity = "1"; }));
  }
  shownPose = hero.pose;
}

async function onPoke() {
  const now = Date.now();
  pokeClicks = pokeClicks.filter((t) => now - t < 1500).concat(now);
  if (pokeClicks.length < 3) return;
  pokeClicks = [];
  const line = await api().poke();
  if (!line) return;
  poked = line;
  renderHome();
  setTimeout(() => { poked = null; renderHome(); }, 8000);
}

// ================================================================ actions

function renderActions(hero) {
  const box = $("hero-actions");
  const a = hero.actions || { mode: "none" };
  if (a.mode === "not_armed") {
    box.innerHTML = `
      <button class="btn" disabled>${esc(a.button)}</button>
      <p class="note">${esc(a.fact)}</p>
      ${a.aside ? `<p class="aside">${esc(a.aside)}</p>` : ""}`;
    return;
  }
  if (a.mode === "stop") {
    const armed = Date.now() < stopArmedUntil;
    box.innerHTML = armed
      ? `<p>${esc(a.confirm)}</p><button class="btn danger" id="stop-yes">Stop it</button><button class="btn secondary" id="stop-no">Keep running</button>`
      : `<button class="btn secondary" id="stop">${esc(a.button)}</button>`;
    if (armed) {
      $("stop-yes").addEventListener("click", async () => { stopArmedUntil = 0; await api().stop(hero.id); tick(); });
      $("stop-no").addEventListener("click", () => { stopArmedUntil = 0; renderActions(hero); });
    } else {
      $("stop").addEventListener("click", () => {
        stopArmedUntil = Date.now() + STOP_CONFIRM_MS;
        renderActions(hero);
        setTimeout(() => { if (Date.now() >= stopArmedUntil) renderActions(hero); }, STOP_CONFIRM_MS + 50);
      });
    }
    return;
  }
  if (a.mode === "start") { renderStartPanel(hero, a.programmes || []); return; }
  box.innerHTML = "";
}

function renderStartPanel(hero, programmes) {
  const box = $("hero-actions");
  if (!programmes.length) { box.innerHTML = ""; return; }
  const mine = choices[hero.id] || (choices[hero.id] = { programme: programmes[0].id, options: {} });
  if (!programmes.some((p) => p.id === mine.programme)) mine.programme = programmes[0].id;
  const programme = programmes.find((p) => p.id === mine.programme);
  for (const s of programme.settings) {
    const ids = s.options.map((o) => o.id);
    if (!ids.includes(mine.options[s.key])) {
      const rec = s.options.find((o) => o.recommended) || s.options[0];
      mine.options[s.key] = rec ? rec.id : undefined;
    }
  }
  box.innerHTML = `
    <div class="label">START A CYCLE</div>
    <div class="tiles" role="radiogroup" aria-label="Programme">
      ${programmes.map((p) => `<button class="tile" role="radio" aria-checked="${p.id === mine.programme}" data-programme="${esc(p.id)}" tabindex="${p.id === mine.programme ? 0 : -1}">${esc(p.label)}</button>`).join("")}
    </div>
    ${programme.settings.map((s) => settingHtml(s, mine.options[s.key])).join("")}
    <div style="margin-top:12px"><button class="btn" id="start">${esc(programme.button)}</button></div>`;
  const tiles = [...box.querySelectorAll(".tile")];
  tiles.forEach((tile, i) => {
    tile.addEventListener("click", () => { mine.programme = tile.dataset.programme; renderStartPanel(hero, programmes); box.querySelector(`[data-programme="${CSS.escape(mine.programme)}"]`).focus(); });
    tile.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!step) return;
      e.preventDefault();
      const next = tiles[(i + step + tiles.length) % tiles.length];
      next.click();
    });
  });
  box.querySelectorAll(".segment").forEach((seg) => {
    seg.addEventListener("click", () => { mine.options[seg.dataset.key] = seg.dataset.value; renderStartPanel(hero, programmes); });
  });
  $("start").addEventListener("click", async () => {
    const options = {};
    for (const s of programme.settings) if (!s.fixed && mine.options[s.key]) options[s.key] = mine.options[s.key];
    $("start").disabled = true;
    await api().start(hero.id, programme.id, options);
    tick();
  });
}

function settingHtml(setting, chosen) {
  let body;
  if (setting.empty) body = `<span class="chip-fixed">${esc(setting.empty)}</span>`;
  else if (setting.fixed) body = `<span class="chip-fixed">${esc(setting.options[0].label)} (fixed)</span>`;
  else body = `<div class="segments" role="radiogroup" aria-label="${esc(setting.label)}">${setting.options.map((o) => `
      <button class="segment" role="radio" aria-checked="${o.id === chosen}" data-key="${esc(setting.key)}" data-value="${esc(o.id)}">${esc(o.label)}${o.recommended ? '<span class="star" title="Recommended">★</span>' : ""}</button>`).join("")}</div>`;
  return `<div class="setting-row"><span class="muted">${esc(setting.label)}</span>${body}</div>`;
}

// ================================================================ documents

function stampHtml(stamp) {
  if (!stamp) return "";
  const gold = ["CONFIRMED", "RECOVERED", "DELIVERED"].includes(stamp);
  return `<span class="stamp ${gold ? "gold" : ""}">${esc(stamp)}</span>`;
}

function trailHtml(trail) {
  const rows = trail.collapsed ? trail.rows.slice(-1) : trail.rows;
  const panel = trail.panel && !trail.collapsed ? `
    <div class="panel-title">${esc(trail.panel.title)}</div>
    ${trail.panel.rows.map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span><span></span></div>`).join("")}
    ${trail.panel.lines.map((l) => `<p>${esc(l)}</p>`).join("")}` : "";
  return `
    <div class="document trail" role="log" aria-label="${esc(trail.title)}">
      ${trail.collapsed ? "" : `<div class="doc-title">${esc(trail.title)}</div>`}
      ${rows.map((r) => `<div class="row"><span class="time">${esc(r.time)}</span><span>${esc(r.text)}</span>${stampHtml(r.stamp)}</div>`).join("")}
      ${panel}
    </div>`;
}

function whereHtml(where) {
  return `
    <div class="card where">
      <div class="label" style="color:var(--red)">${esc(where.title)}</div>
      <img src="${esc(where.crest ? "brand/crest.png" : (poses[where.pose] || ""))}" alt="" style="width:72px;height:72px;float:right">
      <div class="layers">${where.layers.map((l) => `<span>${esc(l.name)}</span><span class="${["WORKING", "CONNECTED"].includes(l.status) ? "" : "bad"}">${esc(l.status)}</span>`).join("")}</div>
      <div class="label">Try</div>
      <ul>${where.try.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
    </div>`;
}

function bindWhy() {
  $("why-close").addEventListener("click", closeWhy);
  $("why").addEventListener("click", (e) => { if (e.target === $("why")) closeWhy(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWhy(); });
}

let whyOpener = null;

function openWhy(why) {
  if (!why) return;
  whyOpener = document.activeElement;
  $("why-title").textContent = why.title;
  $("why-body").innerHTML = why.body.map((p) => `<p>${esc(p)}</p>`).join("");
  $("why-source").textContent = why.source;
  $("why-confidence").textContent = why.confidence;
  $("why").hidden = false;
  $("why-close").focus();
}

function closeWhy() {
  if ($("why").hidden) return;
  $("why").hidden = true;
  if (whyOpener && whyOpener.focus) whyOpener.focus();  // back where the reader was
}

// ================================================================ history

function renderHistory(h) {
  const el = $("view-history");
  el.innerHTML = `
    <h2>${esc(h.title)}</h2>
    ${h.subtitle ? `<p class="subtitle">${esc(h.subtitle)}</p>` : ""}
    ${h.cases.length ? `<div class="card"><div class="label">CASES</div>${h.cases.map((c, i) => `
      <div class="list-row"><span class="muted">${esc(c.opened.slice(0, 5))}</span>
        <button class="case-link" data-case="${i}">${esc(c.number)} · ${esc(c.programme || "")}</button>
        <span class="muted">${esc(c.title)}</span></div>`).join("")}</div>` : ""}
    <div id="case-open"></div>
    <div class="card">
      ${h.rows.length ? h.rows.map((r) => `
        <div class="list-row"><span class="muted">${esc(r.time)}</span>
          <span>${esc(r.text)}${r.detail ? `<div class="detail">${esc(r.detail)}</div>` : ""}</span>${stampHtml(r.stamp)}</div>`).join("") : `<p class="muted">${esc(h.empty)}</p>`}
    </div>`;
  el.querySelectorAll("[data-case]").forEach((b) => {
    b.addEventListener("click", () => { $("case-open").innerHTML = caseHtml(h.cases[Number(b.dataset.case)]); });
  });
}

function caseHtml(c) {
  return `
    <div class="document" style="margin-bottom:12px">
      <div class="case-head"><span>${esc(c.number)}</span><span>${esc(c.title)}</span></div>
      <div class="case-meta">
        <span>Opened</span><span>${esc(c.opened)}</span><span>Programme</span><span>${esc(c.programme || "")}</span>
        <span>Closed</span><span>${esc(c.closed || "open")}</span><span></span><span></span>
      </div>
      <div class="doc-title">EVIDENCE</div>
      ${c.evidence.map((r) => `<div class="row"><span class="time">${esc(r.time)}</span><span>${esc(r.text)}</span>${stampHtml(r.stamp)}</div>`).join("")}
      ${c.closing.length ? `<div class="closing">${c.closing.map((l) => `<div>${esc(l)}</div>`).join("")}</div>` : ""}
    </div>`;
}

// ================================================================ guide

function renderGuide(g) {
  const el = $("view-guide");
  const open = g.entries.filter((e) => e.unlocked);
  const locked = g.entries.filter((e) => !e.unlocked);
  const entry = (e) => `
    <button class="guide-entry ${e.unlocked ? "" : "locked"}" ${e.unlocked ? `data-key="${esc(e.key)}"` : "disabled"}>
      <div class="g-title">${esc(e.title)}${e.new ? '<span class="new-dot"></span>' : ""}</div>
      <div class="g-cond">${esc(e.condition)}</div>
    </button>`;
  el.innerHTML = `<h2>Guide</h2>
    <div class="label">UNLOCKED</div>${open.map(entry).join("")}
    ${locked.length ? `<div class="label" style="margin-top:14px">NOT YET</div>${locked.map(entry).join("")}` : ""}`;
  el.querySelectorAll("[data-key]").forEach((b) => {
    b.addEventListener("click", async () => {
      const e = g.entries.find((x) => x.key === b.dataset.key);
      await api().guide_seen(e.key);
      el.innerHTML = `
        <button class="link" id="guide-back">← Guide</button>
        <div class="card" style="margin-top:10px"><h2>${esc(e.title)}</h2>
          ${e.body ? `<p>${esc(e.body)}</p>` : `<p class="muted">${esc(e.condition)}</p>`}
          ${e.footnote ? `<div class="footnote">${esc(e.footnote)}</div>` : ""}</div>`;
      $("guide-back").addEventListener("click", async () => renderGuide(await api().guide()));
    });
  });
}

// ================================================================ about and diagnostics

function renderAbout(a) {
  const el = $("view-about");
  el.innerHTML = `
    <div class="card" style="text-align:center">
      <img class="about-crest" src="brand/crest.png" alt="The Pastie crest">
      <h2 style="margin-bottom:2px">${esc(a.name)}</h2>
      <div class="muted">Version ${esc(a.version)} · ${esc(a.licence)} licence</div>
      ${a.institution ? `<p style="margin-bottom:0"><strong>${esc(a.institution)}</strong></p><p class="muted" style="margin-top:2px">${esc(a.institution_note)}</p>` : ""}
      <p class="muted">${esc(a.unofficial)}</p>
    </div>
    ${a.org_chart.length ? `<div class="card"><div class="label">${esc(a.division)}</div>
      <div class="org">${a.org_chart.map(([r, d]) => `<span class="role">${esc(r)}</span><span>${esc(d)}</span>`).join("")}</div></div>` : ""}
    <div class="card">
      <button class="link" data-link="${esc(a.repository)}">Source code</button> ·
      <button class="link" data-link="${esc(a.changelog)}">${esc(a.changelog_label)}</button> ·
      <button class="link" id="to-diagnostics">Diagnostics</button>
    </div>`;
  el.querySelectorAll("[data-link]").forEach((b) => b.addEventListener("click", () => api().open_link(b.dataset.link)));
  $("to-diagnostics").addEventListener("click", () => show("diagnostics"));
}

function renderDiagnostics(d) {
  const el = $("view-diagnostics");
  el.innerHTML = `
    <button class="link" id="diag-back">← About</button>
    <h2 style="margin-top:10px">Diagnostics</h2>
    ${d.sections.map((s) => `<div class="card"><div class="label">${esc(s.title)}</div>
      ${s.rows.length ? s.rows.map(([k, v]) => `<div class="list-row" style="grid-template-columns:1fr auto"><span>${esc(k)}</span><span class="muted">${esc(v)}</span></div>`).join("") : '<p class="muted">Nothing.</p>'}</div>`).join("")}`;
  $("diag-back").addEventListener("click", () => show("about"));
}

// ================================================================ settings

async function renderSettings() {
  const el = $("view-settings");
  el.innerHTML = `<h2>Settings</h2><p class="muted">Asking the service…</p>`;
  const [s, appearance] = await Promise.all([api().settings(), api().appearance()]);
  el.innerHTML = `<h2>Settings</h2>
    <div class="card" id="account-card"></div>
    <div class="label" style="margin-top:4px">NOTIFICATIONS</div>
    <div id="messenger-cards"></div>
    <div class="label" style="margin-top:4px">PERSONALITIES</div>
    <div id="personality-cards"><p class="muted">Gathering the cast…</p></div>
    <div class="card" id="appearance-card"></div>`;
  renderAccount(s);
  renderAppearance(appearance);
  renderPersonalities();
  if (!s.ok) {
    $("messenger-cards").innerHTML = `<div class="card"><p class="result bad">The service isn't answering, so there's nothing to show here yet. ${esc(s.error)}</p></div>`;
    return;
  }
  $("messenger-cards").innerHTML = s.messengers.map((m) => `<div class="card" data-messenger="${esc(m.name)}"></div>`).join("");
  for (const m of s.messengers) renderMessenger(m, s.values[m.name] || {}, s.overrides_key);
}

function renderAccount(s) {
  const card = $("account-card");
  card.innerHTML = `
    <div class="label">HON ACCOUNT</div>
    <p class="muted">The service encrypts this with Windows DPAPI under the Windows account running it (yours, as it starts at sign-in), so the file is useless on any other account or PC. It is never stored here, and it cannot be read back out.</p>
    <p>${s.ok && s.account ? "An account is saved." : (s.ok ? "No account saved." : "")}</p>
    <div class="field"><label for="acct-user">Email</label><input type="text" id="acct-user" autocomplete="off"></div>
    <div class="field"><label for="acct-pass">Password</label><input type="password" id="acct-pass" autocomplete="off"></div>
    <button class="btn secondary" id="acct-save">Save account</button>
    <div class="result" id="acct-result"></div>`;
  $("acct-save").addEventListener("click", async () => {
    const r = await api().set_account($("acct-user").value, $("acct-pass").value);
    $("acct-pass").value = "";
    const out = $("acct-result");
    out.className = `result ${r.ok ? "good" : "bad"}`;
    out.textContent = r.ok ? (r.restart_needed ? "Saved. The service will use it after a restart." : "Saved.") : r.error;
  });
}

function renderMessenger(m, saved, overridesKey) {
  const card = document.querySelector(`[data-messenger="${CSS.escape(m.name)}"]`);
  const fields = m.settings.map((s) => fieldHtml(m.name, s, saved)).join("");
  const varying = m.settings.filter((s) => s.per_event);
  const stored = saved[overridesKey] || {};
  const overrides = varying.length && m.alerts.length ? `
    <div class="overrides"><div class="label" style="margin-top:6px">DIFFERENT FOR…</div>
      <table><tr><th>Alert</th>${varying.map((s) => `<th>${esc(s.label)}</th>`).join("")}</tr>
      ${m.alerts.map((a) => `<tr><td>${esc(a.label)}</td>${varying.map((s) => `<td>${overrideHtml(a.kind, s, (stored[a.kind] || {})[s.key])}</td>`).join("")}</tr>`).join("")}
      </table></div>` : "";
  const hasTarget = m.settings.some((s) => s.kind === "target");
  card.innerHTML = `
    <div class="card-head"><div class="label" style="margin:0">${esc(m.label.toUpperCase())}</div></div>
    ${fields}${overrides}
    <div style="margin-top:12px">
      <button class="btn secondary" data-act="save">Save</button>
      <button class="btn secondary" data-act="test">Test</button>
      ${hasTarget ? '<button class="btn secondary" data-act="find">Find</button>' : ""}
    </div>
    <div class="result" data-result></div>`;
  const result = card.querySelector("[data-result]");
  const say = (good, text) => { result.className = `result ${good ? "good" : "bad"}`; result.textContent = text; };
  card.querySelector('[data-act="save"]').addEventListener("click", async () => {
    const values = collect(card, m, overridesKey);
    const r = await api().save_messenger(m.name, values);
    say(r.ok, r.ok ? "Saved." : r.error);
  });
  card.querySelector('[data-act="test"]').addEventListener("click", async () => {
    say(true, "Testing…");
    const r = await api().test_messenger(m.name);
    if (!r.ok) return say(false, r.error);
    say(r.worked, r.worked ? `${r.detail}${r.aside ? ` ${r.aside}` : ""}` : r.detail);
  });
  const find = card.querySelector('[data-act="find"]');
  const discover = async () => {
    const r = await api().discover(m.name);
    if (!r.ok) return say(false, r.error);
    const select = card.querySelector("select[data-target]");
    if (!select) return;
    const current = select.dataset.current || "";
    select.innerHTML = r.targets.length
      ? r.targets.map((t) => `<option value="${esc(t.id)}" ${t.id === current ? "selected" : ""}>${esc(t.label)}${t.detail ? ` (${esc(t.detail)})` : ""}</option>`).join("")
      : '<option value="">nothing found</option>';
  };
  if (find) find.addEventListener("click", discover);
  if (hasTarget && (saved.enabled || saved.address)) discover();
}

function fieldHtml(messenger, s, saved) {
  const value = saved[s.key] ?? s.default;
  const id = `f-${messenger}-${s.key}`;
  const help = s.help ? `<div class="help">${esc(s.help)}</div>` : "";
  if (s.kind === "bool") return `<label class="check"><input type="checkbox" data-key="${esc(s.key)}" ${value ? "checked" : ""}> ${esc(s.label)}</label>${help ? `<div class="help" style="margin-left:23px">${esc(s.help)}</div>` : ""}`;
  let input;
  if (s.kind === "choice") input = `<select id="${esc(id)}" data-key="${esc(s.key)}">${(s.choices || []).map((c) => `<option ${String(c) === String(value) ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  else if (s.kind === "target") input = `<select id="${esc(id)}" data-key="${esc(s.key)}" data-target data-current="${esc(value ?? "")}"><option value="${esc(value ?? "")}">${value ? "(finding…)" : ""}</option></select>`;
  else input = `<input id="${esc(id)}" type="${s.kind === "secret" ? "password" : "text"}" data-key="${esc(s.key)}" value="${esc(value ?? "")}" autocomplete="off">`;
  return `<div class="field"><label for="${esc(id)}">${esc(s.label)}</label>${input}${help}</div>`;
}

function overrideHtml(kind, s, value) {
  if (s.kind === "choice") return `<select data-override="${esc(kind)}" data-key="${esc(s.key)}"><option value="">(default)</option>${(s.choices || []).map((c) => `<option ${String(c) === String(value ?? "") ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  return `<input type="text" data-override="${esc(kind)}" data-key="${esc(s.key)}" value="${esc(value ?? "")}" placeholder="(default)">`;
}

function collect(card, m, overridesKey) {
  const values = {};
  card.querySelectorAll("[data-key]:not([data-override])").forEach((input) => {
    values[input.dataset.key] = input.type === "checkbox" ? input.checked : input.value;
  });
  const overrides = {};
  card.querySelectorAll("[data-override]").forEach((input) => {
    if (input.value === "") return;
    (overrides[input.dataset.override] ||= {})[input.dataset.key] = input.value;
  });
  values[overridesKey] = overrides;
  return values;
}

function renderAppearance(a) {
  const card = $("appearance-card");
  const levels = a.examples || [];
  card.innerHTML = `
    <div class="label">APPEARANCE</div>
    <div class="muted" style="margin-bottom:4px">Personality</div>
    ${levels.map((l) => `<label class="option-block"><input type="radio" name="level" value="${esc(l.level)}" ${l.level === a.level ? "checked" : ""}> <strong>${esc(l.title)}</strong>${l.level === "dry" ? " (default)" : ""}<span class="example">${esc(l.example)}</span></label>`).join("")}
    <div class="field"><label for="theme">Theme</label><select id="theme">
      ${[["system", "Follow Windows"], ["dark", "Dark"], ["light", "Light"]].map(([v, t]) => `<option value="${v}" ${v === a.theme ? "selected" : ""}>${t}</option>`).join("")}</select></div>
    <div class="field"><label for="motion">Reduce motion</label><select id="motion">
      ${[["system", "Follow Windows"], ["on", "On"]].map(([v, t]) => `<option value="${v}" ${v === a.reduce_motion ? "selected" : ""}>${t}</option>`).join("")}</select></div>`;
  const save = async () => {
    const level = card.querySelector('input[name="level"]:checked')?.value || a.level;
    const next = await api().set_appearance(level, $("theme").value, $("motion").value);
    await applyAppearance(next);
    Object.keys(drawn).forEach((k) => delete drawn[k]);
  };
  card.querySelectorAll("input, select").forEach((el) => el.addEventListener("change", save));
}

async function applyAppearance(given) {
  const a = given || (await api().appearance());
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = a.theme === "system" ? (dark ? "dark" : "light") : a.theme;
  document.documentElement.dataset.theme = theme;
  document.body.classList.toggle("reduce-motion", a.reduce_motion === "on");
  api().title_bar(theme === "dark");
}

// ================================================================ personalities
//
// docs/UI-SPEC.md 7.9 and UI-SCREENS 7.3. Everything configurable here is
// presentation: no setting can change a fact, a stamp, a pose's link to real
// state, or the plainness of anything needing action. Python enforces that;
// this only draws the editor.

let cast = null;

async function renderPersonalities() {
  cast = await api().personalities();
  const box = $("personality-cards");
  box.innerHTML = cast.cards.map((c) => `<div class="card personality" data-card="${esc(c.key)}"></div>`).join("");
  cast.cards.forEach(drawCard);
}

function optionsHtml(values, chosen, labels) {
  return values.map((v) => `<option value="${esc(v)}" ${v === chosen ? "selected" : ""}>${esc((labels && labels[v]) || v)}</option>`).join("");
}

const LEVEL_LABELS = { follow: "Follow the global level", plain: "Plain", dry: "Dry", departmental: "Departmental" };

function drawCard(card) {
  const el = document.querySelector(`[data-card="${CSS.escape(card.key)}"]`);
  const isAppliance = card.kind === "appliance";
  const meters = isAppliance ? [0, 1, 2].map((i) => {
    const m = card.meters[i] || { label: "", curve: "rising" };
    return `<div class="meter-edit"><input type="text" data-meter-label="${i}" value="${esc(m.label)}" placeholder="(shipped meter)">
      <select data-meter-curve="${i}">${optionsHtml(cast.curves, m.curve)}</select></div>`;
  }).join("") : "";
  el.innerHTML = `
    <div class="card-head">
      <div class="label" style="margin:0">${esc(card.title.toUpperCase())}</div>
      <span>${card.customised ? '<span class="stamp gold">yours</span>' : ""}</span>
    </div>
    ${!card.verified ? '<p class="note">Takes effect once this appliance is verified. Until then Pastie declines to characterise it.</p>' : ""}
    <div class="field"><label>Name</label><input type="text" data-f="name" value="${esc(card.name)}" maxlength="60"></div>
    ${isAppliance ? `
      <div class="field"><label>Temperament</label><select data-f="temperament">${optionsHtml(cast.temperaments, card.temperament)}</select></div>
      <div class="field"><label>Pastie's stance</label><select data-f="stance">${optionsHtml(cast.stances, card.stance)}</select></div>
      <div class="field"><label>Personality</label><select data-f="level">${optionsHtml(cast.levels, card.level, LEVEL_LABELS)}</select></div>
      <div class="field"><label>Speech</label><span class="muted">Needs a service change first (off)</span></div>
      <div class="muted" style="margin:10px 0 4px">Meters (Departmental). Leave blank for the programme's own.</div>
      ${meters}` : ""}
    <div class="muted" style="margin:12px 0 4px">Lines</div>
    <div class="pools">${card.pools.map((p) => `
      <div class="pool-row"><span>${esc(p.label)}</span>
        <span class="muted">${p.shipped} shipped · ${p.yours} yours${p.disabled ? ` · ${p.disabled} off` : ""}${p.replace ? " · yours only" : ""}</span>
        <button class="link" data-edit-pool="${esc(p.pool)}">Edit</button></div>`).join("")}
      ${isAppliance ? '<div class="pool-row muted"><span>Faults and a full tank</span><span>Plain by rule, and not editable</span><span></span></div>' : ""}
    </div>
    <div class="pool-editor" data-pool-editor hidden></div>
    <div class="preview-box">
      <div class="muted">Preview
        <select data-preview-state>${optionsHtml(cast.states, card.key === "pastie" ? "idle" : "running")}</select>
        <select data-preview-level>${optionsHtml(["departmental", "dry", "plain"], "departmental")}</select></div>
      <div class="preview" data-preview></div>
    </div>
    <div style="margin-top:12px">
      <button class="btn secondary" data-act="save">Save</button>
      <button class="btn secondary" data-act="reset">Reset to default</button>
      <button class="btn secondary" data-act="export">Export pack…</button>
      <button class="btn secondary" data-act="import">Import pack…</button>
    </div>
    <div class="result" data-result></div>`;

  const result = el.querySelector("[data-result]");
  const say = (good, text) => { result.className = `result ${good ? "good" : "bad"}`; result.textContent = text; };
  const collectSheet = () => {
    const data = { title: card.title, meters: [] };
    el.querySelectorAll("[data-f]").forEach((f) => { data[f.dataset.f] = f.value; });
    el.querySelectorAll("[data-meter-label]").forEach((input) => {
      const i = input.dataset.meterLabel;
      const curve = el.querySelector(`[data-meter-curve="${i}"]`).value;
      if (input.value.trim()) data.meters.push({ label: input.value.trim(), curve });
    });
    return data;
  };
  const preview = async () => {
    const hero = await api().preview(card.key, el.querySelector("[data-preview-state]").value,
      el.querySelector("[data-preview-level]").value, collectSheet());
    el.querySelector("[data-preview]").innerHTML = previewHtml(hero);
  };
  el.querySelectorAll("[data-f], [data-meter-label], [data-meter-curve], [data-preview-state], [data-preview-level]")
    .forEach((f) => f.addEventListener("change", preview));
  preview();

  el.querySelector('[data-act="save"]').addEventListener("click", async () => {
    const saved = await api().save_personality(card.key, collectSheet());
    Object.assign(card, saved, { title: card.title, verified: card.verified });
    drawCard(card);
    Object.keys(drawn).forEach((k) => delete drawn[k]);
    const again = document.querySelector(`[data-card="${CSS.escape(card.key)}"] [data-result]`);
    again.className = "result good"; again.textContent = "Saved.";
  });
  el.querySelector('[data-act="reset"]').addEventListener("click", async () => {
    await api().reset_personality(card.key, null);
    Object.keys(drawn).forEach((k) => delete drawn[k]);
    renderPersonalities();
  });
  el.querySelector('[data-act="export"]').addEventListener("click", async () => {
    const r = await api().export_pack(card.key);
    if (r.cancelled) return;
    say(r.ok, r.ok ? `Saved to ${r.path}` : r.error);
  });
  el.querySelector('[data-act="import"]').addEventListener("click", async () => {
    const r = await api().import_pack(card.key);
    if (r.cancelled) return;
    if (!r.ok) return say(false, r.error);
    await renderPersonalities();
    const again = document.querySelector(`[data-card="${CSS.escape(card.key)}"] [data-result]`);
    again.className = "result good";
    again.textContent = r.dropped.length ? `Imported. Left out: ${r.dropped.join("; ")}` : "Imported.";
  });
  el.querySelectorAll("[data-edit-pool]").forEach((b) => b.addEventListener("click", () => openPool(card, b.dataset.editPool, el)));
}

function previewHtml(hero) {
  const f = hero.facts || {};
  const meters = (hero.meters || []).map((m) => `
    <span class="m-label">${esc(m.label)}</span><span class="m-bar"><span style="width:${Number(m.value)}%"></span></span><span class="m-value">${Number(m.value)}</span>`).join("");
  return `
    <div class="preview-head"><img src="${esc(poses[hero.pose] || "")}" alt=""><div>
      <div class="state-word state-${esc(hero.state)}" style="font-size:15px;margin:0">${esc(hero.state_word)}</div>
      <div class="muted">${esc(f.programme || "")}${f.remaining ? ` · ${esc(f.remaining)}` : ""}</div></div></div>
    ${hero.aside ? `<p class="aside">${esc(hero.aside)}</p>` : '<p class="muted">(no remark at this level)</p>'}
    ${meters ? `<div class="meters">${meters}</div>` : ""}`;
}

async function openPool(card, pool, el) {
  const editor = el.querySelector("[data-pool-editor]");
  const data = await api().personality_pool(card.key, pool);
  const added = [...data.added];
  const draw = () => {
    editor.hidden = false;
    editor.innerHTML = `
      <div class="label">${esc(data.label.toUpperCase())}</div>
      <label class="check"><input type="checkbox" data-replace ${data.replace ? "checked" : ""}> Use only my lines</label>
      ${data.shipped.map((l, i) => `<label class="check line"><input type="checkbox" data-ship="${i}" ${l.disabled ? "" : "checked"}> <span>${esc(l.text)}</span></label>`).join("")}
      <div class="muted" style="margin-top:8px">Your lines</div>
      ${added.map((l, i) => `<div class="own-line"><span>${esc(l)}</span><button class="link" data-remove="${i}">Remove</button></div>`).join("") || '<p class="muted">None yet.</p>'}
      <div class="field" style="grid-template-columns:1fr auto"><input type="text" data-new placeholder="Use {name} for the appliance, {household} for the humans"><button class="btn secondary" data-add>Add</button></div>
      <div class="result" data-check></div>
      <button class="btn" data-save-pool>Save lines</button>
      <button class="btn secondary" data-reset-pool>Reset these lines</button>
      <button class="btn secondary" data-close-pool>Close</button>`;
    const input = editor.querySelector("[data-new]");
    const out = editor.querySelector("[data-check]");
    let timer = null;
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        if (!input.value.trim()) { out.textContent = ""; return; }
        const c = await api().check_line(pool, input.value);
        out.className = `result ${c.ok ? (c.warnings.length ? "" : "good") : "bad"}`;
        out.textContent = c.ok ? (c.warnings.join(" ") || "Looks fine.") : c.refused;
      }, 250);
    });
    editor.querySelector("[data-add]").addEventListener("click", async () => {
      const c = await api().check_line(pool, input.value);
      if (!c.ok) { out.className = "result bad"; out.textContent = c.refused; return; }
      added.push(input.value.trim());
      draw();
    });
    editor.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => { added.splice(Number(b.dataset.remove), 1); draw(); }));
    editor.querySelectorAll("[data-ship]").forEach((b) => b.addEventListener("change", () => { data.shipped[Number(b.dataset.ship)].disabled = !b.checked; }));
    editor.querySelector("[data-replace]").addEventListener("change", (e) => { data.replace = e.target.checked; });
    editor.querySelector("[data-save-pool]").addEventListener("click", async () => {
      const disabled = data.shipped.filter((l) => l.disabled).map((l) => l.text);
      const r = await api().save_pool(card.key, pool, disabled, added, data.replace);
      editor.hidden = true;
      await renderPersonalities();
      const again = document.querySelector(`[data-card="${CSS.escape(card.key)}"] [data-result]`);
      again.className = `result ${r.refused.length ? "bad" : "good"}`;
      again.textContent = r.refused.length ? `Saved, except: ${r.refused.join("; ")}` : "Lines saved.";
    });
    editor.querySelector("[data-reset-pool]").addEventListener("click", async () => {
      await api().reset_personality(card.key, pool);
      editor.hidden = true;
      renderPersonalities();
    });
    editor.querySelector("[data-close-pool]").addEventListener("click", () => { editor.hidden = true; });
  };
  draw();
}

// ================================================================ first run
//
// UI-SCREENS 8. Four steps; buttons literal; supporting lines only above Plain;
// the account step always plain; the thumbs-up only on a real delivery.

async function startOnboarding(asides) {
  const el = $("view-onboarding");
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v !== el; });
  document.querySelectorAll(".rail-btn").forEach((b) => b.classList.remove("active"));
  const steps = (n) => `<div class="steps" aria-label="Step ${n} of 4">${[1, 2, 3, 4].map((i) => `<span class="${i <= n ? "done" : ""}"></span>`).join("")}</div>`;
  const aside = (key) => (asides && asides[key] ? `<p class="aside">${esc(asides[key])}</p>` : "");
  const finish = () => { el.hidden = true; show("home"); };

  const account = () => {
    el.innerHTML = `${steps(1)}
      <div class="card">
        <img class="onboard-crest" src="brand/crest.png" alt="The Pastie crest">
        <h2>Connect your Haier account</h2>
        <p class="muted">The service encrypts this with Windows DPAPI under the Windows account running it (yours, as it starts at sign-in), so the file is useless on any other account or PC. It is never stored here, and it cannot be read back out.</p>
        <div class="field"><label for="ob-user">Email</label><input type="text" id="ob-user" autocomplete="off"></div>
        <div class="field"><label for="ob-pass">Password</label><input type="password" id="ob-pass" autocomplete="off"></div>
        <button class="btn" id="ob-connect">Connect</button>
        <div class="result" id="ob-result"></div>
      </div>`;
    $("ob-user").focus();
    $("ob-connect").addEventListener("click", async () => {
      const r = await api().set_account($("ob-user").value, $("ob-pass").value);
      $("ob-pass").value = "";
      if (!r.ok) { $("ob-result").className = "result bad"; $("ob-result").textContent = r.error; return; }
      appliances(r.restart_needed);
    });
  };

  const appliances = (restart) => {
    el.innerHTML = `${steps(2)}
      <div class="card"><h2>Finding appliances…</h2>${aside("appliances")}
        ${restart ? '<p class="note">The background service will use this account once it restarts.</p>' : ""}
        <div id="ob-list"><p class="muted">Asking Haier…</p></div>
        <button class="btn" id="ob-next" disabled>Continue</button></div>`;
    const poll = async () => {
      if (el.hidden || !$("ob-list")) return;
      const s = await api().screen();
      if (s.caseload && s.caseload.length) {
        $("ob-list").innerHTML = s.caseload.map((c) => `
          <div class="appliance-row"><span>${esc(c.name)}</span>
            <span>${esc(c.state_word)}${c.unverified ? ' <span class="stamp plainstamp">unverified</span>' : ""}</span></div>`).join("");
        $("ob-next").disabled = false;
      } else if (s.where) {
        $("ob-list").innerHTML = whereHtml(s.where);
        setTimeout(poll, 3000);
      } else {
        setTimeout(poll, 2000);
      }
    };
    $("ob-next").addEventListener("click", messengers);
    poll();
  };

  const messengers = async () => {
    el.innerHTML = `${steps(3)}
      <div class="card"><h2>Choose how Pastie tells you things</h2>${aside("messengers")}</div>
      <div id="ob-messengers"></div>
      <button class="btn" id="ob-next">Continue</button>`;
    const s = await api().settings();
    if (s.ok) {
      $("ob-messengers").innerHTML = s.messengers.map((m) => `<div class="card" data-messenger="${esc(m.name)}"></div>`).join("");
      for (const m of s.messengers) renderMessenger(m, s.values[m.name] || {}, s.overrides_key);
    }
    $("ob-next").addEventListener("click", () => test(s.ok ? s.messengers : []));
  };

  const test = (list) => {
    el.innerHTML = `${steps(4)}
      <div class="card"><h2>Send a test</h2>
        <img id="ob-pose" src="${esc(poses.normal || "")}" alt="" style="width:96px;height:96px">
        <div class="field"><label for="ob-which">Messenger</label><select id="ob-which">${list.map((m) => `<option value="${esc(m.name)}">${esc(m.label)}</option>`).join("")}</select></div>
        <button class="btn" id="ob-send" ${list.length ? "" : "disabled"}>Send a test</button>
        <div class="result" id="ob-result"></div>
        <div style="margin-top:14px"><button class="btn secondary" id="ob-done">Finish</button></div></div>`;
    $("ob-send").addEventListener("click", async () => {
      const r = await api().test_messenger($("ob-which").value);
      const worked = r.ok && r.worked;
      $("ob-pose").src = poses[worked ? "confirmed" : "fault"] || "";   // thumbs-up only on a real delivery
      $("ob-result").className = `result ${worked ? "good" : "bad"}`;
      $("ob-result").textContent = worked ? `${r.detail}${asides && asides.tested ? ` ${asides.tested}` : ""}` : (r.error || r.detail);
    });
    $("ob-done").addEventListener("click", finish);
  };

  account();
}
