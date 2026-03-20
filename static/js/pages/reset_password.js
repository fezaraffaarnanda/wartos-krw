async function handleReset(e) {
  e.preventDefault();
  const username = document.getElementById("username").value.trim();
  const code = document.getElementById("codeInput").value.trim().toUpperCase();
  const newPw = document.getElementById("newPassword").value;
  const confPw = document.getElementById("confirmPassword").value;
  hideError();

  if (!username || !code || !newPw || !confPw) {
    showError("Semua field wajib diisi.");
    return;
  }
  if (code.length !== 8) {
    showError("Kode autentikasi harus 8 karakter.");
    return;
  }
  if (newPw.length < 8) {
    showError("Password baru minimal 8 karakter.");
    return;
  }
  if (newPw !== confPw) {
    showError("Password baru dan konfirmasi tidak cocok.");
    return;
  }

  setLoading(true);
  try {
    const res = await fetch("/api/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, code, new_password: newPw }),
    });
    const json = await res.json();

    if (res.ok && json.status === "ok") {
      document.getElementById("formState").classList.add("is-hidden");
      document.getElementById("successState").classList.remove("is-hidden");
    } else if (res.status === 429) {
      showError("Terlalu banyak percobaan. Coba lagi dalam beberapa menit.");
    } else {
      showError(json.message || "Gagal mereset password.");
    }
  } catch (_) {
    showError("Gagal terhubung ke server. Coba lagi.");
  } finally {
    setLoading(false);
  }
}

function checkStrength(pw) {
  const fill = document.getElementById("strengthFill");
  const text = document.getElementById("strengthText");
  if (!pw) {
    fill.style.width = "0%";
    text.textContent = "";
    return;
  }

  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;

  const levels = [
    { pct: "20%", color: "#e74c3c", label: "Sangat Lemah" },
    { pct: "40%", color: "#e67e22", label: "Lemah" },
    { pct: "60%", color: "#f1c40f", label: "Cukup" },
    { pct: "80%", color: "#2ecc71", label: "Kuat" },
    { pct: "100%", color: "#27ae60", label: "Sangat Kuat" },
  ];
  const lvl = levels[Math.min(score - 1, 4)] || levels[0];
  fill.style.width = lvl.pct;
  fill.style.backgroundColor = lvl.color;
  text.textContent = lvl.label;
  text.style.color = lvl.color;
}

function togglePw(inputId, iconId) {
  const input = document.getElementById(inputId);
  const icon = document.getElementById(iconId);
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  icon.innerHTML = show
    ? `<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>`
    : `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>`;
}

function setLoading(on) {
  const btn = document.getElementById("btnReset");
  const text = btn.querySelector(".btn-text");
  const loader = document.getElementById("resetLoader");
  btn.disabled = on;
  text.style.opacity = on ? "0" : "1";
  loader.style.display = on ? "block" : "none";
}

function showError(msg) {
  const el = document.getElementById("formError");
  el.textContent = msg;
  el.classList.remove("is-hidden");
}

function hideError() {
  document.getElementById("formError").classList.add("is-hidden");
}
