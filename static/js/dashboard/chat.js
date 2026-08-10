// ── Floating AI Chat (RAG) ────────────────────────────────────────────────────

async function _ensureChatReady() {
  if (_chatReady) return;
  try {
    const fromStorage = localStorage.getItem(_chatStorageKey());
    if (fromStorage && /^\d+$/.test(fromStorage)) {
      _chatSessionId = fromStorage;
    } else {
      await _ensureChatSession(false);
    }
    await _loadChatHistory();
    _chatReady = true;
  } catch (err) {
    _showChatEmptyState();
    console.error("Gagal memuat sesi chat:", err);
  }
}

function _chatStorageKey() {
  const username = currentUser?.username || "anon";
  return `bps_chat_session_${username}`;
}

function initFloatingChat() {
  const input = document.getElementById("chatInput");
  if (!input) return;

  _initChatModal();

  // Shift+Enter = baris baru, Enter = kirim
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage(e);
    }
  });

  const chatView = document.getElementById("chatWindow");
  if (chatView) {
    chatView.classList.add("open");
  }
}

function _chatModalElements() {
  return {
    backdrop: document.getElementById("chatModalBackdrop"),
    title: document.getElementById("chatModalTitle"),
    message: document.getElementById("chatModalMessage"),
    cancelBtn: document.getElementById("chatModalCancelBtn"),
    confirmBtn: document.getElementById("chatModalConfirmBtn"),
  };
}

function _initChatModal() {
  const { backdrop, cancelBtn, confirmBtn } = _chatModalElements();
  if (!backdrop || backdrop.dataset.init === "1") return;

  // Pastikan modal tidak terbuka saat initial load.
  backdrop.hidden = true;

  const close = (result) => {
    backdrop.hidden = true;
    document.body.style.overflow = "";
    const resolver = _chatModalResolver;
    _chatModalResolver = null;
    if (resolver) resolver(result);
  };

  cancelBtn?.addEventListener("click", () => close(false));
  confirmBtn?.addEventListener("click", () => close(true));

  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) close(false);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !backdrop.hidden) close(false);
  });

  backdrop.dataset.init = "1";
}

function showChatDialog({
  title = "Konfirmasi",
  message = "",
  confirmText = "Lanjutkan",
  cancelText = "Batal",
  showCancel = true,
  danger = false,
} = {}) {
  const { backdrop, title: titleEl, message: msgEl, cancelBtn, confirmBtn } = _chatModalElements();
  if (!backdrop || !titleEl || !msgEl || !confirmBtn) {
    return Promise.resolve(false);
  }

  titleEl.textContent = title;
  msgEl.textContent = message;
  confirmBtn.textContent = confirmText;
  confirmBtn.classList.toggle("danger", !!danger);

  if (cancelBtn) {
    cancelBtn.textContent = cancelText;
    cancelBtn.style.display = showCancel ? "" : "none";
  }

  backdrop.hidden = false;
  document.body.style.overflow = "hidden";

  return new Promise((resolve) => {
    _chatModalResolver = resolve;
  });
}

async function _ensureChatSession(forceNew = false) {
  const body = { new: !!forceNew };
  const res = await fetch("/api/ai-chat/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    window.location.href = "/login";
    return "";
  }
  const json = await res.json();
  if (json.status !== "ok" || !json.session?.id) {
    throw new Error(json.message || "Gagal membuat session chat.");
  }
  _chatSessionId = String(json.session.id);
  localStorage.setItem(_chatStorageKey(), _chatSessionId);
  return _chatSessionId;
}

async function _loadChatHistory() {
  if (!_chatSessionId) return;
  const body = document.getElementById("chatBody");
  if (!body) return;

  const qs = new URLSearchParams({ session_id: _chatSessionId }).toString();
  const res = await fetch(`/api/ai-chat/history?${qs}`);
  if (res.status === 401) {
    window.location.href = "/login";
    return;
  }
  const json = await res.json();
  if (json.status !== "ok") return;

  body.innerHTML = "";
  const history = json.history || [];
  if (history.length === 0) {
    _showChatEmptyState();
    return;
  }

  history.forEach((item) => {
    _appendChatMessage(item.role, item.content, item.citations_json || []);
  });
  _scrollChatToBottom();
}

function _showChatEmptyState() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  body.innerHTML = `
    <div class="chat-msg assistant" id="chatEmptyState">
      <img class="chat-avatar" src="/static/logochatbotAI.png" alt="AI">
      <div class="chat-bubble">
        Halo! Saya siap membantu Anda menganalisis berita terkait kondisi ekonomi,
        kemiskinan, pengangguran, dan statistik resmi BPS Kabupaten Karawang.<br><br>
        Silakan ajukan pertanyaan, misalnya:<br>
        &bull; Apa penyebab kenaikan kemiskinan bulan lalu?<br>
        &bull; Bagaimana tren PDRB sektor industri saat ini?<br>
        &bull; Berapa TPT dan TPAK resmi tahun 2025?<br>
        &bull; Sektor KBLI apa yang paling terdampak PHK?
      </div>
    </div>`;
}

