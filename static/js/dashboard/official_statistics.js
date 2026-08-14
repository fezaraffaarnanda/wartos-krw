const OFFICIAL_STATISTICS_YEARS = ["2026", "2025", "2024"];

const OFFICIAL_STATISTICS_BODY_IDS = [
  "officialPdrbLapanganUsahaBody",
  "officialPdrbPengeluaranBody",
  "officialTptTpakBody",
  "officialKemiskinanBody",
];

// Dua seri harga dibedakan lewat hue tetap, bukan gradasi nilai: identitas seri
// tidak boleh ikut berubah saat angkanya berubah.
const OFFICIAL_STATISTICS_SERIES_TONES = {
  adhb: { red: 37, green: 99, blue: 235 },
  adhk: { red: 234, green: 88, blue: 12 },
};

function initOfficialStatisticsControls() {
  const yearSelect = document.getElementById("officialStatsYearSelect");
  const refreshBtn = document.getElementById("officialStatsRefreshBtn");

  if (!yearSelect || yearSelect.dataset.ready === "1") return;

  yearSelect.innerHTML = OFFICIAL_STATISTICS_YEARS.map(
    (year) => `<option value="${escapeAttr(year)}">${escapeHtml(year)}</option>`,
  ).join("");
  yearSelect.value = _officialStatsYear;

  yearSelect.addEventListener("change", () => {
    _officialStatsYear = yearSelect.value || OFFICIAL_STATISTICS_YEARS[0];
    _officialStatsPeriod = "";
    loadOfficialStatistics({ forceRefresh: false });
  });

  refreshBtn?.addEventListener("click", () => {
    loadOfficialStatistics({ forceRefresh: true });
  });

  yearSelect.dataset.ready = "1";
}

function _ensureOfficialStatisticsReady() {
  initOfficialStatisticsControls();
  if (_officialStatsLoaded || _officialStatsLoading) return;
  loadOfficialStatistics({ forceRefresh: false });
}

