let currentProvider = null;
let keyAvailability = { deepseek: false, gemini: false };

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }

  if (typeof showPageLoadingOverlay === "function") {
    showPageLoadingOverlay({
      title: "Menyiapkan pengaturan LLM...",
      subtitle: "Provider dan data usage sedang dimuat.",
    });
  }

  bindEvents();

  try {
    await loadProvider();
    await loadUsage();
  } finally {
    if (typeof hidePageLoadingOverlay === "function") {
      hidePageLoadingOverlay();
    }
  }
});

const bindEvents = () => {
  document.getElementById("btnSaveProvider").addEventListener("click", onSaveProvider);
  document.getElementById("btnRefreshUsage").addEventListener("click", loadUsage);
  document.getElementById("llmUsageDays").addEventListener("change", loadUsage);
  document.querySelectorAll('input[name="llmProvider"]').forEach((radio) => {
    radio.addEventListener("change", renderProviderSelection);
  });
};

async function loadProvider() {
  const statusText = document.getElementById("llmProviderStatusText");
  try {
    const response = await fetch("/api/admin/llm/provider");
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
      statusText.textContent = "Gagal memuat provider aktif.";
      return;
    }

    currentProvider = payload.provider;
    keyAvailability = payload.key_available || { deepseek: false, gemini: false };
    applyProviderToForm();
  } catch (_) {
    statusText.textContent = "Gagal memuat provider aktif.";
  }
}

const applyProviderToForm = () => {
  document.querySelectorAll('input[name="llmProvider"]').forEach((radio) => {
    radio.checked = radio.value === currentProvider;
  });

  document.getElementById("keyPillDeepseek").textContent = keyAvailability.deepseek ? "Key ada" : "Key kosong";
  document.getElementById("keyPillDeepseek").className = `llm-key-pill ${keyAvailability.deepseek ? "yes" : "no"}`;
  document.getElementById("keyPillGemini").textContent = keyAvailability.gemini ? "Key ada" : "Key kosong";
  document.getElementById("keyPillGemini").className = `llm-key-pill ${keyAvailability.gemini ? "yes" : "no"}`;

  document.getElementById("llmProviderStatusText").textContent = `Provider aktif: ${currentProvider || "-"}`;
  renderProviderSelection();
};

const renderProviderSelection = () => {
  const selected = document.querySelector('input[name="llmProvider"]:checked')?.value;
  document.querySelectorAll(".llm-provider-option").forEach((option) => {
    option.classList.toggle("selected", option.dataset.provider === selected);
  });

  const warningBox = document.getElementById("llmProviderWarning");
  if (selected && !keyAvailability[selected]) {
    warningBox.style.display = "block";
    warningBox.textContent =
      `API key untuk '${selected}' belum di-set di .env. Kalau disimpan, fitur LLM akan otomatis fallback ke provider yang key-nya tersedia sampai key diisi.`;
  } else {
    warningBox.style.display = "none";
  }
};

async function onSaveProvider() {
  const selected = document.querySelector('input[name="llmProvider"]:checked')?.value;
  const messageBox = document.getElementById("llmProviderMessage");
  const button = document.getElementById("btnSaveProvider");

  if (!selected) {
    setProviderMessage("Pilih salah satu provider dulu.", "error");
    return;
  }

  button.disabled = true;
  try {
    const response = await fetch("/api/admin/llm/provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: selected }),
    });
    const payload = await response.json();

    if (!response.ok || payload.status !== "ok") {
      setProviderMessage(payload.message || "Gagal simpan provider.", "error");
      return;
    }

    currentProvider = payload.provider;
    keyAvailability = payload.key_available || keyAvailability;
    applyProviderToForm();
    setProviderMessage(payload.warning || "Provider default berhasil disimpan.", payload.warning ? "warn" : "success");
  } catch (_) {
    setProviderMessage("Gagal simpan provider.", "error");
  } finally {
    button.disabled = false;
  }
}

const setProviderMessage = (text, type) => {
  const element = document.getElementById("llmProviderMessage");
  element.className = `admin-message ${type}`;
  element.textContent = text;
};

async function loadUsage() {
  const tbody = document.getElementById("llmUsageTableBody");
  const days = document.getElementById("llmUsageDays").value || "30";
  tbody.innerHTML = `<tr><td colspan="6" class="table-empty">Memuat data usage...</td></tr>`;

  try {
    const response = await fetch(`/api/admin/llm/usage?days=${encodeURIComponent(days)}`);
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
      tbody.innerHTML = `<tr><td colspan="6" class="table-empty">Gagal memuat data usage.</td></tr>`;
      return;
    }

    renderUsageTable(payload.rows || []);
  } catch (_) {
    tbody.innerHTML = `<tr><td colspan="6" class="table-empty">Gagal memuat data usage.</td></tr>`;
  }
}

const renderUsageTable = (rows) => {
  const tbody = document.getElementById("llmUsageTableBody");

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="table-empty">Belum ada data usage pada rentang ini.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((row) => {
      const failed = Math.max(0, (row.request_count || 0) - (row.success_count || 0));
      return `
        <tr>
          <td>${escapeHtml(row.feature || "-")}</td>
          <td>${escapeHtml(row.provider || "-")}</td>
          <td>${escapeHtml(row.model || "-")}</td>
          <td>${row.request_count || 0}</td>
          <td>${failed}</td>
          <td>${(row.total_tokens || 0).toLocaleString("id-ID")}</td>
        </tr>
      `;
    })
    .join("");
};
