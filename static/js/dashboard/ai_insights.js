// ── AI Insights ───────────────────────────────────────────────────────────────

// ── Custom Actor Dropdown ─────────────────────────────────────────────────────

function selectActor(value) {
  _currentActor = value;
  const label = document.getElementById("aiActorLabel");
  if (label) label.textContent = _ACTOR_LABELS[value] || value;
  const subtitleLabel = document.getElementById("aiActorSubtitleLabel");
  if (subtitleLabel) subtitleLabel.textContent = _ACTOR_SUBTITLE_LABELS[value] || value;
  document.querySelectorAll("#aiActorMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
  closeActorDropdown();
  loadAIInsights({ forceRefresh: false });
}

function toggleActorDropdown() {
  const menu = document.getElementById("aiActorMenu");
  const btn  = document.getElementById("aiActorBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closeActorDropdown() {
  const menu = document.getElementById("aiActorMenu");
  const btn  = document.getElementById("aiActorBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

// ── Custom Period Dropdown ────────────────────────────────────────────────────

function _getDefaultPeriod() {
  const month = new Date().getMonth() + 1;
  if (month <= 3) return "q1";
  if (month <= 6) return "q2";
  if (month <= 9) return "q3";
  return "q4";
}

function _initPeriodDropdown() {
  if (_currentPeriod) return;
  const def = _getDefaultPeriod();
  _currentPeriod = def;
  const label = document.getElementById("aiPeriodLabel");
  if (label) label.textContent = _PERIOD_LABELS[def] || def;
  // Mark active option (hanya period dropdown, bukan actor)
  document.querySelectorAll("#aiPeriodMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === def);
  });
  // Close menus on outside click
  document.addEventListener("click", (e) => {
    const ddPeriod = document.getElementById("aiPeriodDropdown");
    if (ddPeriod && !ddPeriod.contains(e.target)) closePeriodDropdown();
    const ddActor = document.getElementById("aiActorDropdown");
    if (ddActor && !ddActor.contains(e.target)) closeActorDropdown();
  });
  // Isi dropdown tahun
  _initYearDropdown();
}

async function _initYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const label = document.getElementById("aiYearLabel");
  if (!menu) return;
  try {
    const res = await fetch("/api/berita/years");
    const json = await res.json();
    const years =
      json.status === "ok" && json.years?.length ? json.years : [_currentYear];
    // Pastikan _currentYear valid
    if (!years.includes(_currentYear)) {
      _currentYear = years[0];
    }
    if (label) label.textContent = _currentYear;
    // Render opsi
    menu.innerHTML = years
      .map(
        (y) =>
          `<button class="ai-period-option${y === _currentYear ? " active" : ""}" 
                data-year="${y}" onclick="selectYear('${y}')">${y}</button>`,
      )
      .join("");
    // Close on outside click
    document.addEventListener(
      "click",
      (e) => {
        const dd = document.getElementById("aiYearDropdown");
        if (dd && !dd.contains(e.target)) closeYearDropdown();
      },
      { once: false },
    );
  } catch {
    if (label) label.textContent = _currentYear;
    menu.innerHTML = `<button class="ai-period-option active" onclick="selectYear('${_currentYear}')">${_currentYear}</button>`;
  }
}

function toggleYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const btn = document.getElementById("aiYearBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closeYearDropdown() {
  const menu = document.getElementById("aiYearMenu");
  const btn = document.getElementById("aiYearBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

function selectYear(value) {
  _currentYear = value;
  // Update label
  const label = document.getElementById("aiYearLabel");
  if (label) label.textContent = value;
  // Update active state
  document.querySelectorAll("#aiYearMenu .ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.year === value);
  });
  closeYearDropdown();
  loadAIInsights({ forceRefresh: false });
}

function togglePeriodDropdown() {
  const menu = document.getElementById("aiPeriodMenu");
  const btn = document.getElementById("aiPeriodBtn");
  if (!menu) return;
  const isOpen = menu.style.display !== "none";
  menu.style.display = isOpen ? "none" : "";
  btn?.classList.toggle("open", !isOpen);
}

function closePeriodDropdown() {
  const menu = document.getElementById("aiPeriodMenu");
  const btn = document.getElementById("aiPeriodBtn");
  if (menu) menu.style.display = "none";
  btn?.classList.remove("open");
}

function selectPeriod(value, label) {
  _currentPeriod = value;
  const labelEl = document.getElementById("aiPeriodLabel");
  if (labelEl) labelEl.textContent = label;
  document.querySelectorAll(".ai-period-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
  closePeriodDropdown();
  loadAIInsights({ forceRefresh: false });
}

function setAILoading(loading, articleCount) {
  _aiLoading = loading;
  const btn = document.getElementById("btnRefreshAI");
  const statusBar = document.getElementById("aiLoadingStatus");
  const statusText = document.getElementById("aiLoadingText");
  const refreshTxt = document.getElementById("btnRefreshText");
  const icon = document.getElementById("refreshIcon");

  if (loading) {
    if (btn) {
      btn.classList.add("loading");
      btn.disabled = true;
    }
    if (refreshTxt) refreshTxt.textContent = "Memuat...";
    if (statusBar) statusBar.style.display = "";
    const n = articleCount ? `${articleCount}` : "";
    if (statusText)
      statusText.textContent = n
        ? `Menganalisis ${n} berita dengan Gemini AI...`
        : "Menganalisis berita dengan Gemini AI...";
    // Animasi pulse pada cards
    ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach((id) => {
      document.getElementById(id)?.classList.add("ai-card-loading");
    });
  } else {
    if (btn) {
      btn.classList.remove("loading");
      btn.disabled = false;
    }
    if (refreshTxt) refreshTxt.textContent = "Refresh";
    if (statusBar) statusBar.style.display = "none";
    ["aiCardPdrb", "aiCardKemiskinan", "aiCardPengangguran"].forEach((id) => {
      document.getElementById(id)?.classList.remove("ai-card-loading");
    });
  }
}

function _showAISkeleton() {
  const skeletonHtml = `<div class="ai-skeleton">
        <div class="ai-skeleton-line"></div>
        <div class="ai-skeleton-line w80"></div>
        <div class="ai-skeleton-line w90"></div>
        <div class="ai-skeleton-line w70"></div>
    </div>`;
  ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = skeletonHtml;
  });
  // Sembunyikan sumber
  ["aiSourcesPdrb", "aiSourcesKemiskinan", "aiSourcesPengangguran"].forEach(
    (id) => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    },
  );
}

function _showAIError(message) {
  const errorHtml = `<div class="ai-error">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        ${escapeHtml(message)}
    </div>`;
  ["aiBodyPdrb", "aiBodyKemiskinan", "aiBodyPengangguran"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = errorHtml;
  });
}

