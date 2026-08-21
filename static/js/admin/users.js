const USERNAME_REGEX = /^[A-Za-z0-9_-]{3,50}$/;
const INPUT_DELIMITER_REGEX = /[\s,]+/;

let currentMe = null;
let usersData = [];
let pendingUsernames = [];
let latestCreatedUsers = [];

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }

  if (typeof showPageLoadingOverlay === "function") {
    showPageLoadingOverlay({
      title: "Menyiapkan manajemen pengguna...",
      subtitle: "Data akun dan status keamanan sedang dimuat.",
    });
  }

  bindEvents();
  renderPendingUsernames();

  try {
    await loadMe();
    await loadUsers();
  } finally {
    if (typeof hidePageLoadingOverlay === "function") {
      hidePageLoadingOverlay();
    }
  }
});

const bindEvents = () => {
  document.getElementById("createUserForm").addEventListener("submit", onCreateUser);
  document.getElementById("btnRefreshUsers").addEventListener("click", loadUsers);
  document.getElementById("usernameInput").addEventListener("keydown", onUsernameInputKeydown);
  document.getElementById("usernameInput").addEventListener("paste", onUsernameInputPaste);
  document.getElementById("usernameInput").addEventListener("blur", commitCurrentInputToTokens);
  document.getElementById("usernameTokenList").addEventListener("click", onUsernameTokenListClick);

  document.querySelectorAll(".admin-modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) {
        backdrop.classList.remove("open");
      }
    });
  });
};

const onUsernameInputKeydown = (event) => {
  const input = event.currentTarget;

  if (event.key === "," || event.key === " " || event.key === "Enter") {
    event.preventDefault();
    addUsernamesFromRawInput(input.value, { clearInput: true });
    return;
  }

  if (event.key === "Backspace" && !input.value.trim() && pendingUsernames.length) {
    removePendingUsername(pendingUsernames[pendingUsernames.length - 1]);
  }
};

const onUsernameInputPaste = (event) => {
  const pastedText = event.clipboardData?.getData("text") || "";
  if (!pastedText || !INPUT_DELIMITER_REGEX.test(pastedText)) {
    return;
  }

  event.preventDefault();
  addUsernamesFromRawInput(pastedText, { clearInput: true });
};

const onUsernameTokenListClick = (event) => {
  const button = event.target.closest("button[data-username]");
  if (!button) {
    return;
  }

  removePendingUsername(button.dataset.username || "");
};

async function loadMe() {
  try {
    const response = await fetch("/api/me");
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const payload = await response.json();
    if (payload.status !== "ok" || payload.role !== "admin") {
      window.location.href = "/dashboard";
      return;
    }

    currentMe = payload;
    const headerUser = document.getElementById("headerUser");
    if (headerUser) {
      headerUser.textContent = payload.username;
    }
  } catch (_) {
    window.location.href = "/login";
  }
}

