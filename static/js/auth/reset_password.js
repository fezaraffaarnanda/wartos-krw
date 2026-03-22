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
