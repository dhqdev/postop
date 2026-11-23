/* PostOp - painel (JS puro, sem build) */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { me: null, settings: null, timer: null };

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
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), err ? 7000 : 3500);
}
function modal(html) { $("#modal-box").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

const fmtDate = (iso) => iso ? new Date(iso).toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" }) : "";
const fmtUsd = (n) => "US$ " + Number(n || 0).toFixed(4);
const KIND = { youtube: "✂️ Cortes YouTube", prompt3d: "🧊 Vídeo 3D", tiktok_post: "📤 Post TikTok" };
const STATUS = { queued: "na fila", running: "processando", done: "concluído", error: "erro", canceled: "cancelado",
  uploading: "enviando", processing: "TikTok processando", published: "publicado", inbox: "nos rascunhos do TikTok" };
const badge = (s) => s ? `<span class="badge ${esc(s)}">${esc(STATUS[s] || s)}</span>` : "";

/* ------------------------------------------------------------ login */
function showLogin() { $("#app").classList.add("hidden"); $("#login").classList.remove("hidden"); }
async function boot() {
  try { state.me = await api("/api/me"); } catch { return showLogin(); }
  $("#login").classList.add("hidden"); $("#app").classList.remove("hidden");
  $("#version").textContent = "v" + state.me.version;
  route();
}
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/api/login", { method: "POST", body: { username: f.get("username"), password: f.get("password") } });
    $("#login-error").textContent = ""; boot();
  } catch (err) { $("#login-error").textContent = err.message; }
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });

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
  const { path, query } = parseHash();
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.route === path));
  (routes[path] || viewDashboard)(query);
}
window.addEventListener("hashchange", () => { if (state.me) route(); });
function every(ms, fn) { fn(); state.timer = setInterval(fn, ms); }

/* ------------------------------------------------------------ painel */
async function viewDashboard() {
  $("#view").innerHTML = `
    <div class="page-head"><h1>Painel</h1><p class="muted">Crie vídeos verticais 9:16 e poste no TikTok.</p></div>
    <div id="setup"></div>
    <div class="grid cols-4" id="stats"></div>
    <div class="grid cols-2" style="margin-top:16px">
      <a class="card" href="#/youtube" style="text-decoration:none;color:inherit">
        <h2>✂️ Cortes do YouTube</h2><p class="muted">Cole um link: baixamos, transcrevemos, a IA escolhe os melhores trechos
        e gera cortes verticais com legenda animada.</p></a>
      <a class="card" href="#/prompt3d" style="text-decoration:none;color:inherit">
        <h2>🧊 Vídeo 3D por prompt</h2><p class="muted">Descreva a ideia: a IA escreve o roteiro, gera as imagens 3D e anima
        tudo em um vídeo vertical.</p></a>
    </div>
    <div class="card" style="margin-top:16px"><h2>Últimos processamentos</h2><div id="recent"></div></div>`;
  try {
    const s = await api("/api/settings");
    const key = s.fields.find((f) => f.key === "openrouter_api_key");
    const tips = [];
    if (!key.is_set) tips.push(`Adicione sua <b>API key do OpenRouter</b> em <a href="#/configuracoes">Configurações</a>.`);
    if (!s.tiktok.connected) tips.push(`Conecte sua conta do <b>TikTok</b> seguindo o <a href="#/tiktok-guia">passo a passo</a>.`);
    if (tips.length) $("#setup").innerHTML = `<div class="callout" style="margin-bottom:16px">${tips.join("<br>")}</div>`;
  } catch { /* ignora */ }
  every(5000, async () => {
    const [st, jobs] = await Promise.all([api("/api/stats"), api("/api/jobs?limit=8")]);
    const running = (st.jobs.running || 0) + (st.jobs.queued || 0);
    $("#stats").innerHTML = [
      ["Vídeos gerados", st.videos], ["Postados no TikTok", st.posted], ["Em processamento", running],
      ["Custo total OpenRouter", fmtUsd(st.cost_usd)],
    ].map(([l, n]) => `<div class="card stat"><div class="muted small">${l}</div><div class="n">${esc(n)}</div></div>`).join("");
    $("#recent").innerHTML = jobsTable(jobs);
  });
}

