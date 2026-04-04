function qs(sel) { return document.querySelector(sel); }
function qsa(sel) { return Array.from(document.querySelectorAll(sel)); }

function applyTheme(theme) {
  const t = theme || "violet";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("ai_study_theme", t); } catch (_) {}
}

function loadTheme() {
  try { return localStorage.getItem("ai_study_theme") || "violet"; } catch (_) { return "violet"; }
}

function escapeHtml(str) {
  return String(str).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function noteParam() {
  const id = window.__NOTE_ID__;
  return id ? `?note_id=${encodeURIComponent(id)}` : "";
}

function ensureNoteSelected() {
  if (!window.__NOTE_ID__) throw new Error("Please select an upload from History (or upload a file first).");
}

async function getJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const data = await res.json(); if (data && data.error) msg = data.error; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try { const data = await res.json(); if (data && data.error) msg = data.error; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

async function downloadFile(url, filename) {
  const res = await fetch(url);
  if (!res.ok) {
    let msg = `Download failed (${res.status})`;
    try { const data = await res.json(); if (data && data.error) msg = data.error; } catch (_) {}
    throw new Error(msg);
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}

// Improved Loading State
function setLoading(el, text, btnEl = null) {
  el.innerHTML = `<div class="empty-state"><div class="spinner"></div><div>${text}</div></div>`;
  el.classList.remove("muted");
  if (btnEl) btnEl.disabled = true;
}

function setError(el, err, btnEl = null) {
  el.innerHTML = `<div class="alert"><i class="ph-fill ph-warning-circle"></i> ${escapeHtml(err.message || String(err))}</div>`;
  if (btnEl) btnEl.disabled = false;
}

function activateTab(name) {
  qsa(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  qsa(".tab-panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
}

async function loadSummary() {
  const box = qs("#summaryBox");
  const btn = qs("#btnSummary");
  setLoading(box, "AI is analyzing your document and generating a summary...", btn);
  try {
    ensureNoteSelected();
    const data = await getJson(`/summarize${noteParam()}`);
    box.innerHTML = escapeHtml(data.summary || "(Empty summary)").replace(/\n/g, '<br>');
  } catch (err) {
    setError(box, err);
  } finally {
    if(btn) btn.disabled = false;
  }
}

async function loadFlashcards() {
  const box = qs("#flashcardsBox");
  const btn = qs("#btnFlashcards");
  setLoading(box, "Extracting key concepts for flashcards...", btn);
  try {
    ensureNoteSelected();
    const data = await getJson(`/flashcards${noteParam()}`);
    const cards = data.flashcards || [];
    if (!cards.length) {
      box.innerHTML = `<div class="empty-state"><i class="ph ph-cards"></i><div>No flashcards generated.</div></div>`;
      return;
    }
    box.innerHTML = cards.map((c, idx) => `
      <div class="flashcard">
        <div class="q"><i class="ph-fill ph-question"></i> ${escapeHtml(c.front ?? c.question ?? "")}</div>
        <div class="a"><i class="ph-fill ph-check-circle" style="color:var(--primary-2)"></i> ${escapeHtml(c.back ?? c.answer ?? "")}</div>
      </div>
    `).join("");
  } catch (err) {
    setError(box, err);
  } finally {
    if(btn) btn.disabled = false;
  }
}

async function loadQuiz() {
  const box = qs("#quizBox");
  const btn = qs("#btnQuiz");
  setLoading(box, "Drafting multiple-choice questions...", btn);
  try {
    ensureNoteSelected();
    const data = await getJson(`/quiz${noteParam()}`);
    const quiz = data.quiz || [];
    if (!quiz.length) {
       box.innerHTML = `<div class="empty-state"><i class="ph ph-exam"></i><div>No quiz generated.</div></div>`;
      return;
    }
    box.innerHTML = quiz.map((q, qIndex) => {
      const options = (q.options || []).map((opt, optIndex) => {
        return `
          <div class="option" data-q="${qIndex}" data-opt="${optIndex}">
            <div style="font-weight:700; color:var(--muted);">${String.fromCharCode(65 + optIndex)}.</div>
            <div>${escapeHtml(opt)}</div>
          </div>
        `;
      }).join("");
      return `
        <div class="quiz-item" data-qwrap="${qIndex}">
          <div class="q">${qIndex + 1}. ${escapeHtml(q.question)}</div>
          ${options}
        </div>
      `;
    }).join("");

    box.querySelectorAll(".option").forEach((optEl) => {
      optEl.addEventListener("click", () => {
        const qIndex = Number(optEl.dataset.q);
        const optIndex = Number(optEl.dataset.opt);
        const correctIndex = Number(quiz[qIndex].correct_index);

        const wrap = box.querySelector(`[data-qwrap="${qIndex}"]`);
        wrap.querySelectorAll(".option").forEach(el => el.classList.remove("correct", "wrong"));

        const correctEl = wrap.querySelector(`.option[data-opt="${correctIndex}"]`);
        if (correctEl) correctEl.classList.add("correct");
        if (optIndex !== correctIndex) optEl.classList.add("wrong");
      });
    });
  } catch (err) {
    setError(box, err);
  } finally {
    if(btn) btn.disabled = false;
  }
}

async function loadChat() {
  const box = qs("#chatBox");
  const btn = qs("#btnChat");
  const input = qs("#chatInput");
  setLoading(box, "Searching your notes and drafting an answer...", btn);
  try {
    ensureNoteSelected();
    const question = (input && input.value ? input.value : "").trim();
    if (!question) throw new Error("Please type a question first.");
    const data = await postJson("/chat", { question, note_id: window.__NOTE_ID__ });
    box.innerHTML = escapeHtml(data.answer || "(No answer)").replace(/\n/g, "<br>");
  } catch (err) {
    setError(box, err);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setupDragAndDrop() {
  const dropZone = qs("#dropZone");
  const fileInput = qs("#fileInput");
  const fileNameDisplay = qs("#fileNameDisplay");

  if (!dropZone || !fileInput) return;

  dropZone.addEventListener("click", () => fileInput.click());
  
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  
  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });
  
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      updateFileName();
    }
  });

  fileInput.addEventListener("change", updateFileName);

  function updateFileName() {
    if (fileInput.files.length > 0) {
      fileNameDisplay.innerHTML = `<i class="ph-fill ph-file-text"></i> ${fileInput.files[0].name}`;
      fileNameDisplay.style.color = "var(--primary-2)";
    }
  }
}

function wire() {
  const btnSummary = qs("#btnSummary");
  const btnFlashcards = qs("#btnFlashcards");
  const btnFlashcardsExport = qs("#btnFlashcardsExport");
  const btnQuiz = qs("#btnQuiz");
  const btnChat = qs("#btnChat");
  const chatInput = qs("#chatInput");
  const themeSelect = qs("#themeSelect");

  const theme = loadTheme();
  applyTheme(theme);
  if (themeSelect) {
    themeSelect.value = theme;
    themeSelect.addEventListener("change", () => applyTheme(themeSelect.value));
  }

  if (btnSummary) btnSummary.addEventListener("click", loadSummary);
  if (btnFlashcards) btnFlashcards.addEventListener("click", loadFlashcards);
  if (btnQuiz) btnQuiz.addEventListener("click", loadQuiz);
  if (btnChat) btnChat.addEventListener("click", loadChat);
  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        loadChat();
      }
    });
  }
  if (btnFlashcardsExport) {
    btnFlashcardsExport.addEventListener("click", async () => {
      try {
        ensureNoteSelected();
        const id = window.__NOTE_ID__;
        await downloadFile(`/flashcards/export${noteParam()}`, `anki_flashcards_note_${id}.tsv`);
      } catch (err) {
        setError(qs("#flashcardsBox"), err);
      }
    });
  }

  qsa(".tab").forEach((t) => {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  });

  setupDragAndDrop();
}

wire();