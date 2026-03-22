async function handleLogin(e) {
  e.preventDefault();

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();

  hideError();

  if (!username || !password) {
    showError("Username dan password wajib diisi.");
    return;
  }

  setLoading(true);

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const json = await res.json();

    if (res.ok && json.status === "ok") {
      if (json.must_change_password) {
        window.location.href = "/change-password";
      } else {
        window.location.href = "/";
      }
    } else if (res.status === 429) {
      showError("Terlalu banyak percobaan login. Coba lagi dalam beberapa menit.");
    } else {
      showError(json.message || "Username atau password salah.");
    }
  } catch (_) {
    showError("Gagal terhubung ke server. Coba lagi.");
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  const btn = document.getElementById("btnLogin");
  const text = btn.querySelector(".btn-text");
  const loader = document.getElementById("loginLoader");
  btn.disabled = on;
  text.style.opacity = on ? "0" : "1";
  loader.style.display = on ? "block" : "none";
}

function showError(msg) {
  const el = document.getElementById("loginError");
  el.textContent = msg;
  el.classList.remove("is-hidden");
}

function hideError() {
  const el = document.getElementById("loginError");
  el.classList.add("is-hidden");
}

function togglePassword() {
  const input = document.getElementById("password");
  const icon = document.getElementById("eyeIcon");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  icon.innerHTML = show
    ? `<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>`
    : `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>`;
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/me");
    if (res.ok) {
      const json = await res.json();
      if (json.status === "ok") {
        window.location.href = json.must_change_password ? "/change-password" : "/";
      }
    }
  } catch (_) {
    // belum login
  }
});