function jobsTable(jobs) {
  if (!jobs.length) return `<p class="muted">Nada por aqui ainda.</p>`;
  return `<table><thead><tr><th>#</th><th>Tipo</th><th>Título</th><th>Status</th><th>Custo</th><th></th></tr></thead><tbody>
    ${jobs.map((j) => `<tr>
      <td>${j.id}</td><td>${KIND[j.kind] || esc(j.kind)}</td>
      <td>${esc(j.title)}<div class="muted small">${esc(j.stage)} · ${fmtDate(j.created_at)}</div>
        ${j.status === "running" ? `<div class="progress"><div style="width:${j.progress}%"></div></div>` : ""}
        ${j.error ? `<div class="error small">${esc(j.error.slice(0, 300))}</div>` : ""}</td>
      <td>${badge(j.status)}</td><td>${fmtUsd(j.cost_usd)}</td>
      <td class="row" style="flex-wrap:nowrap;gap:4px">
        <button class="btn small" onclick="showJob(${j.id})">Detalhes</button>
        ${["queued", "running"].includes(j.status) ? `<button class="btn small danger" onclick="cancelJob(${j.id})">Cancelar</button>` : ""}
        ${["error", "canceled"].includes(j.status) ? `<button class="btn small" onclick="retryJob(${j.id})">Repetir</button>` : ""}
      </td></tr>`).join("")}</tbody></table>`;
}
window.showJob = async (id) => {
  const j = await api(`/api/jobs/${id}`);
  modal(`<h2>${KIND[j.kind] || ""} #${j.id}</h2><p>${badge(j.status)} ${esc(j.stage)}</p>
    ${j.error ? `<p class="error">${esc(j.error)}</p>` : ""}
    <h3>Parâmetros</h3><pre class="log">${esc(JSON.stringify(j.params, null, 2))}</pre>
    <h3>Log</h3><pre class="log">${esc(j.log || "(vazio)")}</pre>
    <div class="row"><span class="spacer"></span>
    ${j.result?.videos?.length ? `<a class="btn primary" href="#/videos?job=${j.id}" onclick="closeModal()">Ver vídeos</a>` : ""}
    <button class="btn" onclick="closeModal()">Fechar</button></div>`);
};
window.cancelJob = async (id) => { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); toast("Cancelamento solicitado"); route(); };
window.retryJob = async (id) => { await api(`/api/jobs/${id}/retry`, { method: "POST" }); toast("Job reenfileirado"); route(); };
window.closeModal = closeModal;

/* ------------------------------------------------------------ YouTube */
function postFields() {
  return `<h3>Postagem automática</h3>
    <label class="check"><input type="checkbox" name="auto_post"> Postar no TikTok assim que ficar pronto</label>
    <div class="row">
      <label>Modo<select name="post_mode"><option value="">Padrão das configurações</option>
        <option value="direct">Publicar direto</option><option value="inbox">Enviar para rascunhos do TikTok</option></select></label>
      <label>Privacidade<select name="privacy"><option value="">Padrão das configurações</option>
        <option value="SELF_ONLY">Só eu (privado)</option><option value="MUTUAL_FOLLOW_FRIENDS">Amigos</option>
        <option value="FOLLOWER_OF_CREATOR">Seguidores</option><option value="PUBLIC_TO_EVERYONE">Público</option></select></label>
    </div>`;
}
function viewYoutube() {
  $("#view").innerHTML = `
    <div class="page-head"><h1>✂️ Cortes do YouTube</h1>
      <p class="muted">Download → transcrição local (Whisper, grátis) → IA escolhe os trechos → corte 9:16 com legenda queimada.</p></div>
    <form id="f" class="card">
      <label>Link do vídeo<input name="url" placeholder="https://www.youtube.com/watch?v=..." required></label>
      <div class="row">
        <label>Quantidade de cortes<input name="max_clips" type="number" value="5" min="1" max="20"></label>
        <label>Duração mínima (s)<input name="min_seconds" type="number" value="20" min="5" max="180"></label>
        <label>Duração máxima (s)<input name="max_seconds" type="number" value="60" min="10" max="600"></label>
      </div>
      <div class="row">
        <label>Enquadramento vertical<select name="reframe">
          <option value="auto">Automático (segue o rosto; sem rosto usa fundo desfocado)</option>
          <option value="face">Recortar no rosto</option><option value="crop">Recortar no centro</option>
          <option value="blur">Vídeo inteiro com fundo desfocado</option></select></label>
        <label>Legenda<select name="subtitle_style"><option value="">Padrão das configurações</option>
          <option value="highlight">Palavra destacada (TikTok)</option><option value="simple">Simples</option>
          <option value="none">Sem legenda</option></select></label>
        <label>Idioma do áudio<input name="language" placeholder="padrão das configurações (ex.: pt)"></label>
      </div>
      <label>Instruções para a IA (opcional)<textarea name="instructions" placeholder="Ex.: priorize momentos engraçados; evite a parte de patrocínio"></textarea></label>
      ${postFields()}
      <button class="btn primary" type="submit">Gerar cortes</button>
    </form>`;
  $("#f").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = Object.fromEntries(f.entries());
    ["max_clips", "min_seconds", "max_seconds"].forEach((k) => (body[k] = Number(body[k])));
    body.auto_post = f.get("auto_post") === "on";
    try {
      const j = await api("/api/jobs/youtube", { method: "POST", body });
      toast(`Job #${j.id} criado. Acompanhe em Processamentos.`); location.hash = "#/jobs";
    } catch (err) { toast(err.message, true); }
  });
}

