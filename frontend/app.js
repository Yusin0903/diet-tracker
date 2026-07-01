"use strict";

const TOKEN_KEY = "diet_token";
const APP_VERSION = "2.0"; // Shown small in the settings sheet (industry-standard "About" placement)
// Auto-detect this device's timezone so "today" is computed in the user's
// own zone (the backend falls back to Taipei if it isn't sent).
const TZ =
  (Intl.DateTimeFormat().resolvedOptions().timeZone) || "Asia/Taipei";
const tzq = (path) => path + (path.includes("?") ? "&" : "?") + "tz=" + encodeURIComponent(TZ);

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  username: localStorage.getItem("diet_user") || "",
  authMode: "login",
  viewDate: startOfToday(), // Which day we're currently looking at (can page back)
};

// ---------- Date helpers ----------
function startOfToday() {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}
function ymd(d) {
  return (
    d.getFullYear() +
    "-" + String(d.getMonth() + 1).padStart(2, "0") +
    "-" + String(d.getDate()).padStart(2, "0")
  );
}
function isViewingToday() {
  return ymd(state.viewDate) === ymd(startOfToday());
}
function dateParam() {
  return "&date=" + ymd(state.viewDate);
}

// ---------- API helper ----------
async function api(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  if (state.token) headers["Authorization"] = "Bearer " + state.token;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    doLogout();
    throw new Error("登入已過期");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "發生錯誤");
  return data;
}

// ---------- DOM refs ----------
const $ = (id) => document.getElementById(id);
const authScreen = $("auth-screen");

// ---------- Line icons (replace emoji so the UI feels like a real app) ----------
const ICONS = {
  camera: '<path d="M21 19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h2.5l1.8-2.6h5.4l1.8 2.6H19a2 2 0 0 1 2 2z"/><circle cx="12" cy="13.5" r="3.6"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M3 12h18"/>',
  pencil: '<path d="M5 19l-1.2 1.2.3-4.2L15.8 4.8a2.2 2.2 0 0 1 3.1 3.1L8 18.9z"/><path d="M13.8 6.8l3.1 3.1"/>',
  star: '<path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8L3.6 9.6l5.8-.8z"/>',
  home: '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
  chart: '<path d="M5 21V4"/><path d="M5 21h16"/><path d="M9 21v-6M14 21V9M19 21v-9"/>',
  book: '<path d="M5 19.5A2.5 2.5 0 0 1 7.5 17H19"/><path d="M7.5 3H19v18H7.5A2.5 2.5 0 0 1 5 18.5v-13A2.5 2.5 0 0 1 7.5 3z"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2.5"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-4.5-4.5L5 21"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="3.5"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.5a4 4 0 0 1 0 7"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  dumbbell: '<path d="M2.5 12h3M18.5 12h3M5.5 12h1.6M16.9 12h1.6"/><rect x="7.1" y="9" width="2.4" height="6" rx="1"/><rect x="14.5" y="9" width="2.4" height="6" rx="1"/>',
};
function ico(name, cls = "") {
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}
// Swap every [data-ico] in the HTML for its SVG (run once at boot)
function renderIcons() {
  document.querySelectorAll("[data-ico]").forEach((el) => {
    el.innerHTML = ico(el.dataset.ico);
  });
}
const appScreen = $("app-screen");

// ========================================================================
// Auth
// ========================================================================
function setupAuth() {
  const tabs = $("auth-tabs");
  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    state.authMode = btn.dataset.mode;
    tabs.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === btn));
    $("invite-field").hidden = state.authMode !== "register";
    $("auth-submit").textContent = state.authMode === "register" ? "註冊" : "登入";
    $("auth-error").textContent = "";
  });

  $("auth-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = $("f-username").value.trim();
    const password = $("f-password").value;
    const invite = $("f-invite").value.trim();
    const submit = $("auth-submit");
    $("auth-error").textContent = "";
    submit.disabled = true;
    try {
      const path = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login";
      const body =
        state.authMode === "register"
          ? { username, password, invite_code: invite }
          : { username, password };
      const data = await api(path, { method: "POST", body });
      onLogin(data.token, data.username);
    } catch (err) {
      $("auth-error").textContent = err.message;
    } finally {
      submit.disabled = false;
    }
  });
}

function onLogin(token, username) {
  state.token = token;
  state.username = username;
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem("diet_user", username);
  showApp();
}

function doLogout() {
  state.token = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem("diet_user");
  authScreen.hidden = false;
  appScreen.hidden = true;
}

// ========================================================================
// Main screen
// ========================================================================
function showApp() {
  authScreen.hidden = true;
  appScreen.hidden = false;
  $("who").textContent = state.username;
  state.viewDate = startOfToday();
  showView("home");
  refresh();
}

async function refresh() {
  updateDateBar();
  await Promise.all([loadSummary(), loadEntries()]);
}

// Update the date bar and toggle the log entry points based on whether it's today.
function updateDateBar() {
  const today = startOfToday();
  const diff = Math.round((today - state.viewDate) / 86400000);
  let label;
  if (diff === 0) label = "今天";
  else if (diff === 1) label = "昨天";
  else if (diff === 2) label = "前天";
  else label = `${state.viewDate.getMonth() + 1}月${state.viewDate.getDate()}日`;
  $("date-main").textContent = label;
  const wk = "日一二三四五六"[state.viewDate.getDay()];
  $("date-sub").textContent = ymd(state.viewDate) + " 週" + wk;
  $("date-next").disabled = isViewingToday(); // Can't view the future
  // Hide the log entry points when viewing history (new logs always go to today)
  const past = !isViewingToday();
  $("app-actions").hidden = past;
  $("camera-input").disabled = past;
}

function shiftDate(days) {
  const d = new Date(state.viewDate);
  d.setDate(d.getDate() + days);
  if (d > startOfToday()) return; // Block the future
  state.viewDate = d;
  refresh();
}

function goToday() {
  state.viewDate = startOfToday();
  refresh();
}

// Jump from a trend bar to that day's home record.
function goToDate(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  d.setHours(0, 0, 0, 0);
  if (d > startOfToday()) return;
  state.viewDate = d;
  showView("home");
  refresh();
}

// ---------- Summary / mascot ----------
// Liquid path: draws a wavy-topped fluid at ratio `frac` (0..1+), clipped inside the body circle.
function liquidPath(frac) {
  const left = 24, right = 176, bottom = 196, fullTop = 44;
  const f = Math.max(0.02, Math.min(frac, 1.12)); // Allow a slight visual overflow
  const y = bottom - f * (bottom - fullTop);
  const half = (right - left) / 2;
  const amp = 6;
  return `M ${left},${y} q ${half / 2},${-amp} ${half},0 q ${half / 2},${amp} ${half},0 L ${right},${bottom} L ${left},${bottom} Z`;
}

function setMascotState(cls) {
  const card = $("cal-card");
  card.classList.remove("state-blue", "state-green", "state-amber", "state-red");
  card.classList.add(cls);
  const stuffed = cls === "state-red";
  $("eyes-normal").hidden = stuffed;
  $("eyes-stuffed").hidden = !stuffed;
  $("cheekL").hidden = !stuffed;
  $("cheekR").hidden = !stuffed;
  $("drips").hidden = !stuffed;
  $("mouth").setAttribute(
    "d",
    stuffed ? "M84,140 q8,9 16,0 q8,-9 16,0" : "M86,138 Q100,148 114,138"
  );
}

async function loadSummary() {
  const s = await api(tzq("/api/summary") + dateParam());
  const cal = s.consumed.calories;
  const pro = s.consumed.protein_g;
  $("cal-value").textContent = cal;

  // === Calorie mascot ===
  if (!s.has_profile) {
    // No body data: don't evaluate, just show calories; mascot stays neutral and half-full.
    setMascotState("state-blue");
    $("liquid").setAttribute("d", liquidPath(0.4));
    $("cal-note").textContent = "今天吃了";
    $("setup-cta").hidden = false;
  } else {
    $("setup-cta").hidden = true;
    const cap = s.cap; // TDEE first, otherwise the calorie ceiling
    $("liquid").setAttribute("d", liquidPath(cal / cap));

    let cls, note;
    if (s.status.tdee === "over") {
      cls = "state-red";
      note = `超過 TDEE +${cal - s.targets.tdee} kcal`;
    } else if (s.status.calories === "in_range") {
      cls = "state-green";
      note = `達標 ✓ 目標 ${s.targets.calories_min}–${s.targets.calories_max}`;
    } else if (s.status.calories === "over") {
      cls = "state-amber";
      note = `超出目標 +${cal - s.targets.calories_max} kcal`;
    } else {
      cls = "state-blue";
      note = `還差 ${s.remaining.calories_to_min} kcal 到目標`;
    }
    setMascotState(cls);
    $("cal-note").textContent = note;
  }

  // === Protein bar ===
  const proCard = $("pro-card");
  $("pro-value").textContent = pro;
  if (!s.has_profile) {
    $("pro-target").textContent = " g";
    $("pro-fill").style.width = "0%";
    proCard.classList.remove("met");
    $("pro-note").textContent = "設定目標後顯示進度";
    $("protein-alert").hidden = true;
  } else {
    const pmin = s.targets.protein_min;
    $("pro-target").textContent = ` / ${pmin} g`;
    $("pro-fill").style.width = Math.min(100, (pro / pmin) * 100) + "%";
    const met = s.status.protein === "met";
    proCard.classList.toggle("met", met);
    $("pro-note").textContent = met ? "蛋白達標 ✓" : `還差 ${s.remaining.protein_to_min} g`;
    const alert = $("protein-alert");
    alert.hidden = met;
    if (!met)
      alert.textContent = `蛋白質還差 ${s.remaining.protein_to_min}g 才到 ${pmin}g`;
  }
}

