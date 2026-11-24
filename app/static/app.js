/* PostOp - painel (JS puro, sem build) */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { me: null, settings: null, themes: null, styles: null, timer: null, queueTimer: null, videos: [] };

/* ------------------------------------------------------------ ícones (traço 1.75, 24x24) */
const ICONS = {
  home: '<path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v11.5h13V9"/><path d="M10 20.5v-6h4v6"/>',
  scissors: '<circle cx="6" cy="6.5" r="2.75"/><circle cx="6" cy="17.5" r="2.75"/><path d="M8.3 8.1 20 19"/><path d="M8.3 15.9 20 5"/>',
  cube: '<path d="M12 2.75 20.25 7.25v9.5L12 21.25 3.75 16.75v-9.5z"/><path d="M3.75 7.25 12 11.75l8.25-4.5"/><path d="M12 11.75v9.5"/>',
  film: '<rect x="3.5" y="3.5" width="17" height="17" rx="3.5"/><path d="M10 8.75v6.5l5.5-3.25z"/>',
  pulse: '<path d="M3 12h3.5l2.5-6.5 4.5 13 2.75-6.5H21"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
  book: '<path d="M5 5.5A2 2 0 0 1 7 3.5h12v13.5H7a2 2 0 0 0-2 2z"/><path d="M5 19a1.5 1.5 0 0 0 1.5 1.5H19"/>',
  send: '<path d="M20.5 3.5 10 14"/><path d="M20.5 3.5 14 20.5l-4-6.5-6.5-4z"/>',
  logout: '<path d="M9.5 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h3.5"/><path d="M15.5 16.5 20 12l-4.5-4.5"/><path d="M20 12H9.5"/>',
  edit: '<path d="M4 20h4.5L19.25 9.25a2.1 2.1 0 0 0-3-3L5.5 17v3"/><path d="M14.5 8l2.5 2.5"/>',
  download: '<path d="M12 4v11"/><path d="M7.5 11 12 15.5l4.5-4.5"/><path d="M5 20h14"/>',
  trash: '<path d="M4.5 7h15"/><path d="M9.5 7V4.5h5V7"/><path d="M6.5 7l.9 12.5a1 1 0 0 0 1 .9h7.2a1 1 0 0 0 1-.9L17.5 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  check: '<path d="M5 12.5 9.5 17 19 7.5"/>',
  retry: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
  eye: '<path d="M2.75 12S6.25 5.5 12 5.5 21.25 12 21.25 12 17.75 18.5 12 18.5 2.75 12 2.75 12z"/><circle cx="12" cy="12" r="2.75"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1"/>',
  sparkle: '<path d="M12 3.5l1.7 4.8 4.8 1.7-4.8 1.7L12 16.5l-1.7-4.8L5.5 10l4.8-1.7z"/><path d="M18.5 15.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/>',
  music: '<path d="M9 18V5.5l11-2V16"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  copy: '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2.5"/><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  arrow: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  coin: '<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.5c-.4-.9-1.3-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.2 0-2.1-.6-2.5-1.5"/><path d="M12 6.5V8M12 16v1.5"/>',
  user: '<circle cx="12" cy="8.5" r="3.75"/><path d="M4.5 20.5c1.3-3.6 4.2-5.5 7.5-5.5s6.2 1.9 7.5 5.5"/>',
  crop: '<path d="M6.5 2.5v13a2 2 0 0 0 2 2h13"/><path d="M17.5 21.5v-13a2 2 0 0 0-2-2h-13"/>',
  frame: '<rect x="7.5" y="3" width="9" height="18" rx="2"/><path d="M3.5 7v10M20.5 7v10"/>',
  captions: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 12.5h3.5M13 12.5h4M7 15.5h6.5"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5S9.7 5.9 12 3.5z"/>',
  key: '<circle cx="8" cy="15.5" r="3.75"/><path d="M10.7 12.8 19.5 4M16.5 7l2.5 2.5M14 9.5l2 2"/>',
  alert: '<path d="M10.3 4.3 2.9 17.5A2 2 0 0 0 4.6 20.5h14.8a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2.5"/><path d="M9.5 2.5V6M14.5 2.5V6M9.5 18v3.5M14.5 18v3.5M2.5 9.5H6M2.5 14.5H6M18 9.5h3.5M18 14.5h3.5"/>',
  phone: '<rect x="6.5" y="2.5" width="11" height="19" rx="2.75"/><path d="M11 18.25h2"/>',
  wand: '<path d="M4 20 14.5 9.5"/><path d="M13 8l3 3"/><path d="M17 3.5v2M20.5 7h-2M19.5 4.5 18 6M8 3.5v2M10 4.5H6"/>',
  image: '<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><circle cx="9" cy="9" r="1.75"/><path d="M20.5 15.5 16 11l-9 9.5"/>',
  layers: '<path d="M12 3.5 21 8l-9 4.5L3 8z"/><path d="M3 12.5l9 4.5 9-4.5"/><path d="M3 16.5l9 4.5 9-4.5"/>',
  external: '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
  /* temas */
  free: '<path d="M4 20h4.5L19.25 9.25a2.1 2.1 0 0 0-3-3L5.5 17v3"/><path d="M14.5 8l2.5 2.5"/>',
  bulb: '<path d="M9.5 18h5M10.5 21h3"/><path d="M12 3a6 6 0 0 0-3.7 10.7c.7.6 1.2 1.4 1.2 2.3v.5h5V16c0-.9.5-1.7 1.2-2.3A6 6 0 0 0 12 3z"/>',
  ghost: '<path d="M5.5 20.5V10a6.5 6.5 0 0 1 13 0v10.5l-2.2-1.5-2.1 1.5-2.2-1.5-2.2 1.5-2.1-1.5z"/><path d="M9.75 10.25v.5M14.25 10.25v.5"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  leaf: '<path d="M4.5 19.5C5 10.5 10 4.5 20 4c-.5 10-6.5 15-15.5 15.5z"/><path d="M4.5 19.5 13.5 10.5"/>',
  bolt: '<path d="M13.5 2.5 5 13.5h6.5l-1 8 8.5-11h-6.5z"/>',
  hourglass: '<path d="M6.5 3.5h11M6.5 20.5h11"/><path d="M7.5 3.5c0 4.5 9 5 9 8.5s-9 4-9 8.5"/><path d="M16.5 3.5c0 4.5-9 5-9 8.5s9 4 9 8.5"/>',
  planet: '<circle cx="12" cy="12" r="5.75"/><path d="M7.2 15.3c-2.8 1.8-4.2 3.5-3.6 4.4.9 1.6 6.3-.4 11.9-4.2s9.2-8.1 8.3-9.7c-.5-.9-2.4-.8-4.9.2" transform="translate(-1.6 -.4)"/>',
  paw: '<circle cx="6.5" cy="10.5" r="1.75"/><circle cx="10" cy="6.5" r="1.75"/><circle cx="14" cy="6.5" r="1.75"/><circle cx="17.5" cy="10.5" r="1.75"/><path d="M12 12.5c-2.9 0-5.25 3-5.25 5.3 0 1.5 1.1 2.2 2.5 2.2.9 0 1.8-.5 2.75-.5s1.85.5 2.75.5c1.4 0 2.5-.7 2.5-2.2 0-2.3-2.35-5.3-5.25-5.3z"/>',
  question: '<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.6a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1.1.9-1.1 1.6v.5"/><path d="M12 17h.01"/>',
  atom: '<circle cx="12" cy="12" r="1.25"/><ellipse cx="12" cy="12" rx="9" ry="3.75"/><ellipse cx="12" cy="12" rx="9" ry="3.75" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="3.75" transform="rotate(120 12 12)"/>',
  star: '<path d="M12 3.75l2.5 5.1 5.6.8-4.05 3.95.95 5.6L12 16.55 6.99 19.2l.96-5.6L3.9 9.65l5.6-.8z"/>',
  mountain: '<path d="M2.5 20 9 9l3.5 6 2.5-3.75L21.5 20z"/><path d="M9 9V3.75l3.25 1.25L9 6.25"/>',
  waves: '<path d="M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/><path d="M3 13c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/><path d="M3 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0"/>',
  smile: '<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14.5c.9 1.2 2.1 1.9 3.5 1.9s2.6-.7 3.5-1.9"/><path d="M9.25 9.75v.5M14.75 9.75v.5"/>',
};
const ic = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.sparkle}</svg>`;

/* ------------------------------------------------------------ utilidades */
async function api(path, opts = {}) {
  const o = { headers: {}, credentials: "same-origin", ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.body); }
  const r = await fetch(path, o);
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Sessão expirada"); }
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    let msg = data?.detail ?? data;
    if (Array.isArray(msg)) msg = msg.map((e) => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join("; ");
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.innerHTML = `${ic(err ? "alert" : "check")}<span>${esc(msg)}</span>`;
  t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), err ? 7000 : 3500);
}
function modal(title, body, foot = "") {
  $("#modal-box").innerHTML = `<div class="modal-head"><h2>${title}</h2>
    <button type="button" class="icon-btn" data-act="close" title="Fechar" aria-label="Fechar">${ic("x")}</button></div>
    ${body}${foot ? `<div class="modal-foot">${foot}</div>` : ""}`;
  $("#modal").classList.remove("hidden");
}
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" }) : "";
const rtf = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });
function fmtAgo(iso) {
  if (!iso) return "";
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  const a = Math.abs(s);
  if (a < 45) return "agora";
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  if (a < 604800) return rtf.format(Math.round(s / 86400), "day");
  return new Date(iso).toLocaleDateString("pt-BR");
}
function fmtUsd(n) {
  n = Number(n || 0);
  const digits = n > 0 && n < 0.995 ? (n < 0.01 ? 4 : 3) : 2;
  return "US$ " + n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: digits });
}
const fmtDur = (s) => { s = Math.round(Number(s || 0)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

const KIND = { youtube: "Cortes do YouTube", prompt3d: "Vídeo 3D", tiktok_post: "Post no TikTok" };
const KIND_ICON = { youtube: "scissors", prompt3d: "cube", tiktok_post: "send" };
const STATUS = { queued: "na fila", running: "processando", done: "concluído", error: "erro", canceled: "cancelado",
  uploading: "enviando", processing: "TikTok processando", published: "publicado", inbox: "nos rascunhos" };
const badge = (s) => s ? `<span class="badge ${esc(s)}">${esc(STATUS[s] || s)}</span>` : "";
const PRIVACY = { SELF_ONLY: "Só eu (privado)", MUTUAL_FOLLOW_FRIENDS: "Amigos", FOLLOWER_OF_CREATOR: "Seguidores", PUBLIC_TO_EVERYONE: "Público" };

function empty(icon, title, text, actions = "") {
  return `<div class="empty">${ic(icon)}<b>${title}</b><div>${text}</div>${actions ? `<div class="row">${actions}</div>` : ""}</div>`;
}
const createButtons = () => `<a class="btn small" href="#/youtube">${ic("scissors", "sm")} Cortes do YouTube</a>
  <a class="btn small" href="#/prompt3d">${ic("cube", "sm")} Vídeo 3D</a>`;

function pageHead(icon, title, text, flow = []) {
  return `<div class="page-head"><div class="head-icon">${ic(icon)}</div><div class="grow"><h1>${title}</h1><p>${text}</p>
    ${flow.length ? `<div class="flow">${flow.map((f) => `<span>${f}</span>`).join('<span class="sep">›</span>')}</div>` : ""}</div></div>`;
}
const toggle = (name, title, desc, checked = false) => `<label class="toggle-row"><span class="t"><b>${title}</b>${desc ? `<span>${desc}</span>` : ""}</span>
  <span class="switch"><input type="checkbox" name="${name}" ${checked ? "checked" : ""}><span></span></span></label>`;
const radioChips = (name, opts, value) => `<div class="chips" role="radiogroup">${opts.map(([v, l, extra = ""]) =>
  `<label class="chip">${extra}<input type="radio" name="${name}" value="${esc(v)}" ${v === value ? "checked" : ""}>${l}</label>`).join("")}</div>`;
const optionCards = (name, opts, value) => `<div class="options">${opts.map(([v, icon, t, d, tag = ""]) =>
  `<label class="option"><input type="radio" name="${name}" value="${esc(v)}" ${v === value ? "checked" : ""}>${ic(icon)}
   <span><b>${t}</b><span class="d">${d}</span></span>${tag}</label>`).join("")}</div>`;
function setRangeFill(r) { r.style.setProperty("--p", `${((r.value - r.min) * 100) / (r.max - r.min)}%`); }

/* ------------------------------------------------------------ casca: menu, saúde, fila */
const NAV = [
  ["", [["/", "home", "Início"]]],
  ["Criar", [["/youtube", "scissors", "Cortes do YouTube"], ["/prompt3d", "cube", "Vídeo 3D"]]],
  ["Biblioteca", [["/videos", "film", "Vídeos"], ["/jobs", "pulse", "Processamentos"]]],
  ["Ajustes", [["/configuracoes", "sliders", "Configurações"], ["/tiktok-guia", "book", "Conectar TikTok"]]],
];
const TABBAR = [["/", "home", "Início"], ["/youtube", "scissors", "Cortes"], ["/prompt3d", "cube", "3D"], ["/videos", "film", "Vídeos"], ["/jobs", "pulse", "Fila"]];
function renderShell() {
  const count = (r) => r === "/jobs" ? `<span class="count hidden" data-count></span>` : "";
  $("#nav").innerHTML = NAV.map(([sec, items]) => (sec ? `<div class="nav-label">${sec}</div>` : "") +
    items.map(([r, i, l]) => `<a href="#${r}" data-route="${r}">${ic(i)}<span>${l}</span>${count(r)}</a>`).join("")).join("");
  $("#tabbar").innerHTML = TABBAR.map(([r, i, l]) => `<a href="#${r}" data-route="${r}">${ic(i)}<span>${l}</span>${count(r)}</a>`).join("");
  $("#topbar-actions").innerHTML = `<a class="icon-btn" href="#/configuracoes" title="Configurações" aria-label="Configurações">${ic("sliders")}</a>
    <button type="button" class="icon-btn" data-act="logout" title="Sair" aria-label="Sair">${ic("logout")}</button>`;
  $("#logout").innerHTML = ic("logout");
}
function setQueueCount(n) {
  $$("[data-count]").forEach((el) => { el.textContent = n; el.classList.toggle("hidden", !n); });
}
async function pollQueue() {
  if (!state.me || document.hidden) return;
  try { const st = await api("/api/stats"); setQueueCount((st.jobs.running || 0) + (st.jobs.queued || 0)); } catch { /* */ }
}
async function loadSettings() {
  state.settings = await api("/api/settings");
  renderHealth();
  return state.settings;
}
const setting = (k) => state.settings?.fields.find((f) => f.key === k);
function renderHealth() {
  const s = state.settings;
  if (!s) return;
  const key = setting("openrouter_api_key")?.is_set;
  const tk = s.tiktok.connected;
  $("#health").innerHTML = `
    <a href="#/configuracoes" data-tab="openrouter"><span class="dot ${key ? "on" : "off"}"></span>IA ${key ? "conectada" : "sem chave"}</a>
    <a href="${tk ? "#/configuracoes" : "#/tiktok-guia"}" data-tab="tiktok"><span class="dot ${tk ? "on" : "off"}"></span>TikTok ${tk ? "conectado" : "desconectado"}</a>`;
}
async function loadThemes() {
  if (!state.themes) {
    try { const t = await api("/api/themes"); state.themes = t.themes; state.styles = t.styles; } catch { state.themes = []; state.styles = []; }
  }
  return state.themes;
}