async function loadOfficialStatistics({ forceRefresh = false } = {}) {
  if (_officialStatsLoading) return;

  initOfficialStatisticsControls();
  _setOfficialStatisticsLoading(true);
  _showOfficialStatisticsSkeleton();

  try {
    const params = new URLSearchParams({ year: _officialStatsYear || OFFICIAL_STATISTICS_YEARS[0] });
    if (forceRefresh) params.set("refresh", "1");

    const res = await fetch(`/api/official-statistics?${params.toString()}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }

    const json = await res.json();
    if (json.status !== "ok") {
      throw new Error(json.message || "Gagal memuat statistik resmi BPS.");
    }

    _officialStatsLoaded = true;
    renderOfficialStatistics(json);
  } catch (error) {
    console.error("Gagal memuat statistik resmi:", error);
    _renderOfficialStatisticsError(error.message || "Gagal memuat statistik resmi BPS.");
  } finally {
    _setOfficialStatisticsLoading(false);
  }
}

function _setOfficialStatisticsLoading(loading) {
  _officialStatsLoading = loading;

  const refreshBtn = document.getElementById("officialStatsRefreshBtn");
  const yearSelect = document.getElementById("officialStatsYearSelect");
  const status = document.getElementById("officialStatsStatusText");

  if (refreshBtn) {
    refreshBtn.disabled = loading;
    refreshBtn.classList.toggle("is-loading", loading);
    refreshBtn.textContent = loading ? "Memuat..." : "Refresh Data";
  }

  if (yearSelect) yearSelect.disabled = loading;
  if (status && loading) status.textContent = "Mengambil statistik resmi terbaru dari Web API BPS...";
}

function _showOfficialStatisticsSkeleton() {
  OFFICIAL_STATISTICS_BODY_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = `
      <div class="official-stat-skeleton">
        <div class="official-stat-skeleton-line w30"></div>
        <div class="official-stat-skeleton-grid">
          <div class="official-stat-skeleton-box"></div>
          <div class="official-stat-skeleton-box"></div>
          <div class="official-stat-skeleton-box"></div>
        </div>
        <div class="official-stat-skeleton-chart"></div>
        <div class="official-stat-skeleton-line"></div>
        <div class="official-stat-skeleton-line w80"></div>
      </div>
    `;
  });
}

function _renderOfficialStatisticsError(message) {
  OFFICIAL_STATISTICS_BODY_IDS.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = `<div class="official-stat-empty"><strong>Gagal memuat data.</strong><span>${escapeHtml(message)}</span></div>`;
  });

  const status = document.getElementById("officialStatsStatusText");
  if (status) status.textContent = "Terjadi kendala saat mengambil statistik resmi BPS.";

  _renderOfficialStatisticsPeriodControl([]);
  _destroyOfficialStatisticsCharts();
}

function renderOfficialStatistics(payload) {
  _officialStatsPayload = payload;

  const datasets = payload.datasets || {};
  const year = String(payload.year || _officialStatsYear || OFFICIAL_STATISTICS_YEARS[0]);
  _officialStatsYear = year;

  const yearSelect = document.getElementById("officialStatsYearSelect");
  if (yearSelect) yearSelect.value = year;

  const periods = _collectOfficialStatisticsPeriods(datasets);
  _officialStatsPeriod = _resolveOfficialStatisticsPeriod(periods, datasets);
  _renderOfficialStatisticsPeriodControl(periods);

  _renderOfficialStatisticsStatus(payload, datasets, periods);
  _renderOfficialStatisticsCards(datasets);
}

function _renderOfficialStatisticsCards(datasets) {
  _renderPdrbTriwulananCard("officialPdrbLapanganUsahaBody", datasets.pdrb_lapangan_usaha, {
    chartId: "officialPdrbLapanganUsahaChart",
    shareChartId: "officialPdrbLapanganUsahaShareChart",
    entityLabel: "Lapangan Usaha",
    limitValueChart: true,
  });
  _renderPdrbTriwulananCard("officialPdrbPengeluaranBody", datasets.pdrb_pengeluaran, {
    chartId: "officialPdrbPengeluaranChart",
    shareChartId: "officialPdrbPengeluaranShareChart",
    entityLabel: "Komponen Pengeluaran",
    limitValueChart: false,
  });
  _renderTptTpakCard("officialTptTpakBody", datasets.tpt_tpak);
  _renderKemiskinanCard("officialKemiskinanBody", datasets.kemiskinan);
}

function _renderOfficialStatisticsStatus(payload, datasets, periods) {
  const status = document.getElementById("officialStatsStatusText");
  if (!status) return;

  const availableCount = Number(payload.available_count || 0);
  const datasetCount = Number(payload.dataset_count || Object.keys(datasets).length || 0);
  const activePeriod = periods.find((period) => period.period_key === _officialStatsPeriod);
  const periodText = activePeriod ? ` — ${activePeriod.label} ${payload.year}` : "";

  status.textContent = `${availableCount}/${datasetCount} tabel resmi berhasil dimuat untuk tahun ${payload.year}${periodText}.`;
}

// ── Periode ────────────────────────────────────────────────────────────────

function _collectOfficialStatisticsPeriods(datasets) {
  const merged = new Map();

  ["pdrb_lapangan_usaha", "pdrb_pengeluaran"].forEach((key) => {
    (datasets[key]?.periods || []).forEach((period) => {
      const existing = merged.get(period.period_key);
      if (!existing) {
        merged.set(period.period_key, { ...period });
        return;
      }
      existing.available = existing.available || period.available;
    });
  });

  return Array.from(merged.values());
}

function _resolveOfficialStatisticsPeriod(periods, datasets) {
  const stillAvailable = periods.some(
    (period) => period.period_key === _officialStatsPeriod && period.available,
  );
  if (stillAvailable) return _officialStatsPeriod;

  const preferred =
    datasets.pdrb_lapangan_usaha?.default_period_key || datasets.pdrb_pengeluaran?.default_period_key;
  if (preferred) return preferred;

  return periods.find((period) => period.available)?.period_key || "";
}

function _renderOfficialStatisticsPeriodControl(periods) {
  const control = document.getElementById("officialStatsPeriodControl");
  if (!control) return;

  if (!periods.length) {
    control.innerHTML = "";
    control.hidden = true;
    return;
  }

  control.hidden = false;
  control.innerHTML = periods
    .map(
      (period) => `
        <button
          type="button"
          class="official-stats-period-btn${period.period_key === _officialStatsPeriod ? " is-active" : ""}"
          data-period="${escapeAttr(period.period_key)}"
          aria-pressed="${period.period_key === _officialStatsPeriod}"
          ${period.available ? "" : 'disabled title="Belum dirilis BPS untuk tahun ini."'}
        >${escapeHtml(period.label)}</button>
      `,
    )
    .join("");

  control.querySelectorAll("button[data-period]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPeriod = button.dataset.period || "";
      if (!nextPeriod || nextPeriod === _officialStatsPeriod) return;

      // Semua periode sudah ada di payload, jadi ganti periode cukup render ulang.
      _officialStatsPeriod = nextPeriod;
      if (_officialStatsPayload) renderOfficialStatistics(_officialStatsPayload);
    });
  });
}

// ── Kartu PDRB ─────────────────────────────────────────────────────────────

function _renderPdrbTriwulananCard(bodyId, dataset, { chartId, shareChartId, entityLabel, limitValueChart }) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  const block = dataset?.by_period?.[_officialStatsPeriod];
  if (!dataset || !dataset.available || !block) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(
      dataset?.message || "Tidak ada data untuk periode terpilih.",
    );
    _destroyOfficialStatisticsChart(chartId);
    _destroyOfficialStatisticsChart(shareChartId);
    return;
  }

  const total = block.total || {};
  const leadingRow = block.rows?.[0] || {};
  const valueRows = limitValueChart ? block.top_rows || [] : block.rows || [];
  const shareRows = (block.rows || []).filter((row) => typeof row.share === "number");

  const hasCodes = (block.rows || []).some((row) => Boolean(row.code));

  const rowsHtml = (block.rows || [])
    .map(
      (row) => `
        <tr>
          ${hasCodes ? `<td><strong>${escapeHtml(row.code || "—")}</strong></td>` : ""}
          <td>${escapeHtml(row.label || "—")}</td>
          <td>${escapeHtml(row.adhb_display || "—")}</td>
          <td>${escapeHtml(row.adhk_display || "—")}</td>
          <td>${escapeHtml(row.share_display || "—")}%</td>
          <td>${escapeHtml(row.implicit_index_display || "—")}</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-tight">
      ${_buildOfficialStatisticsMetricHtml("Total ADHB", `${total.adhb_display || "—"} miliar`)}
      ${_buildOfficialStatisticsMetricHtml("Total ADHK 2010", `${total.adhk_display || "—"} miliar`)}
      ${_buildOfficialStatisticsMetricHtml("Indeks Harga Implisit", total.implicit_index_display || "—")}
      ${_buildOfficialStatisticsMetricHtml(
        "Terbesar",
        `${leadingRow.label || "—"} (${leadingRow.share_display || "—"}%)`,
      )}
    </div>
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    ${_buildOfficialStatisticsComparisonHtml(dataset)}
    <div class="official-stat-chart-card tone-blue">
      <div class="official-stat-chart-head">
        <strong>Nilai ADHB dan ADHK</strong>
        <span>${escapeHtml(dataset.unit || "—")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="${escapeAttr(chartId)}"></canvas>
      </div>
    </div>
    <div class="official-stat-chart-card tone-teal">
      <div class="official-stat-chart-head">
        <strong>Distribusi terhadap Total PDRB</strong>
        <span>${escapeHtml(dataset.share_unit || "Persen")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="${escapeAttr(shareChartId)}"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: `Rincian ${entityLabel}`,
      subtitle: "IHI = indeks harga implisit (ADHB dibagi ADHK, basis 2010 = 100).",
      tableHead: `
        <tr>
          ${hasCodes ? "<th>Kode</th>" : ""}
          <th>${escapeHtml(entityLabel)}</th>
          <th>ADHB</th>
          <th>ADHK</th>
          <th>Share</th>
          <th>IHI</th>
        </tr>
      `,
      tableBody: rowsHtml,
      wrapClassName: "official-stat-table-wrap compact-scroll",
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderPdrbValueChart(chartId, valueRows);
  _renderPdrbShareChart(shareChartId, shareRows);
}

function _buildOfficialStatisticsComparisonHtml(dataset) {
  const comparison = dataset.comparison || {};
  const yearOverYear = comparison.year_over_year?.[_officialStatsPeriod];
  const quarterOverQuarter = comparison.quarter_over_quarter?.[_officialStatsPeriod];
  if (!yearOverYear && !quarterOverQuarter) return "";

  const items = [];
  if (yearOverYear) {
    items.push(
      _buildOfficialStatisticsMetricHtml(
        `vs ${comparison.previous_year || "tahun lalu"}`,
        `${yearOverYear.delta_display} (${yearOverYear.delta_percentage_display})`,
      ),
    );
  }
  if (quarterOverQuarter) {
    items.push(
      _buildOfficialStatisticsMetricHtml(
        `vs ${quarterOverQuarter.previous_period_label}`,
        `${quarterOverQuarter.delta_display} (${quarterOverQuarter.delta_percentage_display})`,
      ),
    );
  }

  return `<div class="official-stat-metric-row official-stat-metric-row-tight">${items.join("")}</div>`;
}

function _renderPdrbValueChart(chartId, rows) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;

  const adhbTone = OFFICIAL_STATISTICS_SERIES_TONES.adhb;
  const adhkTone = OFFICIAL_STATISTICS_SERIES_TONES.adhk;

  _createOfficialStatisticsChart(chartId, canvas, {
    type: "bar",
    data: {
      labels: rows.map((row) => _truncateLabel(row.label, 42)),
      datasets: [
        {
          label: "ADHB",
          data: rows.map((row) => row.adhb),
          backgroundColor: `rgba(${adhbTone.red}, ${adhbTone.green}, ${adhbTone.blue}, 0.85)`,
          borderRadius: 4,
          borderSkipped: false,
        },
        {
          label: "ADHK 2010",
          data: rows.map((row) => row.adhk),
          backgroundColor: `rgba(${adhkTone.red}, ${adhkTone.green}, ${adhkTone.blue}, 0.85)`,
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      layout: { padding: { left: 8, right: 8, top: 4, bottom: 4 } },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: {
          callbacks: {
            label(context) {
              return `${context.dataset.label}: ${_formatAxisNumber(context.parsed.x)} miliar`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(148, 163, 184, 0.16)" },
          ticks: {
            callback(value) {
              return _formatAxisNumber(value);
            },
          },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#475569", font: { size: 12, weight: "600" } },
        },
      },
    },
  });
}

function _renderPdrbShareChart(chartId, rows) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;

  // Satu seri besaran: gradasi satu hue, bukan hue per kategori.
  const values = rows.map((row) => row.share);

  _createOfficialStatisticsChart(chartId, canvas, {
    type: "bar",
    data: {
      labels: rows.map((row) => _truncateLabel(row.label, 42)),
      datasets: [
        {
          data: values,
          backgroundColor: _buildValueDrivenColors(values, { red: 13, green: 148, blue: 136 }),
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      layout: { padding: { left: 8, right: 8, top: 4, bottom: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              return `${_formatAxisNumber(context.parsed.x)}% dari total PDRB`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(148, 163, 184, 0.16)" },
          ticks: {
            callback(value) {
              return `${_formatAxisNumber(value)}%`;
            },
          },
        },
        y: {
          grid: { display: false },
          ticks: { color: "#475569", font: { size: 12, weight: "600" } },
        },
      },
    },
  });
}

// ── Kartu ketenagakerjaan dan kemiskinan ───────────────────────────────────

function _renderTptTpakCard(bodyId, dataset) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  if (!dataset || !dataset.available) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(dataset?.message || "Tidak ada data TPT/TPAK untuk tahun terpilih.");
    _destroyOfficialStatisticsChart("officialTptTpakChart");
    return;
  }

  const tpak = dataset.indicators?.tpak || {};
  const tpt = dataset.indicators?.tpt || {};

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-tight">
      ${_buildOfficialStatisticsMetricHtml("TPAK Total", `${tpak.total_display || "—"}%`)}
      ${_buildOfficialStatisticsMetricHtml("TPT Total", `${tpt.total_display || "—"}%`)}
      ${_buildOfficialStatisticsMetricHtml("Gap Gender TPAK", _buildGapDisplay(tpak.male, tpak.female))}
    </div>
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    <div class="official-stat-chart-card tone-teal">
      <div class="official-stat-chart-head">
        <strong>Perbandingan TPAK dan TPT</strong>
        <span>${escapeHtml(dataset.unit || "—")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-medium official-stat-chart-wrap-wide">
        <canvas id="officialTptTpakChart"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Rincian Gender",
      subtitle: "Komposisi indikator ketenagakerjaan per jenis kelamin.",
      tableHead: `
        <tr>
          <th>Indikator</th>
          <th>Laki-laki</th>
          <th>Perempuan</th>
          <th>Jumlah</th>
        </tr>
      `,
      tableBody: `
        <tr>
          <td>${escapeHtml(tpak.label || "TPAK")}</td>
          <td>${escapeHtml(tpak.male_display || "—")}%</td>
          <td>${escapeHtml(tpak.female_display || "—")}%</td>
          <td>${escapeHtml(tpak.total_display || "—")}%</td>
        </tr>
        <tr>
          <td>${escapeHtml(tpt.label || "TPT")}</td>
          <td>${escapeHtml(tpt.male_display || "—")}%</td>
          <td>${escapeHtml(tpt.female_display || "—")}%</td>
          <td>${escapeHtml(tpt.total_display || "—")}%</td>
        </tr>
      `,
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsTptChart(dataset);
}

function _renderKemiskinanCard(bodyId, dataset) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  if (!dataset || !dataset.available) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(dataset?.message || "Tidak ada data kemiskinan untuk tahun terpilih.");
    _destroyOfficialStatisticsChart("officialKemiskinanChart");
    return;
  }

  const focusArea = dataset.focus_area_metrics || {};
  const comparisonRows = dataset.comparison_rows || [];
  const rowsHtml = comparisonRows
    .map(
      (row) => `
        <tr class="${row.is_focus_area ? "is-highlight" : ""}">
          <td>${escapeHtml(row.label || "—")}</td>
          <td>${escapeHtml(row.poverty_rate_display || "—")}%</td>
          <td>${escapeHtml(row.poor_population_display || "—")}</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-tight">
      ${_buildOfficialStatisticsMetricHtml("Garis Kemiskinan", `${focusArea.poverty_line_display || "—"} rupiah`)}
      ${_buildOfficialStatisticsMetricHtml("Penduduk Miskin", `${focusArea.poor_population_display || "—"} ribu jiwa`)}
      ${_buildOfficialStatisticsMetricHtml("Persentase Miskin", `${focusArea.poverty_rate_display || "—"}%`)}
    </div>
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    <div class="official-stat-chart-card tone-rose">
      <div class="official-stat-chart-head">
        <strong>Persentase Penduduk Miskin</strong>
        <span>Perbandingan antarwilayah</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="officialKemiskinanChart"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Perbandingan Wilayah",
      subtitle: "Kabupaten/kota pembanding pada tahun terpilih.",
      tableHead: `
        <tr>
          <th>Wilayah</th>
          <th>% Miskin</th>
          <th>Penduduk Miskin</th>
        </tr>
      `,
      tableBody: rowsHtml,
      wrapClassName: "official-stat-table-wrap compact-scroll",
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsPovertyChart(comparisonRows);
}

function _renderOfficialStatisticsTptChart(dataset) {
  const canvas = document.getElementById("officialTptTpakChart");
  if (!canvas) return;

  const tpak = dataset.indicators?.tpak || {};
  const tpt = dataset.indicators?.tpt || {};

  _createOfficialStatisticsChart("officialTptTpakChart", canvas, {
    type: "bar",
    data: {
      labels: ["Laki-laki", "Perempuan", "Jumlah"],
      datasets: [
        {
          label: "TPAK",
          data: [tpak.male, tpak.female, tpak.total],
          backgroundColor: "rgba(13, 148, 136, 0.85)",
          borderRadius: 4,
        },
        {
          label: "TPT",
          data: [tpt.male, tpt.female, tpt.total],
          backgroundColor: "rgba(190, 24, 93, 0.85)",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, usePointStyle: true },
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(148, 163, 184, 0.16)" },
          ticks: {
            callback(value) {
              return `${_formatAxisNumber(value)}%`;
            },
          },
        },
      },
    },
  });
}

function _renderOfficialStatisticsPovertyChart(rows) {
  const canvas = document.getElementById("officialKemiskinanChart");
  if (!canvas) return;

  const values = rows.map((row) => row.poverty_rate);
  const backgroundColors = _buildValueDrivenColors(values, {
    red: 225,
    green: 29,
    blue: 72,
  });
  const borderColors = rows.map((row, index) =>
    row.is_focus_area
      ? "rgba(136, 19, 55, 0.95)"
      : backgroundColors[index].replace(/,\s*[\d.]+\)$/, ", 1)"),
  );

  _createOfficialStatisticsChart("officialKemiskinanChart", canvas, {
    type: "bar",
    data: {
      labels: rows.map((row) => _truncateLabel(row.label, 22)),
      datasets: [
        {
          data: rows.map((row) => row.poverty_rate),
          backgroundColor: backgroundColors,
          borderColor: borderColors,
          borderWidth: rows.map((row) => (row.is_focus_area ? 2 : 0)),
          borderRadius: 4,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(148, 163, 184, 0.16)" },
          ticks: {
            callback(value) {
              return `${_formatAxisNumber(value)}%`;
            },
          },
        },
      },
    },
  });
}

// ── Registry chart ─────────────────────────────────────────────────────────

function _createOfficialStatisticsChart(chartId, canvas, config) {
  _destroyOfficialStatisticsChart(chartId);

  if (!window.Chart) return null;

  const chart = new Chart(canvas, config);
  _officialStatsCharts[chartId] = chart;
  return chart;
}

function _destroyOfficialStatisticsChart(chartId) {
  const chart = _officialStatsCharts[chartId];
  if (chart) chart.destroy();
  delete _officialStatsCharts[chartId];
}

function _destroyOfficialStatisticsCharts() {
  Object.keys(_officialStatsCharts).forEach(_destroyOfficialStatisticsChart);
}

// ── Builder HTML bersama ───────────────────────────────────────────────────

function _buildOfficialStatisticsMetricHtml(label, value) {
  return `
    <div class="official-stat-metric">
      <span class="official-stat-metric-label">${escapeHtml(label)}</span>
      <strong class="official-stat-metric-value">${escapeHtml(value)}</strong>
    </div>
  `;
}

function _buildOfficialStatisticsCardMetaHtml(dataset) {
  const updatedText = _formatOfficialStatisticsTimestamp(dataset?.updated_at) || "Belum ada timestamp pembaruan.";
  const sourceText = dataset?.source || "Web API BPS";

  return `
    <div class="official-stat-card-meta">
      <span class="official-stat-card-meta-item">
        <strong>Pembaruan</strong>
        <span>${escapeHtml(updatedText)}</span>
      </span>
      <span class="official-stat-card-meta-item official-stat-card-meta-item-source">
        <strong>Sumber</strong>
        <span>${escapeHtml(sourceText)}</span>
      </span>
    </div>
  `;
}

function _buildOfficialStatisticsTablePanelHtml({
  title,
  subtitle,
  tableHead,
  tableBody,
  wrapClassName = "official-stat-table-wrap",
}) {
  return `
    <div class="official-stat-table-panel">
      <div class="official-stat-table-head">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(subtitle)}</span>
      </div>
      <div class="${wrapClassName}">
        <table class="official-stat-table">
          <thead>${tableHead}</thead>
          <tbody>${tableBody}</tbody>
        </table>
      </div>
    </div>
  `;
}

function _buildOfficialStatisticsEmptyHtml(message) {
  return `
    <div class="official-stat-empty">
      <strong>Belum ada data untuk tabel ini.</strong>
      <span>${escapeHtml(message)}</span>
    </div>
  `;
}

function _formatOfficialStatisticsTimestamp(value) {
  if (!value) return "";
  const normalized = String(value).replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);

  return `${date.toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  })}, ${date.toLocaleTimeString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
  })} WIB`;
}

function _formatAxisNumber(value) {
  return Number(value || 0).toLocaleString("id-ID", { maximumFractionDigits: 2 });
}

function _truncateLabel(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

function _buildGapDisplay(a, b) {
  if (typeof a !== "number" || typeof b !== "number") return "—";
  return `${Math.abs(a - b).toLocaleString("id-ID", { maximumFractionDigits: 2 })}%`;
}

function _buildValueDrivenColors(values, tone) {
  const numericValues = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!numericValues.length) {
    return values.map(() => `rgba(${tone.red}, ${tone.green}, ${tone.blue}, 0.55)`);
  }

  const minValue = Math.min(...numericValues);
  const maxValue = Math.max(...numericValues);
  const range = maxValue - minValue;

  return values.map((value) => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return `rgba(${tone.red}, ${tone.green}, ${tone.blue}, 0.45)`;
    }

    const intensity = range === 0 ? 1 : (value - minValue) / range;
    const alpha = 0.35 + intensity * 0.6;
    return `rgba(${tone.red}, ${tone.green}, ${tone.blue}, ${alpha.toFixed(3)})`;
  });
}
