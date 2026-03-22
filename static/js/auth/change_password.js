document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/me");
    const json = await res.json();
    if (!res.ok || json.status !== "ok") {
      window.location.href = "/login";
      return;
    }
    if (!json.must_change_password) {
      document.getElementById("mandatoryNote")?.classList.add("is-hidden");
    }
  } catch (_) {
    window.location.href = "/login";
  }
});

async function handleChangePassword(e) {
  e.preventDefault();
  const newPw = document.getElementById("newPassword").value;
  const confPw = document.getElementById("confirmPassword").value;
  hideMsg();

  if (newPw.length < 8) {
    showMsg("Password baru minimal 8 karakter.", "error");
    return;
  }
  if (newPw !== confPw) {
    showMsg("Password baru dan konfirmasi tidak cocok.", "error");
    return;
  }

  setLoading(true);
  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: newPw }),
    });
    const json = await res.json();

    if (res.ok && json.status === "ok") {
      showMsg("Password berhasil diubah! Mengalihkan ke dashboard...", "success");
      setTimeout(() => {
        window.location.href = "/";
      }, 1500);
    } else {
      showMsg(json.message || "Gagal mengubah password.", "error");
    }
  } catch (_) {
    showMsg("Gagal terhubung ke server. Coba lagi.", "error");
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  const btn = document.getElementById("btnSubmit");
  const text = btn.querySelector(".btn-text");
  const loader = document.getElementById("submitLoader");
  btn.disabled = on;
  text.style.opacity = on ? "0" : "1";
  loader.style.display = on ? "block" : "none";
}

function showMsg(msg, type) {
  const el = document.getElementById("formMessage");
  el.textContent = msg;
  el.classList.remove("is-hidden");
  el.classList.toggle("is-success", type === "success");
}

function hideMsg() {
  const el = document.getElementById("formMessage");
  el.classList.add("is-hidden");
  el.classList.remove("is-success");
}