/* ------------------------------------------------------------ login */
function showLogin() {
  state.me = null; clearInterval(state.timer); clearInterval(state.queueTimer);
  $("#app").classList.add("hidden"); $("#login").classList.remove("hidden");
}
async function boot() {
  try { state.me = await api("/api/me"); } catch { return showLogin(); }
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  renderShell();
  $("#version").textContent = "v" + state.me.version;
  loadSettings().catch(() => {});
  clearInterval(state.queueTimer); pollQueue(); state.queueTimer = setInterval(pollQueue, 8000);
  route();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const btn = $("button", e.target); btn.disabled = true;
  try {
    await api("/api/login", { method: "POST", body: { username: f.get("username"), password: f.get("password") } });
    $("#login-error").textContent = ""; boot();
  } catch (err) { $("#login-error").textContent = err.message; } finally { btn.disabled = false; }
});
async function logout() { try { await api("/api/logout", { method: "POST" }); } finally { showLogin(); } }
$("#logout").addEventListener("click", logout);

/* ------------------------------------------------------------ rotas */
const routes = {
  "/": viewDashboard, "/youtube": viewYoutube, "/prompt3d": viewPrompt3d, "/videos": viewVideos,
  "/jobs": viewJobs, "/configuracoes": viewSettings, "/tiktok-guia": viewGuide,
};
function parseHash() {
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = h.split("?");
  return { path, query: new URLSearchParams(qs || "") };
}
function route() {
  clearInterval(state.timer);
  closeModal();
  const { path, query } = parseHash();
  $$("[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === path));
  window.scrollTo(0, 0);
  Promise.resolve((routes[path] || viewDashboard)(query)).catch((err) => toast(err.message, true));
}
window.addEventListener("hashchange", () => { if (state.me) route(); });
function every(ms, fn) {
  const run = () => Promise.resolve(fn()).catch(() => {});
  run(); state.timer = setInterval(() => { if (!document.hidden) run(); }, ms);
}

/* ------------------------------------------------------------ ações (delegação de cliques) */
const ACTIONS = {
  close: () => closeModal(),
  logout: () => logout(),
  "job-details": (d) => showJob(Number(d.id)),
  "job-cancel": async (d) => { await api(`/api/jobs/${d.id}/cancel`, { method: "POST" }); toast("Cancelamento solicitado"); refreshView(); },
  "job-retry": async (d) => { const j = await api(`/api/jobs/${d.id}/retry`, { method: "POST" }); toast(`Reenviado para a fila como #${j.id}`); refreshView(); },
  "job-delete": (d) => confirmBox("Remover do histórico?", "Os vídeos gerados por este processamento continuam na biblioteca.", "Remover", async () => {
    await api(`/api/jobs/${d.id}`, { method: "DELETE" }); toast("Removido do histórico"); refreshView();
  }),
  "video-post": (d) => postDialog(Number(d.id)),
  "video-edit": (d) => editVideo(Number(d.id)),
  "video-delete": (d) => confirmBox("Apagar vídeo?", "O arquivo será removido do servidor. Isso não apaga posts já publicados no TikTok.", "Apagar", async () => {
    await api(`/api/videos/${d.id}`, { method: "DELETE" }); toast("Vídeo apagado"); refreshView();
  }),
  copy: async (d) => { try { await navigator.clipboard.writeText(d.copy); toast("Copiado"); } catch { toast(d.copy); } },
  "use-model": (d) => useModel(d.key, d.model),
};
document.addEventListener("click", async (e) => {
  const tab = e.target.closest("a[data-tab]");
  if (tab) {
    sessionStorage.setItem("cfgTab", tab.dataset.tab);
    if (tab.getAttribute("href") === location.hash) { e.preventDefault(); route(); }
  }
  const el = e.target.closest("[data-act]");
  if (!el || !ACTIONS[el.dataset.act]) return;
  e.preventDefault();
  try { await ACTIONS[el.dataset.act](el.dataset, el); } catch (err) { toast(err.message, true); }
});
function refreshView() { const l = $("#list"); if (l) l._sig = ""; route(); }
function confirmBox(title, text, label, onOk) {
  modal(title, `<p class="muted">${text}</p>`,
    `<button type="button" class="btn" data-act="close">Cancelar</button><button type="button" class="btn danger" id="ok">${label}</button>`);
  $("#ok").onclick = async () => { $("#ok").disabled = true; try { await onOk(); closeModal(); } catch (err) { toast(err.message, true); $("#ok").disabled = false; } };
}

/* ------------------------------------------------------------ início */
async function viewDashboard() {
  $("#view").innerHTML = `
    <div class="hello"><h1>Olá${state.me?.user ? `, ${esc(state.me.user)}` : ""}</h1><p>O que vamos criar hoje?</p></div>
    <div id="setup"></div>
    <div class="paths">
      <a class="path" href="#/youtube">
        <div class="head-icon">${ic("scissors", "lg")}</div>
        <h2>Cortes do YouTube</h2>
        <p>Cole um link e receba os melhores trechos em vídeos verticais, com legenda animada e enquadramento no rosto.</p>
        <div class="flow"><span>Link</span><span class="sep">›</span><span>Transcrição grátis</span><span class="sep">›</span><span>IA escolhe os trechos</span><span class="sep">›</span><span>Cortes 9:16</span></div>
        <span class="go">Criar cortes ${ic("arrow", "sm")}</span>
      </a>
      <a class="path cyan" href="#/prompt3d">
        <div class="head-icon">${ic("cube", "lg")}</div>
        <h2>Vídeo 3D por tema</h2>
        <p>Escolha um tema como terror ou curiosidades. A IA escreve o roteiro e o PostOp monta e anima as cenas em 3D.</p>
        <div class="flow"><span>Tema</span><span class="sep">›</span><span>Roteiro</span><span class="sep">›</span><span>Cenas 3D</span><span class="sep">›</span><span>Animação</span></div>
        <span class="go">Criar vídeo 3D ${ic("arrow", "sm")}</span>
      </a>
    </div>
    <div class="section"><div class="section-head"><h2>Comece por um tema</h2>
      <a class="btn ghost small" href="#/prompt3d">Ver todos ${ic("arrow", "sm")}</a></div><div class="chips" id="theme-chips"></div></div>
    <div class="section"><div class="grid cols-4" id="stats"></div></div>
    <div class="section card"><div class="section-head"><h2>Últimos processamentos</h2>
      <a class="btn ghost small" href="#/jobs">Ver todos ${ic("arrow", "sm")}</a></div><div id="recent"></div></div>`;
  loadThemes().then((themes) => {
    const box = $("#theme-chips");
    if (box) box.innerHTML = themes.map((t) => `<a class="chip" href="#/prompt3d?tema=${esc(t.key)}">${ic(t.icon, "sm")}${esc(t.name)}</a>`).join("");
  });
  loadSettings().then((s) => {
    const key = setting("openrouter_api_key")?.is_set;
    const tk = s.tiktok.connected;
    if (key && tk) return;
    const item = (ok, label, href, tab) => `<a class="chip ${ok ? "active" : ""}" href="${href}" data-tab="${tab}">${ic(ok ? "check" : "plus", "sm")}${label}</a>`;
    $("#setup").innerHTML = `<div class="card setup"><div class="grow"><h2 style="margin:0 0 2px">Primeiros passos</h2>
      <div class="muted small">${[key, tk].filter(Boolean).length} de 2 concluídos. A chave da IA escreve os roteiros e escolhe os cortes; o TikTok é só para postar.</div></div>
      <div class="steps-mini">${item(key, "Chave do OpenRouter", "#/configuracoes", "openrouter")}${item(tk, "Conectar o TikTok", "#/tiktok-guia", "tiktok")}</div></div>`;
  }).catch(() => {});
  every(5000, async () => {
    const [st, jobs] = await Promise.all([api("/api/stats"), api("/api/jobs?limit=6")]);
    const running = (st.jobs.running || 0) + (st.jobs.queued || 0);
    setQueueCount(running);
    $("#stats").innerHTML = [
      ["film", "Vídeos gerados", st.videos], ["send", "Postados no TikTok", st.posted],
      ["pulse", "Na fila agora", running], ["coin", "Gasto com IA", fmtUsd(st.cost_usd)],
    ].map(([i, l, n]) => `<div class="card stat"><div class="l">${ic(i)}${l}</div><div class="n">${esc(n)}</div></div>`).join("");
    renderJobs($("#recent"), jobs, { compact: true });
  });
}

/* ------------------------------------------------------------ processamentos */
function jobItem(j, hl) {
  const live = ["queued", "running"].includes(j.status);
  const vids = j.result?.videos?.length;
  const acts = [
    vids ? `<a class="icon-btn" href="#/videos?job=${j.id}" title="Ver vídeos" aria-label="Ver vídeos">${ic("film")}</a>` : "",
    `<button type="button" class="icon-btn" data-act="job-details" data-id="${j.id}" title="Detalhes e log" aria-label="Detalhes">${ic("eye")}</button>`,
    live ? `<button type="button" class="icon-btn danger" data-act="job-cancel" data-id="${j.id}" title="Cancelar" aria-label="Cancelar">${ic("x")}</button>` : "",
    ["error", "canceled"].includes(j.status) ? `<button type="button" class="icon-btn" data-act="job-retry" data-id="${j.id}" title="Tentar de novo" aria-label="Tentar de novo">${ic("retry")}</button>` : "",
    !live ? `<button type="button" class="icon-btn danger" data-act="job-delete" data-id="${j.id}" title="Remover do histórico" aria-label="Remover">${ic("trash")}</button>` : "",
  ].join("");
  return `<div class="item ${String(j.id) === String(hl) ? "flash" : ""}">
    <div class="kind ${esc(j.kind)}">${ic(KIND_ICON[j.kind] || "pulse")}</div>
    <div class="body">
      <div class="t" title="${esc(j.title)}">${esc(j.title)}</div>
      <div class="meta"><span>#${j.id}</span><span>${esc(KIND[j.kind] || j.kind)}</span>${j.stage ? `<span>${esc(j.stage)}</span>` : ""}
        <span title="${esc(fmtDate(j.created_at))}">${esc(fmtAgo(j.created_at))}</span></div>
      ${j.status === "running" ? `<div class="progress"><div style="width:${Number(j.progress) || 0}%"></div></div>` : ""}
      ${j.error ? `<div class="err">${esc(j.error.slice(0, 260))}</div>` : ""}
    </div>
    <div class="side">${badge(j.status)}<span class="cost">${fmtUsd(j.cost_usd)}</span><div class="acts">${acts}</div></div>
  </div>`;
}
function renderJobs(box, jobs, { hl = "", compact = false } = {}) {
  if (!box) return;
  const sig = jobs.map((j) => [j.id, j.status, j.progress, j.stage, j.cost_usd, j.error?.length].join(":")).join("|") + fmtAgo(jobs[0]?.created_at);
  if (box._sig === sig) return;
  box._sig = sig;
  box.innerHTML = jobs.length ? `<div class="list">${jobs.map((j) => jobItem(j, hl)).join("")}</div>`
    : empty("pulse", "Nada por aqui ainda", compact ? "Seus vídeos em produção aparecem aqui." : "Quando você gerar um vídeo, o progresso aparece aqui.", createButtons());
}
function viewJobs(query) {
  let hl = query.get("novo") || "";
  $("#view").innerHTML = pageHead("pulse", "Processamentos", "Um vídeo é produzido por vez. A lista se atualiza sozinha.") +
    `<div class="card"><div id="list"></div></div>`;
  every(3000, async () => {
    const jobs = await api("/api/jobs?limit=100");
    setQueueCount(jobs.filter((j) => ["queued", "running"].includes(j.status)).length);
    renderJobs($("#list"), jobs, { hl });
    hl = "";
  });
}
async function showJob(id) {
  const j = await api(`/api/jobs/${id}`);
  modal(`${esc(KIND[j.kind] || j.kind)} #${j.id}`,
    `<div class="row" style="align-items:center;margin-bottom:12px">${badge(j.status)}<span class="muted small">${esc(j.stage)}</span></div>
    ${j.error ? `<div class="callout">${ic("alert")}<div>${esc(j.error)}</div></div>` : ""}
    <h3>Parâmetros</h3><pre class="log">${esc(JSON.stringify(j.params, null, 2))}</pre>
    <h3>Log</h3><pre class="log">${esc(j.log || "(vazio)")}</pre>`,
    `${j.result?.videos?.length ? `<a class="btn primary" href="#/videos?job=${j.id}">${ic("film", "sm")} Ver vídeos</a>` : ""}
     <button type="button" class="btn" data-act="close">Fechar</button>`);
}

/* ------------------------------------------------------------ postagem automática (comum) */
function postFields() {
  return `<details class="more"><summary>${ic("send")}<span>Postar no TikTok automaticamente <span class="sub">· opcional</span></span>${ic("chevron")}</summary>
    <div class="in">
      ${toggle("auto_post", "Postar assim que ficar pronto", "Cada vídeo vai para o TikTok sem você precisar abrir a biblioteca.")}
      <div class="row" style="margin-top:12px">
        <label>Modo<select name="post_mode"><option value="">Padrão das configurações</option>
          <option value="direct">Publicar direto</option><option value="inbox">Enviar para os rascunhos do TikTok</option></select></label>
        <label>Privacidade<select name="privacy"><option value="">Padrão das configurações</option>
          ${Object.entries(PRIVACY).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
      </div></div></details>`;
}
const postValues = (f) => ({ auto_post: f.get("auto_post") === "on", post_mode: f.get("post_mode") || "", privacy: f.get("privacy") || "" });

/* ------------------------------------------------------------ cortes do YouTube */
function youtubeId(url) {
  const m = String(url).trim().match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|live\/|embed\/)|youtu\.be\/)([\w-]{6,})/i);
  return m ? m[1] : "";
}
const CLIP_PRESETS = [["curto", "Curtos", 15, 30], ["medio", "Médios", 20, 60], ["longo", "Longos", 60, 90]];
const REFRAME = { auto: "enquadramento automático", face: "recorte no rosto", crop: "recorte no centro", blur: "vídeo inteiro com fundo desfocado" };
function viewYoutube() {
  $("#view").innerHTML = pageHead("scissors", "Cortes do YouTube",
    "Cole o link de um vídeo. O PostOp transcreve o áudio de graça no servidor, a IA escolhe os trechos com mais potencial e entrega cortes verticais prontos.",
    ["Baixar", "Transcrever (Whisper, grátis)", "Escolher trechos", "Cortar 9:16 com legenda"]) + `
    <form id="f" autocomplete="off">
      <div class="card">
        <div class="step-title"><span class="n">1</span>Link do vídeo</div>
        <div class="big-input"><div class="input-icon">${ic("link")}<input name="url" placeholder="https://www.youtube.com/watch?v=..." required aria-label="Link do vídeo do YouTube"></div>
          <button type="button" class="btn" id="paste">${ic("copy", "sm")} Colar</button></div>
        <div id="yt"></div>
      </div>
      <div class="card">
        <div class="step-title"><span class="n">2</span>Cortes</div>
        <div class="range-row">
          <div class="range"><label><span class="top">Quantidade de cortes<output id="o-clips">5</output></span>
            <input type="range" name="max_clips" min="1" max="20" value="5"></label></div>
          <div class="field"><div class="field-label" style="margin-bottom:8px">Duração de cada corte</div>
            <div class="chips" id="presets">${CLIP_PRESETS.map(([k, l, a, b]) => `<button type="button" class="chip" data-min="${a}" data-max="${b}" aria-pressed="${k === "medio"}">${l} <span class="muted">${a}–${b} s</span></button>`).join("")}</div></div>
        </div>
        <div class="row" style="margin-top:16px">
          <label>Mínimo (segundos)<input name="min_seconds" type="number" value="20" min="5" max="180"></label>
          <label>Máximo (segundos)<input name="max_seconds" type="number" value="60" min="10" max="600"></label>
        </div>
        <label><span>Instruções para a IA <span class="help">(opcional)</span></span>
          <textarea name="instructions" rows="2" style="min-height:70px" placeholder="Ex.: priorize momentos engraçados; evite a parte do patrocínio"></textarea></label>
      </div>
      <div class="card">
        <div class="step-title"><span class="n">3</span>Formato vertical</div>
        ${optionCards("reframe", [
          ["auto", "sparkle", "Automático", "Segue o rosto. Sem rosto, usa fundo desfocado."],
          ["face", "user", "Rosto", "Recorta sempre em quem está falando."],
          ["crop", "crop", "Centro", "Recorte fixo no meio da imagem."],
          ["blur", "frame", "Vídeo inteiro", "Mostra tudo, com fundo desfocado."],
        ], "auto")}
        <div class="field-label" style="margin:20px 0 8px">Legenda</div>
        ${radioChips("subtitle_style", [["", "Padrão das configurações"], ["highlight", "Palavra destacada"], ["simple", "Simples"], ["none", "Sem legenda"]], "")}
      </div>
      <details class="more"><summary>${ic("globe")}<span>Idioma do áudio <span class="sub">· padrão das configurações</span></span>${ic("chevron")}</summary>
        <div class="in"><label>Código do idioma<input name="language" placeholder="ex.: pt, en, es ou auto"><span class="help">Deixe vazio para usar o idioma das Configurações.</span></label></div></details>
      ${postFields()}
      <div class="actionbar"><div class="sum" id="sum"></div><button class="btn primary lg" type="submit">${ic("scissors", "sm")} Gerar cortes</button></div>
    </form>`;
  const form = $("#f");
  const range = $("[name=max_clips]", form);
  const update = () => {
    const f = new FormData(form);
    $("#o-clips").textContent = range.value; setRangeFill(range);
    const min = Number(f.get("min_seconds")), max = Number(f.get("max_seconds"));
    $$("#presets .chip").forEach((c) => c.setAttribute("aria-pressed", String(Number(c.dataset.min) === min && Number(c.dataset.max) === max)));
    $("#sum").innerHTML = `<b>até ${range.value} corte${range.value === "1" ? "" : "s"}</b> de ${min}–${max} s · ${REFRAME[f.get("reframe")] || ""}`;
    const url = f.get("url").trim(), id = youtubeId(url);
    $("#yt").innerHTML = id ? `<div class="yt-preview"><img src="https://i.ytimg.com/vi/${esc(id)}/mqdefault.jpg" alt="">
        <div class="t"><b>${ic("check")}Vídeo do YouTube</b><span class="muted">ID ${esc(id)}</span></div></div>`
      : url && url.length > 8 ? `<p class="help" style="margin:10px 0 0;color:var(--warn)">Esse link não parece ser do YouTube.</p>` : "";
  };
  form.addEventListener("input", update);
  $$("#presets .chip").forEach((c) => c.addEventListener("click", () => {
    form.min_seconds.value = c.dataset.min; form.max_seconds.value = c.dataset.max; update();
  }));
  $("#paste").addEventListener("click", async () => {
    try { form.url.value = (await navigator.clipboard.readText()).trim(); update(); } catch { toast("O navegador não deixou colar. Use Ctrl+V no campo.", true); form.url.focus(); }
  });
  update();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(form);
    const body = {
      url: f.get("url").trim(), max_clips: Number(f.get("max_clips")), min_seconds: Number(f.get("min_seconds")),
      max_seconds: Number(f.get("max_seconds")), reframe: f.get("reframe"), subtitle_style: f.get("subtitle_style") || "",
      language: f.get("language").trim(), instructions: f.get("instructions"), ...postValues(f),
    };
    if (body.min_seconds >= body.max_seconds) return toast("A duração mínima precisa ser menor que a máxima.", true);
    const btn = $("button[type=submit]", form); btn.disabled = true;
    try {
      const j = await api("/api/jobs/youtube", { method: "POST", body });
      toast(`Cortes na fila (#${j.id})`); location.hash = `#/jobs?novo=${j.id}`;
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  });
}

