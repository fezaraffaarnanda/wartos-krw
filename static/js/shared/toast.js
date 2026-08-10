// Toast notification, dipromosikan dari templates/admin_relevance.html (dulu
// satu-satunya toast di app, inline, tidak bisa dipakai halaman lain).
// Inject DOM sendiri saat panggilan pertama -- halaman cukup satu <script>
// tag, tidak perlu menyalin markup wrapper ke tiap template.

const TOAST_ICONS = { info: "ℹ️", success: "✅", warning: "⚠️", error: "❌" };

function _ensureToastWrap() {
  let wrap = document.getElementById("sharedToastWrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "shared-toast-wrap";
    wrap.id = "sharedToastWrap";
    document.body.appendChild(wrap);
  }
  return wrap;
}

function showToast(message, type = "info", duration = 5000) {
  const wrap = _ensureToastWrap();
  const el = document.createElement("div");
  el.className = `shared-toast ${type}`;
  el.innerHTML = `
    <span class="shared-toast-icon">${TOAST_ICONS[type] || TOAST_ICONS.info}</span>
    <span>${escapeHtml(message)}</span>
    <button class="shared-toast-close" aria-label="Tutup">✕</button>`;
  const remove = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 200);
  };
  el.querySelector(".shared-toast-close").addEventListener("click", remove);
  wrap.appendChild(el);
  if (duration > 0) setTimeout(remove, duration);
}
