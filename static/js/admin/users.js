let currentMe = null;
let usersData = [];

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }
  bindEvents();
  await loadMe();
  await loadUsers();
});

function bindEvents() {
  document.getElementById("createUserForm").addEventListener("submit", onCreateUser);
  document.getElementById("btnRefreshUsers").addEventListener("click", loadUsers);
  document.querySelectorAll(".admin-modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) backdrop.classList.remove("open");
    });
  });
}

async function loadMe() {
  try {
    const res = await fetch("/api/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    if (json.status !== "ok" || json.role !== "admin") {
      window.location.href = "/dashboard";
      return;
    }
    currentMe = json;
    const headerUser = document.getElementById("headerUser");
    if (headerUser) headerUser.textContent = json.username;
  } catch (_) {
    window.location.href = "/login";
  }
}

async function loadUsers() {
  const tbody = document.getElementById("usersTableBody");
  tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Memuat data pengguna...</td></tr>`;
  try {
    const res = await fetch("/api/admin/users");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (res.status === 403) {
      window.location.href = "/dashboard";
      return;
    }
    const json = await res.json();
    if (!res.ok || json.status !== "ok") {
      tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Gagal memuat pengguna.</td></tr>`;
      return;
    }

    usersData = json.data || [];
    renderUsersTable();
  } catch (_) {
    tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Gagal memuat pengguna.</td></tr>`;
  }
}

function renderUsersTable() {
  const tbody = document.getElementById("usersTableBody");
  const countText = document.getElementById("userCountText");
  const users = usersData;

  countText.textContent = `${users.length} pengguna`;
  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="table-empty">Belum ada pengguna.</td></tr>`;
    return;
  }

  tbody.innerHTML = users
    .map((u) => {
      const isSelf = currentMe && String(u.id) === String(currentMe.id);
      const passStatus = u.must_change_password
        ? `<span class="status-pill warn">Wajib ganti password</span>`
        : `<span class="status-pill ok">Aktif</span>`;
      const codeStatus = u.has_active_code
        ? `<span class="status-pill code">Ada kode aktif</span>`
        : `<span class="status-pill ok">Tidak ada</span>`;

      return `
        <tr>
          <td><strong>${escapeHtml(u.username || "-")}</strong>${isSelf ? " <small>(Anda)</small>" : ""}</td>
          <td><span class="user-role-badge">${escapeHtml(u.role || "user")}</span></td>
          <td>${passStatus}</td>
          <td>${codeStatus}</td>
          <td>
            <div class="row-actions">
              <button class="btn-mini" type="button" onclick="generateCode(${u.id}, '${escapeAttr(u.username || "")}')">Generate Kode</button>
              <button
                class="btn-mini warn"
                type="button"
                onclick="deleteUser(${u.id}, '${escapeAttr(u.username || "")}')"
                ${isSelf ? "disabled" : ""}
                title="${isSelf ? "Akun sendiri tidak dapat dihapus" : "Hapus pengguna"}"
              >Hapus</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

async function onCreateUser(e) {
  e.preventDefault();
  clearCreateMessage();

  const usernameInput = document.getElementById("usernameInput");
  const btn = document.getElementById("btnCreateUser");
  const username = usernameInput.value.trim().toLowerCase();

  if (!/^[A-Za-z0-9_-]{3,50}$/.test(username)) {
    setCreateMessage("Format username tidak valid. Gunakan 3-50 karakter huruf/angka/_/-.", "error");
    return;
  }

  btn.disabled = true;
  try {
    const res = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username }),
    });
    const json = await res.json();

    if (!res.ok || json.status !== "ok") {
      setCreateMessage(json.message || "Gagal membuat pengguna.", "error");
      return;
    }

    usernameInput.value = "";
    setCreateMessage(`Pengguna '${json.user?.username || username}' berhasil dibuat.`, "success");
    showPasswordModal(json.user?.username || username, json.generated_password || "");
    await loadUsers();
  } catch (_) {
    setCreateMessage("Gagal terhubung ke server.", "error");
  } finally {
    btn.disabled = false;
  }
}

async function deleteUser(userId, username) {
  if (!confirm(`Yakin ingin menghapus pengguna '${username}'?`)) return;

  try {
    const res = await fetch(`/api/admin/users/${userId}`, {
      method: "DELETE",
    });
    const json = await res.json();
    if (!res.ok || json.status !== "ok") {
      alert(json.message || "Gagal menghapus pengguna.");
      return;
    }
    await loadUsers();
    setCreateMessage(json.message || "Pengguna berhasil dihapus.", "success");
  } catch (_) {
    alert("Gagal terhubung ke server.");
  }
}

async function generateCode(userId, username) {
  if (!confirm(`Generate kode autentikasi baru untuk '${username}'? Kode lama akan tidak berlaku.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/admin/users/${userId}/auth-code`, {
      method: "POST",
    });
    const json = await res.json();
    if (!res.ok || json.status !== "ok") {
      alert(json.message || "Gagal membuat kode autentikasi.");
      return;
    }
    showCodeModal(json.username || username, json.code || "", json.expires_at || "");
    await loadUsers();
  } catch (_) {
    alert("Gagal terhubung ke server.");
  }
}

function showPasswordModal(username, password) {
  document.getElementById("newUsernameValue").value = username;
  document.getElementById("newPasswordValue").value = password;
  document.getElementById("passwordModalBackdrop").classList.add("open");
}

function showCodeModal(username, code, expiry) {
  document.getElementById("codeUsernameValue").value = username;
  document.getElementById("authCodeValue").value = code;
  document.getElementById("authCodeExpiryValue").value = expiry;
  document.getElementById("codeModalBackdrop").classList.add("open");
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("open");
}

async function copySecret(inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const text = input.value;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    alert("Berhasil disalin.");
  } catch (_) {
    input.select();
    document.execCommand("copy");
    alert("Berhasil disalin.");
  }
}

function setCreateMessage(message, type) {
  const el = document.getElementById("createUserMessage");
  el.textContent = message;
  el.className = `admin-message ${type}`;
}

function clearCreateMessage() {
  const el = document.getElementById("createUserMessage");
  el.className = "admin-message";
  el.textContent = "";
}