/* ------------------------------------------------------------ vídeo 3D por tema */
const THEME_HUE = { "": 220, curiosidades: 45, terror: 355, misterios: 270, folclore: 140, mitologia: 30, historia: 20, espaco: 230,
  animais: 95, e_se: 185, ciencia: 165, fabula: 320, motivacional: 10, satisfatorio: 290, humor: 55 };
const STYLE_SWATCH = { pixar3d: "#7cc4ff,#ffb86b", realista3d: "#9aa4b2,#3b4252", documental: "#8fbf7f,#3d5a3a", sombrio: "#2b2f3a,#0b0c10",
  fantasia: "#c08bff,#ffcf6b", anime3d: "#ff7eb6,#7aa2ff", lowpoly: "#ffd6a5,#a0c4ff", clay: "#ffadad,#fdffb6", neon: "#ff2bd6,#2be4ff" };
async function viewPrompt3d(query) {
  const [themes] = await Promise.all([loadThemes(), state.settings ? null : loadSettings().catch(() => null)]);
  const styles = state.styles?.length ? state.styles : [{ key: "pixar3d", name: "Animação 3D" }];
  const first = query.get("tema") && themes.find((t) => t.key === query.get("tema"));
  const cards = [{ key: "", name: "Ideia livre", tagline: "Descreva do seu jeito, sem regras de gênero", icon: "free" }, ...themes];
  const hasKey = Boolean(setting("openrouter_api_key")?.is_set);
  const textModel = setting("text_model")?.value || "";
  $("#view").innerHTML = pageHead("cube", "Vídeo 3D por tema",
    "Escolha um tema e a ideia já vem pronta. A IA escreve o roteiro e o PostOp monta e anima cada cena em 3D no próprio servidor: cenários, pessoas, animais e objetos.",
    ["Tema", "Roteiro (IA)", "Cenas 3D", "Animação", "Vídeo 9:16"]) + `
    <form id="f" autocomplete="off">
      <input type="hidden" name="theme" value="">
      <div class="card">
        <div class="step-title"><span class="n">1</span>Escolha um tema</div>
        <div class="themes" id="themes">${cards.map((t) => `<button type="button" class="theme" data-theme="${esc(t.key)}" aria-pressed="false" style="--h:${THEME_HUE[t.key] ?? 220}">
          <span class="ok">${ic("check")}</span><span class="ti">${ic(t.icon)}</span>
          <span><b>${esc(t.name)}</b><br><span class="d">${esc(t.tagline)}</span></span>
          ${t.key ? `<span class="meta">${esc(t.style_name)} · ${t.scenes} cenas</span>` : ""}</button>`).join("")}</div>
      </div>
      <div class="card">
        <div class="step-title"><span class="n">2</span>Ideia do vídeo</div>
        <div id="theme-note"></div>
        <label style="margin-bottom:12px"><textarea name="prompt" required minlength="3" aria-label="Ideia do vídeo"
          placeholder="Ex.: um gato astronauta descobrindo um planeta feito de doces"></textarea></label>
        <div id="ideas"></div>
      </div>
      <div class="card">
        <div class="step-title"><span class="n">3</span>Visual e duração</div>
        <div class="field-label" style="margin-bottom:8px">Estilo visual</div>
        ${radioChips("style", styles.map((s) => [s.key, esc(s.name), `<span class="sw" style="background:linear-gradient(135deg,${STYLE_SWATCH[s.key] || "#888,#444"})"></span>`]), "pixar3d")}
        <div class="range-row" style="margin-top:22px">
          <div class="range"><label><span class="top">Cenas<output id="o-scenes"></output></span><input type="range" name="scenes" min="1" max="15" step="1" value="6"></label></div>
          <div class="range"><label><span class="top">Segundos por cena<output id="o-secs"></output></span><input type="range" name="seconds_per_scene" min="2" max="10" step="0.5" value="3.5"></label></div>
        </div>
        <p class="help" id="engine-note" style="margin-top:14px"></p>
      </div>
      <div class="card">
        <div class="step-title"><span class="n">4</span>Texto e música</div>
        ${toggle("captions", "Texto de cada cena na tela", "Frases curtas do roteiro aparecem sobre o vídeo.", true)}
        <label class="toggle-row" style="cursor:default"><span class="t"><b>Música de fundo</b><span>Opcional: mp3, m4a, wav, aac ou ogg.</span></span></label>
        <input type="file" name="music" accept="audio/*" aria-label="Música de fundo">
      </div>
      ${postFields()}
      <div class="actionbar"><div class="sum" id="sum"></div><button class="btn primary lg" type="submit">${ic("sparkle", "sm")} Gerar vídeo</button></div>
    </form>`;
  const form = $("#f");
  const ta = form.prompt;
  let lastIdea = "";
  $("#engine-note").innerHTML = `${ic("cube", "sm")} As cenas são desenhadas e animadas pelo motor 3D do PostOp, sem custo de imagem. ` +
    (hasKey ? `Só o roteiro usa IA (<code>${esc(textModel || "modelo das Configurações")}</code>, centavos por vídeo).`
      : `Sem chave do OpenRouter, o roteiro é montado automaticamente a partir da ideia. <a href="#/configuracoes">Configurar a IA</a> para roteiros melhores.`);

  const update = () => {
    const f = new FormData(form);
    const scenes = Number(f.get("scenes")), secs = Number(f.get("seconds_per_scene"));
    $$("input[type=range]", form).forEach(setRangeFill);
    $("#o-scenes").textContent = scenes;
    $("#o-secs").textContent = `${String(secs).replace(".", ",")} s`;
    const theme = themes.find((t) => t.key === f.get("theme"));
    const style = styles.find((s) => s.key === f.get("style"))?.name || "";
    $("#sum").innerHTML = `<b>${esc(theme?.name || "Ideia livre")}</b> · ${esc(style)} · ${scenes} cenas · ≈ ${Math.round(scenes * secs)} s · 3D no servidor`;
  };
  const showIdeas = (theme) => {
    $("#theme-note").innerHTML = theme ? `<div class="theme-note">${ic(theme.icon)}<div><b>${esc(theme.name)}</b> · ${esc(theme.tagline)}.
      O roteiro segue as regras do gênero; edite a ideia à vontade ou toque numa sugestão.</div></div>` : "";
    $("#ideas").innerHTML = theme ? `<div class="field-label" style="margin-bottom:8px">Sugestões</div><div class="chips">${theme.ideas.map((idea) =>
      `<button type="button" class="chip idea" data-idea="${esc(idea)}" aria-pressed="${idea === ta.value}">${esc(idea)}</button>`).join("")}</div>` : "";
  };
  const pickTheme = (key, { fill = true } = {}) => {
    const theme = themes.find((t) => t.key === key);
    form.theme.value = theme ? theme.key : "";
    $$("#themes .theme").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.theme === form.theme.value)));
    if (theme) {
      const styleInput = $(`input[name=style][value="${theme.style}"]`, form);
      if (styleInput) styleInput.checked = true;
      form.scenes.value = theme.scenes; form.seconds_per_scene.value = theme.seconds;
      const edited = ta.value.trim() && ta.value !== lastIdea;
      if (fill && !edited) { ta.value = theme.ideas[0]; lastIdea = ta.value; }
      else if (fill && edited) toast("Tema aplicado. Sua ideia foi mantida; toque numa sugestão para trocar.");
    }
    showIdeas(theme); update();
  };
  $("#themes").addEventListener("click", (e) => {
    const b = e.target.closest(".theme");
    if (!b) return;
    const same = b.dataset.theme && b.dataset.theme === form.theme.value;
    if (same) { // clicar de novo no mesmo tema: próxima ideia
      const t = themes.find((x) => x.key === b.dataset.theme);
      const i = t.ideas.indexOf(ta.value);
      if (!ta.value.trim() || i >= 0) { ta.value = t.ideas[(i + 1) % t.ideas.length]; lastIdea = ta.value; showIdeas(t); }
      return;
    }
    pickTheme(b.dataset.theme);
    if (window.innerWidth < 820) ta.scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("#ideas").addEventListener("click", (e) => {
    const b = e.target.closest("[data-idea]");
    if (!b) return;
    ta.value = b.dataset.idea; lastIdea = ta.value;
    $$("#ideas .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
    update();
  });
  form.addEventListener("input", (e) => {
    if (e.target === ta) $$("#ideas .chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.idea === ta.value)));
    update();
  });
  pickTheme(first ? first.key : "", { fill: Boolean(first) });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form); btn.disabled = true;
    const f = new FormData(form);
    try {
      let music_path = "";
      const file = f.get("music");
      if (file && file.size) {
        const up = new FormData(); up.append("file", file);
        music_path = (await api("/api/uploads/music", { method: "POST", body: up })).music_path;
      }
      const body = {
        prompt: f.get("prompt").trim(), theme: f.get("theme") || "", style: f.get("style"), scenes: Number(f.get("scenes")),
        seconds_per_scene: Number(f.get("seconds_per_scene")), captions: f.get("captions") === "on", music_path, ...postValues(f),
      };
      const j = await api("/api/jobs/prompt3d", { method: "POST", body });
      toast(`Vídeo na fila (#${j.id})`); location.hash = `#/jobs?novo=${j.id}`;
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  });
}

