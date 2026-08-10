// Dialog konfirmasi/alert admin, dipromosikan dari static/js/admin/users.js.
// Inject DOM sendiri saat panggilan pertama -- halaman cukup satu <script>
// tag, tidak perlu menyalin markup #adminDialogBackdrop ke tiap template.

let _dialogResolver = null;
let _dialogInitialized = false;

function _ensureDialogDom() {
  if (document.getElementById("adminDialogBackdrop")) return;
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="admin-modal-backdrop" id="adminDialogBackdrop" role="dialog" aria-modal="true" aria-labelledby="adminDialogTitle">
      <div class="admin-modal admin-dialog-modal">
        <div class="admin-dialog-head">
          <div class="admin-dialog-icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 8v4" />
              <path d="M12 16h.01" />
            </svg>
          </div>
          <div>
            <h3 id="adminDialogTitle">Informasi</h3>
            <p id="adminDialogMessage">Pesan dialog.</p>
          </div>
        </div>
        <div class="modal-actions admin-dialog-actions">
          <button class="btn-admin ghost" type="button" id="adminDialogCancelBtn">Batal</button>
          <button class="btn-admin" type="button" id="adminDialogConfirmBtn">Oke</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(wrap.firstElementChild);
}

function _getDialogElements() {
  return {
    backdrop: document.getElementById("adminDialogBackdrop"),
    title: document.getElementById("adminDialogTitle"),
    message: document.getElementById("adminDialogMessage"),
    cancelBtn: document.getElementById("adminDialogCancelBtn"),
    confirmBtn: document.getElementById("adminDialogConfirmBtn"),
  };
}

function _initDialogModal() {
  if (_dialogInitialized) return;
  const { backdrop, cancelBtn, confirmBtn } = _getDialogElements();
  if (!backdrop) return;

  const close = (result) => {
    backdrop.classList.remove("open");
    document.body.style.overflow = "";
    const resolver = _dialogResolver;
    _dialogResolver = null;
    if (resolver) resolver(result);
  };

  cancelBtn?.addEventListener("click", () => close(false));
  confirmBtn?.addEventListener("click", () => close(true));
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && backdrop.classList.contains("open")) close(false);
  });

  _dialogInitialized = true;
}

function showDialog({
  title = "Informasi",
  message = "",
  confirmText = "Oke",
  cancelText = "Batal",
  showCancel = false,
  danger = false,
} = {}) {
  _ensureDialogDom();
  _initDialogModal();

  const { backdrop, title: titleEl, message: messageEl, cancelBtn, confirmBtn } = _getDialogElements();
  if (!backdrop || !titleEl || !messageEl || !confirmBtn) {
    return Promise.resolve(false);
  }

  titleEl.textContent = title;
  messageEl.textContent = message;
  confirmBtn.textContent = confirmText;
  confirmBtn.classList.toggle("warn", danger);

  if (cancelBtn) {
    cancelBtn.textContent = cancelText;
    cancelBtn.style.display = showCancel ? "" : "none";
  }

  backdrop.classList.add("open");
  document.body.style.overflow = "hidden";

  return new Promise((resolve) => {
    _dialogResolver = resolve;
  });
}