function _toggleChatLoading(loading) {
  _chatLoading = loading;
  const typing = document.getElementById("chatTyping");
  const btn = document.getElementById("chatSendBtn");
  const input = document.getElementById("chatInput");
  if (typing) typing.style.display = loading ? "inline-flex" : "none";
  if (btn) btn.disabled = loading;
  if (input) input.disabled = loading;
}

function _scrollChatToBottom() {
  const body = document.getElementById("chatBody");
  if (!body) return;
  body.scrollTop = body.scrollHeight;
}

function _buildCitationMap(citations = []) {
  const map = {};
  if (!Array.isArray(citations)) return map;
  citations.forEach((c, idx) => {
    const key = String(c?.cite_id || "").toUpperCase();
    if (!key) return;
    map[key] = {
      ...c,
      num: Number(c?.num || 0) > 0 ? Number(c.num) : idx + 1,
    };
  });
  return map;
}

function _renderInlineCitationIcon(citation) {
  const cid = escapeHtml(citation?.cite_id || "S??");
  const url = escapeHtml(citation?.url || "#");
  const title = escapeHtml(citation?.title || "Sumber berita");
  const num = Number(citation?.num || 0) > 0 ? Number(citation.num) : 1;
  return `<a class="ai-cite chat-inline-cite" href="${url}" target="_blank" rel="noopener noreferrer" title="${title}">${num}<span class="sr-only">${cid}</span></a>`;
}

function _renderChatText(text, citations = []) {
  const citationMap = _buildCitationMap(citations);
  const normalized = _normalizeCitationMarkers(text || "", "S");
  let html = _markdownToHtmlSafe(normalized);
  html = html.replace(/\[(S\d{2})\]/gi, (_, rawId) => {
    const cid = String(rawId || "").toUpperCase();
    const citation = citationMap[cid];
    if (!citation) return "";
    return _renderInlineCitationIcon(citation);
  });
  return `<div class="md-content">${html}</div>`;
}

function _appendChatMessage(role, content, citations = []) {
  const body = document.getElementById("chatBody");
  if (!body) return null;

  const empty = document.getElementById("chatEmptyState");
  if (empty) empty.remove();

  const wrap = document.createElement("div");
  wrap.className = `chat-msg ${role === "user" ? "user" : "assistant"}`;

  const avatarHtml = role !== "user"
    ? `<img class="chat-avatar" src="/static/logochatbotAI.png" alt="AI">`
    : "";

  wrap.innerHTML = `${avatarHtml}<div class="chat-bubble">${_renderChatText(content, citations)}</div>`;
  body.appendChild(wrap);
  _scrollChatToBottom();
  return wrap.querySelector(".chat-bubble");
}

async function toggleChatWindow() {
  _openView("chat", { updateHash: true });
}

function closeChatWindow() {
  _openView("overview", { updateHash: true });
}

async function clearChatConversation() {
  if (!_chatSessionId) {
    await _ensureChatSession(false);
  }
  if (!_chatSessionId) return;

  const ok = await showChatDialog({
    title: "Hapus Percakapan?",
    message:
      "Semua pesan dalam sesi chat ini akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.",
    confirmText: "Ya, Hapus",
    cancelText: "Batal",
    showCancel: true,
    danger: true,
  });
  if (!ok) return;

  try {
    const res = await fetch("/api/ai-chat/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: _chatSessionId }),
    });
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status !== "ok") {
      await showChatDialog({
        title: "Gagal Menghapus",
        message: json.message || "Gagal menghapus percakapan.",
        confirmText: "Tutup",
        showCancel: false,
      });
      return;
    }
    _showChatEmptyState();
    await showChatDialog({
      title: "Berhasil",
      message: "Percakapan berhasil dibersihkan.",
      confirmText: "Oke",
      showCancel: false,
    });
  } catch (err) {
    await showChatDialog({
      title: "Terjadi Kendala",
      message: "Gagal menghapus percakapan: " + err.message,
      confirmText: "Tutup",
      showCancel: false,
    });
  }
}

/**
 * Hapus blok [PERTANYAAN: ...] dari teks sebelum ditampilkan ke user.
 * Blok ini disisipkan LLM di akhir jawaban dan di-parse terpisah di backend.
 * Stripping di sisi JS juga sebagai safety-net saat streaming berlangsung.
 */
function _stripFollowUpBlock(text) {
  return (text || "").replace(/\[PERTANYAAN:.*?\]/gis, "").trim();
}

/**
 * Render tombol pertanyaan lanjutan di bawah bubble AI.
 * @param {HTMLElement} msgWrap  — elemen .chat-msg.assistant
 * @param {string[]}    questions — array 1-3 pertanyaan
 */
function _appendFollowUps(msgWrap, questions) {
  if (!msgWrap || !questions?.length) return;

  const container = document.createElement("div");
  container.className = "chat-followups";

  questions.forEach((q) => {
    const btn = document.createElement("button");
    btn.className   = "chat-followup-btn";
    btn.type        = "button";
    btn.textContent = q;
    btn.title       = "Klik untuk mengirim pertanyaan ini";
    btn.onclick     = () => {
      // Hapus semua chip follow-up agar chat tidak penuh
      document.querySelectorAll(".chat-followups").forEach((el) => el.remove());
      _sendFollowUp(q);
    };
    container.appendChild(btn);
  });

  msgWrap.appendChild(container);
  _scrollChatToBottom();
}

