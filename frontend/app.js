"use strict";

const RING_CIRC = 2 * Math.PI * 52; // 326.7
const TOKEN_KEY = "diet_token";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  username: localStorage.getItem("diet_user") || "",
  authMode: "login",
};

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
const appScreen = $("app-screen");

// ========================================================================
// 認證
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
// 主畫面
// ========================================================================
function showApp() {
  authScreen.hidden = true;
  appScreen.hidden = false;
  $("who").textContent = state.username;
  refresh();
}

async function refresh() {
  await Promise.all([loadSummary(), loadEntries()]);
}

// ---------- Summary / rings ----------
function setRing(prefix, value, fraction, status, noteText) {
  const card = $(prefix + "-card");
  const arc = $(prefix + "-arc");
  $(prefix + "-value").textContent = value;
  $(prefix + "-note").textContent = noteText;
  const f = Math.max(0, Math.min(1, fraction));
  arc.style.strokeDashoffset = String(RING_CIRC * (1 - f));
  card.classList.remove("good", "warn", "bad");
  if (status) card.classList.add(status);
}

async function loadSummary() {
  const s = await api("/api/summary");
  $("today-date").textContent = s.date;

  // 熱量:以 calories_max 當環滿格基準
  const cal = s.consumed.calories;
  const calFrac = cal / s.targets.calories_max;
  let calStatus = "warn"; // under
  let calNote;
  if (s.status.calories === "in_range") {
    calStatus = "good";
    calNote = `達標 · 剩 ${s.targets.calories_max - cal}`;
  } else if (s.status.calories === "over") {
    calStatus = "bad";
    calNote = `超標 ${cal - s.targets.calories_max}`;
  } else {
    calNote = `離 ${s.targets.calories_min} 還差 ${s.remaining.calories_to_min}`;
  }
  setRing("cal", cal, calFrac, calStatus, calNote);

  // 蛋白:以 protein_min 當滿格基準
  const pro = s.consumed.protein_g;
  const proFrac = pro / s.targets.protein_min;
  const proStatus = s.status.protein === "met" ? "good" : "bad";
  const proNote =
    s.status.protein === "met"
      ? `達標 ${pro} / ${s.targets.protein_min}`
      : `差 ${s.remaining.protein_to_min} g`;
  setRing("pro", pro, proFrac, proStatus, proNote);

  // 蛋白不足明顯提示(cut 期最關鍵)
  const alert = $("protein-alert");
  if (s.status.protein === "short") {
    alert.hidden = false;
    alert.textContent = `⚠️ 蛋白質還差 ${s.remaining.protein_to_min}g 才到 ${s.targets.protein_min}g 下限`;
  } else {
    alert.hidden = true;
  }
}

// ---------- Entries ----------
const SOURCE_BADGE = { photo: "📷", manual: "✏️", favorite: "⭐" };