/* ------------------------------------------------------------ Prompt 3D */
async function viewPrompt3d() {
  let styles = ["pixar3d", "realista3d", "anime3d", "lowpoly", "clay", "neon"];
  try { styles = (await api("/api/settings")).styles; } catch { /* */ }
  const names = { pixar3d: "Animação 3D (estilo Pixar)", realista3d: "3D realista (Unreal)", anime3d: "Anime 3D",
    lowpoly: "Low poly / isométrico", clay: "Massinha (claymation)", neon: "Neon / cyberpunk" };
  $("#view").innerHTML = `
    <div class="page-head"><h1>🧊 Vídeo 3D por prompt</h1>
      <p class="muted">Roteiro (IA de texto) → imagens 3D (IA de imagem) → animação → vídeo 9:16 com texto na tela.</p></div>
    <form id="f" class="card">
      <label>Ideia do vídeo<textarea name="prompt" required placeholder="Ex.: um astronauta gato descobrindo um planeta feito de doces"></textarea></label>
      <div class="row">
        <label>Estilo<select name="style">${styles.map((s) => `<option value="${s}">${names[s] || s}</option>`).join("")}</select></label>
        <label>Cenas<input name="scenes" type="number" value="6" min="1" max="15"></label>
        <label>Segundos por cena<input name="seconds_per_scene" type="number" value="3.5" step="0.5" min="2" max="10"></label>
      </div>
      <label>Estilo personalizado (opcional, em inglês, substitui o estilo acima)<input name="custom_style" placeholder="ex.: isometric 3D, glossy toys, studio light"></label>
      <label>Animação<select name="animation">
        <option value="local">Efeito 3D local (movimento de câmera/parallax) · grátis</option>
        <option value="ai">IA de vídeo do OpenRouter (image-to-video) · pago por segundo</option></select>
        <span class="help">Modo IA usa o modelo de vídeo das Configurações (padrão Veo 3.1 Lite ≈ US$ 0,03/s). 6 cenas de 4s ≈ US$ 0,72.</span></label>
      <label class="check"><input type="checkbox" name="ai_fallback" checked> Se a IA de vídeo falhar, usar o efeito local</label>
      <label class="check"><input type="checkbox" name="captions" checked> Mostrar o texto de cada cena na tela</label>
      <label>Música de fundo (opcional)<input type="file" name="music" accept="audio/*"></label>
      ${postFields()}
      <button class="btn primary" type="submit">Gerar vídeo 3D</button>
    </form>`;
  $("#f").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", e.target); btn.disabled = true;
    const f = new FormData(e.target);
    try {
      let music_path = "";
      const file = f.get("music");
      if (file && file.size) {
        const up = new FormData(); up.append("file", file);
        music_path = (await api("/api/uploads/music", { method: "POST", body: up })).music_path;
      }
      const body = {
        prompt: f.get("prompt"), style: f.get("style"), scenes: Number(f.get("scenes")),
        seconds_per_scene: Number(f.get("seconds_per_scene")), custom_style: f.get("custom_style"),
        animation: f.get("animation"), ai_fallback: f.get("ai_fallback") === "on", captions: f.get("captions") === "on",
        music_path, auto_post: f.get("auto_post") === "on", post_mode: f.get("post_mode"), privacy: f.get("privacy"),
      };
      const j = await api("/api/jobs/prompt3d", { method: "POST", body });
      toast(`Job #${j.id} criado.`); location.hash = "#/jobs";
    } catch (err) { toast(err.message, true); } finally { btn.disabled = false; }
  });
}

