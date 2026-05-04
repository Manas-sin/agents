const screens = {
  input: document.getElementById("screen-input"),
  chat: document.getElementById("screen-chat"),
  breakdown: document.getElementById("screen-breakdown"),
  solver: document.getElementById("screen-solver"),
  completion: document.getElementById("screen-completion"),
  saved: document.getElementById("screen-saved"),
};

const state = {
  sessionId: null,
  lastResponse: null,
  ttsOn: true,
  pickedFile: null,
};

const GREETING =
  "Abey scene kya hai bhai! Apna homework paste kar ya photo daal — chal nikalte hain isse.";

function show(name) {
  Object.values(screens).forEach((s) => s.classList.remove("active"));
  screens[name].classList.add("active");
}

function showError(msg) {
  const banner = document.getElementById("error-banner");
  document.getElementById("error-text").textContent = msg;
  banner.classList.remove("hidden");
  setTimeout(() => banner.classList.add("hidden"), 6000);
}
document.getElementById("error-close").onclick = () =>
  document.getElementById("error-banner").classList.add("hidden");

function setLoading(on, text) {
  const el = document.getElementById("loading");
  if (on) {
    document.getElementById("loading-text").textContent = text || "Soch raha hu...";
    el.classList.remove("hidden");
  } else {
    el.classList.add("hidden");
  }
}

async function api(path, method = "GET", body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j && j.detail) detail = j.detail;
    } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

async function uploadImage(file) {
  const fd = new FormData();
  fd.append("image", file);
  fd.append("student_id", "demo-student");
  const res = await fetch("/api/sessions/from-image", { method: "POST", body: fd });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j && j.detail) detail = j.detail;
    } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

// ─── TTS (server-side via Gemini) ─────────────────────────────────────────────

let currentAudio = null;
const audioCache = new Map(); // text → ObjectURL

function stopAudio() {
  if (currentAudio) {
    try { currentAudio.pause(); } catch (e) {}
    currentAudio = null;
  }
  // also cancel any browser TTS in case it's queued
  if (window.speechSynthesis) window.speechSynthesis.cancel();
}