async function loadUsers() {
  const tbody = document.getElementById("usersTableBody");
  tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Memuat data pengguna...</td></tr>`;

  try {
    const response = await fetch("/api/admin/users");
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (response.status === 403) {
      window.location.href = "/dashboard";
      return;
    }

    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") {
      tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Gagal memuat pengguna.</td></tr>`;
      return;
    }

    usersData = payload.data || [];
    renderUsersTable();
  } catch (_) {
    tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Gagal memuat pengguna.</td></tr>`;
  }
}

const renderUsersTable = () => {
  const tbody = document.getElementById("usersTableBody");
  const countText = document.getElementById("userCountText");

  countText.textContent = `${usersData.length} pengguna`;
  if (!usersData.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Belum ada pengguna.</td></tr>`;
    return;
  }

  tbody.innerHTML = usersData
    .map((user) => {
      const isSelf = currentMe && String(user.id) === String(currentMe.id);
      const passwordStatus = user.must_change_password
        ? `<span class="status-pill warn">Wajib ganti password</span>`
        : `<span class="status-pill ok">Aktif</span>`;
      const codeStatus = user.has_active_code
        ? `<span class="status-pill code">Ada kode aktif</span>`
        : `<span class="status-pill ok">Tidak ada</span>`;

      return `
        <tr>
          <td><strong>${escapeHtml(user.username || "-")}</strong>${isSelf ? " <small>(Anda)</small>" : ""}</td>
          <td><span class="user-role-badge">${escapeHtml(user.role || "user")}</span></td>
          <td>${passwordStatus}</td>
          <td>${codeStatus}</td>
          <td>
            <div class="row-actions">
              <button class="btn-mini" type="button" onclick="generateCode(${user.id}, '${escapeAttr(user.username || "")}')">Generate Kode</button>
              <button
                class="btn-mini warn"
                type="button"
                onclick="deleteUser(${user.id}, '${escapeAttr(user.username || "")}')"
                ${isSelf ? "disabled" : ""}
                title="${isSelf ? "Akun sendiri tidak dapat dihapus" : "Hapus pengguna"}"
              >Hapus</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
};

async function onCreateUser(event) {
  event.preventDefault();
  clearCreateMessage();
  commitCurrentInputToTokens();

  if (!pendingUsernames.length) {
    setCreateMessage("Masukkan minimal satu username terlebih dahulu.", "error");
    focusUsernameInput();
    return;
  }

  const button = document.getElementById("btnCreateUser");
  button.disabled = true;

  try {
    const response = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usernames: pendingUsernames }),
    });
    const payload = await response.json();

    if (!response.ok || payload.status !== "ok") {
      const errorMessage = buildFailedCreateMessage(payload.errors || [], payload.message);
      setCreateMessage(errorMessage, "error");
      return;
    }

    const createdUsers = normalizeCreatedUsers(payload);
    const failedUsers = Array.isArray(payload.errors) ? payload.errors : [];

    setCreateMessage(buildSuccessCreateMessage(payload, failedUsers), "success");
    showPasswordModal(createdUsers, payload.message || "");
    pendingUsernames = pendingUsernames.filter(
      (username) => failedUsers.some((item) => item.username === username),
    );
    renderPendingUsernames();
    await loadUsers();
  } catch (_) {
    setCreateMessage("Gagal terhubung ke server.", "error");
  } finally {
    button.disabled = false;
  }
}

const addUsernamesFromRawInput = (rawValue, { clearInput = false } = {}) => {
  const input = document.getElementById("usernameInput");
  const rawTokens = String(rawValue || "")
    .split(INPUT_DELIMITER_REGEX)
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);

  if (clearInput) {
    input.value = "";
  }

  if (!rawTokens.length) {
    return;
  }

  clearCreateMessage();

  const rejectedMessages = [];
  rawTokens.forEach((token) => {
    const result = addPendingUsername(token);
    if (result) {
      rejectedMessages.push(result);
    }
  });

  if (rejectedMessages.length) {
    setCreateMessage(rejectedMessages.join(" "), "error");
  }
};

const addPendingUsername = (username) => {
  if (!USERNAME_REGEX.test(username)) {
    return `Username '${username}' tidak valid.`;
  }

  if (pendingUsernames.includes(username)) {
    return `Username '${username}' sudah ada di daftar.`;
  }

  pendingUsernames = [...pendingUsernames, username];
  renderPendingUsernames();
  return "";
};

const removePendingUsername = (username) => {
  pendingUsernames = pendingUsernames.filter((item) => item !== username);
  renderPendingUsernames();
  clearCreateMessage();
  focusUsernameInput();
};

const renderPendingUsernames = () => {
  const tokenList = document.getElementById("usernameTokenList");
  const queueText = document.getElementById("queuedUserText");

  tokenList.innerHTML = pendingUsernames
    .map(
      (username) => `
        <span class="admin-token-chip">
          <span>${escapeHtml(username)}</span>
          <button type="button" data-username="${escapeAttr(username)}" aria-label="Hapus ${escapeAttr(username)}">&times;</button>
        </span>
      `,
    )
    .join("");

  if (!pendingUsernames.length) {
    queueText.textContent = "Belum ada username yang siap dibuat.";
    return;
  }

  queueText.textContent = `${pendingUsernames.length} username siap dibuat.`;
};

const commitCurrentInputToTokens = () => {
  const input = document.getElementById("usernameInput");
  addUsernamesFromRawInput(input.value, { clearInput: true });
};

const focusUsernameInput = () => {
  const input = document.getElementById("usernameInput");
  input?.focus();
};

const normalizeCreatedUsers = (payload) => {
  if (Array.isArray(payload.users) && payload.users.length) {
    return payload.users;
  }

  if (payload.user) {
    return [
      {
        ...payload.user,
        generated_password: payload.generated_password || "",
      },
    ];
  }

  return [];
};

const buildFailedCreateMessage = (errors, fallbackMessage) => {
  if (!errors.length) {
    return fallbackMessage || "Gagal membuat pengguna.";
  }

  const details = errors.map((item) => `${item.username}: ${item.message}`).join(" | ");
  return fallbackMessage ? `${fallbackMessage} ${details}` : details;
};

const buildSuccessCreateMessage = (payload, failedUsers) => {
  if (!failedUsers.length) {
    return payload.message || "Pengguna berhasil dibuat.";
  }

  const failedList = failedUsers.map((item) => `${item.username} (${item.message})`).join(", ");
  return `${payload.message || "Sebagian pengguna berhasil dibuat."} Gagal: ${failedList}.`;
};

window.deleteUser = async (userId, username) => {
  const confirmed = await showDialog({
    title: "Hapus Pengguna?",
    message: `Pengguna '${username}' akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.`,
    confirmText: "Ya, Hapus",
    cancelText: "Batal",
    showCancel: true,
    danger: true,
  });
  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(`/api/admin/users/${userId}`, {
      method: "DELETE",
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") {
      await showDialog({
        title: "Gagal Menghapus",
        message: payload.message || "Gagal menghapus pengguna.",
        confirmText: "Tutup",
      });
      return;
    }

    await loadUsers();
    setCreateMessage(payload.message || "Pengguna berhasil dihapus.", "success");
  } catch (_) {
    await showDialog({
      title: "Koneksi Gagal",
      message: "Gagal terhubung ke server.",
      confirmText: "Tutup",
    });
  }
};

window.generateCode = async (userId, username) => {
  const confirmed = await showDialog({
    title: "Generate Kode Baru?",
    message: `Kode autentikasi baru untuk '${username}' akan dibuat dan kode lama otomatis tidak berlaku.`,
    confirmText: "Generate",
    cancelText: "Batal",
    showCancel: true,
  });
  if (!confirmed) {
    return;
  }

  try {
    const response = await fetch(`/api/admin/users/${userId}/auth-code`, {
      method: "POST",
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") {
      await showDialog({
        title: "Gagal Generate Kode",
        message: payload.message || "Gagal membuat kode autentikasi.",
        confirmText: "Tutup",
      });
      return;
    }

    showCodeModal(payload.username || username, payload.code || "", payload.expires_at || "");
    await loadUsers();
  } catch (_) {
    await showDialog({
      title: "Koneksi Gagal",
      message: "Gagal terhubung ke server.",
      confirmText: "Tutup",
    });
  }
};

// showDialog() dipromosikan ke static/js/shared/dialog.js -- dimuat sebagai
// <script> terpisah, meng-inject markup #adminDialogBackdrop sendiri.

const showPasswordModal = (createdUsers, message) => {
  latestCreatedUsers = createdUsers;

  const list = document.getElementById("createdUsersList");
  const description = document.getElementById("passwordModalDescription");
  const copyAllButton = document.getElementById("copyAllCredentialsBtn");

  description.textContent = message || "Password sementara hanya ditampilkan sekali. Simpan dan berikan ke user secara aman.";
  list.innerHTML = createdUsers
    .map((user, index) => renderCreatedUserCard(user, index))
    .join("");
  copyAllButton.style.display = createdUsers.length > 1 ? "" : "none";

  document.getElementById("passwordModalBackdrop").classList.add("open");
};

const renderCreatedUserCard = (user, index) => `
  <div class="secret-box">
    <div class="secret-box-header">
      <div class="secret-label">Pengguna ${index + 1}</div>
      <button class="btn-admin ghost" type="button" onclick="copyCredential(${index})">Salin Akun</button>
    </div>
    <div class="secret-stack">
      <div>
        <div class="secret-label">Username</div>
        <input id="createdUsernameValue_${index}" class="secret-value" value="${escapeAttr(user.username || "")}" readonly />
      </div>
      <div>
        <div class="secret-label">Password Sementara</div>
        <div class="secret-row">
          <input id="createdPasswordValue_${index}" class="secret-value" value="${escapeAttr(user.generated_password || "")}" readonly />
          <button class="btn-admin ghost" type="button" onclick="copySecret('createdPasswordValue_${index}')">Salin</button>
        </div>
      </div>
    </div>
  </div>
`;

const showCodeModal = (username, code, expiry) => {
  document.getElementById("codeUsernameValue").value = username;
  document.getElementById("authCodeValue").value = code;
  document.getElementById("authCodeExpiryValue").value = expiry;
  document.getElementById("codeModalBackdrop").classList.add("open");
};

window.closeModal = (id) => {
  const element = document.getElementById(id);
  if (element) {
    element.classList.remove("open");
  }
};

window.copySecret = async (inputId) => {
  const input = document.getElementById(inputId);
  if (!input || !input.value) {
    return;
  }

  await copyText(input.value);
};

window.copyCredential = async (index) => {
  const user = latestCreatedUsers[index];
  if (!user) {
    return;
  }

  await copyText(`Username: ${user.username}\nPassword sementara: ${user.generated_password}`);
};

window.copyAllCredentials = async () => {
  if (!latestCreatedUsers.length) {
    return;
  }

  const text = latestCreatedUsers
    .map(
      (user, index) =>
        `Pengguna ${index + 1}\nUsername: ${user.username}\nPassword sementara: ${user.generated_password}`,
    )
    .join("\n\n");

  await copyText(text);
};

const copyText = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }

  await showDialog({
    title: "Berhasil Disalin",
    message: "Teks berhasil disalin ke clipboard.",
    confirmText: "Oke",
  });
};

const setCreateMessage = (message, type) => {
  const element = document.getElementById("createUserMessage");
  element.textContent = message;
  element.className = `admin-message ${type}`;
};

const clearCreateMessage = () => {
  const element = document.getElementById("createUserMessage");
  element.className = "admin-message";
  element.textContent = "";
};