function _renderSources(catKey, sources) {
  // catKey: "Pdrb" | "Kemiskinan" | "Pengangguran"
  const wrap = document.getElementById(`aiSources${catKey}`);
  const label = document.getElementById(`aiSourcesLabel${catKey}`);
  const list = document.getElementById(`aiSourcesList${catKey}`);
  if (!wrap || !label || !list) return;

  if (!sources || sources.length === 0) {
    wrap.style.display = "none";
    return;
  }

  label.textContent = `Sumber Berita (${sources.length})`;
  list.innerHTML = sources
    .map((s) => {
      const title = escapeHtml(s.title || "—");
      const url = escapeHtml(s.url || "#");
      const num = Number(s.num || 0) > 0 ? `<strong>[${Number(s.num)}]</strong> ` : "";
      return `<li><a href="${url}" target="_blank" rel="noopener noreferrer">${num}${title}</a></li>`;
    })
    .join("");
  wrap.style.display = "";
  list.style.display = "none"; // collapsed by default
}

function toggleSources(catKey) {
  const list = document.getElementById(`aiSourcesList${catKey}`);
  const btn = document.querySelector(`#aiSources${catKey} .ai-sources-toggle`);
  if (!list) return;
  const isOpen = list.style.display !== "none";
  list.style.display = isOpen ? "none" : "";
  if (btn) btn.classList.toggle("open", !isOpen);
}

function _buildSourceMapByTag(sourceList = []) {
  const map = {};
  if (!Array.isArray(sourceList)) return map;
  sourceList.forEach((s, idx) => {
    const tag = String(s?.tag_id || "").toUpperCase();
    if (!tag) return;
    map[tag] = {
      ...s,
      num: Number(s.num || 0) > 0 ? Number(s.num) : idx + 1,
    };
  });
  return map;
}