/* ------------------------------------------------------------ Vídeos */
async function viewVideos(query) {
  const job = query.get("job");
  $("#view").innerHTML = `<div class="page-head row"><div><h1>🎞️ Vídeos</h1>
    <p class="muted">${job ? `Do processamento #${esc(job)} · <a href="#/videos">ver todos</a>` : "Todos os vídeos gerados"}</p></div></div>
    <div id="list" class="videos"></div>`;
  const load = async () => {
    const vids = await api("/api/videos" + (job ? `?job_id=${encodeURIComponent(job)}` : ""));
    const list = $("#list");
    if (!vids.length) { list.innerHTML = `<p class="muted">Nenhum vídeo ainda.</p>`; return; }
    // não recria os players que já existem (evita pausar o vídeo)
    const html = vids.map((v) => `<div class="vcard" data-id="${v.id}">
      <video src="${esc(v.url)}" poster="${esc(v.thumb)}" controls preload="none" playsinline></video>
      <div class="body">
        <div class="title">${esc(v.title)}</div>
        <div class="muted small">${KIND[v.kind] || ""} · ${v.duration}s ${v.score ? `· nota ${Math.round(v.score)}` : ""}</div>
        <div class="small">${esc((v.caption || "").slice(0, 140))} <span class="muted">${esc(v.hashtags)}</span></div>
        <div>${badge(v.tiktok_status)} ${v.tiktok_error ? `<div class="error small">${esc(v.tiktok_error.slice(0, 200))}</div>` : ""}</div>
        <div class="actions">
          <button class="btn small primary" onclick="postDialog(${v.id})">📤 TikTok</button>
          <button class="btn small" onclick="editVideo(${v.id})">✏️</button>
          <a class="btn small" href="${esc(v.url)}" download>⬇️</a>
          <button class="btn small danger" onclick="deleteVideo(${v.id})">🗑️</button>
        </div></div></div>`).join("");
    const sig = vids.map((v) => v.id + v.tiktok_status + v.title + v.caption).join("|");
    if (list._sig !== sig) { list.innerHTML = html; list._sig = sig; state.videos = vids; }
  };
  every(8000, load);
}
window.editVideo = (id) => {
  const v = state.videos.find((x) => x.id === id);
  modal(`<h2>Editar texto do post</h2><form id="ef">
    <label>Título<input name="title" value="${esc(v.title)}"></label>
    <label>Legenda do post<textarea name="caption">${esc(v.caption)}</textarea></label>
    <label>Hashtags<input name="hashtags" value="${esc(v.hashtags)}"></label>
    <div class="row"><span class="spacer"></span><button type="button" class="btn" onclick="closeModal()">Cancelar</button>
    <button class="btn primary">Salvar</button></div></form>`);
  $("#ef").addEventListener("submit", async (e) => {
    e.preventDefault();
    await api(`/api/videos/${id}`, { method: "PATCH", body: Object.fromEntries(new FormData(e.target)) });
    closeModal(); toast("Salvo"); $("#list")._sig = ""; route();
  });
};
window.deleteVideo = async (id) => {
  modal(`<h2>Apagar vídeo?</h2><p class="muted">O arquivo será removido do servidor.</p>
    <div class="row"><span class="spacer"></span><button class="btn" onclick="closeModal()">Cancelar</button>
    <button class="btn danger" id="del">Apagar</button></div>`);
  $("#del").onclick = async () => { await api(`/api/videos/${id}`, { method: "DELETE" }); closeModal(); toast("Apagado"); route(); };
};
window.postDialog = async (id) => {
  const v = state.videos.find((x) => x.id === id);
  const s = await api("/api/settings");
  if (!s.tiktok.connected) {
    modal(`<h2>TikTok não conectado</h2><p>Conecte sua conta antes de postar.</p>
      <div class="row"><span class="spacer"></span><a class="btn primary" href="#/tiktok-guia" onclick="closeModal()">Ver passo a passo</a></div>`);
    return;
  }
  const val = (k) => s.fields.find((f) => f.key === k)?.value;
  let creator = null;
  try { creator = await api("/api/tiktok/creator"); } catch (err) { toast("Não consegui ler o perfil do TikTok: " + err.message, true); }
  const opts = creator?.privacy_level_options || ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"];
  const names = { SELF_ONLY: "Só eu (privado)", MUTUAL_FOLLOW_FRIENDS: "Amigos", FOLLOWER_OF_CREATOR: "Seguidores", PUBLIC_TO_EVERYONE: "Público" };
  modal(`<h2>Postar no TikTok</h2>
    ${creator ? `<p class="muted">Conta: <b>${esc(creator.creator_nickname || creator.creator_username || "")}</b>
      ${creator.max_video_post_duration_sec ? ` · máx. ${creator.max_video_post_duration_sec}s` : ""}</p>` : ""}
    <form id="pf">
      <label>Texto do post<textarea name="title">${esc([v.caption || v.title, v.hashtags].filter(Boolean).join(" "))}</textarea></label>
      <div class="row">
        <label>Modo<select name="mode"><option value="direct" ${val("tiktok_default_mode") === "direct" ? "selected" : ""}>Publicar direto</option>
          <option value="inbox" ${val("tiktok_default_mode") === "inbox" ? "selected" : ""}>Enviar para rascunhos do app</option></select></label>
        <label>Privacidade<select name="privacy">${opts.map((o) => `<option value="${o}" ${o === val("tiktok_default_privacy") ? "selected" : ""}>${names[o] || o}</option>`).join("")}</select></label>
      </div>
      <label class="check"><input type="checkbox" name="disable_comment" ${creator?.comment_disabled ? "checked disabled" : ""}> Desativar comentários</label>
      <label class="check"><input type="checkbox" name="disable_duet" ${creator?.duet_disabled ? "checked disabled" : ""}> Desativar dueto</label>
      <label class="check"><input type="checkbox" name="disable_stitch" ${creator?.stitch_disabled ? "checked disabled" : ""}> Desativar costura (stitch)</label>
      <p class="help">Ao postar, você concorda com a <a href="https://www.tiktok.com/legal/page/global/music-usage-confirmation/en" target="_blank">Music Usage Confirmation</a> do TikTok.
      Apps ainda não auditados pelo TikTok só publicam como privado.</p>
      <div class="row"><span class="spacer"></span><button type="button" class="btn" onclick="closeModal()">Cancelar</button>
      <button class="btn primary">Postar</button></div></form>`);
  $("#pf").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    try {
      await api(`/api/videos/${id}/tiktok`, { method: "POST", body: {
        title: f.get("title"), mode: f.get("mode"), privacy: f.get("privacy"),
        disable_comment: f.get("disable_comment") === "on", disable_duet: f.get("disable_duet") === "on",
        disable_stitch: f.get("disable_stitch") === "on" } });
      closeModal(); toast("Envio para o TikTok na fila"); $("#list")._sig = ""; route();
    } catch (err) { toast(err.message, true); }
  });
};

/* ------------------------------------------------------------ Jobs */
function viewJobs() {
  $("#view").innerHTML = `<div class="page-head"><h1>⚙️ Processamentos</h1>
    <p class="muted">Atualiza sozinho a cada 3 segundos. Um vídeo é processado por vez.</p></div>
    <div class="card" id="jobs"></div>`;
  every(3000, async () => { $("#jobs").innerHTML = jobsTable(await api("/api/jobs?limit=100")); });
}

/* ------------------------------------------------------------ Configurações */
async function viewSettings(query) {
  const s = await api("/api/settings");
  state.settings = s;
  const err = query.get("tiktok_error");
  const fromTikTok = Boolean(err || query.get("tiktok"));
  if (err) toast("TikTok: " + err, true);
  if (query.get("tiktok") === "ok") toast("Conta do TikTok conectada! 🎉");
  // volta do TikTok: abre a aba TikTok e limpa o ?tiktok=... da URL (não repete o aviso)
  if (fromTikTok) { sessionStorage.setItem("cfgTab", "tiktok"); history.replaceState(null, "", "#/configuracoes"); }
  const tab = sessionStorage.getItem("cfgTab") || "openrouter";
  const groups = { openrouter: "🤖 OpenRouter (IA)", video: "🎬 Vídeo e legendas", tiktok: "📱 TikTok" };
  $("#view").innerHTML = `<div class="page-head"><h1>🔧 Configurações</h1></div>
    <div class="tabs">${Object.entries(groups).map(([g, n]) => `<button data-tab="${g}">${n}</button>`).join("")}</div>
    <div id="tab"></div>`;
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => { sessionStorage.setItem("cfgTab", b.dataset.tab); renderTab(b.dataset.tab); }));
  renderTab(tab);
}

function fieldHtml(f) {
  const ph = f.secret ? (f.is_set ? `${f.hint} (deixe vazio para manter)` : "não definido") : f.default;
  let input;
  if (f.kind === "select") input = `<select name="${f.key}">${f.options.map((o) => `<option ${o === f.value ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  else if (f.kind === "textarea") input = `<textarea name="${f.key}" placeholder="${esc(ph)}"></textarea>`;
  else input = `<input name="${f.key}" type="${f.kind === "password" ? "password" : "text"}" value="${esc(f.value)}" placeholder="${esc(ph)}" autocomplete="off">`;
  const clear = f.secret && f.is_set ? ` <a href="#" class="small" onclick="clearSecret(event,'${f.key}')">apagar</a>` : "";
  return `<label>${esc(f.label)}${clear}${input}${f.help ? `<span class="help">${esc(f.help)}</span>` : ""}</label>`;
}

function renderTab(tab) {
  const s = state.settings;
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  const fields = s.fields.filter((f) => f.group === tab);
  let extra = "";
  if (tab === "openrouter") {
    extra = `<div class="row" style="margin-bottom:16px">
      <button type="button" class="btn" onclick="testKey()">Testar chave</button>
      <button type="button" class="btn" onclick="loadModels()">Ver modelos e preços</button></div>
      <div id="key-info"></div><div id="models"></div>`;
  }
  if (tab === "tiktok") {
    const t = s.tiktok;
    extra = `<div class="card" style="margin-bottom:16px;background:var(--panel-2)">
      <h2>Conta do TikTok</h2>
      ${t.connected ? `<div class="callout ok">✅ Conectado ${t.display_name ? `como <b>${esc(t.display_name)}</b>` : ""}
          <div class="small muted">Permissões: ${esc(t.scope)}</div></div>
          ${["video.publish", "video.upload"].filter((sc) => !(t.scope || "").split(",").includes(sc)).map((sc) =>
            `<div class="callout" style="margin-bottom:8px">Falta a permissão <b>${sc}</b>: adicione no app do TikTok Developers e clique em Reconectar.</div>`).join("")}
          <button type="button" class="btn danger" onclick="disconnectTikTok()">Desconectar</button>
          <a class="btn" href="/api/tiktok/connect">Reconectar</a>`
        : `<p class="muted">${t.configured ? "Client Key e Secret salvos. Agora conecte a conta:" : "Preencha Client Key e Client Secret abaixo e salve. Depois conecte."}</p>
           ${t.configured ? `<a class="btn primary" href="/api/tiktok/connect">🔗 Conectar conta do TikTok</a>` : `<button type="button" class="btn" disabled>🔗 Conectar conta do TikTok</button>`}`}
      <h3>Redirect URI (cole no TikTok Developers)</h3>
      <div class="copy"><code>${esc(t.redirect_uri)}</code><button type="button" class="btn small" onclick="copyText('${esc(t.redirect_uri)}')">Copiar</button></div>
      <p class="small muted">Não sabe por onde começar? Veja o <a href="#/tiktok-guia">passo a passo</a>.</p></div>`;
  }
  $("#tab").innerHTML = `${extra}<form id="sf" class="card">${fields.map(fieldHtml).join("")}
    <button class="btn primary">Salvar</button></form>`;
  $("#sf").addEventListener("submit", async (e) => {
    e.preventDefault();
    const values = {};
    for (const [k, v] of new FormData(e.target).entries()) values[k] = v;
    try { state.settings = await api("/api/settings", { method: "PUT", body: { values } }); toast("Configurações salvas"); renderTab(tab); }
    catch (err) { toast(err.message, true); }
  });
}
window.clearSecret = async (e, key) => {
  e.preventDefault();
  state.settings = await api("/api/settings", { method: "PUT", body: { values: {}, clear: [key] } });
  toast("Apagado"); renderTab(sessionStorage.getItem("cfgTab") || "openrouter");
};
window.copyText = async (t) => { try { await navigator.clipboard.writeText(t); toast("Copiado!"); } catch { toast(t); } };
window.disconnectTikTok = async () => { await api("/api/tiktok/disconnect", { method: "POST" }); state.settings = await api("/api/settings"); renderTab("tiktok"); };
window.testKey = async () => {
  try {
    const r = await api("/api/openrouter/test", { method: "POST" });
    const i = r.info || {};
    $("#key-info").innerHTML = `<div class="callout ok">Chave OK · usado: US$ ${Number(i.usage || 0).toFixed(4)}
      ${i.limit != null ? ` · limite: US$ ${i.limit}` : ""} ${i.is_free_tier ? " · plano grátis (sem créditos)" : ""}</div>`;
  } catch (err) { $("#key-info").innerHTML = `<div class="callout">${esc(err.message)}</div>`; }
};
window.loadModels = async () => {
  $("#models").innerHTML = `<p class="muted">Carregando...</p>`;
  try {
    const g = await api("/api/openrouter/models");
    const use = (key, id) => `<button type="button" class="btn small" onclick="useModel('${key}','${esc(id)}')">usar</button>`;
    const table = (rows, key, cols) => `<div class="models-table"><table><thead><tr>${cols.map((c) => `<th>${c[0]}</th>`).join("")}<th></th></tr></thead>
      <tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td>${c[1](r)}</td>`).join("")}<td>${use(key, r.id)}</td></tr>`).join("")}</tbody></table></div>`;
    const price = (m) => m.free ? `<span class="badge done">grátis</span>` : `$${m.prompt_per_m}/M in · $${m.completion_per_m}/M out`;
    $("#models").innerHTML = `
      <h3>Modelos de texto (mais baratos primeiro)</h3>${table(g.text.slice(0, 60), "text_model", [["Modelo", (m) => `<code>${esc(m.id)}</code>`], ["Preço", price]])}
      <h3>Modelos de imagem</h3>${table(g.image, "image_model", [["Modelo", (m) => `<code>${esc(m.id)}</code>`], ["Preço", price]])}
      <h3>Modelos de vídeo</h3>${g.video.length ? table(g.video, "video_model", [["Modelo", (m) => `<code>${esc(m.id)}</code>`],
        ["Formatos", (m) => esc((m.aspect_ratios || []).join(", "))], ["Durações (s)", (m) => esc((m.durations || []).join(", "))],
        ["Preço", (m) => `<span class="small">${esc(JSON.stringify(m.pricing || ""))}</span>`]]) : `<p class="muted">Nenhum retornado.</p>`}`;
  } catch (err) { $("#models").innerHTML = `<div class="callout">${esc(err.message)}</div>`; }
};
window.useModel = (key, id) => { const el = $(`[name=${key}]`); if (el) { el.value = id; toast(`${id} selecionado. Clique em Salvar.`); el.scrollIntoView({ block: "center" }); } };

/* ------------------------------------------------------------ Guia TikTok */
async function viewGuide() {
  const s = await api("/api/settings");
  const base = state.me.public_url;
  const redirect = s.tiktok.redirect_uri;
  const cp = (t) => `<div class="copy"><code>${esc(t)}</code><button class="btn small" onclick="copyText('${esc(t)}')">Copiar</button></div>`;
  $("#view").innerHTML = `<div class="page-head"><h1>📘 Passo a passo: conectar o TikTok</h1>
    <p class="muted">Leva uns 15 minutos. Você cria um "app" grátis no TikTok for Developers e cola as chaves aqui.</p></div>
    <div class="card">
    ${s.tiktok.connected ? `<div class="callout ok">✅ Sua conta já está conectada${s.tiktok.display_name ? ` (${esc(s.tiktok.display_name)})` : ""}.</div>` : ""}
    <ol class="steps">
      <li><b class="st">Crie uma conta de desenvolvedor</b>
        Acesse <a href="https://developers.tiktok.com/" target="_blank">developers.tiktok.com</a>, clique em <i>Log in</i>
        e entre com sua conta do TikTok (pode ser a mesma que vai postar).</li>
      <li><b class="st">Crie o app</b>
        Vá em <i>Manage apps</i> → <i>Connect an app</i> (ou <i>Create app</i>). Escolha <i>Individual</i> ou sua empresa.
        Preencha nome (ex.: PostOp), ícone, categoria e descrição.</li>
      <li><b class="st">Preencha os links obrigatórios do app</b>
        Em <i>Basic information</i>, use:
        <div class="small muted">Website / Web URL</div>${cp(base)}
        <div class="small muted">Terms of Service URL</div>${cp(base + "/termos")}
        <div class="small muted">Privacy Policy URL</div>${cp(base + "/privacidade")}
        Em <i>Platforms</i>, marque <b>Web</b>.</li>
      <li><b class="st">Adicione os produtos</b>
        Em <i>Products</i> → <i>Add products</i>, adicione <b>Login Kit</b> e <b>Content Posting API</b>.
        Dentro de Content Posting API, ative a opção <b>Direct Post</b> (para publicar direto, não só rascunho).</li>
      <li><b class="st">Configure o Redirect URI</b>
        Em <i>Login Kit</i> → <i>Redirect URI</i> → <i>Web</i>, cole exatamente:${cp(redirect)}</li>
      <li><b class="st">Escolha as permissões (Scopes)</b>
        Em <i>Scopes</i>, adicione: <code>user.info.basic</code> <code>video.upload</code> <code>video.publish</code>.</li>
      <li><b class="st">Use o Sandbox para começar agora</b>
        Enquanto o app não é aprovado, crie um <b>Sandbox</b> (botão no topo da página do app), adicione sua conta em
        <i>Target users</i> e use as chaves do sandbox. Funciona na hora.
        <div class="callout">Até o TikTok aprovar o app, os posts saem como <b>privados (Só eu)</b>. Depois é só mudar para público no app do TikTok, ou pedir a auditoria (passo 10).</div></li>
      <li><b class="st">Copie as chaves</b>
        Em <i>App details</i> (ou no Sandbox), copie <b>Client key</b> e <b>Client secret</b> e cole em
        <a href="#/configuracoes" onclick="sessionStorage.setItem('cfgTab','tiktok')">Configurações → TikTok</a>. Clique em <b>Salvar</b>.</li>
      <li><b class="st">Conecte a conta</b>
        Em Configurações → TikTok, clique em <b>Conectar conta do TikTok</b>, faça login e autorize. Você volta para cá com a conta conectada.
        ${s.tiktok.configured ? `<div style="margin-top:8px"><a class="btn primary" href="/api/tiktok/connect">🔗 Conectar agora</a></div>` : ""}</li>
      <li><b class="st">(Opcional) Envie o app para revisão</b>
        Para postar público direto, clique em <i>Submit for review</i>. Explique o uso ("ferramenta interna para publicar vídeos
        criados por mim na minha conta") e envie um vídeo curto mostrando a plataforma postando. A aprovação costuma levar alguns dias.</li>
      <li><b class="st">Teste</b>
        Em <a href="#/videos">Vídeos</a>, clique em <b>📤 TikTok</b> em qualquer vídeo. O status muda para
        "publicado" ou "nos rascunhos do TikTok" quando terminar.</li>
    </ol>
    <h3>Problemas comuns</h3>
    <ul class="muted">
      <li><b class="st">redirect_uri mismatch</b>: o Redirect URI no TikTok tem que ser idêntico ao mostrado acima (com https e sem barra no final).</li>
      <li><b class="st">scope_not_authorized</b>: faltou adicionar o scope no app ou reconectar depois de adicionar.</li>
      <li><b class="st">unaudited_client_can_only_post_to_private_accounts</b>: app ainda não aprovado; use privacidade "Só eu" ou envie para revisão.</li>
      <li><b class="st">spam_risk_too_many_posts</b>: o TikTok limita quantos posts por dia uma conta pode fazer pela API.</li>
    </ul></div>`;
}

boot();