async function loadEntries() {
  const entries = await api("/api/entries");
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
      <span class="entry-badge">${SOURCE_BADGE[e.source] || "🍽️"}</span>
      <div class="entry-main">
        <div class="entry-name"></div>
        <div class="entry-sub">${time}${e.note ? " · " + escapeHtml(e.note) : ""}</div>
      </div>
      <div class="entry-macro">
        <div class="entry-cal">${e.calories}</div>
        <div class="entry-pro">${e.protein_g}g</div>
      </div>
      <button class="entry-del" title="刪除">✕</button>`;
    li.querySelector(".entry-name").textContent = e.name;
    li.querySelector(".entry-del").addEventListener("click", async () => {
      try {
        await api(`/api/entries/${e.id}`, { method: "DELETE" });
        await refresh();
      } catch (err) {
        toast(err.message, true);
      }
    });
    list.appendChild(li);
  }
}

async function createEntry(payload) {
  await api("/api/entries", { method: "POST", body: payload });
  closeModal();
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
  $("modal").hidden = true;
  $("modal-body").innerHTML = "";
}

function confirmForm(prefill, source) {
  return `
    <label class="field"><span>名稱</span>
      <input id="m-name" type="text" value="${escapeAttr(prefill.name || "")}" /></label>
    <label class="field"><span>熱量 (kcal)</span>
      <input id="m-cal" type="number" inputmode="numeric" value="${prefill.calories ?? ""}" /></label>
    <label class="field"><span>蛋白質 (g)</span>
      <input id="m-pro" type="number" inputmode="decimal" step="0.1" value="${prefill.protein_g ?? ""}" /></label>
    <label class="field"><span>備註(可選)</span>
      <input id="m-note" type="text" placeholder="" /></label>
    <button class="btn-primary" id="m-save">確認記錄</button>
    <input type="hidden" id="m-source" value="${source}" />`;
}

function bindConfirm() {
  $("m-save").addEventListener("click", async () => {
    const name = $("m-name").value.trim();
    const calories = parseInt($("m-cal").value, 10);
    const protein_g = parseFloat($("m-pro").value);
    if (!name || isNaN(calories) || isNaN(protein_g)) {
      toast("請填完整名稱與數值", true);
      return;
    }
    try {
      await createEntry({
        name,
        calories,
        protein_g,
        source: $("m-source").value,
        note: $("m-note").value.trim() || null,
      });
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ---------- 手動輸入 ----------
function openManual() {
  openModal("手動輸入", confirmForm({}, "manual"));
  bindConfirm();
}

// ---------- 拍照分析 ----------
function openPhoto() {
  $("camera-input").click();
}

async function handlePhoto(file) {
  if (!file) return;
  const url = URL.createObjectURL(file);
  openModal(
    "拍照辨識",
    `<img class="preview-img" src="${url}" alt="預覽" />
     <div class="analyzing"><div class="spinner"></div>Gemini 辨識中…</div>`
  );
  try {
    const form = new FormData();
    form.append("file", file);
    const result = await api("/api/analyze", { method: "POST", body: form, isForm: true });
    const itemsHtml =
      result.items && result.items.length
        ? `<p class="items-hint">辨識內容:${result.items
            .map((i) => escapeHtml(i.food))
            .join("、")} · 信心 ${escapeHtml(result.confidence || "")}</p>`
        : "";
    $("modal-body").innerHTML =
      `<img class="preview-img" src="${url}" alt="預覽" />` +
      itemsHtml +
      confirmForm(result, "photo");
    bindConfirm();
  } catch (err) {
    $("modal-body").innerHTML =
      `<p class="items-hint" style="color:var(--bad)">${escapeHtml(err.message)}</p>` +
      confirmForm({}, "manual");
    bindConfirm();
  }
}

// ---------- 常用食物 ----------
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
      <p class="items-hint">新增常用食物</p>
      <label class="field"><span>名稱</span><input id="nf-name" type="text" /></label>
      <label class="field"><span>熱量 (kcal)</span><input id="nf-cal" type="number" inputmode="numeric" /></label>
      <label class="field"><span>蛋白質 (g)</span><input id="nf-pro" type="number" inputmode="decimal" step="0.1" /></label>
      <button class="btn-primary" id="nf-save">新增到常用</button>`;
    $("modal-body").innerHTML = html;

    // 綁定每個常用食物
    $("modal-body").querySelectorAll(".fav-item").forEach((row) => {
      const id = row.dataset.id;
      const f = foods.find((x) => String(x.id) === id);
      row.querySelector('[data-act="add"]').addEventListener("click", async () => {
        try {
          await createEntry({
            name: f.name,
            calories: f.calories,
            protein_g: f.protein_g,
            source: "favorite",
          });
        } catch (err) {
          toast(err.message, true);
        }
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
  $("act-photo").addEventListener("click", openPhoto);
  $("act-manual").addEventListener("click", openManual);
  $("act-fav").addEventListener("click", openFavorites);
  $("camera-input").addEventListener("change", (e) => {
    handlePhoto(e.target.files[0]);
    e.target.value = "";
  });
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