function _renderInsightCitationLink(source) {
  const num = Number(source?.num || 0) > 0 ? Number(source.num) : 1;
  const url = escapeHtml(source?.url || "#");
  const title = escapeHtml(source?.title || "Sumber berita");
  return `<a class="ai-cite" href="${url}" target="_blank" rel="noopener noreferrer" title="${title}">${num}</a>`;
}

function _renderInsightMarkdownHtml(text, sourceMapByTag = {}) {
  const raw = String(text || "");

  // Backward compatibility: data lama dari backend sudah berupa HTML inline citation
  if (raw.includes("<a") && raw.includes("ai-cite")) {
    return `<div class="ai-insight-text md-content">${raw}</div>`;
  }

  const normalized = _normalizeCitationMarkers(raw, "PKT");
  let html = _markdownToHtmlSafe(normalized);

  // Jika map tersedia, ganti marker [P01]/[K01]/[T01] menjadi link angka inline.
  if (sourceMapByTag && Object.keys(sourceMapByTag).length > 0) {
    html = html.replace(/\[([PKT]\d{2})\]/gi, (_, rawId) => {
      const tag = String(rawId || "").toUpperCase();
      const src = sourceMapByTag[tag];
      if (!src) return "";
      return _renderInsightCitationLink(src);
    });
  }

  return `<div class="ai-insight-text md-content">${html}</div>`;
}

function renderAIInsights(json) {
  const { data, article_count: count, quarter, sources = {} } = json;

  // Teks insight (render langsung; streaming token ditangani event SSE delta)
  const categoryMap = {
    aiBodyPdrb: data?.pdrb || "—",
    aiBodyKemiskinan: data?.kemiskinan || "—",
    aiBodyPengangguran: data?.pengangguran || "—",
  };

  Object.entries(categoryMap).forEach(([id, text]) => {
    const el = document.getElementById(id);
    if (!el) return;

    const catKey =
      id === "aiBodyPdrb"
        ? "pdrb"
        : id === "aiBodyKemiskinan"
        ? "kemiskinan"
        : "pengangguran";
    const map = _buildSourceMapByTag(sources[catKey] || []);
    el.innerHTML = _renderInsightMarkdownHtml(text || "—", map);
  });

  // Label periode
  const quarterEl = document.getElementById("aiQuarterLabel");
  if (quarterEl) quarterEl.textContent = quarter || "periode ini";

  // Label aktor di subtitle
  const actorSubtitleEl = document.getElementById("aiActorSubtitleLabel");
  if (actorSubtitleEl) actorSubtitleEl.textContent = _ACTOR_SUBTITLE_LABELS[_currentActor] || _ACTOR_LABELS[_currentActor] || "BPS";

  // Badge jumlah berita
  const countBadge = document.getElementById("aiArticleCount");
  const countText = document.getElementById("aiArticleCountText");
  if (countBadge && countText) {
    countText.textContent = `${count} berita dianalisis`;
    countBadge.style.display = count ? "" : "none";
  }

  // Sumber berita per kategori
  _renderSources("Pdrb", sources.pdrb || []);
  _renderSources("Kemiskinan", sources.kemiskinan || []);
  _renderSources("Pengangguran", sources.pengangguran || []);
}