/* ------------------------------------------------------------ vídeos */
const VIDEO_FILTERS = [["all", "Todos"], ["youtube", "Cortes"], ["prompt3d", "3D"], ["posted", "Postados"], ["pending", "Não postados"]];
async function viewVideos(query) {
  const job = query.get("job");
  let filter = sessionStorage.getItem("vFilter") || "all";
  $("#view").innerHTML = pageHead("film", "Vídeos", job ? `Do processamento #${esc(job)} · <a href="#/videos">ver todos</a>` : "Tudo o que você gerou, pronto para postar.") +
    `<div class="toolbar"><div class="chips" id="filters">${VIDEO_FILTERS.map(([k, l]) => `<button type="button" class="chip" data-f="${k}" aria-pressed="${k === filter}">${l}</button>`).join("")}</div>
     <span class="spacer"></span><span class="muted small" id="vcount"></span></div><div id="list" class="videos"></div>`;
  const posted = (v) => ["published", "inbox"].includes(v.tiktok_status);
  const draw = () => {
    const list = $("#list");
    const vids = state.videos.filter((v) => filter === "all" || v.kind === filter || (filter === "posted" && posted(v)) || (filter === "pending" && !posted(v)));
    $("#vcount").textContent = `${vids.length} vídeo${vids.length === 1 ? "" : "s"}`;
    const sig = filter + vids.map((v) => v.id + v.tiktok_status + v.title + v.caption + v.hashtags).join("|");
    if (list._sig === sig) return; // não recria os players (evita pausar o vídeo)
    list._sig = sig;
    if (!vids.length) {
      list.innerHTML = `<div style="grid-column:1/-1" class="card">${state.videos.length ? empty("film", "Nenhum vídeo neste filtro", "Troque o filtro acima.")
        : empty("film", "Nenhum vídeo ainda", "Crie o primeiro a partir de um link do YouTube ou de um tema 3D.", createButtons())}</div>`;
      return;
    }
    list.innerHTML = vids.map((v) => `<div class="vcard" data-id="${v.id}">
      <div class="media"><video src="${esc(v.url)}" poster="${esc(v.thumb)}" controls preload="none" playsinline></video>
        <span class="pill">${ic(KIND_ICON[v.kind] || "film")}${v.kind === "youtube" ? "Corte" : "3D"}</span>
        <span class="pill right">${fmtDur(v.duration)}</span></div>
      <div class="body">
        <div class="title" title="${esc(v.title)}">${esc(v.title)}</div>
        ${v.caption || v.hashtags ? `<div class="cap">${esc(v.caption || "")} ${esc(v.hashtags || "")}</div>` : ""}
        <div class="row" style="gap:6px;align-items:center">${v.tiktok_status ? badge(v.tiktok_status) : ""}${v.score ? `<span class="tag">nota ${Math.round(v.score)}</span>` : ""}</div>
        ${v.tiktok_error ? `<div class="error small" style="margin:0">${esc(v.tiktok_error.slice(0, 180))}</div>` : ""}
        <div class="actions">
          <button type="button" class="btn small primary" data-act="video-post" data-id="${v.id}">${ic("send", "sm")} ${posted(v) ? "Repostar" : "Postar"}</button>
          <button type="button" class="icon-btn" data-act="video-edit" data-id="${v.id}" title="Editar texto do post" aria-label="Editar">${ic("edit")}</button>
          <a class="icon-btn" href="${esc(v.url)}" download title="Baixar" aria-label="Baixar">${ic("download")}</a>
          <button type="button" class="icon-btn danger" data-act="video-delete" data-id="${v.id}" title="Apagar" aria-label="Apagar">${ic("trash")}</button>
        </div></div></div>`).join("");
  };
  $("#filters").addEventListener("click", (e) => {
    const b = e.target.closest("[data-f]");
    if (!b) return;
    filter = b.dataset.f; sessionStorage.setItem("vFilter", filter);
    $$("#filters .chip").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
    draw();
  });
  every(8000, async () => {
    state.videos = await api("/api/videos" + (job ? `?job_id=${encodeURIComponent(job)}` : ""));
    draw();
  });
}
function editVideo(id) {
  const v = state.videos.find((x) => x.id === id);
  modal("Editar texto do post", `<form id="ef">
    <label>Título<input name="title" value="${esc(v.title)}"></label>
    <label>Legenda do post<textarea name="caption">${esc(v.caption)}</textarea></label>
    <label>Hashtags<input name="hashtags" value="${esc(v.hashtags)}"></label>
    <div class="modal-foot"><button type="button" class="btn" data-act="close">Cancelar</button><button class="btn primary">Salvar</button></div></form>`);
  $("#ef").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/api/videos/${id}`, { method: "PATCH", body: Object.fromEntries(new FormData(e.target)) });
      closeModal(); toast("Salvo"); refreshView();
    } catch (err) { toast(err.message, true); }
  });
}
async function postDialog(id) {
  const v = state.videos.find((x) => x.id === id);
  const s = await loadSettings();
  if (!s.tiktok.connected) {
    modal("TikTok não conectado", `<p class="muted">Conecte sua conta antes de postar. Leva uns 15 minutos na primeira vez.</p>`,
      `<button type="button" class="btn" data-act="close">Agora não</button><a class="btn primary" href="#/tiktok-guia">${ic("book", "sm")} Ver passo a passo</a>`);
    return;
  }
  const val = (k) => setting(k)?.value;
  let creator = null;
  try { creator = await api("/api/tiktok/creator"); } catch (err) { toast("Não consegui ler o perfil do TikTok: " + err.message, true); }
  const opts = creator?.privacy_level_options || Object.keys(PRIVACY);
  const check = (name, label, forced) => `<label class="check"><input type="checkbox" name="${name}" ${forced ? "checked disabled" : ""}> ${label}</label>`;
  modal("Postar no TikTok", `
    ${creator ? `<p class="muted" style="margin-top:-6px">Conta <b style="color:var(--text)">${esc(creator.creator_nickname || creator.creator_username || "")}</b>
      ${creator.max_video_post_duration_sec ? ` · até ${creator.max_video_post_duration_sec} s por vídeo` : ""}</p>` : ""}
    <form id="pf">
      <label>Texto do post<textarea name="title">${esc([v.caption || v.title, v.hashtags].filter(Boolean).join(" "))}</textarea></label>
      <div class="row">
        <label>Modo<select name="mode"><option value="direct" ${val("tiktok_default_mode") === "direct" ? "selected" : ""}>Publicar direto</option>
          <option value="inbox" ${val("tiktok_default_mode") === "inbox" ? "selected" : ""}>Enviar para os rascunhos do app</option></select></label>
        <label>Privacidade<select name="privacy">${opts.map((o) => `<option value="${esc(o)}" ${o === val("tiktok_default_privacy") ? "selected" : ""}>${esc(PRIVACY[o] || o)}</option>`).join("")}</select></label>
      </div>
      <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:14px">
        ${check("disable_comment", "Desativar comentários", creator?.comment_disabled)}
        ${check("disable_duet", "Desativar dueto", creator?.duet_disabled)}
        ${check("disable_stitch", "Desativar costura (stitch)", creator?.stitch_disabled)}</div>
      <p class="help">Ao postar, você concorda com a <a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank" rel="noopener">Music Usage Confirmation</a> do TikTok.
        Apps ainda não aprovados pelo TikTok só publicam como privado.</p>
      <div class="modal-foot"><button type="button" class="btn" data-act="close">Cancelar</button><button class="btn primary">${ic("send", "sm")} Postar</button></div></form>`);
  $("#pf").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api(`/api/videos/${id}/tiktok`, { method: "POST", body: {
        title: f.get("title"), mode: f.get("mode"), privacy: f.get("privacy"),
        disable_comment: f.get("disable_comment") === "on" || Boolean(creator?.comment_disabled),
        disable_duet: f.get("disable_duet") === "on" || Boolean(creator?.duet_disabled),
        disable_stitch: f.get("disable_stitch") === "on" || Boolean(creator?.stitch_disabled) } });
      closeModal(); toast("Envio para o TikTok na fila"); refreshView();
    } catch (err) { toast(err.message, true); }
  });
}

/* ------------------------------------------------------------ configurações */
const CFG_TABS = { openrouter: ["chip", "IA (OpenRouter)"], video: ["captions", "Vídeo e legendas"], tiktok: ["phone", "TikTok"] };
const RECOMMENDED = [
  ["text_model", "Texto", [["google/gemini-2.5-flash-lite", "US$ 0,10 / 0,40 por milhão de tokens"], ["openrouter/free", "grátis, modelo sorteado"]]],
];
async function viewSettings(query) {
  const s = await loadSettings();
  const err = query.get("tiktok_error");
  const fromTikTok = Boolean(err || query.get("tiktok"));
  if (err) toast("TikTok: " + err, true);
  if (query.get("tiktok") === "ok") toast("Conta do TikTok conectada");
  // volta do TikTok: abre a aba TikTok e limpa o ?tiktok=... da URL (não repete o aviso)
  if (fromTikTok) { sessionStorage.setItem("cfgTab", "tiktok"); history.replaceState(null, "", "#/configuracoes"); }
  const tab = CFG_TABS[sessionStorage.getItem("cfgTab")] ? sessionStorage.getItem("cfgTab") : "openrouter";
  $("#view").innerHTML = pageHead("sliders", "Configurações", "Chaves, modelos de IA, legendas e a conexão com o TikTok.") +
    `<div class="tabs" role="tablist">${Object.entries(CFG_TABS).map(([g, [i, n]]) => `<button type="button" role="tab" data-tabbtn="${g}">${ic(i)}${n}</button>`).join("")}</div>
    <div id="tab"></div>`;
  $$("[data-tabbtn]").forEach((b) => b.addEventListener("click", () => { sessionStorage.setItem("cfgTab", b.dataset.tabbtn); renderTab(b.dataset.tabbtn); }));
  state.settings = s;
  renderTab(tab);
}
function fieldHtml(f) {
  const ph = f.secret ? (f.is_set ? `${f.hint} (deixe vazio para manter)` : "não definido") : f.default;
  let input;
  if (f.kind === "select") input = `<select name="${f.key}">${f.options.map((o) => `<option ${o === f.value ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  else if (f.kind === "textarea") input = `<textarea name="${f.key}" placeholder="${esc(ph)}"></textarea>`;
  else input = `<input name="${f.key}" type="${f.kind === "password" ? "password" : "text"}" value="${esc(f.value)}" placeholder="${esc(ph)}" autocomplete="off">`;
  const status = f.secret ? (f.is_set ? ` <span class="tag free">definido</span> <a href="#" class="small" data-clear="${f.key}" style="color:var(--muted)">apagar</a>` : ` <span class="tag">vazio</span>`) : "";
  return `<label><span>${esc(f.label)}${status}</span>${input}${f.help ? `<span class="help">${esc(f.help)}</span>` : ""}</label>`;
}
function renderTab(tab) {
  const s = state.settings;
  $$("[data-tabbtn]").forEach((b) => { b.classList.toggle("active", b.dataset.tabbtn === tab); b.setAttribute("aria-selected", String(b.dataset.tabbtn === tab)); });
  const fields = s.fields.filter((f) => f.group === tab);
  let extra = "";
  if (tab === "openrouter") {
    extra = `<div class="card"><div class="section-head"><h2>Modelos recomendados</h2><span class="muted small">preços de nov/2026</span></div>
      <p class="muted small">A IA só escreve texto (roteiros e escolha dos cortes). As cenas 3D e a transcrição (Whisper) são feitas no servidor, sem custo. Toque em "usar" para preencher o campo e depois em Salvar.</p>
      <table><tbody>${RECOMMENDED.map(([key, label, models]) => models.map(([id, price], i) => `<tr>
        ${i === 0 ? `<td rowspan="${models.length}" class="muted small" style="width:80px">${label}</td>` : ""}
        <td><code>${esc(id)}</code></td><td class="small muted">${esc(price)}</td>
        <td style="width:60px"><button type="button" class="btn small" data-act="use-model" data-key="${key}" data-model="${esc(id)}">usar</button></td></tr>`).join("")).join("")}</tbody></table>
      <div class="row" style="margin-top:16px;align-items:center">
        <button type="button" class="btn" id="test-key">${ic("key", "sm")} Testar chave</button>
        <button type="button" class="btn" id="list-models">${ic("layers", "sm")} Ver todos os modelos e preços</button></div>
      <div id="key-info"></div><div id="models"></div></div>`;
  }
  if (tab === "tiktok") {
    const t = s.tiktok;
    const missing = ["video.publish", "video.upload"].filter((sc) => !(t.scope || "").split(",").includes(sc));
    extra = `<div class="card"><h2>Conta do TikTok</h2>
      ${t.connected ? `<div class="callout ok">${ic("check")}<div>Conectado ${t.display_name ? `como <b>${esc(t.display_name)}</b>` : ""}
          <div class="small muted">Permissões: ${esc(t.scope)}</div></div></div>
          ${missing.map((sc) => `<div class="callout">${ic("alert")}<div>Falta a permissão <b>${sc}</b>: adicione no app do TikTok Developers e clique em Reconectar.</div></div>`).join("")}
          <div class="row"><a class="btn" href="/api/tiktok/connect">${ic("retry", "sm")} Reconectar</a>
          <button type="button" class="btn danger" id="tk-off">Desconectar</button></div>`
        : `<p class="muted">${t.configured ? "Client Key e Secret salvos. Agora conecte a conta:" : "Preencha Client Key e Client Secret abaixo e salve. Depois conecte."}</p>
           ${t.configured ? `<a class="btn primary" href="/api/tiktok/connect">${ic("link", "sm")} Conectar conta do TikTok</a>` : `<button type="button" class="btn" disabled>${ic("link", "sm")} Conectar conta do TikTok</button>`}`}
      <h3>Redirect URI (cole no TikTok Developers)</h3>
      <div class="copy"><code>${esc(t.redirect_uri)}</code><button type="button" class="btn small" data-act="copy" data-copy="${esc(t.redirect_uri)}">${ic("copy", "sm")} Copiar</button></div>
      <p class="small muted" style="margin:0">Primeira vez? Siga o <a href="#/tiktok-guia">passo a passo</a>.</p></div>`;
  }
  $("#tab").innerHTML = `${extra}<form id="sf" class="card">${fields.map(fieldHtml).join("")}
    <button class="btn primary">${ic("check", "sm")} Salvar</button></form>`;
  $("#test-key")?.addEventListener("click", testKey);
  $("#list-models")?.addEventListener("click", loadModels);
  $("#tk-off")?.addEventListener("click", async () => {
    await api("/api/tiktok/disconnect", { method: "POST" }); await loadSettings(); renderTab("tiktok");
  });
  $$("[data-clear]").forEach((a) => a.addEventListener("click", async (e) => {
    e.preventDefault();
    state.settings = await api("/api/settings", { method: "PUT", body: { values: {}, clear: [a.dataset.clear] } });
    renderHealth(); toast("Apagado"); renderTab(tab);
  }));
  $("#sf").addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = {};
    for (const [k, v] of new FormData(e.target).entries()) values[k] = v;
    const btn = $("button", e.target); btn.disabled = true;
    try { state.settings = await api("/api/settings", { method: "PUT", body: { values } }); renderHealth(); toast("Configurações salvas"); renderTab(tab); }
    catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  });
}
async function testKey() {
  try {
    const r = await api("/api/openrouter/test", { method: "POST" });
    const i = r.info || {};
    $("#key-info").innerHTML = `<div class="callout ok">${ic("check")}<div>Chave OK · usado: ${fmtUsd(i.usage)}
      ${i.limit != null ? ` · limite: ${fmtUsd(i.limit)}` : ""} ${i.is_free_tier ? " · plano grátis (sem créditos): 50 pedidos/dia em modelos grátis" : ""}</div></div>`;
  } catch (err) { $("#key-info").innerHTML = `<div class="callout">${ic("alert")}<div>${esc(err.message)}</div></div>`; }
}
async function loadModels() {
  $("#models").innerHTML = `<p class="muted" style="margin-top:14px">Carregando...</p>`;
  try {
    const g = await api("/api/openrouter/models");
    const use = (key, id) => `<button type="button" class="btn small" data-act="use-model" data-key="${key}" data-model="${esc(id)}">usar</button>`;
    const table = (rows, key, cols) => `<div class="models-table"><table><thead><tr>${cols.map((c) => `<th>${c[0]}</th>`).join("")}<th></th></tr></thead>
      <tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td>${c[1](r)}</td>`).join("")}<td>${use(key, r.id)}</td></tr>`).join("")}</tbody></table></div>`;
    const price = (m) => m.free ? `<span class="tag free">grátis</span>` : `<span class="small">$${m.prompt_per_m}/M in · $${m.completion_per_m}/M out</span>`;
    $("#models").innerHTML = `
      <h3>Texto (mais baratos primeiro)</h3>${table(g.text.slice(0, 60), "text_model", [["Modelo", (m) => `<code>${esc(m.id)}</code>`], ["Preço", price]])}`;
  } catch (err) { $("#models").innerHTML = `<div class="callout">${ic("alert")}<div>${esc(err.message)}</div></div>`; }
}
function useModel(key, id) {
  const el = $(`[name=${key}]`);
  if (!el) return;
  el.value = id; el.focus(); el.scrollIntoView({ block: "center", behavior: "smooth" });
  toast(`${id} no campo. Clique em Salvar.`);
}

/* ------------------------------------------------------------ guia TikTok */
async function viewGuide() {
  const s = await loadSettings();
  const base = state.me.public_url;
  const redirect = s.tiktok.redirect_uri;
  const cp = (t) => `<div class="copy"><code>${esc(t)}</code><button type="button" class="btn small" data-act="copy" data-copy="${esc(t)}">${ic("copy", "sm")} Copiar</button></div>`;
  const ext = (href, label) => `<a href="${href}" target="_blank" rel="noopener">${label} ${ic("external", "sm")}</a>`;
  $("#view").innerHTML = pageHead("book", "Conectar o TikTok", "Leva uns 15 minutos. Você cria um app grátis no TikTok for Developers e cola as chaves aqui.") + `
    <div class="card">
    ${s.tiktok.connected ? `<div class="callout ok">${ic("check")}<div>Sua conta já está conectada${s.tiktok.display_name ? ` (${esc(s.tiktok.display_name)})` : ""}.</div></div>` : ""}
    <ol class="steps">
      <li><b class="st">Crie uma conta de desenvolvedor</b>
        Acesse ${ext("https://developers.tiktok.com/", "developers.tiktok.com")}, clique em <i>Log in</i>
        e entre com sua conta do TikTok (pode ser a mesma que vai postar).</li>
      <li><b class="st">Crie o app</b>
        Vá em <i>Manage apps</i> › <i>Connect an app</i> (ou <i>Create app</i>). Escolha <i>Individual</i> ou sua empresa.
        Preencha nome (ex.: PostOp), ícone, categoria e descrição.</li>
      <li><b class="st">Preencha os links obrigatórios do app</b>
        Em <i>Basic information</i>, use:
        <div class="small muted" style="margin-top:8px">Website / Web URL</div>${cp(base)}
        <div class="small muted">Terms of Service URL</div>${cp(base + "/termos")}
        <div class="small muted">Privacy Policy URL</div>${cp(base + "/privacidade")}
        Em <i>Platforms</i>, marque <b>Web</b>.</li>
      <li><b class="st">Adicione os produtos</b>
        Em <i>Products</i> › <i>Add products</i>, adicione <b>Login Kit</b> e <b>Content Posting API</b>.
        Dentro de Content Posting API, ative a opção <b>Direct Post</b> (para publicar direto, não só rascunho).</li>
      <li><b class="st">Configure o Redirect URI</b>
        Em <i>Login Kit</i> › <i>Redirect URI</i> › <i>Web</i>, cole exatamente:${cp(redirect)}</li>
      <li><b class="st">Escolha as permissões (Scopes)</b>
        Em <i>Scopes</i>, adicione: <code>user.info.basic</code> <code>video.upload</code> <code>video.publish</code>.</li>
      <li><b class="st">Use o Sandbox para começar agora</b>
        Enquanto o app não é aprovado, crie um <b>Sandbox</b> (botão no topo da página do app), adicione sua conta em
        <i>Target users</i> e use as chaves do sandbox. Funciona na hora.
        <div class="callout">${ic("info")}<div>Até o TikTok aprovar o app, os posts saem como <b>privados (Só eu)</b>. Depois é só mudar para público no app do TikTok, ou pedir a revisão (passo 10).</div></div></li>
      <li><b class="st">Copie as chaves</b>
        Em <i>App details</i> (ou no Sandbox), copie <b>Client key</b> e <b>Client secret</b> e cole em
        <a href="#/configuracoes" data-tab="tiktok">Configurações › TikTok</a>. Clique em <b>Salvar</b>.</li>
      <li><b class="st">Conecte a conta</b>
        Em Configurações › TikTok, clique em <b>Conectar conta do TikTok</b>, faça login e autorize. Você volta para cá com a conta conectada.
        ${s.tiktok.configured ? `<div style="margin-top:10px"><a class="btn primary" href="/api/tiktok/connect">${ic("link", "sm")} Conectar agora</a></div>` : ""}</li>
      <li><b class="st">(Opcional) Envie o app para revisão</b>
        Para postar público direto, clique em <i>Submit for review</i>. Explique o uso ("ferramenta interna para publicar vídeos
        criados por mim na minha conta") e envie um vídeo curto mostrando a plataforma postando. A aprovação costuma levar alguns dias.</li>
      <li><b class="st">Teste</b>
        Em <a href="#/videos">Vídeos</a>, clique em <b>Postar</b> em qualquer vídeo. O status muda para
        "publicado" ou "nos rascunhos" quando terminar.</li>
    </ol></div>
    <div class="card"><h2>Problemas comuns</h2>
    <div class="list">
      <div class="item"><div class="kind">${ic("link")}</div><div class="body"><b>redirect_uri mismatch</b><div class="meta">O Redirect URI no TikTok tem que ser idêntico ao mostrado acima (com https e sem barra no final).</div></div></div>
      <div class="item"><div class="kind">${ic("key")}</div><div class="body"><b>scope_not_authorized</b><div class="meta">Faltou adicionar o scope no app ou reconectar depois de adicionar.</div></div></div>
      <div class="item"><div class="kind">${ic("eye")}</div><div class="body"><b>unaudited_client_can_only_post_to_private_accounts</b><div class="meta">App ainda não aprovado: use privacidade "Só eu" ou envie para revisão.</div></div></div>
      <div class="item"><div class="kind">${ic("clock")}</div><div class="body"><b>spam_risk_too_many_posts</b><div class="meta">O TikTok limita quantos posts por dia uma conta pode fazer pela API.</div></div></div>
    </div></div>`;
}

boot();
