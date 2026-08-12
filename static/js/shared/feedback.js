// Modal "Kirim Masukan" -- dipicu tombol sidebar (permanen) atau otomatis
// setelah milestone pemakaian (lihat activity.js + services/feedback_service.py).
// Pola self-inject DOM sama seperti shared/dialog.js -- satu <script> tag per
// halaman, tidak perlu menyalin markup modal ke tiap template.

const _FEEDBACK_CATEGORIES = [
  { value: "berita", label: "Data Berita" },
  { value: "ai_chat", label: "AI Chat" },
  { value: "ai_insight", label: "Insight AI" },
  { value: "statistik_resmi", label: "Data Official Statistic" },
  { value: "scraping", label: "Scraping" },
  { value: "lainnya", label: "Lainnya" },
];

let _feedbackRating = 0;
let _feedbackTriggerSource = "sidebar";
let _feedbackAutoPromptShown = false;

function _ensureFeedbackDom() {
  if (document.getElementById("feedbackModalBackdrop")) return;

  const stars = [1, 2, 3, 4, 5]
    .map((n) => `<button type="button" class="feedback-star" data-rating="${n}" aria-label="Beri ${n} bintang">★</button>`)
    .join("");
  const options = _FEEDBACK_CATEGORIES
    .map((c) => `<option value="${c.value}">${escapeHtml(c.label)}</option>`)
    .join("");

  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="feedback-modal-backdrop" id="feedbackModalBackdrop" role="dialog" aria-modal="true" aria-labelledby="feedbackModalTitle">
      <div class="feedback-modal">
        <div class="feedback-modal-head">
          <h3 id="feedbackModalTitle">Kirim Masukan</h3>
          <button type="button" class="feedback-modal-close" id="feedbackModalCloseBtn" aria-label="Tutup">✕</button>
        </div>
        <div class="feedback-modal-body">
          <label class="feedback-field-label">Seberapa puas Anda dengan WARTOS?</label>
          <div class="feedback-stars" id="feedbackStars">${stars}</div>

          <label class="feedback-field-label" for="feedbackCategorySelect">Kategori</label>
          <select class="feedback-select" id="feedbackCategorySelect">${options}</select>

          <label class="feedback-field-label" for="feedbackCommentInput">Komentar (opsional)</label>
          <textarea class="feedback-textarea" id="feedbackCommentInput" maxlength="2000" rows="4" placeholder="Ceritakan pengalaman Anda..."></textarea>

          <p class="feedback-error" id="feedbackError" hidden></p>
        </div>
        <div class="feedback-modal-actions">
          <button type="button" class="feedback-btn feedback-btn-ghost" id="feedbackDismissBtn" hidden>Nanti saja</button>
          <button type="button" class="feedback-btn feedback-btn-primary" id="feedbackSubmitBtn">Kirim</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(wrap.firstElementChild);

  document.getElementById("feedbackStars").addEventListener("click", (event) => {
    const btn = event.target.closest(".feedback-star");
    if (!btn) return;
    _feedbackRating = Number(btn.dataset.rating);
    _renderFeedbackStars();
  });

  document.getElementById("feedbackModalCloseBtn").addEventListener("click", () => _closeFeedbackModal());
  document.getElementById("feedbackModalBackdrop").addEventListener("click", (event) => {
    if (event.target.id === "feedbackModalBackdrop") _closeFeedbackModal();
  });
  document.getElementById("feedbackDismissBtn").addEventListener("click", () => _dismissFeedbackPrompt());
  document.getElementById("feedbackSubmitBtn").addEventListener("click", () => _submitFeedback());
}

function _renderFeedbackStars() {
  document.querySelectorAll("#feedbackStars .feedback-star").forEach((btn) => {
    btn.classList.toggle("active", Number(btn.dataset.rating) <= _feedbackRating);
  });
}

