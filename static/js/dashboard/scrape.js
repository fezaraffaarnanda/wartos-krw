async function scrapeBerita() {
  const btn = document.getElementById("btnScrape");
  btn.classList.add("loading");
  btn.disabled = true;

  const input = document.getElementById("maxArticles");
  maxArticlesGlobal = input.value ? parseInt(input.value) : 150;

  await loadNewsSources();
  renderProgressRows("progressRows");

  showProgress();
  resetProgressBars();

  try {
    const res = await fetch("/api/scrape", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_articles: maxArticlesGlobal }),
    });

    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }

    const json = await res.json();

    if (json.status === "started") {
      if (typeof trackEvent === "function") trackEvent("scrape_run");
      startPolling();
    } else {
      alert("Error: " + (json.message || "Terjadi kesalahan."));
      hideProgress();
      btn.classList.remove("loading");
      btn.disabled = false;
    }
  } catch (err) {
    alert("Gagal menjalankan scraping: " + err.message);
    hideProgress();
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// ── Progress polling ──────────────────────────────────────────────────────────

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(fetchProgress, 1500);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function fetchProgress() {
  try {
    const res = await fetch("/api/scrape/progress");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const json = await res.json();
    updateProgressUI(json.progress, json.overall);

    if (json.overall && json.overall.done) {
      stopPolling();
      onScrapingDone(json.overall);
    }
  } catch (err) {
    console.error("Gagal fetch progress:", err);
  }
}

function resetProgressBars() {
  const sub = document.getElementById("progressSubtitle");
  if (sub) sub.textContent = "Memulai...";
  SOURCE_KEYS.forEach((key) => {
    const bar = document.getElementById(`bar-${key}`);
    const count = document.getElementById(`count-${key}`);
    const status = document.getElementById(`status-${key}`);
    if (!bar || !count || !status) return;
    bar.style.width = "0%";
    bar.className = "progress-bar-fill";
    count.textContent = "0";
    status.textContent = "Menunggu...";
  });
}

function updateProgressUI(progress, overall) {
  const max = maxArticlesGlobal || 150;
  let runningSource = "";

  SOURCE_KEYS.forEach((key) => {
    const src = progress[key];
    if (!src) return;

    const bar = document.getElementById(`bar-${key}`);
    const count = document.getElementById(`count-${key}`);
    const status = document.getElementById(`status-${key}`);
    if (!bar || !count || !status) return;

    const pct = Math.min(100, Math.round((src.scraped / max) * 100));
    bar.style.width = pct + "%";
    count.textContent = src.scraped;

    if (src.status === "running") {
      bar.className = "progress-bar-fill running";
      status.textContent = src.message || "Berjalan...";
      runningSource = key;
    } else if (src.status === "done") {
      bar.className = "progress-bar-fill done";
      bar.style.width = "100%";
      status.textContent = src.message || "Selesai";
    } else if (src.status === "error") {
      bar.className = "progress-bar-fill error";
      status.textContent = src.message || "Error";
    } else {
      status.textContent = src.message || "Menunggu...";
    }
  });

  const subtitle = document.getElementById("progressSubtitle");
  if (!subtitle) return;
  if (runningSource) {
    subtitle.textContent = `Sedang: ${SOURCE_LABELS_UI[runningSource] || runningSource}`;
  } else if (overall && overall.active) {
    subtitle.textContent = "Menyiapkan sumber berikutnya...";
  }
}

function onScrapingDone(overall) {
  const btn = document.getElementById("btnScrape");
  btn.classList.remove("loading");
  btn.disabled = false;

  const subtitle = document.getElementById("progressSubtitle");
  const total = overall.total_inserted || 0;
  if (subtitle) subtitle.textContent = `Selesai — ${total} berita baru disimpan`;

  SOURCE_KEYS.forEach((key) => {
    const bar = document.getElementById(`bar-${key}`);
    if (bar && bar.className.includes("running")) {
      bar.className = "progress-bar-fill done";
      bar.style.width = "100%";
    }
  });

  if (overall.error) {
    alert("Scraping selesai dengan error: " + overall.error);
  }

  loadOverviewSummary();
  loadBerita();
  loadLastScrape();
}

function showProgress() {
  document.getElementById("scrapeProgress").style.display = "block";
}

function hideProgress() {
  document.getElementById("scrapeProgress").style.display = "none";
}
