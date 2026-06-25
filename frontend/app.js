"use strict";

const TOKEN_KEY = "diet_token";
// 自動偵測這台裝置的時區,讓「今天」依使用者所在時區計算(後端沒帶就退回台北)。
const TZ =
  (Intl.DateTimeFormat().resolvedOptions().timeZone) || "Asia/Taipei";
const tzq = (path) => path + (path.includes("?") ? "&" : "?") + "tz=" + encodeURIComponent(TZ);

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

// ---------- Summary / 吉祥物 ----------
// 水位 path:依比例 frac(0~1+)畫出有波浪頂的液體,裁切在身體圓內。
function liquidPath(frac) {
  const left = 24, right = 176, bottom = 196, fullTop = 44;
  const f = Math.max(0.02, Math.min(frac, 1.12)); // 容許略微溢出視覺
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
    stuffed ? "M84,136 q8,9 16,0 q8,-9 16,0" : "M86,134 Q100,144 114,134"
  );
}

async function loadSummary() {
  const s = await api(tzq("/api/summary"));
  $("today-date").textContent = s.date;
  const cal = s.consumed.calories;
  const pro = s.consumed.protein_g;
  $("cal-value").textContent = cal;

  // === 熱量吉祥物 ===
  if (!s.has_profile) {
    // 沒設定身體數據:不評估,只顯示熱量,吉祥物維持中性、半滿。
    setMascotState("state-blue");
    $("liquid").setAttribute("d", liquidPath(0.4));
    $("cal-note").textContent = "今天吃了";
    $("setup-cta").hidden = false;
  } else {
    $("setup-cta").hidden = true;
    const cap = s.cap; // TDEE 優先,否則熱量上限
    $("liquid").setAttribute("d", liquidPath(cal / cap));

    let cls, note;
    if (s.status.tdee === "over") {
      cls = "state-red";
      const over = cal - s.targets.tdee;
      note = `🚨 超過 TDEE ${over} kcal`;
    } else if (s.status.calories === "in_range") {
      cls = "state-green";
      note = `達標 ✓ 目標 ${s.targets.calories_min}–${s.targets.calories_max}`;
    } else if (s.status.calories === "over") {
      cls = "state-amber";
      const toTdee = s.remaining.calories_to_tdee;
      note = `超出目標 · 距 TDEE 還有 ${toTdee}`;
    } else {
      cls = "state-blue";
      note = `離目標還差 ${s.remaining.calories_to_min} kcal`;
    }
    setMascotState(cls);
    $("cal-note").textContent = note;
  }

  // === 蛋白條 ===
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
    $("pro-note").textContent = met ? "蛋白達標 💪" : `還差 ${s.remaining.protein_to_min} g`;
    const alert = $("protein-alert");
    alert.hidden = met;
    if (!met)
      alert.textContent = `⚠️ 蛋白質還差 ${s.remaining.protein_to_min}g 才到 ${pmin}g`;
  }
}

// ---------- Entries ----------
const SOURCE_BADGE = { photo: "📷", manual: "✏️", favorite: "⭐" };

async function loadEntries() {
  const entries = await api(tzq("/api/entries"));
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
  await api(tzq("/api/entries"), { method: "POST", body: payload });
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
    "辨識食物照片",
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
// 每日目標 / 身體數據設定
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

    <button class="btn-primary" id="pf-save">儲存目標</button>`;

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