async function fetchTtsUrl(text) {
  if (audioCache.has(text)) return audioCache.get(text);
  const res = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`TTS failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  audioCache.set(text, url);
  return url;
}

async function speak(text, force = false) {
  if (!text) return;
  if (!force && !state.ttsOn) return;
  stopAudio();
  try {
    const url = await fetchTtsUrl(text);
    const audio = new Audio(url);
    currentAudio = audio;
    audio.onended = () => { if (currentAudio === audio) currentAudio = null; };
    await audio.play();
  } catch (e) {
    console.warn("[tts] failed, falling back to browser TTS:", e);
    if (window.speechSynthesis) {
      const u = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(u);
    }
  }
}

const ttsBtn = document.getElementById("tts-toggle");
function refreshTtsBtn() {
  ttsBtn.textContent = state.ttsOn ? "🔊" : "🔇";
  ttsBtn.classList.toggle("on", state.ttsOn);
}
refreshTtsBtn();
ttsBtn.onclick = () => {
  state.ttsOn = !state.ttsOn;
  refreshTtsBtn();
  if (!state.ttsOn) stopAudio();
};

document.getElementById("greeting-speak").onclick = () => speak(GREETING, true);

// ─── Splash → first interaction unlocks audio ──────────────────────────────────

const splash = document.getElementById("splash");
const mainApp = document.getElementById("main-app");
document.getElementById("splash-go").onclick = () => {
  // unlock TTS by speaking on the user-gesture stack
  speak(GREETING, true);
  splash.classList.add("fade-out");
  mainApp.classList.remove("hidden");
  setTimeout(() => splash.remove(), 500);
};

// ─── Bubbles + translate-after-bot ────────────────────────────────────────────

async function translateText(text) {
  const res = await api("/api/translate", "POST", { text });
  return res.english;
}

function appendBubble(text, who, opts = {}) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = `bubble ${who}` + (opts.english ? " english" : "");
  div.textContent = text;
  chat.appendChild(div);

  if (who === "bot" && !opts.english) {
    const actions = document.createElement("div");
    actions.className = "bubble-actions";
    const trans = document.createElement("button");
    trans.className = "translate-btn";
    trans.textContent = "🇬🇧 English mein chahiye?";
    trans.onclick = async () => {
      trans.disabled = true;
      trans.textContent = "translating...";
      try {
        const en = await translateText(text);
        appendBubble(en, "bot", { english: true });
        trans.remove();
        actions.remove();
      } catch (e) {
        trans.disabled = false;
        trans.textContent = "🇬🇧 English mein chahiye?";
        showError(e.message);
      }
    };
    actions.appendChild(trans);
    chat.appendChild(actions);
  }

  chat.scrollTop = chat.scrollHeight;
  if (who === "bot") speak(text);
}

// ─── Render router ─────────────────────────────────────────────────────────────

function render(response) {
  state.lastResponse = response;
  state.sessionId = response.session_id;

  if (response.saved_to_library) {
    show("saved");
    speak("Done bhai! Library mein save ho gaya. Mast kaam kiya!");
    return;
  }

  const interrupt = response.interrupt;
  if (!interrupt) {
    show("saved");
    return;
  }

  switch (interrupt.type) {
    case "breakdown_review":
      renderBreakdown(interrupt, response);
      show("breakdown");
      break;
    case "step_chat":
      renderStep(interrupt, response);
      show("solver");
      break;
    case "completion_check":
      document.getElementById("completion-msg").textContent = interrupt.message;
      speak(interrupt.message);
      show("completion");
      break;
    default:
      console.warn("Unknown interrupt type", interrupt);
  }
}

function renderBreakdown(interrupt, response) {
  const meta = document.getElementById("breakdown-meta");
  meta.textContent =
    `${interrupt.steps.length} steps` +
    (response.detected_subject ? ` · ${response.detected_subject}` : "") +
    (response.detected_class_level ? ` · class ${response.detected_class_level}` : "");

  const list = document.getElementById("breakdown-list");
  list.replaceChildren();
  interrupt.steps.forEach((s) => {
    const li = document.createElement("li");
    li.append(document.createTextNode(s.question + " "));
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = s.difficulty;
    li.appendChild(pill);
    list.appendChild(li);
  });
}

function renderStep(interrupt, response) {
  const step = interrupt.step;
  document.getElementById("step-title").textContent =
    `Step ${response.current_step_index + 1}: ${step.question}`;
  document.getElementById("step-meta").textContent =
    `${step.subject} · ${step.difficulty} · hints used: ${step.hints_used}`;

  if (interrupt.intro) {
    document.getElementById("chat").replaceChildren();
    appendBubble(interrupt.intro, "bot");
  } else if (interrupt.last_reply) {
    appendBubble(interrupt.last_reply, "bot");
  }
}

// ─── Tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
  };
});

// ─── Text path ─────────────────────────────────────────────────────────────────

document.getElementById("start-btn").onclick = async () => {
  const text = document.getElementById("homework-text").value.trim();
  if (!text) return showError("Kuch toh likh yaar!");
  setLoading(true, "Plan bana raha hu...");
  try {
    const res = await api("/api/sessions", "POST", { homework_text: text });
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
};

// ─── Free chat mode ────────────────────────────────────────────────────────────

const chatSession = { id: null };

function uuid() {
  return "chat-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
}

function appendChatBubble(text, who, opts = {}) {
  const chat = document.getElementById("chat-free");
  const div = document.createElement("div");
  div.className = `bubble ${who}`;
  div.textContent = text;
  chat.appendChild(div);

  if (who === "bot" && !opts.skipActions) {
    const actions = document.createElement("div");
    actions.className = "bubble-actions";
    const trans = document.createElement("button");
    trans.className = "translate-btn";
    trans.textContent = "🇬🇧 English mein chahiye?";
    trans.onclick = async () => {
      trans.disabled = true;
      trans.textContent = "translating...";
      try {
        const en = await translateText(text);
        const en_div = document.createElement("div");
        en_div.className = "bubble bot english";
        en_div.textContent = en;
        chat.appendChild(en_div);
        chat.scrollTop = chat.scrollHeight;
        trans.remove();
        actions.remove();
      } catch (e) {
        trans.disabled = false;
        trans.textContent = "🇬🇧 English mein chahiye?";
        showError(e.message);
      }
    };
    actions.appendChild(trans);
    chat.appendChild(actions);
  }

  chat.scrollTop = chat.scrollHeight;
}

function playB64Wav(b64) {
  if (!b64) return;
  if (!state.ttsOn) return;
  stopAudio();
  // base64 → blob → object URL → Audio
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const blob = new Blob([bytes], { type: "audio/wav" });
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  currentAudio = audio;
  audio.onended = () => { if (currentAudio === audio) currentAudio = null; URL.revokeObjectURL(url); };
  audio.play().catch((e) => console.warn("[audio] play failed", e));
}

function appendFollowUpChips(items) {
  if (!items || !items.length) return;
  const chat = document.getElementById("chat-free");
  const wrap = document.createElement("div");
  wrap.className = "chips";
  items.forEach((label) => {
    const b = document.createElement("button");
    b.className = "chip";
    b.textContent = label;
    b.onclick = () => {
      wrap.remove();
      sendChatMessage(label);
    };
    wrap.appendChild(b);
  });
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

async function sendChatMessage(text) {
  appendChatBubble(text, "user");
  setLoading(true, "Soch raha hu...");
  try {
    const res = await api("/api/chat", "POST", {
      session_id: chatSession.id,
      message: text,
    });
    appendChatBubble(res.reply, "bot");
    playB64Wav(res.audio_b64);
    appendFollowUpChips(res.follow_ups);
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}

document.getElementById("start-chat-btn").onclick = async () => {
  chatSession.id = uuid();
  document.getElementById("chat-free").replaceChildren();
  show("chat");
  setLoading(true, "Connecting...");
  try {
    const res = await api("/api/chat", "POST", {
      session_id: chatSession.id,
      message: "(student just opened chat — greet them in your style and ask what they want help with)",
    });
    appendChatBubble(res.reply, "bot");
    playB64Wav(res.audio_b64);
    appendFollowUpChips(res.follow_ups);
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
};

document.getElementById("chat-free-send").onclick = async () => {
  const input = document.getElementById("chat-free-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await sendChatMessage(text);
};

document.getElementById("chat-free-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("chat-free-send").click();
});

document.getElementById("chat-back-btn").onclick = () => {
  stopAudio();
  show("input");
};

// ─── Image path ────────────────────────────────────────────────────────────────

const imageInput = document.getElementById("image-input");

imageInput.onchange = (e) => {
  const file = e.target.files[0];
  if (!file) return;
  state.pickedFile = file;
  document.getElementById("image-preview-img").src = URL.createObjectURL(file);
  document.getElementById("image-preview").classList.remove("hidden");
};

document.getElementById("image-clear-btn").onclick = () => {
  state.pickedFile = null;
  imageInput.value = "";
  document.getElementById("image-preview").classList.add("hidden");
};

document.getElementById("image-start-btn").onclick = async () => {
  if (!state.pickedFile) return;
  setLoading(true, "Photo dekh raha hu...");
  try {
    const res = await uploadImage(state.pickedFile);
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
};

// ─── Breakdown / solver / completion ───────────────────────────────────────────

document.getElementById("confirm-breakdown-btn").onclick = async () => {
  setLoading(true, "Step ready kar raha hu...");
  try {
    const res = await api(`/api/sessions/${state.sessionId}/resume`, "POST", {
      payload: { action: "confirm" },
    });
    document.getElementById("chat").replaceChildren();
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
};

async function sendStepAction(action, text = "") {
  if (text) appendBubble(text, "user");
  setLoading(true, "Soch raha hu...");
  try {
    const res = await api(`/api/sessions/${state.sessionId}/resume`, "POST", {
      payload: { action, text },
    });
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

document.getElementById("send-btn").onclick = async () => {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await sendStepAction("ask", text);
};

document.getElementById("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("send-btn").click();
});

document.querySelectorAll("#screen-solver .actions button").forEach((btn) => {
  btn.onclick = () => sendStepAction(btn.dataset.action, "");
});

document.getElementById("confirm-done-btn").onclick = async () => {
  setLoading(true, "Save kar raha hu...");
  try {
    const res = await api(`/api/sessions/${state.sessionId}/resume`, "POST", {
      payload: { confirmed: true },
    });
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
};

document.getElementById("not-done-btn").onclick = async () => {
  setLoading(true);
  try {
    const res = await api(`/api/sessions/${state.sessionId}/resume`, "POST", {
      payload: { confirmed: false },
    });
    document.getElementById("chat").replaceChildren();
    render(res);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
};

document.getElementById("restart-btn").onclick = () => {
  state.sessionId = null;
  state.pickedFile = null;
  document.getElementById("homework-text").value = "";
  document.getElementById("chat").replaceChildren();
  document.getElementById("image-preview").classList.add("hidden");
  imageInput.value = "";
  show("input");
};

show("input");
if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = () => {};
