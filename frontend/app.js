// ── 공통 유틸 ─────────────────────────────────
const $ = (id) => document.getElementById(id);
const views = { list: $("viewList"), create: $("viewCreate"), chat: $("viewChat") };

function showView(name) {
  for (const v of Object.values(views)) v.hidden = true;
  views[name].hidden = false;
}

let SCHEMA = null;      // {character:[...], player:[...]}
let SETTINGS_DEF = null; // 슬라이더 정의
let currentCharId = null;
let currentSettings = {}; // 현재 캐릭터의 대화 설정

// 새 캐릭터 폼을 열 때 미리 채워둘 기본값(유리). 이름만 바꿔 저장하면 편하다.
const DEFAULT_CHARACTER = {
  name: "유리",
  age_range: "20",
  type: "여성/미소녀",
  tagline: "유저를 짝사랑하는 소꿉친구(동생)",
  personality: "오빠(유저)를 매우 친근하게 대함. 기본적으로 착하나, 오빠가 다른 여자와 대화하는 모습을 보면 큰 질투를 느낌.\n감정 기복이 크다. 오빠가 다른 여자 얘기를 꺼내거나 무심하게 굴면 눈에 띄게 삐지고 토라지지만, 다정하게 대해주면 금세 풀려서 활짝 웃는다. 짝사랑을 들키지 않으려 애쓰지만 자주 티가 난다.",
  speech_style: "반말. 밝고 애교 섞인 톤에 약간 메스가키 같은 짓궂음이 있음. 오빠를 놀리듯 굴다가도 삐지면 뾰로통하게, 질투 나면 토라진 말투가 됨. \"~잖아\", \"~니까\", \"치\" 같은 어미를 자주 씀.",
  voice_examples: [
    "정말~ 오빠는 나 없이는 안 된다니까~?",
    "오빠 오늘 아침도 내가 깨워줬잖아. 고마운 줄 알아~",
    "...딴 여자랑 얘기하는게 그렇게 재밌어?",
    "치, 됐어. 오빠 미워… 아니, 안 미워. 그니까 나만 봐.",
    "어? 그, 그런 거 아니거든?! 오해하지 마."
  ],
  address_term: "오빠",
  nickname: "오빠야",
  nickname_threshold: 60,
  background: "대학생. 부유한 집안. 어릴 때부터 오빠(유저)를 짝사랑해, 서울로 올라간 오빠를 따라 근처 대학으로 진학하고 바로 옆집으로 이사 왔다. 오빠와의 미래를 위해 착실히 아르바이트로 적금 중. 오빠에게 여자친구가 있는지 늘 궁금해한다. 매일 아침 오빠를 깨우러 그의 집에 간다.",
  world: "현대 일상물",
  scene: "이른 아침, 유리가 옆집인 오빠(유저)의 집에 들어와 아직 자고 있는 오빠를 깨우러 온 참이다. 커튼을 걷으며 \"오빠, 아침이야! 언제까지 잘 거야~\" 하고 부르는 상황.",
  relationship: "소꿉친구",
  initial_affinity: 50,
  appearance: "옅은 갈색의 긴 머리, 머리와 같은 옅은 갈색 눈. 한국인 아이돌과 같은 특출난 이목구비를 가진 20세 여대생.\n글래머러스한 몸매 — 가슴과 엉덩이가 크고, 허리는 잘록하며 배에는 선명한 11자 복근이 있음. 키는 보통.",
  outfit: "노출도가 꽤 있는 옷과 과감한 속옷을 위주로 입고 있다.\n흰색과 빨간색 조합의 컬러를 선호.",
  moods: ["경계", "무관심", "냉담", "짜증", "차분", "호기심", "흥미", "누그러짐", "다정", "쓸쓸", "슬픔", "당황", "설렘", "집착", "애욕", "행복", "토라짐", "두근거림", "부끄러움", "질투"]
};
const DEFAULT_PLAYER = {
  name: "성태",
  gender: "남성",
  age_range: "27",
  background: "자취 중인 대학생. 옆집 소꿉친구 유리를 편한 여동생처럼 대하며, 유리의 마음은 아직 눈치채지 못하고 있다.",
  appearance: "20대 중후반의 평범한 한국 남성. 키는 보통보다 약간 큰 편, 마른 체형. 특별히 꾸미지 않는 수수한 인상."
};