async function loadAIInsights({
  forceRefresh = false,
  period = "",
} = {}) {
  if (_aiLoading) return;

  if (_aiInsightStream) {
    _aiInsightStream.close();
    _aiInsightStream = null;
  }

  _initPeriodDropdown();
  const selectedPeriod = period || _currentPeriod || _getDefaultPeriod();

  // ── Cek sessionStorage terlebih dahulu ────────────────────────────────────
  // Tujuan: hindari hit backend setiap kali user kembali ke halaman
  // dalam sesi browser yang sama.
  // forceRefresh bypass cache karena butuh data segar.
  if (!forceRefresh) {
    const cacheKey = `ai_insights_v2_${_currentActor}_${selectedPeriod}_${_currentYear || ""}`;
    try {
      const raw = sessionStorage.getItem(cacheKey);
      if (raw) {
        const cached = JSON.parse(raw);
        if (cached && cached.status === "ok") {
          renderAIInsights(cached);
          return; // ← langsung render, tidak hit backend sama sekali
        }
      }
    } catch (_) {
      /* abaikan error parse / storage penuh */
    }
  }

  setAILoading(true);
  if (!forceRefresh) _showAISkeleton();
  if (typeof trackEvent === "function") trackEvent("ai_insight_generate");

  try {
    const params = new URLSearchParams({ period: selectedPeriod });
    if (forceRefresh) params.set("refresh", "1");
    if (_currentYear)  params.set("year", _currentYear);
    params.set("actor", _currentActor);
    const url = "/api/ai-insights/stream?" + params.toString();

    const streamState = {
      pdrb: "",
      kemiskinan: "",
      pengangguran: "",
      sourceMap: {
        pdrb: {},
        kemiskinan: {},
        pengangguran: {},
      },
      sources: {
        pdrb: [],
        kemiskinan: [],
        pengangguran: [],
      },
      quarter: "",
      article_count: 0,
      done: false,
    };

    const categoryToElement = {
      pdrb: "aiBodyPdrb",
      kemiskinan: "aiBodyKemiskinan",
      pengangguran: "aiBodyPengangguran",
    };

    _aiInsightStream = new EventSource(url);

    await new Promise((resolve, reject) => {
      _aiInsightStream.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data || "{}");
          const statusText = document.getElementById("aiLoadingText");

          if (payload.type === "start") {
            streamState.article_count = Number(payload.article_count || 0);
            streamState.quarter = payload.quarter || "periode ini";
            if (statusText) {
              statusText.textContent = `Insight AI sedang dibuat (${streamState.article_count} berita)...`;
            }
            return;
          }

          if (payload.type === "category_start") {
            const cat = payload.category;
            streamState.sourceMap[cat] = _buildSourceMapByTag(payload.source_map || []);
            return;
          }

          if (payload.type === "delta") {
            const cat = payload.category;
            streamState[cat] = (streamState[cat] || "") + (payload.text || "");
            const el = document.getElementById(categoryToElement[cat]);
            if (el) {
              el.innerHTML = _renderInsightMarkdownHtml(
                streamState[cat],
                streamState.sourceMap[cat] || {},
              );
            }
            return;
          }

          if (payload.type === "category_done") {
            const cat = payload.category;
            streamState[cat] = payload.text || streamState[cat] || "";
            streamState.sources[cat] = payload.sources || [];
            const el = document.getElementById(categoryToElement[cat]);
            if (el) {
              el.innerHTML = _renderInsightMarkdownHtml(
                streamState[cat],
                streamState.sourceMap[cat] || {},
              );
            }
            return;
          }

          if (payload.type === "done") {
            const finalJson = {
              status: payload.status || "ok",
              cached: !!payload.cached,
              quarter: payload.quarter || streamState.quarter,
              article_count: payload.article_count ?? streamState.article_count,
              data: payload.data || {
                pdrb: streamState.pdrb,
                kemiskinan: streamState.kemiskinan,
                pengangguran: streamState.pengangguran,
              },
              sources: payload.sources || streamState.sources,
            };

            renderAIInsights(finalJson);

            try {
              const cacheKey = `ai_insights_v2_${_currentActor}_${selectedPeriod}_${_currentYear || ""}`;
              sessionStorage.setItem(cacheKey, JSON.stringify(finalJson));
            } catch (_) {
              // ignore
            }

            if (statusText) {
              statusText.textContent = `Selesai — ${finalJson.article_count || 0} berita dianalisis.`;
            }

            streamState.done = true;
            resolve();
            return;
          }

          if (payload.type === "error") {
            reject(new Error(payload.message || "Gagal memuat insight AI."));
          }
        } catch (err) {
          reject(err);
        }
      };

      _aiInsightStream.onerror = () => {
        if (!streamState.done) {
          reject(new Error("Koneksi stream terputus saat memuat insight AI."));
        }
      };
    });
  } catch (err) {
    _showAIError("Gagal menghubungi server. Coba refresh halaman.");
    console.error("AI Insights error:", err);
  } finally {
    if (_aiInsightStream) {
      _aiInsightStream.close();
      _aiInsightStream = null;
    }
    setAILoading(false);
  }
}

function refreshAIInsights() {
  if (_aiInsightStream) {
    _aiInsightStream.close();
    _aiInsightStream = null;
  }
  // Hapus cache sessionStorage untuk periode yang sedang aktif,
  // agar forceRefresh benar-benar mengambil data segar dari backend.
  try {
    const p = _currentPeriod || _getDefaultPeriod();
    sessionStorage.removeItem(`ai_insights_v2_${_currentActor}_${p}_${_currentYear || ""}`);
  } catch (_) {
    /* abaikan */
  }
  loadAIInsights({ forceRefresh: true });
}
