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
    // 재입장 시 마지막 장면 이미지가 있으면 그걸로, 없으면 기준 초상.
    renderPortrait(data.scene || data.portrait);
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

// ── 초상(캐릭터 이미지) ────────────────────────
let portraitConfirmed = false;   // 기준 초상 확정 여부(장면 이미지 생성 가능 조건)
let sceneBusy = false;           // 장면 이미지 생성 중 중복 방지
function renderPortrait(url) {
  const img = $("portraitImg"), empty = $("portraitEmpty"), loading = $("portraitLoading");
  loading.hidden = true;
  portraitConfirmed = !!url;
  syncAdultToggle("adultTogglePortrait");   // 초상 영역 토글을 현재 설정값으로
  if (url) {
    // 초상 확정 상태: 이미지 표시, 생성 버튼 숨김(변경 불가), 갤러리 버튼 노출
    img.src = url;
    img.hidden = false;
    empty.hidden = true;
    $("galleryBtn").hidden = false;
  } else {
    img.hidden = true;
    img.removeAttribute("src");
    empty.hidden = false;
    $("galleryBtn").hidden = true;
  }
}

async function openGallery() {
  const grid = $("galleryGrid"), empty = $("galleryEmpty");
  grid.innerHTML = "";
  empty.hidden = true;
  try {
    const res = await fetch(`/api/characters/${currentCharId}/gallery`);
    const data = await res.json();
    if (!data.images || !data.images.length) {
      empty.hidden = false;
    } else {
      for (const url of data.images) {
        const im = document.createElement("img");
        im.src = url;
        im.loading = "lazy";
        im.addEventListener("click", () => openLightbox(url));   // 새 탭 대신 인페이지 확대
        grid.appendChild(im);
      }
    }
  } catch (e) {
    empty.hidden = false;
  }
  $("galleryModal").hidden = false;
}
function closeGallery() { $("galleryModal").hidden = true; }

// ── 라이트박스(이미지 인페이지 확대) ──────────────
function openLightbox(url) {
  $("lightboxImg").src = url;
  $("lightbox").hidden = false;
}
function closeLightbox() {
  $("lightbox").hidden = true;
  $("lightboxImg").removeAttribute("src");
}

let portraitTimer = null;
function portraitLoadingOn() {
  $("portraitEmpty").hidden = true;
  $("portraitLoading").hidden = false;
  let sec = 0;
  $("portraitTimer").textContent = "그리는 중… 0초";
  portraitTimer = setInterval(() => {
    sec++;
    $("portraitTimer").textContent = `그리는 중… ${sec}초`;
  }, 1000);
}
function portraitLoadingOff() {
  $("portraitLoading").hidden = true;
  if (portraitTimer) { clearInterval(portraitTimer); portraitTimer = null; }
}