// ── 호감도 색 (차가운 빗빛 → 따뜻한 호박색) ──────
function affinityColor(v) {
  const t = Math.max(0, Math.min(100, v)) / 100;
  const hue = 210 + (35 - 210) * t;
  const sat = 30 + 25 * t;
  const light = 50 + 8 * t;
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

// ── 스키마 → 폼 필드 자동 생성 (preset이 있으면 그 값으로 미리 채움) ──
function buildFields(container, schema, preset = {}) {
  container.innerHTML = "";
  for (const f of schema) {
    const wrap = document.createElement("label");
    wrap.className = "field";

    const label = document.createElement("span");
    label.className = "field__label";
    label.textContent = f.label + (f.required ? " *" : "");
    wrap.appendChild(label);

    // 채울 값: preset에 있으면 그것, 없으면 스키마 default
    const hasPreset = Object.prototype.hasOwnProperty.call(preset, f.key);
    const value = hasPreset ? preset[f.key] : f.default;

    let el;
    let placeholder = f.hint || "";
    if (f.type === "textarea") {
      el = document.createElement("textarea");
      el.rows = 2;
    } else if (f.type === "number") {
      el = document.createElement("input");
      el.type = "number";
    } else if (f.type === "list" || f.type === "tags") {
      el = document.createElement("textarea");
      el.rows = 2;
      placeholder = placeholder + " (한 줄에 하나)";
      if (value && value.length) el.value = value.join("\n");
    } else {
      el = document.createElement("input");
      el.type = "text";
    }
    el.className = "field__input";
    el.dataset.key = f.key;
    el.dataset.type = f.type;
    if (placeholder) el.placeholder = placeholder;
    if (value !== undefined && f.type !== "list" && f.type !== "tags") {
      el.value = value;
    }
    wrap.appendChild(el);
    container.appendChild(wrap);
  }
}

// ── 폼에서 값 수집 ──────────────────────────────
function collectFields(container) {
  const out = {};
  for (const el of container.querySelectorAll("[data-key]")) {
    const key = el.dataset.key;
    const type = el.dataset.type;
    let val = el.value.trim();
    if (type === "list" || type === "tags") {
      out[key] = val ? val.split("\n").map((s) => s.trim()).filter(Boolean) : [];
    } else if (type === "number") {
      out[key] = val === "" ? 0 : Number(val);
    } else {
      out[key] = val;
    }
  }
  return out;
}

// ── 캐릭터 목록 ────────────────────────────────
async function loadList() {
  const res = await fetch("/api/characters");
  const chars = await res.json();
  const cards = $("cards");
  cards.innerHTML = "";
  $("listEmpty").hidden = chars.length > 0;
  for (const c of chars) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card__portrait"></div>
      <div class="card__body">
        <h3 class="card__name">${escapeHtml(c.name)}</h3>
        <p class="card__tag">${escapeHtml(c.tagline || "")}</p>
      </div>
      <button class="card__del" title="삭제" data-id="${c.id}">✕</button>`;
    card.querySelector(".card__del").addEventListener("click", async (e) => {
      e.stopPropagation();
      if (confirm(`'${c.name}' 캐릭터를 삭제할까?`)) {
        await fetch(`/api/characters/${c.id}`, { method: "DELETE" });
        loadList();
      }
    });
    card.addEventListener("click", () => openChat(c.id));
    cards.appendChild(card);
  }
}

// ── 생성 화면 ─────────────────────────────────
function openCreate() {
  buildFields($("charFields"), SCHEMA.character, DEFAULT_CHARACTER);
  buildFields($("playerFields"), SCHEMA.player, DEFAULT_PLAYER);
  showView("create");
}

async function saveCharacter() {
  const character = collectFields($("charFields"));
  const player = collectFields($("playerFields"));
  if (!character.name) { alert("이름은 필수야."); return; }

  // 생성 시 AI가 초기 상태를 스캔하므로 시간이 걸린다 → 로딩 오버레이 표시
  showOverlay();
  try {
    const res = await fetch("/api/characters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character, player }),
    });
    const data = await res.json();
    hideOverlay();
    openChat(data.id);
  } catch (e) {
    hideOverlay();
    alert("캐릭터 생성에 실패했어. 서버와 Ollama가 켜져 있는지 확인해줘.");
  }
}

// ── 로딩 오버레이 ─────────────────────────────
let overlayTimer = null;
function showOverlay() {
  const ov = $("overlay");
  ov.hidden = false;
  let sec = 0;
  $("overlayTimer").textContent = "0초";
  overlayTimer = setInterval(() => {
    sec++;
    $("overlayTimer").textContent = sec + "초";
  }, 1000);
}
function hideOverlay() {
  $("overlay").hidden = true;
  if (overlayTimer) { clearInterval(overlayTimer); overlayTimer = null; }
}

// ── 대화 화면 ─────────────────────────────────
async function openChat(charId) {
  currentCharId = charId;
  $("log").innerHTML = "";
  showView("chat");
  try {
    const res = await fetch(`/api/chat/${charId}/state`);
    const data = await res.json();
    const c = data.character || {};
    $("charName").textContent = c.name || "캐릭터";
    $("scene").textContent = c.scene || "";
    $("memTitle").textContent = (c.name || "캐릭터") + "가 기억하는 것";
    $("memTitle").dataset.base = (c.name || "캐릭터") + "가 기억하는 것";
    document.title = c.name || "캐릭터 챗";
    currentSettings = data.settings || {};
    renderState(data);
    // 저장된 대화 기록 복원 (뒤로 갔다 와도, 서버를 껐다 켜도 유지)
    if (data.history && data.history.length) {
      for (const turn of data.history) {
        addMessage(turn.content, turn.role === "user" ? "user" : "char");
      }
    }
  } catch (e) {
    $("scene").textContent = "상태를 불러오지 못했어.";
  }
  $("input").focus();
}

function showUnlockEffect() {
  // 상한 해방 순간: 대화창에 특별한 안내 + 힌트 박스 강조
  const div = document.createElement("div");
  div.className = "unlock-flash";
  div.textContent = "── 마음의 빗장이 풀렸다 ──";
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

function renderSecret(unlock) {
  const box = $("secretBox");
  if (!unlock || !unlock.has_hint) { box.hidden = true; return; }
  box.hidden = false;
  $("secretText").textContent = unlock.hint_masked || "";
  if (unlock.unlocked) {
    box.classList.add("secret--unlocked");
    $("secretLabel").textContent = "마음을 열었다";
  } else {
    box.classList.remove("secret--unlocked");
    $("secretLabel").textContent = "이 아이가 바라는 것…";
  }
}

function renderState(s) {
  $("affinityValue").textContent = s.affinity;
  $("affinityFill").style.width = s.affinity + "%";
  $("affinityFill").style.backgroundColor = affinityColor(s.affinity);
  const trust = s.trust ?? 0;
  $("trustValue").textContent = trust;
  $("trustFill").style.width = trust + "%";
  $("mood").textContent = s.mood;
  renderSecret(s.unlock);
  const memEl = $("memories");
  const olderEl = $("memoriesOlder");
  const toggleBtn = $("memToggle");
  memEl.innerHTML = "";
  olderEl.innerHTML = "";
  const mems = s.memories || [];
  const RECENT = 10;

  if (mems.length === 0) {
    const li = document.createElement("li");
    li.className = "memories__empty";
    li.textContent = "아직 기억하는 게 없어.";
    memEl.appendChild(li);
    olderEl.hidden = true;
    toggleBtn.hidden = true;
  } else {
    // 최근 10개는 항상 표시 (최신부터)
    const recent = mems.slice(-RECENT).reverse();
    for (const m of recent) {
      const li = document.createElement("li");
      li.textContent = m;
      memEl.appendChild(li);
    }
    // 그보다 오래된 것들은 토글 버튼으로 여닫기
    const older = mems.slice(0, Math.max(0, mems.length - RECENT)).reverse();
    if (older.length > 0) {
      for (const m of older) {
        const li = document.createElement("li");
        li.textContent = m;
        olderEl.appendChild(li);
      }
      toggleBtn.hidden = false;
      const isOpen = !olderEl.hidden;
      toggleBtn.textContent = (isOpen ? "▾ 오래된 기억 숨기기" : `▸ 그 외 ${older.length}개 더 보기`);
    } else {
      toggleBtn.hidden = true;
      olderEl.hidden = true;
    }
  }
  // 제목에 총 개수
  const memTitle = $("memTitle");
  if (memTitle) {
    const base = memTitle.dataset.base || memTitle.textContent.replace(/\s*\(\d+\)$/, "");
    memTitle.dataset.base = base;
    memTitle.textContent = mems.length ? `${base} (${mems.length})` : base;
  }
}

// 대사/지문 분리: 괄호 '( )' 안은 지문(행동·상황), 밖은 대사.
// 각각 다른 스타일의 조각으로 쪼개 캐릭터챗처럼 또렷하게 보여준다.
function appendSegments(container, text) {
  const parts = text.split(/(\([^)]*\))/g);
  for (let part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const seg = document.createElement("span");
    if (trimmed.startsWith("(") && trimmed.endsWith(")")) {
      seg.className = "seg seg--narration";
      seg.textContent = trimmed.slice(1, -1).trim();   // 괄호 벗겨 지문으로
    } else {
      seg.className = "seg seg--dialogue";
      seg.textContent = trimmed;
    }
    container.appendChild(seg);
  }
  // 조각이 하나도 안 잡히면(이상한 경우) 원문 그대로
  if (!container.childNodes.length) {
    const seg = document.createElement("span");
    seg.className = "seg seg--dialogue";
    seg.textContent = text;
    container.appendChild(seg);
  }
}

function addMessage(text, who) {
  // 캐릭터 응답이 비어 오면(모델 문제) 빈 말풍선 대신 안내를 띄운다.
  if (who === "char" && (!text || !text.trim())) {
    text = "(…응답이 비어서 왔어. '진행하기'나 다시 말을 걸어봐.)";
  }
  const div = document.createElement("div");
  div.className = "msg msg--" + who;
  appendSegments(div, text);
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "typing";
  div.innerHTML = "<span></span><span></span><span></span>";
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
  return div;
}

async function send(action, dialogue) {
  // 행동/상황과 대화를 하나의 메시지로 합친다. 형식: (행동) "대화"
  let message = "";
  if (action) message += `(${action})`;
  if (dialogue) message += (message ? " " : "") + dialogue;
  if (!message) return;

  addMessage(message, "user");
  $("actionInput").value = "";
  $("input").value = "";
  $("actionInput").disabled = true;
  $("input").disabled = true;
  $("sendBtn").disabled = true;
  const typing = showTyping();
  try {
    const res = await fetch(`/api/chat/${currentCharId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    typing.remove();
    addMessage(data.reply, "char");
    renderState(data);
    if (data.just_unlocked) showUnlockEffect();
  } catch (e) {
    typing.remove();
    addMessage("(응답을 받지 못했어. 잠시 후 다시.)", "char");
  } finally {
    $("actionInput").disabled = false;
    $("input").disabled = false;
    $("sendBtn").disabled = false;
    $("input").focus();
  }
}

async function advance() {
  // 유저 입력 없이 이야기를 다음으로 진전
  $("actionInput").disabled = true;
  $("input").disabled = true;
  $("sendBtn").disabled = true;
  $("advanceBtn").disabled = true;
  const typing = showTyping();
  try {
    const res = await fetch(`/api/chat/${currentCharId}/advance`, { method: "POST" });
    const data = await res.json();
    typing.remove();
    addMessage(data.reply, "char");
    renderState(data);
  } catch (e) {
    typing.remove();
    addMessage("(응답을 받지 못했어. 잠시 후 다시.)", "char");
  } finally {
    $("actionInput").disabled = false;
    $("input").disabled = false;
    $("sendBtn").disabled = false;
    $("advanceBtn").disabled = false;
    $("input").focus();
  }
}

async function suggestLine() {
  // 할 말 추천: 결과를 대화칸에 채운다(자동 전송 아님 — 유저가 고쳐서 보낼 수 있게).
  const btn = $("suggestBtn");
  const prev = btn.textContent;
  btn.disabled = true;
  btn.textContent = "생각 중…";
  try {
    const res = await fetch(`/api/chat/${currentCharId}/suggest`, { method: "POST" });
    const data = await res.json();
    if (data.line) {
      $("input").value = data.line;
      $("input").focus();
    }
  } catch (e) {
    /* 조용히 무시 — 추천 실패해도 직접 입력하면 됨 */
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
}

// ── 대화 설정 모달 ────────────────────────────
function openSettings() {
  const wrap = $("settingsFields");
  wrap.innerHTML = "";
  for (const def of SETTINGS_DEF) {
    const cur = currentSettings[def.key] ?? def.default;
    const field = document.createElement("div");
    field.className = "setting";
    field.innerHTML = `
      <div class="setting__label">
        <span class="setting__name">${def.label}</span>
        <span class="setting__val" id="sv_${def.key}"></span>
      </div>
      <input class="setting__slider" type="range" id="ss_${def.key}"
             min="${def.min}" max="${def.max}" step="1" value="${cur}">
      <div class="setting__ends"><span>${def.low_label}</span><span>${def.high_label}</span></div>`;
    wrap.appendChild(field);

    const slider = field.querySelector(`#ss_${def.key}`);
    const valEl = field.querySelector(`#sv_${def.key}`);
    const showVal = () => { valEl.textContent = `${slider.value} / ${def.max}`; };
    showVal();
    // 슬라이더를 놓으면 저장
    slider.addEventListener("input", showVal);
    slider.addEventListener("change", saveSettings);
  }
  $("settingsModal").hidden = false;
}

function closeSettings() { $("settingsModal").hidden = true; }

async function saveSettings() {
  const settings = {};
  for (const def of SETTINGS_DEF) {
    const slider = $(`ss_${def.key}`);
    if (slider) settings[def.key] = Number(slider.value);
  }
  currentSettings = settings;
  try {
    await fetch(`/api/chat/${currentCharId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings }),
    });
  } catch (e) { /* 저장 실패해도 다음 대화에 반영 시도 */ }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── 이벤트 연결 ────────────────────────────────
$("newCharBtn").addEventListener("click", openCreate);
$("backFromCreate").addEventListener("click", () => { showView("list"); loadList(); });
$("saveCharBtn").addEventListener("click", saveCharacter);
$("backFromChat").addEventListener("click", () => { showView("list"); loadList(); });
$("resetBtn").addEventListener("click", async () => {
  await fetch(`/api/chat/${currentCharId}/reset`, { method: "POST" });
  openChat(currentCharId);
});
$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const action = $("actionInput").value.trim();
  const dialogue = $("input").value.trim();
  if (action || dialogue) send(action, dialogue);
});
$("advanceBtn").addEventListener("click", advance);
$("suggestBtn").addEventListener("click", suggestLine);
$("memToggle").addEventListener("click", () => {
  const olderEl = $("memoriesOlder");
  olderEl.hidden = !olderEl.hidden;
  const btn = $("memToggle");
  const count = olderEl.children.length;
  btn.textContent = olderEl.hidden ? `▸ 그 외 ${count}개 더 보기` : "▾ 오래된 기억 숨기기";
});
$("settingsBtn").addEventListener("click", openSettings);
$("settingsClose").addEventListener("click", closeSettings);
$("settingsModal").addEventListener("click", (e) => {
  if (e.target === $("settingsModal")) closeSettings();  // 바깥 클릭 시 닫기
});

// ── 시작 ──────────────────────────────────────
async function init() {
  hideOverlay();              // 페이지 시작 시 오버레이는 무조건 숨김 (잔류 방지)
  showView("list");           // 먼저 목록 화면부터 보이기
  try {
    const res = await fetch("/api/schema");
    SCHEMA = await res.json();
    const sres = await fetch("/api/settings-def");
    SETTINGS_DEF = await sres.json();
    await loadList();
  } catch (e) {
    console.error("초기화 실패:", e);
  }
}
init();
