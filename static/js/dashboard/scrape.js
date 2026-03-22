async function scrapeBerita() {
  const btn = document.getElementById("btnScrape");
  btn.classList.add("loading");
  btn.disabled = true;

  const input = document.getElementById("maxArticles");
  maxArticlesGlobal = input.value ? parseInt(input.value) : 150;

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

const SOURCE_KEYS = [
  "radartegal",
  "panturapost",
  "tribunjateng",
  "kompas",
  "setdategal",
];

function resetProgressBars() {
  document.getElementById("progressSubtitle").textContent = "Memulai...";
  SOURCE_KEYS.forEach((key) => {
    document.getElementById(`bar-${key}`).style.width = "0%";
    document.getElementById(`bar-${key}`).className = "progress-bar-fill";
    document.getElementById(`count-${key}`).textContent = "0";
    document.getElementById(`status-${key}`).textContent = "Menunggu...";
  });
}

function updateProgressUI(progress, overall) {
  const max = maxArticlesGlobal || 150;
  let runningSource = "";

  SOURCE_KEYS.forEach((key) => {
    const src = progress[key];
    if (!src) return;

    const pct = Math.min(100, Math.round((src.scraped / max) * 100));
    const bar = document.getElementById(`bar-${key}`);
    const count = document.getElementById(`count-${key}`);
    const status = document.getElementById(`status-${key}`);

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
  if (runningSource) {
    const labels = {
      radartegal: "Radar Tegal",
      panturapost: "Pantura Post",
      tribunjateng: "Tribun Jateng",
      kompas: "Kompas",
      setdategal: "Setda Tegal",
    };
    subtitle.textContent = `Sedang: ${labels[runningSource] || runningSource}`;
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
  subtitle.textContent = `Selesai — ${total} berita baru disimpan`;

  SOURCE_KEYS.forEach((key) => {
    const bar = document.getElementById(`bar-${key}`);
    if (bar.className.includes("running")) {
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