function _closeFeedbackModal() {
  const backdrop = document.getElementById("feedbackModalBackdrop");
  if (backdrop) backdrop.classList.remove("open");
  document.body.style.overflow = "";
}

function _resetFeedbackForm() {
  _feedbackRating = 0;
  _renderFeedbackStars();
  const comment = document.getElementById("feedbackCommentInput");
  if (comment) comment.value = "";
  const category = document.getElementById("feedbackCategorySelect");
  if (category) category.selectedIndex = 0;
  const error = document.getElementById("feedbackError");
  if (error) error.hidden = true;
}

function openFeedbackModal({ triggerSource = "sidebar" } = {}) {
  _ensureFeedbackDom();
  _resetFeedbackForm();
  _feedbackTriggerSource = triggerSource;

  const dismissBtn = document.getElementById("feedbackDismissBtn");
  if (dismissBtn) dismissBtn.hidden = triggerSource !== "auto_prompt";

  const backdrop = document.getElementById("feedbackModalBackdrop");
  if (backdrop) backdrop.classList.add("open");
  document.body.style.overflow = "hidden";
}

function _dismissFeedbackPrompt() {
  _closeFeedbackModal();
  fetch("/api/feedback/dismiss", { method: "POST" }).catch(() => {});
}

function _submitFeedback() {
  const errorEl = document.getElementById("feedbackError");
  if (_feedbackRating < 1) {
    if (errorEl) {
      errorEl.textContent = "Pilih rating bintang dulu.";
      errorEl.hidden = false;
    }
    return;
  }

  const category = document.getElementById("feedbackCategorySelect").value;
  const comment = document.getElementById("feedbackCommentInput").value;
  const submitBtn = document.getElementById("feedbackSubmitBtn");
  submitBtn.disabled = true;

  fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating: _feedbackRating,
      category,
      comment,
      page_path: window.location.pathname,
      trigger_source: _feedbackTriggerSource,
    }),
  })
    .then((res) => res.json().then((json) => ({ ok: res.ok, json })))
    .then(({ ok, json }) => {
      submitBtn.disabled = false;
      if (!ok) {
        if (errorEl) {
          errorEl.textContent = json.message || "Gagal mengirim masukan.";
          errorEl.hidden = false;
        }
        return;
      }
      _closeFeedbackModal();
      if (typeof showToast === "function") {
        showToast(json.message || "Terima kasih atas masukannya.", "success");
      }
    })
    .catch(() => {
      submitBtn.disabled = false;
      if (errorEl) {
        errorEl.textContent = "Gagal mengirim masukan. Coba lagi.";
        errorEl.hidden = false;
      }
    });
}

window.showFeedbackAutoPrompt = function () {
  if (_feedbackAutoPromptShown) return;
  const backdrop = document.getElementById("feedbackModalBackdrop");
  if (backdrop && backdrop.classList.contains("open")) return;
  _feedbackAutoPromptShown = true;
  openFeedbackModal({ triggerSource: "auto_prompt" });
};

function initFeedbackWidget() {
  const btn = document.getElementById("feedbackSidebarBtn");
  if (btn) {
    btn.addEventListener("click", () => openFeedbackModal({ triggerSource: "sidebar" }));
  }

  // Di dashboard, loadUserInfo() sudah men-cache /api/me — reuse hasilnya
  // supaya tidak ada dua request identik saat load awal. Di halaman lain
  // cache itu tidak ada, jadi fetch sendiri.
  const userInfo =
    typeof window.getCachedUserInfo === "function"
      ? window.getCachedUserInfo()
      : fetch("/api/me").then((res) => (res.ok ? res.json() : null));

  Promise.resolve(userInfo)
    .then((json) => {
      if (json && json.feedback_prompt && json.feedback_prompt.should_prompt) {
        window.showFeedbackAutoPrompt();
      }
    })
    .catch(() => {});
}

document.addEventListener("DOMContentLoaded", initFeedbackWidget);