/**
 * Isi chatInput dengan pertanyaan dan langsung kirim.
 */
function _sendFollowUp(question) {
  const input = document.getElementById("chatInput");
  if (!input || _chatLoading) return;
  input.value = question;
  sendChatMessage(null);
}

async function sendChatMessage(event) {
  if (event) event.preventDefault();
  if (_chatLoading) return;

  const input = document.getElementById("chatInput");
  if (!input) return;

  const message = (input.value || "").trim();
  if (!message) return;

  if (message.length > 1200) {
    alert("Pesan terlalu panjang. Maksimal 1200 karakter.");
    return;
  }

  try {
    if (!_chatSessionId) {
      await _ensureChatSession(false);
    }

    _appendChatMessage("user", message, []);
    input.value = "";
    _toggleChatLoading(true);
    if (typeof trackEvent === "function") trackEvent("ai_chat_message");

    const assistantBubble = _appendChatMessage("assistant", "", []);
    let streamedText = "";
    let activeCitations = [];

    const res = await fetch("/api/ai-chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: _chatSessionId,
        message,
      }),
    });

    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }

    if (!res.ok || !res.body) {
      let errMessage = "Terjadi kendala saat memproses chat.";
      try {
        const fallback = await res.json();
        errMessage = fallback.message || errMessage;
      } catch (_) {
        // noop
      }
      if (assistantBubble) {
        assistantBubble.innerHTML = _renderChatText(errMessage, []);
      }
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    // Label "outer" dipakai agar inner-loop bisa langsung membreak outer-loop
    // ketika event "done" atau "error" diterima.
    // Ini penting untuk Vercel serverless: koneksi HTTP tidak selalu ditutup
    // setelah generator Flask selesai, sehingga reader.read() bisa hang selamanya
    // meski semua data sudah diterima. Dengan break berbasis event aplikasi (bukan
    // bergantung pada penutupan stream), UI selalu kembali normal setelah respons.
    outer: while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawEvent = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);

        if (rawEvent) {
          const dataLines = rawEvent
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim());

          if (dataLines.length > 0) {
            const dataStr = dataLines.join("");
            try {
              const payload = JSON.parse(dataStr);

              if (payload.type === "start") {
                if (payload.session_id) {
                  _chatSessionId = String(payload.session_id);
                  localStorage.setItem(_chatStorageKey(), _chatSessionId);
                }
                if (Array.isArray(payload.sources)) {
                  activeCitations = payload.sources;
                }
              } else if (payload.type === "delta") {
                streamedText += payload.text || "";
                if (assistantBubble) {
                  // Strip blok [PERTANYAAN: ...] agar tidak tampil saat streaming
                  assistantBubble.innerHTML = _renderChatText(
                    _stripFollowUpBlock(streamedText),
                    activeCitations,
                  );
                }
                _scrollChatToBottom();
              } else if (payload.type === "done") {
                if (payload.session_id) {
                  _chatSessionId = String(payload.session_id);
                  localStorage.setItem(_chatStorageKey(), _chatSessionId);
                }
                if (Array.isArray(payload.citations) && payload.citations.length > 0) {
                  activeCitations = payload.citations;
                }
                if (assistantBubble) {
                  assistantBubble.innerHTML = _renderChatText(
                    _stripFollowUpBlock(streamedText),
                    activeCitations,
                  );
                }
                // Render tombol pertanyaan lanjutan
                if (Array.isArray(payload.follow_ups) && payload.follow_ups.length > 0) {
                  _appendFollowUps(assistantBubble?.parentElement, payload.follow_ups);
                }
                // Keluar dari loop segera setelah event "done" — jangan tunggu
                // stream ditutup dari sisi server (tidak reliable di Vercel serverless)
                reader.cancel().catch(() => {});
                break outer;
              } else if (payload.type === "error") {
                const msg = payload.message || "Terjadi kendala saat memproses chat.";
                if (assistantBubble) {
                  assistantBubble.innerHTML = _renderChatText(msg, []);
                }
                // Sama seperti "done" — keluar segera
                reader.cancel().catch(() => {});
                break outer;
              }
            } catch (_) {
              // Abaikan frame SSE yang tidak valid
            }
          }
        }

        boundary = buffer.indexOf("\n\n");
      }
    }

    if (!streamedText && assistantBubble) {
      assistantBubble.innerHTML = _renderChatText(
        "Tidak ada respons dari server AI. Silakan coba lagi.",
        [],
      );
    }
  } catch (err) {
    _appendChatMessage("assistant", "Gagal menghubungi server AI chat. Silakan coba lagi.", []);
    console.error("Chat error:", err);
  } finally {
    _toggleChatLoading(false);
    const inputAfter = document.getElementById("chatInput");
    if (inputAfter) inputAfter.focus();
  }
}