// ---------- Entries ----------
const SOURCE_ICON = { photo: "camera", manual: "pencil", favorite: "star", barcode: "scan", recipe: "book" };

async function loadEntries() {
  const entries = await api(tzq("/api/entries") + dateParam());
  const list = $("entry-list");
  list.innerHTML = "";
  $("empty-hint").hidden = entries.length > 0;
  for (const e of entries) {
    const li = document.createElement("li");
    li.className = "entry";
    const time = new Date(e.eaten_at).toLocaleTimeString("zh-TW", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    li.innerHTML = `
      <span class="entry-badge">${ico(SOURCE_ICON[e.source] || "pencil")}</span>
      <div class="entry-main">
        <div class="entry-name"></div>
        <div class="entry-sub">${time}${e.note ? " · " + escapeHtml(e.note) : ""}</div>
      </div>
      <div class="entry-macro">
        <div class="entry-cal">${e.calories}</div>
        <div class="entry-pro">${e.protein_g}g</div>
      </div>
      <span class="entry-chev">${ico("chevron")}</span>`;
    li.querySelector(".entry-name").textContent = e.name;
    li.addEventListener("click", () => openEntryEdit(e)); // Tap the row → edit / delete
    list.appendChild(li);
  }
}

// Tap an entry → edit fields or delete (replaces the old direct ✕).
function openEntryEdit(e) {
  openModal(
    "編輯記錄",
    `<label class="field"><span>名稱</span>
       <input id="e-name" type="text" value="${escapeAttr(e.name)}" /></label>
     <div class="grid2">
       <label class="field"><span>熱量 (kcal)</span>
         <input id="e-cal" type="number" inputmode="numeric" value="${e.calories}" /></label>
       <label class="field"><span>蛋白質 (g)</span>
         <input id="e-pro" type="number" inputmode="decimal" step="0.1" value="${e.protein_g}" /></label>
     </div>
     <label class="field"><span>備註(可選)</span>
       <input id="e-note" type="text" value="${escapeAttr(e.note || "")}" /></label>
     <button class="btn-primary" id="e-save">儲存</button>
     <button class="ghost-btn fullw" id="e-fav">${ico("star")} 加入常用</button>
     <button class="btn-danger" id="e-del">刪除這筆記錄</button>`
  );
  $("e-fav").addEventListener("click", async () => {
    const name = $("e-name").value.trim();
    const calories = parseInt($("e-cal").value, 10);
    const protein_g = parseFloat($("e-pro").value);
    if (!name || isNaN(calories) || isNaN(protein_g)) {
      toast("請填完整名稱與數值", true);
      return;
    }
    try {
      await api("/api/foods", { method: "POST", body: { name, calories, protein_g } });
      toast("已加入常用");
    } catch (err) {
      toast(err.message, true);
    }
  });
  $("e-save").addEventListener("click", async () => {
    const name = $("e-name").value.trim();
    const calories = parseInt($("e-cal").value, 10);
    const protein_g = parseFloat($("e-pro").value);
    if (!name || isNaN(calories) || isNaN(protein_g)) {
      toast("請填完整名稱與數值", true);
      return;
    }
    try {
      await api(tzq(`/api/entries/${e.id}`), {
        method: "PUT",
        body: { name, calories, protein_g, note: $("e-note").value.trim() || null },
      });
      closeModal();
      await refresh();
      toast("已更新 ✓");
    } catch (err) {
      toast(err.message, true);
    }
  });
  $("e-del").addEventListener("click", async () => {
    try {
      await api(`/api/entries/${e.id}`, { method: "DELETE" });
      closeModal();
      await refresh();
      toast("已刪除");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function createEntry(payload) {
  await api(tzq("/api/entries"), { method: "POST", body: payload });
  closeModal();
  state.viewDate = startOfToday(); // New logs go to today, so jump back so the user sees them
  await refresh();
  toast("已記錄 ✓");
}

// ========================================================================
// Modal
// ========================================================================
function openModal(title, html) {
  $("modal-title").textContent = title;
  $("modal-body").innerHTML = html;
  $("modal").hidden = false;
}
function closeModal() {
  stopScan(); // Always stop the camera when the modal closes
  $("modal").hidden = true;
  $("modal-body").innerHTML = "";
}

function confirmForm(prefill, source) {
  return `
    <label class="field"><span>名稱</span>
      <input id="m-name" type="text" value="${escapeAttr(prefill.name || "")}" /></label>
    <div class="grid2">
      <label class="field"><span>熱量 (kcal/份)</span>
        <input id="m-cal" type="number" inputmode="numeric" value="${prefill.calories ?? ""}" /></label>
      <label class="field"><span>蛋白質 (g/份)</span>
        <input id="m-pro" type="number" inputmode="decimal" step="0.1" value="${prefill.protein_g ?? ""}" /></label>
    </div>
    <label class="field"><span>份數</span>
      <input id="m-serv" type="number" inputmode="decimal" step="0.5" min="0" value="1" /></label>
    <div class="total-preview" id="m-total" hidden></div>
    <label class="field"><span>備註(可選)</span>
      <input id="m-note" type="text" placeholder="" /></label>
    <button class="btn-primary" id="m-save">確認記錄</button>
    <input type="hidden" id="m-source" value="${source}" />`;
}

function bindConfirm() {
  const servEl = document.getElementById("m-serv"); // Barcode results have no servings field, they use grams instead
  const totalEl = document.getElementById("m-total");

  const recalc = () => {
    if (!servEl || !totalEl) return;
    const cal = parseFloat($("m-cal").value);
    const pro = parseFloat($("m-pro").value);
    const serv = parseFloat(servEl.value);
    if (!isNaN(cal) && !isNaN(serv) && serv > 0 && serv !== 1) {
      const tp = isNaN(pro) ? "?" : +(pro * serv).toFixed(1);
      totalEl.textContent = `總計 ${Math.round(cal * serv)} kcal · ${tp} g 蛋白(${serv} 份)`;
      totalEl.hidden = false;
    } else {
      totalEl.hidden = true;
    }
  };
  if (servEl) ["m-cal", "m-pro", "m-serv"].forEach((id) => $(id).addEventListener("input", recalc));
  recalc();

  $("m-save").addEventListener("click", async () => {
    const name = $("m-name").value.trim();
    const calPer = parseInt($("m-cal").value, 10);
    const proPer = parseFloat($("m-pro").value);
    if (!name || isNaN(calPer) || isNaN(proPer)) {
      toast("請填完整名稱與數值", true);
      return;
    }
    const serv = servEl ? parseFloat(servEl.value) : 1;
    const mult = !servEl || isNaN(serv) || serv <= 0 ? 1 : serv;
    try {
      await createEntry({
        name,
        calories: Math.round(calPer * mult),
        protein_g: +(proPer * mult).toFixed(1),
        source: $("m-source").value,
        note: $("m-note").value.trim() || null,
      });
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ---------- Manual input ----------
function openManual() {
  openModal("手動輸入", confirmForm({}, "manual"));
  bindConfirm();
}

// ---------- Photo analysis ----------
let _photoFile = null;
let _photoUrl = null;

// Let the user choose "take a photo" or "pick from album" first — only "take"
// forces the camera (capture); album / files don't pass capture. Works on both
// Android and iOS.
function openPhoto() {
  openModal(
    "新增照片",
    `<p class="items-hint">要用相機拍,還是從相簿 / 檔案選一張?</p>
     <div class="choice-row">
       <button class="choice-btn" id="ph-cam"><span class="choice-ic">${ico("camera")}</span>拍照</button>
       <button class="choice-btn" id="ph-lib"><span class="choice-ic">${ico("image")}</span>從相簿選</button>
     </div>`
  );
  $("ph-cam").addEventListener("click", () => pickPhoto(true));
  $("ph-lib").addEventListener("click", () => pickPhoto(false));
}

function pickPhoto(useCamera) {
  const input = $("camera-input");
  if (useCamera) input.setAttribute("capture", "environment");
  else input.removeAttribute("capture");
  input.value = "";
  input.click();
}

function handlePhoto(file) {
  if (!file) return;
  if (_photoUrl) URL.revokeObjectURL(_photoUrl);
  _photoFile = file;
  _photoUrl = URL.createObjectURL(file);
  photoHintStep("");
}

// Before analysis the user can add an optional text hint (e.g. "youtiao"),
// sent to Gemini alongside the image to cut the misrecognition rate sharply.
function photoHintStep(hint) {
  openModal(
    "辨識食物照片",
    `<img class="preview-img" src="${_photoUrl}" alt="預覽" />
     <label class="field"><span>補充說明(可選,幫 AI 認得更準)</span>
       <input id="ph-hint" type="text" value="${escapeAttr(hint || "")}"
         placeholder="例如:油條、滷雞腿便當、無糖" /></label>
     <button class="btn-primary" id="ph-go">開始辨識</button>`
  );
  $("ph-go").addEventListener("click", runAnalyze);
}

async function runAnalyze() {
  const hint = $("ph-hint") ? $("ph-hint").value.trim() : "";
  openModal(
    "辨識食物照片",
    `<img class="preview-img" src="${_photoUrl}" alt="預覽" />
     <div class="analyzing"><div class="spinner"></div>Gemini 辨識中…</div>`
  );
  try {
    const form = new FormData();
    form.append("file", _photoFile);
    if (hint) form.append("hint", hint);
    const result = await api("/api/analyze", { method: "POST", body: form, isForm: true });
    const itemsHtml =
      result.items && result.items.length
        ? `<p class="items-hint">辨識內容:${result.items
            .map((i) => escapeHtml(i.food))
            .join("、")} · 信心 ${escapeHtml(result.confidence || "")}</p>`
        : "";
    $("modal-body").innerHTML =
      `<img class="preview-img" src="${_photoUrl}" alt="預覽" />` +
      itemsHtml +
      `<button class="ghost-btn redo-btn" id="ph-redo">辨識不準?加說明再試一次</button>` +
      confirmForm(result, "photo");
    $("ph-redo").addEventListener("click", () => photoHintStep(hint));
    bindConfirm();
  } catch (err) {
    $("modal-body").innerHTML =
      `<p class="items-hint" style="color:var(--bad)">${escapeHtml(err.message)}</p>` +
      `<button class="ghost-btn redo-btn" id="ph-redo">重試辨識</button>` +
      confirmForm({}, "manual");
    $("ph-redo").addEventListener("click", () => photoHintStep(hint));
    bindConfirm();
  }
}

// ---------- Favorite foods ----------
async function openFavorites() {
  openModal("常用食物", `<div class="analyzing"><div class="spinner"></div></div>`);
  try {
    const foods = await api("/api/foods");
    let html = "";
    if (foods.length === 0) html += `<p class="items-hint">還沒有常用食物,下面新增一個。</p>`;
    for (const f of foods) {
      html += `
        <div class="fav-item" data-id="${f.id}">
          <div class="fav-info">
            <div class="fav-name">${escapeHtml(f.name)}</div>
            <div class="fav-macro">${f.calories} kcal · ${f.protein_g}g 蛋白</div>
          </div>
          <button class="fav-add" data-act="add">記一筆</button>
          <button class="fav-del" data-act="del" title="刪除">🗑</button>
        </div>`;
    }
    html += `
      <div class="divider"></div>
      <p class="items-hint">新增常用食物(填「每份」的量,記錄時再選幾份)</p>
      <label class="field"><span>名稱</span><input id="nf-name" type="text" placeholder="例如:雞胸肉(每 100g)" /></label>
      <div class="grid2">
        <label class="field"><span>每份熱量 (kcal)</span><input id="nf-cal" type="number" inputmode="numeric" /></label>
        <label class="field"><span>每份蛋白 (g)</span><input id="nf-pro" type="number" inputmode="decimal" step="0.1" /></label>
      </div>
      <button class="btn-primary" id="nf-save">新增到常用</button>`;
    $("modal-body").innerHTML = html;

    // Wire up each favorite food
    $("modal-body").querySelectorAll(".fav-item").forEach((row) => {
      const id = row.dataset.id;
      const f = foods.find((x) => String(x.id) === id);
      row.querySelector('[data-act="add"]').addEventListener("click", () => {
        logWithServings({
          name: f.name,
          perCal: f.calories,
          perPro: f.protein_g,
          unit: "每份",
          source: "favorite",
        });
      });
      row.querySelector('[data-act="del"]').addEventListener("click", async () => {
        try {
          await api(`/api/foods/${id}`, { method: "DELETE" });
          openFavorites();
        } catch (err) {
          toast(err.message, true);
        }
      });
    });

    $("nf-save").addEventListener("click", async () => {
      const name = $("nf-name").value.trim();
      const calories = parseInt($("nf-cal").value, 10);
      const protein_g = parseFloat($("nf-pro").value);
      if (!name || isNaN(calories) || isNaN(protein_g)) {
        toast("請填完整", true);
        return;
      }
      try {
        await api("/api/foods", { method: "POST", body: { name, calories, protein_g } });
        openFavorites();
      } catch (err) {
        toast(err.message, true);
      }
    });
  } catch (err) {
    toast(err.message, true);
  }
}

// ========================================================================
// Barcode scan (live camera → Open Food Facts lookup → confirm amount → log)
// ========================================================================
const OFF_FIELDS = "product_name,brands,nutriments,serving_quantity,serving_size";
let scanStream = null;
let scanTimer = null;
let zxingReader = null;

// Load the bundled ZXing (only when there's no native BarcodeDetector, e.g. iOS Safari).
function ensureZXing() {
  if (window.ZXing) return Promise.resolve(true);
  return new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "/vendor/zxing.min.js";
    s.onload = () => resolve(!!window.ZXing);
    s.onerror = () => resolve(false);
    document.head.appendChild(s);
  });
}

// Look up a barcode on Open Food Facts (queried directly from the frontend;
// public data, no key). Returns null if not found.
async function lookupBarcode(code) {
  const url =
    `https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(code)}.json?fields=${OFF_FIELDS}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error("查詢失敗");
  const data = await res.json();
  if (data.status !== 1 || !data.product) return null;
  const p = data.product;
  const n = p.nutriments || {};
  const num = (v) => {
    const x = parseFloat(v);
    return isNaN(x) ? null : x;
  };
  const brand = (p.brands || "").split(",")[0].trim();
  const name = [brand, p.product_name].filter(Boolean).join(" ").trim() || "未知商品";
  return {
    barcode: code,
    name,
    cal100: num(n["energy-kcal_100g"]),
    pro100: num(n["proteins_100g"]),
    servingG: num(p.serving_quantity),
  };
}

function stopScan() {
  if (scanTimer) {
    clearTimeout(scanTimer);
    scanTimer = null;
  }
  if (zxingReader) {
    try {
      zxingReader.reset();
    } catch (_) {}
    zxingReader = null;
  }
  if (scanStream) {
    scanStream.getTracks().forEach((t) => t.stop());
    scanStream = null;
  }
}

// Ask the camera for continuous autofocus and a higher resolution so small barcodes scan better.
function tuneCamera(stream) {
  try {
    const track = stream && stream.getVideoTracks && stream.getVideoTracks()[0];
    if (!track || !track.getCapabilities) return;
    const caps = track.getCapabilities();
    const advanced = [];
    if (caps.focusMode && caps.focusMode.includes("continuous"))
      advanced.push({ focusMode: "continuous" });
    if (advanced.length) track.applyConstraints({ advanced }).catch(() => {});
  } catch (_) {}
}

async function openScan() {
  openModal(
    "掃條碼",
    `<div class="scanbox">
       <video id="scan-video" class="scan-video" playsinline muted autoplay></video>
       <div class="scan-frame" aria-hidden="true">
         <span class="c tl"></span><span class="c tr"></span>
         <span class="c bl"></span><span class="c br"></span>
         <div class="scan-laser"></div>
       </div>
     </div>
     <p class="items-hint scan-hint">把條碼對準框內,辨識到會自動帶出營養</p>
     <button class="ghost-btn" id="scan-manual" style="width:100%;padding:11px">改用手動輸入條碼</button>`
  );
  $("scan-manual").addEventListener("click", () => {
    stopScan();
    openManualBarcode();
  });
  const video = $("scan-video");
  const onHit = (code) => {
    stopScan();
    onBarcode(code);
  };

  // Path A: native BarcodeDetector (Android Chrome etc., most power-efficient)
  if ("BarcodeDetector" in window) {
    try {
      scanStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      video.srcObject = scanStream;
      await video.play().catch(() => {});
      tuneCamera(scanStream);
      const detector = new BarcodeDetector({
        formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39"],
      });
      const tick = async () => {
        if (!scanStream) return;
        try {
          const codes = await detector.detect(video);
          if (codes && codes.length) return onHit(codes[0].rawValue);
        } catch (_) {}
        scanTimer = setTimeout(tick, 350);
      };
      tick();
      return;
    } catch (_) {
      stopScan(); // Fall through to path B or manual
    }
  }

  // Path B: ZXing pure-JS decode (browsers without BarcodeDetector, e.g. iOS Safari)
  try {
    if (!(await ensureZXing())) throw new Error("zxing load failed");
    zxingReader = new ZXing.BrowserMultiFormatReader();
    const cb = (result) => {
      if (result) onHit(result.getText());
    };
    try {
      await zxingReader.decodeFromConstraints(
        {
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        },
        video,
        cb
      );
    } catch (_) {
      await zxingReader.decodeFromVideoDevice(null, video, cb); // Fallback: default camera
    }
    // ZXing manages its own stream; once started, grab the video's stream to request continuous focus
    setTimeout(() => tuneCamera(video.srcObject), 600);
  } catch (_) {
    openManualBarcode("無法啟動掃描(相機權限被拒或不支援),請手動輸入條碼:");
  }
}

function openManualBarcode(hint) {
  openModal(
    "輸入條碼",
    `${hint ? `<p class="items-hint">${escapeHtml(hint)}</p>` : ""}
     <label class="field"><span>條碼數字</span>
       <input id="bc-input" type="text" inputmode="numeric" placeholder="例如 4710…" /></label>
     <button class="btn-primary" id="bc-go">查詢</button>`
  );
  $("bc-go").addEventListener("click", () => {
    const code = $("bc-input").value.trim();
    if (!code) {
      toast("請輸入條碼", true);
      return;
    }
    onBarcode(code);
  });
}

async function onBarcode(code) {
  openModal(
    "查詢中…",
    `<div class="analyzing"><div class="spinner"></div>查詢條碼 ${escapeHtml(code)}…</div>`
  );
  let prod = null;
  try {
    prod = await lookupBarcode(code);
  } catch (_) {
    // Network or lookup error, treat as not found
  }
  if (!prod) {
    $("modal-title").textContent = "查不到商品";
    $("modal-body").innerHTML =
      `<p class="items-hint">Open Food Facts 查不到條碼 ${escapeHtml(code)},改手動輸入:</p>` +
      confirmForm({}, "manual");
    bindConfirm();
    return;
  }
  showBarcodeResult(prod);
}

// Shared: log one entry by choosing "servings" (favorites + barcodes). perCal/perPro are "per serving".
function logWithServings({ name, perCal, perPro, unit, source }) {
  perCal = perCal || 0;
  perPro = perPro || 0;
  openModal(
    "記到今天",
    `<div class="fav-item" style="margin-bottom:14px">
       <div class="fav-info">
         <div class="fav-name"></div>
         <div class="fav-macro">${escapeHtml(unit)} ${perCal} kcal · ${perPro}g 蛋白</div>
       </div>
     </div>
     <label class="field"><span>份數</span>
       <input id="lw-serv" type="number" inputmode="decimal" step="0.5" min="0" value="1" /></label>
     <div class="total-preview" id="lw-total"></div>
     <button class="btn-primary" id="lw-go">記到今天</button>`
  );
  $("modal-body").querySelector(".fav-name").textContent = name;
  const total = $("lw-total");
  const recalc = () => {
    const s = parseFloat($("lw-serv").value);
    if (!isNaN(s) && s > 0) {
      total.hidden = false;
      total.textContent = `總計 ${Math.round(perCal * s)} kcal · ${+(perPro * s).toFixed(1)} g 蛋白(${s} 份)`;
    } else {
      total.hidden = true;
    }
  };
  recalc();
  $("lw-serv").addEventListener("input", recalc);
  $("lw-go").addEventListener("click", async () => {
    const s = parseFloat($("lw-serv").value);
    const mult = isNaN(s) || s <= 0 ? 1 : s;
    try {
      await createEntry({
        name,
        calories: Math.round(perCal * mult),
        protein_g: +(perPro * mult).toFixed(1),
        source,
        note: mult !== 1 ? `${mult} 份` : null,
      });
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function showBarcodeResult(prod) {
  // No nutrition at all → fall back to manual entry (prefilled name)
  if (prod.cal100 == null && prod.pro100 == null) {
    $("modal-title").textContent = "查不到營養";
    $("modal-body").innerHTML =
      `<p class="items-hint">這個商品查不到營養數據,手動填一下:</p>` +
      confirmForm({ name: prod.name }, "barcode");
    bindConfirm();
    return;
  }
  // Per "serving": convert with the per-serving grams if available, otherwise treat per 100g as one serving
  let perCal, perPro, unit;
  if (prod.servingG) {
    perCal = prod.cal100 != null ? Math.round((prod.cal100 * prod.servingG) / 100) : 0;
    perPro = prod.pro100 != null ? +((prod.pro100 * prod.servingG) / 100).toFixed(1) : 0;
    unit = `每份 ${prod.servingG}g`;
  } else {
    perCal = prod.cal100 != null ? prod.cal100 : 0;
    perPro = prod.pro100 != null ? prod.pro100 : 0;
    unit = "每 100g";
  }
  logWithServings({ name: prod.name, perCal, perPro, unit, source: "barcode" });
}

// ========================================================================
// Daily targets / body data setup
// ========================================================================
const ACTIVITY_OPTS = [
  ["sedentary", "久坐(幾乎不運動)"],
  ["light", "輕度(每週 1-3 天)"],
  ["moderate", "中度(每週 3-5 天)"],
  ["active", "高度(每週 6-7 天)"],
  ["very_active", "非常高(體力工作/兩練)"],
];
const GOAL_OPTS = [["cut", "減脂"], ["maintain", "維持"], ["bulk", "增肌"]];

function opts(list, sel) {
  return list
    .map(([v, t]) => `<option value="${v}"${v === sel ? " selected" : ""}>${t}</option>`)
    .join("");
}

async function openProfile() {
  openModal("每日目標設定", `<div class="analyzing"><div class="spinner"></div></div>`);
  let p = {};
  try {
    const r = await api("/api/profile");
    p = r.profile || {};
  } catch (_) {}
  const mode = p.mode || "auto";

  $("modal-body").innerHTML = `
    <div class="tabs" id="pf-tabs">
      <button class="tab ${mode === "auto" ? "active" : ""}" data-m="auto">自動估算</button>
      <button class="tab ${mode === "manual" ? "active" : ""}" data-m="manual">手動輸入</button>
    </div>

    <div id="pf-auto" ${mode === "manual" ? "hidden" : ""}>
      <p class="items-hint">填規格估 TDEE。有體脂率(InBody/體脂計)會更準;若量測報告直接給 BMR,填進去最準。</p>
      <div class="grid2">
        <label class="field"><span>性別</span>
          <select id="pf-sex">${opts([["male", "男"], ["female", "女"]], p.sex)}</select></label>
        <label class="field"><span>年齡</span><input id="pf-age" type="number" inputmode="numeric" value="${p.age ?? ""}" /></label>
        <label class="field"><span>身高 (cm)</span><input id="pf-height" type="number" inputmode="decimal" value="${p.height_cm ?? ""}" /></label>
        <label class="field"><span>體重 (kg)</span><input id="pf-weight" type="number" inputmode="decimal" value="${p.weight_kg ?? ""}" /></label>
      </div>
      <label class="field"><span>活動量</span><select id="pf-activity">${opts(ACTIVITY_OPTS, p.activity_level || "moderate")}</select></label>
      <label class="field"><span>目標</span><select id="pf-goal">${opts(GOAL_OPTS, p.goal || "cut")}</select></label>
      <div class="grid2">
        <label class="field"><span>體脂率 % (可選)</span><input id="pf-bf" type="number" inputmode="decimal" value="${p.body_fat_pct ?? ""}" placeholder="如 18" /></label>
        <label class="field"><span>量測 BMR (可選)</span><input id="pf-bmr" type="number" inputmode="numeric" value="${p.measured_bmr ?? ""}" placeholder="報告上的" /></label>
      </div>
      <button class="ghost-btn" id="pf-estimate" style="width:100%;padding:11px">試算 TDEE</button>
      <div id="pf-preview" class="pf-preview" hidden></div>
    </div>

    <div id="pf-manual" ${mode === "auto" ? "hidden" : ""}>
      <p class="items-hint">已經知道自己的目標?直接填三個數字。</p>
      <label class="field"><span>熱量下限 (kcal)</span><input id="pf-cmin" type="number" inputmode="numeric" value="${p.calories_min ?? ""}" /></label>
      <label class="field"><span>熱量上限 (kcal)</span><input id="pf-cmax" type="number" inputmode="numeric" value="${p.calories_max ?? ""}" /></label>
      <label class="field"><span>蛋白下限 (g)</span><input id="pf-pmin" type="number" inputmode="numeric" value="${p.protein_min ?? ""}" /></label>
    </div>

    <button class="btn-primary" id="pf-save">儲存目標</button>
    <div class="app-version">好好吃飯 · v${APP_VERSION}</div>`;

  let curMode = mode;
  $("pf-tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (!b) return;
    curMode = b.dataset.m;
    $("pf-tabs").querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === b));
    $("pf-auto").hidden = curMode !== "auto";
    $("pf-manual").hidden = curMode !== "manual";
  });

  function autoPayload() {
    return {
      mode: "auto",
      sex: $("pf-sex").value,
      age: intOrNull($("pf-age").value),
      height_cm: floatOrNull($("pf-height").value),
      weight_kg: floatOrNull($("pf-weight").value),
      activity_level: $("pf-activity").value,
      goal: $("pf-goal").value,
      body_fat_pct: floatOrNull($("pf-bf").value),
      measured_bmr: intOrNull($("pf-bmr").value),
    };
  }
  function manualPayload() {
    return {
      mode: "manual",
      calories_min: intOrNull($("pf-cmin").value),
      calories_max: intOrNull($("pf-cmax").value),
      protein_min: intOrNull($("pf-pmin").value),
    };
  }

  $("pf-estimate").addEventListener("click", async () => {
    try {
      const r = await api("/api/profile/preview", { method: "POST", body: autoPayload() });
      const methodLabel = { mifflin: "Mifflin 公式", katch: "Katch-McArdle(用體脂)", measured: "量測 BMR" }[r.method] || r.method;
      $("pf-preview").hidden = false;
      $("pf-preview").innerHTML =
        `<div class="pf-tdee">TDEE ≈ <b>${r.tdee}</b> kcal</div>
         <div class="pf-detail">熱量目標 ${r.calories_min}–${r.calories_max} · 蛋白 ${r.protein_min}g
         <br>BMR ${r.bmr}${r.lbm ? " · 淨體重 " + r.lbm + "kg" : ""} · ${methodLabel}</div>`;
    } catch (err) {
      toast(err.message, true);
    }
  });

  $("pf-save").addEventListener("click", async () => {
    try {
      const body = curMode === "manual" ? manualPayload() : autoPayload();
      await api("/api/profile", { method: "PUT", body });
      closeModal();
      await refresh();
      toast("目標已更新 ✓");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function intOrNull(v) {
  const n = parseInt(v, 10);
  return isNaN(n) ? null : n;
}
function floatOrNull(v) {
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

// ========================================================================
// View switching (home / recipes / trends)
// ========================================================================
function showView(name) {
  $("view-home").hidden = name !== "home";
  $("view-recipes").hidden = name !== "recipes";
  $("view-stats").hidden = name !== "stats";
  $("view-friends").hidden = name !== "friends";
  $("view-exercise").hidden = name !== "exercise";
  document
    .querySelectorAll(".tabbar-btn")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "recipes") loadRecipes();
  if (name === "stats") loadStats();
  if (name === "friends") loadFriends();
  if (name === "exercise") loadExerciseMonth();
}

// ========================================================================
// Trends (week / month calorie bar chart + target min/max)
// ========================================================================
let statsRange = "week";

function weekRange() {
  const t = startOfToday();
  const mondayOffset = (t.getDay() + 6) % 7; // Monday = 0
  const start = new Date(t);
  start.setDate(t.getDate() - mondayOffset);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return [start, end];
}
function monthRange() {
  const t = startOfToday();
  return [new Date(t.getFullYear(), t.getMonth(), 1), new Date(t.getFullYear(), t.getMonth() + 1, 0)];
}

async function loadStats() {
  document
    .querySelectorAll("#stats-seg .seg-btn")
    .forEach((b) => b.classList.toggle("active", b.dataset.range === statsRange));
  const [start, end] = statsRange === "week" ? weekRange() : monthRange();
  const chart = $("stats-chart");
  chart.innerHTML = `<div class="analyzing"><div class="spinner"></div></div>`;
  $("stats-cards").innerHTML = "";
  try {
    const data = await api(tzq("/api/stats") + `&start=${ymd(start)}&end=${ymd(end)}`);
    renderStats(data);
  } catch (err) {
    toast(err.message, true);
  }
}

function calClass(cal, t) {
  if (!t) return "b-neutral";
  if (cal === 0) return "b-zero";
  if (t.tdee && cal > t.tdee) return "b-red";
  if (cal > t.calories_max) return "b-amber";
  if (cal >= t.calories_min) return "b-green";
  return "b-blue";
}

function renderStats(data) {
  const t = data.targets;
  const days = data.days;
  const todayStr = ymd(startOfToday());
  const cals = days.map((d) => d.calories);
  // Scale ceiling: max of data, target ceiling and TDEE, plus 12% headroom
  let top = Math.max(...cals, t ? t.calories_max : 0, t && t.tdee ? t.tdee : 0, 100);
  top = top * 1.12;
  const H = 188; // Plot area height in px
  const y = (v) => Math.max(0, Math.min(H, (v / top) * H));
  const month = statsRange === "month";

  // Target band (min~max) and TDEE line
  let bands = "";
  if (t) {
    const yMin = y(t.calories_min);
    const yMax = y(t.calories_max);
    bands += `<div class="band" style="bottom:${yMin}px;height:${yMax - yMin}px"></div>`;
    bands += `<div class="goal-line" style="bottom:${yMax}px"><span>上限 ${t.calories_max}</span></div>`;
    bands += `<div class="goal-line" style="bottom:${yMin}px"><span>下限 ${t.calories_min}</span></div>`;
    if (t.tdee) bands += `<div class="tdee-line" style="bottom:${y(t.tdee)}px"><span>TDEE ${t.tdee}</span></div>`;
  }

  const bars = days
    .map((d) => {
      const h = d.calories > 0 ? Math.max(3, y(d.calories)) : 0;
      const dd = new Date(d.date + "T00:00:00");
      const lbl = month ? dd.getDate() : "日一二三四五六"[dd.getDay()];
      const showLbl = !month || dd.getDate() === 1 || dd.getDate() % 5 === 0;
      const isToday = d.date === todayStr ? " is-today" : "";
      const tappable = d.date <= todayStr ? " tappable" : ""; // Future days aren't tappable
      return `<div class="bar-col${isToday}${tappable}" data-date="${d.date}">
          <div class="bar-wrap"><div class="bar ${calClass(d.calories, t)}" style="height:${h}px"></div></div>
          <div class="bar-lbl">${showLbl ? lbl : ""}</div>
        </div>`;
    })
    .join("");

  $("stats-chart").innerHTML = `
    <div class="plot" style="height:${H}px">${bands}<div class="bars ${month ? "dense" : ""}">${bars}</div></div>
    <p class="chart-hint">點長條看那天的記錄</p>`;

  // Stat cards: average, on-target days, average gap
  const logged = days.filter((d) => d.calories > 0);
  const avg = logged.length ? Math.round(logged.reduce((s, d) => s + d.calories, 0) / logged.length) : 0;
  const cards = [];
  cards.push(statCard("平均 / 天", logged.length ? `${avg}` : "—", "kcal"));
  if (t) {
    const onTarget = logged.filter((d) => d.calories >= t.calories_min && d.calories <= t.calories_max).length;
    cards.push(statCard("達標天數", `${onTarget}`, `/ ${logged.length} 天`));
    if (t.tdee && logged.length) {
      const gap = Math.round(t.tdee - avg); // Positive = deficit
      cards.push(statCard(gap >= 0 ? "平均赤字" : "平均盈餘", `${Math.abs(gap)}`, "kcal/天", gap >= 0 ? "good" : "bad"));
    }
  }
  $("stats-cards").innerHTML = cards.join("");
  if (!t) {
    $("stats-cards").insertAdjacentHTML(
      "beforeend",
      `<p class="items-hint" style="grid-column:1/-1;text-align:center">設定每日目標後,這裡會畫出上下限與缺口。</p>`
    );
  }
}

function statCard(label, value, unit, tone) {
  return `<div class="stat-card${tone ? " " + tone : ""}">
      <div class="stat-val">${value}<span>${unit}</span></div>
      <div class="stat-lbl">${label}</div>
    </div>`;
}

// ========================================================================
// Recipes
// ========================================================================
const splitLines = (s) =>
  (s || "").split("\n").map((x) => x.trim()).filter(Boolean);

async function loadRecipes() {
  const list = $("recipe-list");
  list.innerHTML = `<div class="analyzing"><div class="spinner"></div></div>`;
  try {
    const recipes = await api("/api/recipes");
    list.innerHTML = "";
    $("recipe-empty").hidden = recipes.length > 0;
    for (const r of recipes) {
      const meta = [];
      if (r.calories != null) meta.push(`${r.calories} kcal/份`);
      if (r.protein_g != null) meta.push(`${r.protein_g}g 蛋白`);
      if (r.servings != null) meta.push(`${r.servings} 份`);
      const card = document.createElement("div");
      card.className = "recipe-card";
      card.innerHTML = `
        <div class="recipe-card-main">
          <div class="recipe-name"></div>
          <div class="recipe-meta">${meta.map((m) => `<span>${escapeHtml(m)}</span>`).join("")}</div>
        </div>
        <span class="entry-chev">${ico("chevron")}</span>`;
      card.querySelector(".recipe-name").textContent = r.name;
      card.addEventListener("click", () => openRecipeDetail(r));
      list.appendChild(card);
    }
  } catch (err) {
    toast(err.message, true);
  }
}

// Pull the 11-char video ID out of any YouTube URL format
function ytId(url) {
  if (!url) return null;
  const m = String(url).match(
    /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/))([\w-]{11})/
  );
  return m ? m[1] : null;
}

function openRecipeDetail(r, readonly = false) {
  const ing = splitLines(r.ingredients);
  const steps = splitLines(r.steps);
  const chips = [];
  if (r.calories != null) chips.push(`${r.calories} kcal/份`);
  if (r.protein_g != null) chips.push(`蛋白 ${r.protein_g}g`);
  if (r.servings != null) chips.push(`${r.servings} 份`);
  const vid = ytId(r.video_url);
  const videoHtml = vid
    ? `<div class="video-embed"><iframe src="https://www.youtube.com/embed/${vid}" title="食譜影片" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>`
    : r.video_url
    ? `<a class="video-link" href="${escapeAttr(r.video_url)}" target="_blank" rel="noopener">▶ 開啟影片連結</a>`
    : "";
  openModal(
    "",
    `<div class="recipe-detail">
       <h2 class="rd-title"></h2>
       ${chips.length ? `<div class="rd-chips">${chips.map((c) => `<span>${escapeHtml(c)}</span>`).join("")}</div>` : ""}
       ${videoHtml}
       ${ing.length ? `<h3 class="rd-h">食材</h3><ul class="rd-ing">${ing.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>` : ""}
       ${steps.length ? `<h3 class="rd-h">步驟</h3><ol class="rd-steps">${steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>` : ""}
       ${readonly ? "" : `<div class="rd-actions">
         ${r.calories != null ? `<button class="btn-primary" id="rd-log">記一份到今天</button>` : ""}
         <div class="rd-row">
           <button class="ghost-btn" id="rd-edit">編輯</button>
           <button class="btn-danger" id="rd-del">刪除</button>
         </div>
       </div>`}
     </div>`
  );
  $("modal-body").querySelector(".rd-title").textContent = r.name;
  if (readonly) return; // Friend's recipe — view only, no edit/delete/log.
  const logBtn = $("rd-log");
  if (logBtn) logBtn.addEventListener("click", () => logRecipe(r));
  $("rd-edit").addEventListener("click", () => openRecipeForm(r));
  $("rd-del").addEventListener("click", async () => {
    try {
      await api(`/api/recipes/${r.id}`, { method: "DELETE" });
      closeModal();
      loadRecipes();
      toast("已刪除");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// Log one serving of a recipe: choose servings, auto-convert calories / protein
function logRecipe(r) {
  const cal = r.calories || 0;
  const pro = r.protein_g || 0;
  openModal(
    "記到今天",
    `<div class="fav-item" style="margin-bottom:14px">
       <div class="fav-info">
         <div class="fav-name"></div>
         <div class="fav-macro">每份 ${cal} kcal · ${pro}g 蛋白</div>
       </div>
     </div>
     <label class="field"><span>份數</span>
       <input id="lr-serv" type="number" inputmode="decimal" step="0.5" min="0" value="1" /></label>
     <div class="total-preview" id="lr-total"></div>
     <button class="btn-primary" id="lr-go">記到今天</button>`
  );
  $("modal-body").querySelector(".fav-name").textContent = r.name;
  const total = $("lr-total");
  const recalc = () => {
    const s = parseFloat($("lr-serv").value);
    if (!isNaN(s) && s > 0) {
      total.hidden = false;
      total.textContent = `總計 ${Math.round(cal * s)} kcal · ${+(pro * s).toFixed(1)} g 蛋白(${s} 份)`;
    } else {
      total.hidden = true;
    }
  };
  recalc();
  $("lr-serv").addEventListener("input", recalc);
  $("lr-go").addEventListener("click", async () => {
    const s = parseFloat($("lr-serv").value);
    const mult = isNaN(s) || s <= 0 ? 1 : s;
    try {
      await api(tzq("/api/entries"), {
        method: "POST",
        body: {
          name: r.name,
          calories: Math.round(cal * mult),
          protein_g: +(pro * mult).toFixed(1),
          source: "recipe",
          note: mult !== 1 ? `${mult} 份` : null,
        },
      });
      closeModal();
      await refresh();
      showView("home");
      toast("已記錄 ✓");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function openRecipeForm(r) {
  const e = r || {};
  openModal(
    r ? "編輯食譜" : "新增食譜",
    `<label class="field"><span>食譜名稱</span>
       <input id="rf-name" type="text" value="${escapeAttr(e.name || "")}" placeholder="例如:雞胸蓋飯" /></label>
     <div class="grid3">
       <label class="field"><span>每份熱量</span>
         <input id="rf-cal" type="number" inputmode="numeric" value="${e.calories ?? ""}" placeholder="kcal" /></label>
       <label class="field"><span>每份蛋白</span>
         <input id="rf-pro" type="number" inputmode="decimal" step="0.1" value="${e.protein_g ?? ""}" placeholder="g" /></label>
       <label class="field"><span>產出份數</span>
         <input id="rf-serv" type="number" inputmode="decimal" step="0.5" value="${e.servings ?? ""}" placeholder="份" /></label>
     </div>
     <label class="field"><span>食材(一行一項)</span>
       <textarea id="rf-ing" rows="4" placeholder="雞胸肉 200g&#10;白飯 1 碗&#10;醬油 1 匙">${escapeHtml(e.ingredients || "")}</textarea></label>
     <label class="field"><span>步驟(一行一步)</span>
       <textarea id="rf-steps" rows="5" placeholder="雞胸切片醃 10 分鐘&#10;下鍋煎熟&#10;鋪在白飯上、淋醬">${escapeHtml(e.steps || "")}</textarea></label>
     <label class="field"><span>YouTube 連結(可選,會直接嵌入影片)</span>
       <input id="rf-video" type="url" inputmode="url" value="${escapeAttr(e.video_url || "")}" placeholder="https://youtu.be/..." /></label>
     <button class="btn-primary" id="rf-save">${r ? "儲存變更" : "建立食譜"}</button>`
  );
  $("rf-save").addEventListener("click", async () => {
    const name = $("rf-name").value.trim();
    if (!name) {
      toast("請填食譜名稱", true);
      return;
    }
    const body = {
      name,
      calories: intOrNull($("rf-cal").value),
      protein_g: floatOrNull($("rf-pro").value),
      servings: floatOrNull($("rf-serv").value),
      ingredients: $("rf-ing").value.trim() || null,
      steps: $("rf-steps").value.trim() || null,
      video_url: $("rf-video").value.trim() || null,
    };
    try {
      if (r) await api(`/api/recipes/${r.id}`, { method: "PUT", body });
      else await api("/api/recipes", { method: "POST", body });
      closeModal();
      loadRecipes();
      toast(r ? "已更新 ✓" : "已新增 ✓");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ========================================================================
// Exercise (calendar check-in)
// ========================================================================
const EX_TYPES = [
  { key: "running", emoji: "🏃", label: "跑步", hasDistance: true },
  { key: "strength", emoji: "🏋️", label: "重訓", hasDistance: false },
  { key: "yoga", emoji: "🧘", label: "瑜伽", hasDistance: false },
  { key: "cycling", emoji: "🚴", label: "單車", hasDistance: true },
  { key: "swimming", emoji: "🏊", label: "游泳", hasDistance: true },
  { key: "ball", emoji: "⚽", label: "球類", hasDistance: false },
  { key: "walking", emoji: "🚶", label: "走路", hasDistance: true },
  { key: "stretch", emoji: "🤸", label: "伸展", hasDistance: false },
  { key: "other", emoji: "➕", label: "其他", hasDistance: false },
];
const EX_BY_KEY = Object.fromEntries(EX_TYPES.map((t) => [t.key, t]));

const exState = {
  year: state.viewDate.getFullYear(),
  month: state.viewDate.getMonth() + 1, // 1–12
  selected: ymd(startOfToday()),
  days: [], // this month's "YYYY-MM-DD" strings that have a log
};

function exIsCurrentRealMonth() {
  const now = startOfToday();
  return exState.year === now.getFullYear() && exState.month === now.getMonth() + 1;
}

async function loadExerciseMonth() {
  $("ex-month-title").textContent = `${exState.month}月`;
  $("ex-year-month").textContent = `${exState.year}年${exState.month}月`;
  $("ex-next-month").disabled = exIsCurrentRealMonth();
  try {
    const d = await api(tzq(`/api/exercises/month?year=${exState.year}&month=${exState.month}`));
    exState.days = d.days;
    $("ex-streak-num").textContent = d.streak;
    renderExCalendarGrid();
    await loadExerciseDay();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderExCalendarGrid() {
  const grid = $("ex-cal-grid");
  grid.innerHTML = "";
  const todayStr = ymd(startOfToday());
  const first = new Date(exState.year, exState.month - 1, 1);
  const daysInMonth = new Date(exState.year, exState.month, 0).getDate();
  const offset = first.getDay(); // 0 = Sunday
  for (let i = 0; i < offset; i++) {
    const blank = document.createElement("div");
    blank.className = "ex-day-cell blank";
    grid.appendChild(blank);
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${exState.year}-${String(exState.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const cell = document.createElement("div");
    cell.className = "ex-day-cell";
    if (dateStr > todayStr) cell.classList.add("future");
    if (dateStr === todayStr) cell.classList.add("today");
    if (dateStr === exState.selected) cell.classList.add("selected");
    const hasLog = exState.days.includes(dateStr);
    cell.innerHTML = `<span>${day}</span>${hasLog ? '<span class="ex-dot"></span>' : ""}`;
    if (dateStr <= todayStr) {
      cell.addEventListener("click", () => {
        exState.selected = dateStr;
        grid.querySelectorAll(".ex-day-cell").forEach((c) => c.classList.remove("selected"));
        cell.classList.add("selected");
        loadExerciseDay();
      });
    }
    grid.appendChild(cell);
  }
}

function shiftExMonth(delta) {
  let m = exState.month + delta;
  let y = exState.year;
  if (m < 1) { m = 12; y -= 1; }
  if (m > 12) { m = 1; y += 1; }
  exState.year = y;
  exState.month = m;
  const now = startOfToday();
  exState.selected = exIsCurrentRealMonth()
    ? ymd(now)
    : `${y}-${String(m).padStart(2, "0")}-01`;
  loadExerciseMonth();
}

function goToExerciseToday() {
  const now = startOfToday();
  exState.year = now.getFullYear();
  exState.month = now.getMonth() + 1;
  exState.selected = ymd(now);
  loadExerciseMonth();
}

async function loadExerciseDay() {
  const isToday = exState.selected === ymd(startOfToday());
  $("ex-day-title").textContent = isToday ? "今天" : exState.selected;
  $("ex-add").hidden = !isToday;
  const list = $("ex-day-list");
  try {
    const d = await api(tzq("/api/exercises") + `&date=${exState.selected}`);
    list.innerHTML = "";
    $("ex-day-empty").hidden = d.items.length > 0;
    for (const e of d.items) {
      const t = EX_BY_KEY[e.ex_type] || EX_BY_KEY.other;
      const li = document.createElement("li");
      li.className = "entry";
      const detail = [`${e.duration_min} 分`];
      if (e.distance_km != null) detail.push(`${e.distance_km} km`);
      li.innerHTML = `
        <span class="entry-badge emoji">${t.emoji}</span>
        <div class="entry-main">
          <div class="entry-name">${escapeHtml(t.label)}</div>
          <div class="entry-sub">${detail.join(" · ")}</div>
        </div>
        <div class="entry-macro">
          <div class="entry-cal">-${e.calories}</div>
        </div>
        <span class="entry-chev">${ico("chevron")}</span>`;
      li.addEventListener("click", () => openExerciseDetail(e));
      list.appendChild(li);
    }
  } catch (err) {
    toast(err.message, true);
  }
}

function openExerciseDetail(e) {
  const t = EX_BY_KEY[e.ex_type] || EX_BY_KEY.other;
  const detail = [`${e.duration_min} 分鐘`];
  if (e.distance_km != null) detail.push(`${e.distance_km} km`);
  openModal(
    t.label,
    `<div class="fav-item" style="margin-bottom:14px">
       <div class="fav-info">
         <div class="fav-name">${escapeHtml(t.label)}</div>
         <div class="fav-macro">${detail.join(" · ")} · 約 ${e.calories} kcal</div>
       </div>
     </div>
     ${e.note ? `<p class="items-hint">${escapeHtml(e.note)}</p>` : ""}
     <button class="btn-danger" id="ex-del">刪除這筆記錄</button>`
  );
  $("ex-del").addEventListener("click", async () => {
    try {
      await api(`/api/exercises/${e.id}`, { method: "DELETE" });
      closeModal();
      loadExerciseMonth();
      toast("已刪除");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

function openExerciseForm() {
  const typeGrid = EX_TYPES.map(
    (t) => `<div class="ex-type-btn" data-type="${t.key}">
      <div class="ex-type-emoji">${t.emoji}</div>
      <div class="ex-type-label">${t.label}</div>
    </div>`
  ).join("");
  openModal(
    "記一筆運動",
    `<div class="ex-type-grid" id="ex-type-grid">${typeGrid}</div>
     <label class="field"><span>時長(分鐘)</span>
       <input id="ex-duration" type="number" inputmode="numeric" min="1" placeholder="例如:30" /></label>
     <label class="field" id="ex-distance-field" hidden><span>距離(km,可選)</span>
       <input id="ex-distance" type="number" inputmode="decimal" step="0.1" min="0" /></label>
     <label class="field"><span>備註(可選)</span>
       <input id="ex-note" type="text" placeholder="" /></label>
     <button class="btn-primary" id="ex-save">記錄</button>`
  );
  let chosen = null;
  const grid = $("ex-type-grid");
  grid.querySelectorAll(".ex-type-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      chosen = btn.dataset.type;
      grid.querySelectorAll(".ex-type-btn").forEach((b) => b.classList.toggle("active", b === btn));
      $("ex-distance-field").hidden = !EX_BY_KEY[chosen].hasDistance;
    });
  });
  $("ex-save").addEventListener("click", async () => {
    if (!chosen) {
      toast("請選擇運動類型", true);
      return;
    }
    const duration = parseInt($("ex-duration").value, 10);
    if (!duration || duration <= 0) {
      toast("請輸入時長", true);
      return;
    }
    try {
      await api(tzq("/api/exercises"), {
        method: "POST",
        body: {
          ex_type: chosen,
          duration_min: duration,
          distance_km: floatOrNull($("ex-distance").value),
          note: $("ex-note").value.trim() || null,
        },
      });
      closeModal();
      loadExerciseMonth();
      toast("已記錄 ✓");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ========================================================================
// Friends + sharing
// ========================================================================
const MASCOT_FILL = { blue: "#F4A06A", green: "#E8732E", amber: "#E8B04B", red: "#D8503A" };

// Standalone mini mascot (for viewing a friend's "bear state"): state + fill level only.
function mascotSVG(state, fraction) {
  const fill = MASCOT_FILL[state] || MASCOT_FILL.blue;
  const stuffed = state === "red";
  const mouth = stuffed ? "M84,136 q8,9 16,0 q8,-9 16,0" : "M86,134 Q100,144 114,134";
  return `<svg class="mini-mascot" viewBox="0 0 200 215" aria-hidden="true">
    <defs><clipPath id="miniClip"><circle cx="100" cy="120" r="72"/></clipPath></defs>
    <circle cx="100" cy="120" r="72" fill="#fff" stroke="rgba(46,38,32,.14)" stroke-width="1.5"/>
    <g clip-path="url(#miniClip)"><path d="${liquidPath(fraction)}" fill="${fill}" opacity="0.95"/></g>
    <circle cx="80" cy="108" r="6" fill="#2E2620"/><circle cx="120" cy="108" r="6" fill="#2E2620"/>
    <path d="${mouth}" fill="none" stroke="#2E2620" stroke-width="4" stroke-linecap="round"/>
  </svg>`;
}

async function loadFriends() {
  const body = $("friends-body");
  body.innerHTML = `<div class="analyzing"><div class="spinner"></div></div>`;
  try {
    const d = await api("/api/friends");
    let html = "";

    if (d.incoming.length) {
      html += `<h3 class="rd-h">好友邀請</h3>`;
      for (const r of d.incoming) {
        html += `<div class="friend-row" data-fid="${r.friendship_id}">
          <span class="friend-name">${escapeHtml(r.username)}</span>
          <span class="friend-actions">
            <button class="mini-btn ok" data-act="accept">${ico("check")}</button>
            <button class="mini-btn" data-act="reject">${ico("x")}</button>
          </span></div>`;
      }
    }

    html += `<h3 class="rd-h">我的好友</h3>`;
    if (!d.friends.length) {
      html += `<p class="items-hint">還沒有好友,上面輸入對方帳號送出邀請吧。</p>`;
    } else {
      for (const f of d.friends) {
        const tags = [];
        if (f.shares.share_diet) tags.push("飲食");
        else if (f.shares.share_mascot) tags.push("熊狀態");
        if (f.shares.share_recipes) tags.push("食譜");
        html += `<div class="friend-row tappable" data-uid="${f.user_id}" data-name="${escapeAttr(f.username)}">
          <span class="friend-name">${escapeHtml(f.username)}</span>
          <span class="friend-tags">${tags.map((t) => `<i>${t}</i>`).join("") || "<i class='muted'>未分享</i>"}</span>
          <span class="entry-chev">${ico("chevron")}</span></div>`;
      }
    }

    if (d.outgoing.length) {
      html += `<h3 class="rd-h">邀請中</h3>`;
      for (const r of d.outgoing) {
        html += `<div class="friend-row" data-fid="${r.friendship_id}">
          <span class="friend-name">${escapeHtml(r.username)}</span>
          <span class="friend-tags"><i class="muted">等待接受</i></span>
          <button class="mini-btn" data-act="cancel">${ico("x")}</button></div>`;
      }
    }
    body.innerHTML = html;

    // Bind row actions
    body.querySelectorAll(".friend-row").forEach((row) => {
      const fid = row.dataset.fid;
      const accept = row.querySelector('[data-act="accept"]');
      const reject = row.querySelector('[data-act="reject"]');
      const cancel = row.querySelector('[data-act="cancel"]');
      if (accept) accept.addEventListener("click", () => friendAction(`/api/friends/${fid}/accept`, "POST"));
      if (reject) reject.addEventListener("click", () => friendAction(`/api/friends/${fid}`, "DELETE"));
      if (cancel) cancel.addEventListener("click", () => friendAction(`/api/friends/${fid}`, "DELETE"));
      if (row.classList.contains("tappable"))
        row.addEventListener("click", () => openFriendFeed(row.dataset.uid, row.dataset.name));
    });
  } catch (err) {
    toast(err.message, true);
  }
}

async function friendAction(path, method) {
  try {
    await api(path, { method });
    loadFriends();
  } catch (err) {
    toast(err.message, true);
  }
}

async function openFriendFeed(uid, name) {
  openModal(name, `<div class="analyzing"><div class="spinner"></div></div>`);
  try {
    const f = await api(tzq(`/api/friends/${uid}/feed`) + dateParam());
    let html = "";
    if (f.mascot) {
      html += `<div class="friend-mascot">${mascotSVG(f.mascot.state, f.mascot.fraction)}
        <p class="items-hint" style="text-align:center">${escapeHtml(name)} 今天的熊</p></div>`;
    }
    if (f.summary) {
      const s = f.summary;
      html += `<div class="fav-item" style="margin-bottom:12px"><div class="fav-info">
        <div class="fav-name">今天攝取</div>
        <div class="fav-macro">${s.consumed.calories} kcal · ${s.consumed.protein_g}g 蛋白${s.targets ? ` · 目標 ${s.targets.calories_min}–${s.targets.calories_max}` : ""}</div>
      </div></div>`;
      if (f.entries && f.entries.length) {
        html += `<ul class="entry-list">` + f.entries.map((e) =>
          `<li class="entry"><span class="entry-badge">${ico(SOURCE_ICON[e.source] || "pencil")}</span>
            <div class="entry-main"><div class="entry-name">${escapeHtml(e.name)}</div></div>
            <div class="entry-macro"><div class="entry-cal">${e.calories}</div><div class="entry-pro">${e.protein_g}g</div></div></li>`
        ).join("") + `</ul>`;
      } else {
        html += `<p class="items-hint">今天還沒有記錄。</p>`;
      }
    }
    if (f.recipes) {
      html += `<h3 class="rd-h">食譜</h3>`;
      if (!f.recipes.length) html += `<p class="items-hint">還沒有食譜。</p>`;
      html += `<div class="recipe-list" id="friend-recipes"></div>`;
    }
    if (!f.mascot && !f.summary && !f.recipes) {
      html += `<p class="items-hint">這位好友目前沒有分享任何內容。</p>`;
    }
    $("modal-body").innerHTML = html;

    if (f.recipes && f.recipes.length) {
      const wrap = $("friend-recipes");
      f.recipes.forEach((r) => {
        const card = document.createElement("div");
        card.className = "recipe-card";
        const meta = [];
        if (r.calories != null) meta.push(`${r.calories} kcal/份`);
        if (r.protein_g != null) meta.push(`${r.protein_g}g 蛋白`);
        card.innerHTML = `<div class="recipe-card-main"><div class="recipe-name">${escapeHtml(r.name)}</div>
          <div class="recipe-meta">${meta.map((m) => `<span>${m}</span>`).join("")}</div></div>
          <span class="entry-chev">${ico("chevron")}</span>`;
        card.addEventListener("click", () => openRecipeDetail(r, true)); // read-only
        wrap.appendChild(card);
      });
    }
  } catch (err) {
    toast(err.message, true);
  }
}

async function addFriend() {
  const username = $("ff-username").value.trim();
  if (!username) {
    toast("請輸入帳號", true);
    return;
  }
  try {
    const r = await api("/api/friends/request", { method: "POST", body: { username } });
    $("ff-username").value = "";
    toast(r.status === "accepted" ? "已成為好友" : "邀請已送出");
    loadFriends();
  } catch (err) {
    toast(err.message, true);
  }
}

async function openShareSettings() {
  openModal("分享設定", `<div class="analyzing"><div class="spinner"></div></div>`);
  let p = { share_mascot: true, share_diet: false, share_recipes: false };
  try {
    p = await api("/api/share");
  } catch (_) {}
  const row = (id, label, desc, on) =>
    `<label class="switch-row">
       <span><b>${label}</b><small>${desc}</small></span>
       <input type="checkbox" id="${id}" ${on ? "checked" : ""} />
     </label>`;
  $("modal-body").innerHTML =
    `<p class="items-hint">選擇好友可以看到你的哪些東西(套用到所有好友)。</p>` +
    row("sh-mascot", "今天的熊狀態", "只看得到你的吉祥物(綠/紅),看不到數字", p.share_mascot) +
    row("sh-diet", "飲食記錄", "當日攝取數字與每一筆記錄", p.share_diet) +
    row("sh-recipes", "食譜", "你建立的所有食譜", p.share_recipes) +
    `<button class="btn-primary" id="sh-save">儲存</button>`;
  $("sh-save").addEventListener("click", async () => {
    try {
      await api("/api/share", {
        method: "PUT",
        body: {
          share_mascot: $("sh-mascot").checked,
          share_diet: $("sh-diet").checked,
          share_recipes: $("sh-recipes").checked,
        },
      });
      closeModal();
      toast("已更新分享設定");
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ========================================================================
// Utils
// ========================================================================
let toastTimer;
function toast(msg, bad = false) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast" + (bad ? " bad" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 2400);
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) {
  return escapeHtml(s);
}

// ========================================================================
// Boot
// ========================================================================
function setupApp() {
  $("logout").addEventListener("click", doLogout);
  $("open-profile").addEventListener("click", openProfile);
  $("setup-cta").addEventListener("click", openProfile);
  $("act-photo").addEventListener("click", openPhoto);
  $("act-scan").addEventListener("click", openScan);
  $("act-manual").addEventListener("click", openManual);
  $("act-fav").addEventListener("click", openFavorites);
  $("camera-input").addEventListener("change", (e) => {
    handlePhoto(e.target.files[0]);
    e.target.value = "";
  });
  document.querySelectorAll(".tabbar-btn").forEach((b) =>
    b.addEventListener("click", () => showView(b.dataset.view))
  );
  $("date-prev").addEventListener("click", () => shiftDate(-1));
  $("date-next").addEventListener("click", () => shiftDate(1));
  $("date-center").addEventListener("click", goToday);
  $("stats-seg").addEventListener("click", (e) => {
    const b = e.target.closest(".seg-btn");
    if (!b) return;
    statsRange = b.dataset.range;
    loadStats();
  });
  $("stats-chart").addEventListener("click", (e) => {
    const col = e.target.closest(".bar-col.tappable");
    if (col && col.dataset.date) goToDate(col.dataset.date);
  });
  $("recipe-add").addEventListener("click", () => openRecipeForm(null));
  $("ff-add").addEventListener("click", addFriend);
  $("ff-username").addEventListener("keydown", (e) => {
    if (e.key === "Enter") addFriend();
  });
  $("share-settings").addEventListener("click", openShareSettings);
  $("ex-prev-month").addEventListener("click", () => shiftExMonth(-1));
  $("ex-next-month").addEventListener("click", () => shiftExMonth(1));
  $("ex-today-month").addEventListener("click", goToExerciseToday);
  $("ex-add").addEventListener("click", openExerciseForm);
  renderIcons();
  $("modal-close").addEventListener("click", closeModal);
  $("modal").addEventListener("click", (e) => {
    if (e.target === $("modal")) closeModal();
  });
}

setupAuth();
setupApp();
if (state.token) {
  showApp();
} else {
  authScreen.hidden = false;
}

// Service worker
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