let portraitBusy = false;
async function genPortrait(refreshTags = false) {
  // refreshTags=false → 저장된 태그 재사용(시드만 다르게, LLM 미호출)
  // refreshTags=true  → LLM으로 태그를 새로 뽑아 생성(느림)
  if (portraitBusy) return;                       // 생성 중엔 중복 클릭 무시
  portraitBusy = true;
  const regenBtn = $("portraitRegen"), retagBtn = $("portraitRetag"),
        confirmBtn = $("portraitConfirm"), genBtn = $("portraitGenBtn");
  const activeBtn = refreshTags ? retagBtn : regenBtn;   // 눌린 버튼에 진행 표시
  const activeLabel = activeBtn.textContent;
  regenBtn.disabled = true; retagBtn.disabled = true; confirmBtn.disabled = true; genBtn.disabled = true;
  activeBtn.textContent = "생성 중…";
  portraitLoadingOn();
  try {
    const qs = "n=4" + (refreshTags ? "&refresh_tags=1" : "");
    const res = await fetch(`/api/characters/${currentCharId}/portrait/variations?${qs}`,
                            { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert(err.detail || "초상 생성에 실패했어. ComfyUI가 켜져 있는지 확인해줘.");
      renderPortrait($("portraitImg").src && !$("portraitImg").hidden ? $("portraitImg").src : null);
      return;
    }
    const data = await res.json();
    openPortraitModal(data.candidates);           // 새 후보로 교체(선택 해제 → 확정 버튼 다시 비활성)
  } catch (e) {
    alert("초상 생성 중 오류가 났어.");
  } finally {
    portraitLoadingOff();
    portraitBusy = false;
    regenBtn.disabled = false; retagBtn.disabled = false; genBtn.disabled = false;
    activeBtn.textContent = activeLabel;
    confirmBtn.disabled = (selectedCandidate === null);   // 선택된 게 있을 때만 확정 가능
  }
}

let selectedCandidate = null;

function openPortraitModal(candidates) {
  const grid = $("portraitGrid");
  grid.innerHTML = "";
  selectedCandidate = null;
  $("portraitConfirm").disabled = true;
  syncAdultToggle("adultToggleModal");   // 모달 토글을 현재 설정값으로
  for (const c of candidates) {
    const im = document.createElement("img");
    im.src = c.image;
    im.title = `seed ${c.seed}`;
    im.addEventListener("click", () => {
      // 클릭 = 선택(하이라이트). 확정은 '확정하기' 버튼으로.
      for (const el of grid.children) el.classList.remove("selected");
      im.classList.add("selected");
      selectedCandidate = c.index;
      $("portraitConfirm").disabled = false;
    });
    grid.appendChild(im);
  }
  $("portraitModal").hidden = false;
}

function closePortraitModal() { $("portraitModal").hidden = true; }

async function confirmPortrait() {
  if (selectedCandidate === null) return;
  const ok = confirm("이 초상으로 확정할까?\n\n확정하면 이 캐릭터의 기준 초상이 되고, 이후엔 바꿀 수 없어. "
                     + "앞으로의 이미지는 이 초상을 토대로 생성돼.");
  if (!ok) return;
  try {
    await fetch(`/api/characters/${currentCharId}/portrait/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: selectedCandidate }),
    });
  } catch (e) { /* 무시 */ }
  closePortraitModal();
  renderPortrait(`/api/characters/${currentCharId}/portrait?t=${Date.now()}`);
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

async function maybeGenerateScene(data) {
  // 장면 전환(scene_changed)일 때, 확정 초상을 기준으로 장면 이미지를 생성해 초상 영역에 표시.
  // (갤러리에도 저장됨. 기준 초상이 없으면 생성 안 함.)
  if (!portraitConfirmed || sceneBusy) return;
  if (!data || !data.scene_changed) return;
  const prompt = (data.image_prompt || "").trim();
  if (!prompt) return;

  sceneBusy = true;
  portraitLoadingOn();   // 초상 영역에 로딩 표시
  try {
    const res = await fetch(`/api/characters/${currentCharId}/scene-image`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_prompt: prompt }),
    });
    if (res.ok) {
      const d = await res.json();
      if (d.image) {
        const img = $("portraitImg");
        img.src = d.image + (d.image.includes("?") ? "&" : "?") + "t=" + Date.now();
        img.hidden = false;
        $("portraitEmpty").hidden = true;
        $("galleryBtn").hidden = false;
      }
    }
  } catch (e) {
    /* 이미지 실패해도 대화는 계속 — 조용히 무시 */
  } finally {
    portraitLoadingOff();
    sceneBusy = false;
  }
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
    await maybeGenerateScene(data);   // 장면 전환이면 장면 이미지 생성(초상 영역에 표시)
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
    await maybeGenerateScene(data);   // 장면 전환이면 장면 이미지 생성
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

// ── 성인 이미지 토글(초상 영역·모달·설정창 공유) ──
async function setAdult(on) {
  currentSettings = { ...currentSettings, adult_images: on };
  for (const id of ["adultTogglePortrait", "adultToggleModal", "adultToggleSettings"]) {
    const el = $(id); if (el) el.checked = on;   // 토글 3개 동기화
  }
  try {
    await fetch(`/api/chat/${currentCharId}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: currentSettings }),
    });
  } catch (e) { /* 저장 실패해도 다음 생성에 반영 시도 */ }
}
function syncAdultToggle(id) {
  const el = $(id); if (el) el.checked = !!currentSettings.adult_images;
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
  // 성인 이미지 생성 토글
  const adultField = document.createElement("div");
  adultField.className = "setting setting--toggle";
  adultField.innerHTML = `
    <label class="adult-toggle">
      <input type="checkbox" id="adultToggleSettings"> 성인 이미지 생성
    </label>
    <p class="setting__note">끄면 이미지 네거티브에 성인 태그를 넣어 건전하게 생성해. 켜면 허용.</p>`;
  wrap.appendChild(adultField);
  const adultEl = adultField.querySelector("#adultToggleSettings");
  adultEl.checked = !!currentSettings.adult_images;
  adultEl.addEventListener("change", (e) => setAdult(e.target.checked));

  $("settingsModal").hidden = false;
}

function closeSettings() { $("settingsModal").hidden = true; }

async function saveSettings() {
  const settings = {};
  for (const def of SETTINGS_DEF) {
    const slider = $(`ss_${def.key}`);
    if (slider) settings[def.key] = Number(slider.value);
  }
  // 성인 이미지 토글 값 보존(슬라이더만 바꿔도 안 날아가게)
  const adultEl = $("adultToggleSettings");
  settings.adult_images = adultEl ? adultEl.checked : !!currentSettings.adult_images;
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
$("portraitGenBtn").addEventListener("click", () => genPortrait(false));  // 첫 생성(태그 없으면 자동 변환)
$("portraitRegen").addEventListener("click", () => genPortrait(false));   // 시드만 다르게(LLM 미호출)
$("portraitRetag").addEventListener("click", () => genPortrait(true));    // 태그 새로 뽑기(LLM 호출)
$("portraitConfirm").addEventListener("click", confirmPortrait);
$("adultTogglePortrait").addEventListener("change", (e) => setAdult(e.target.checked));
$("adultToggleModal").addEventListener("change", (e) => setAdult(e.target.checked));
$("portraitModalClose").addEventListener("click", closePortraitModal);
// 초상 모달은 바깥을 눌러도 닫히지 않게(실수로 닫혀 후보가 날아가는 것 방지). ✕로만 닫음.
$("galleryBtn").addEventListener("click", openGallery);
$("galleryModalClose").addEventListener("click", closeGallery);
$("galleryModal").addEventListener("click", (e) => {
  if (e.target === $("galleryModal")) closeGallery();
});
$("lightbox").addEventListener("click", closeLightbox);   // 확대 이미지 아무 데나 클릭 → 닫기
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("lightbox").hidden) closeLightbox();
});
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
