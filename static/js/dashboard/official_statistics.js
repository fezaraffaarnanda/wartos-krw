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
  const latestYear = dataset.latest_year || dataset.year;
  const series = dataset.series || [];

  const rowsHtml = series
    .slice()
    .reverse()
    .map(
      (point) => `
        <tr class="${point.year === latestYear ? "is-highlight" : ""}">
          <td>${escapeHtml(point.year_label || "—")}</td>
          <td>${escapeHtml(point.tpak_display || "—")}%</td>
          <td>${escapeHtml(point.tpt_display || "—")}%</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-tight">
      ${_buildOfficialStatisticsMetricHtml(`TPAK ${latestYear}`, `${tpak.total_display || "—"}%`)}
      ${_buildOfficialStatisticsMetricHtml(`TPT ${latestYear}`, `${tpt.total_display || "—"}%`)}
      ${_buildLaborChangeMetricHtml("TPT", tpt)}
    </div>
    ${_buildLaborCoverageNoteHtml(dataset)}
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    <div class="official-stat-chart-card tone-teal">
      <div class="official-stat-chart-head">
        <strong>Tren TPAK dan TPT</strong>
        <span>${escapeHtml(dataset.unit || "—")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-medium official-stat-chart-wrap-wide">
        <canvas id="officialTptTpakChart"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Seri Tahunan",
      subtitle: "TPAK dan TPT Kabupaten Karawang per tahun, terbaru di atas.",
      tableHead: `
        <tr>
          <th>Tahun</th>
          <th>TPAK</th>
          <th>TPT</th>
        </tr>
      `,
      tableBody: rowsHtml,
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsTptChart(dataset);
}

function _buildLaborChangeMetricHtml(shortLabel, indicator) {
  const change = indicator?.change || {};
  if (!change.delta_display) {
    return _buildOfficialStatisticsMetricHtml(`Perubahan ${shortLabel}`, "—");
  }
  return _buildOfficialStatisticsMetricHtml(
    `${shortLabel} vs ${change.previous_year}`,
    `${change.delta_display} (${change.delta_percentage_display})`,
  );
}

function _buildLaborCoverageNoteHtml(dataset) {
  if (!dataset.is_latest_fallback) return "";
  return `
    <p class="official-stat-note">
      BPS belum merilis angka ${escapeHtml(String(dataset.year))}. Angka yang ditampilkan adalah rilis terakhir, tahun ${escapeHtml(String(dataset.latest_year))}.
    </p>
  `;
}

function _renderKemiskinanCard(bodyId, dataset) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  if (!dataset || !dataset.available) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(dataset?.message || "Tidak ada data kemiskinan untuk tahun terpilih.");
    _destroyOfficialStatisticsChart("officialKemiskinanChart");
    _destroyOfficialStatisticsChart("officialKemiskinanDepthChart");
    return;
  }

  const metrics = dataset.metrics || {};
  const povertyRate = metrics.poverty_rate || {};
  const poorPopulation = metrics.poor_population || {};
  const povertyLine = metrics.poverty_line || {};
  const latestYear = dataset.latest_year || dataset.year;
  const series = dataset.series || [];

  const rowsHtml = series
    .slice()
    .reverse()
    .map(
      (point) => `
        <tr class="${point.year === latestYear ? "is-highlight" : ""}">
          <td>${escapeHtml(point.year_label || "—")}</td>
          <td>${escapeHtml(point.poverty_rate_display || "—")}</td>
          <td>${escapeHtml(point.poor_population_display || "—")}</td>
          <td>${escapeHtml(point.depth_index_display || "—")}</td>
          <td>${escapeHtml(point.severity_index_display || "—")}</td>
          <td>${escapeHtml(point.poverty_line_display || "—")}</td>
          <td>${escapeHtml(point.gini_ratio_display || "—")}</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-quad">
      ${_buildOfficialStatisticsMetricHtml(`P0 ${latestYear}`, `${povertyRate.value_display || "—"}%`)}
      ${_buildOfficialStatisticsMetricHtml("Penduduk Miskin", `${poorPopulation.value_display || "—"} ribu`)}
      ${_buildOfficialStatisticsMetricHtml("Garis Kemiskinan", `Rp ${povertyLine.value_display || "—"}`)}
      ${_buildKemiskinanChangeMetricHtml(povertyRate)}
    </div>
    ${_buildKemiskinanCoverageNoteHtml(dataset)}
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    <div class="official-stat-chart-card tone-rose">
      <div class="official-stat-chart-head">
        <strong>Tren Persentase Penduduk Miskin</strong>
        <span>Persen</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-medium official-stat-chart-wrap-wide">
        <canvas id="officialKemiskinanChart"></canvas>
      </div>
    </div>
    <div class="official-stat-chart-card tone-amber">
      <div class="official-stat-chart-head">
        <strong>Kedalaman dan Keparahan</strong>
        <span>Indeks</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-medium official-stat-chart-wrap-wide">
        <canvas id="officialKemiskinanDepthChart"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Seri Tahunan",
      subtitle: "Indikator kemiskinan Kabupaten Karawang per tahun, terbaru di atas.",
      tableHead: `
        <tr>
          <th>Tahun</th>
          <th>P0 (%)</th>
          <th>Ribu Jiwa</th>
          <th>P1</th>
          <th>P2</th>
          <th>GK (Rp)</th>
          <th>Gini</th>
        </tr>
      `,
      tableBody: rowsHtml,
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Olahan BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsPovertyChart(dataset);
  _renderOfficialStatisticsPovertyDepthChart(dataset);
}

function _buildKemiskinanChangeMetricHtml(metric) {
  const change = metric?.change || {};
  if (!change.delta_display) {
    return _buildOfficialStatisticsMetricHtml("Perubahan P0", "—");
  }
  return _buildOfficialStatisticsMetricHtml(
    `P0 vs ${change.previous_year}`,
    `${change.delta_display} (${change.delta_percentage_display})`,
  );
}

function _buildKemiskinanCoverageNoteHtml(dataset) {
  if (!dataset.is_latest_fallback) return "";
  return `
    <p class="official-stat-note">
      Angka ${escapeHtml(String(dataset.year))} belum tersedia. Yang ditampilkan adalah rilis terakhir, tahun ${escapeHtml(String(dataset.latest_year))}.
    </p>
  `;
}

// Sumbu tahun dirapatkan supaya tahun yang tidak terisi tampil sebagai putus
// garis, bukan tersamar jadi tren mulus.
function _buildOfficialStatisticsYearAxis(points) {
  const years = points.map((point) => point.year);
  const axisYears = [];
  if (!years.length) return axisYears;
  for (let year = Math.min(...years); year <= Math.max(...years); year += 1) {
    axisYears.push(year);
  }
  return axisYears;
}

function _pickSeriesValue(points, year, field) {
  const point = points.find((item) => item.year === year);
  const value = point ? point[field] : null;
  return typeof value === "number" ? value : null;
}

function _renderOfficialStatisticsPovertyChart(dataset) {
  const canvas = document.getElementById("officialKemiskinanChart");
  if (!canvas) return;

  const points = dataset.series || [];
  const axisYears = _buildOfficialStatisticsYearAxis(points);

  _createOfficialStatisticsChart("officialKemiskinanChart", canvas, {
    type: "line",
    data: {
      labels: axisYears.map(String),
      datasets: [
        {
          label: "Persentase penduduk miskin",
          data: axisYears.map((year) => _pickSeriesValue(points, year, "poverty_rate")),
          borderColor: "rgba(190, 24, 93, 1)",
          backgroundColor: "rgba(190, 24, 93, 0.12)",
          pointStyle: "circle",
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          tension: 0.25,
          spanGaps: false,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              if (value === null || value === undefined) return "Tidak tersedia";
              return `${_formatAxisNumber(value)}% penduduk miskin`;
            },
            // Jumlah absolut ditaruh di tooltip, bukan sumbu kedua: skala persen
            // dan ribu jiwa berbeda jauh dan dual-axis gampang menyesatkan.
            afterLabel(context) {
              const year = Number(context.label);
              const count = _pickSeriesValue(dataset.series || [], year, "poor_population");
              if (count === null) return "";
              return `${_formatAxisNumber(count)} ribu jiwa`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: false,
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

function _renderOfficialStatisticsPovertyDepthChart(dataset) {
  const canvas = document.getElementById("officialKemiskinanDepthChart");
  if (!canvas) return;

  const points = dataset.series || [];
  const axisYears = _buildOfficialStatisticsYearAxis(points);

  _createOfficialStatisticsChart("officialKemiskinanDepthChart", canvas, {
    type: "line",
    data: {
      labels: axisYears.map(String),
      datasets: [
        {
          label: "P1 (kedalaman)",
          data: axisYears.map((year) => _pickSeriesValue(points, year, "depth_index")),
          borderColor: "rgba(217, 119, 6, 1)",
          backgroundColor: "rgba(217, 119, 6, 0.12)",
          pointStyle: "circle",
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          tension: 0.25,
          spanGaps: false,
          fill: false,
        },
        {
          label: "P2 (keparahan)",
          data: axisYears.map((year) => _pickSeriesValue(points, year, "severity_index")),
          borderColor: "rgba(30, 64, 175, 1)",
          backgroundColor: "rgba(30, 64, 175, 0.12)",
          pointStyle: "triangle",
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2,
          borderDash: [6, 3],
          tension: 0.25,
          spanGaps: false,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              if (value === null || value === undefined) return `${context.dataset.label}: tidak tersedia`;
              return `${context.dataset.label}: ${_formatAxisNumber(value)}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(148, 163, 184, 0.16)" },
        },
      },
    },
  });
}

function _renderOfficialStatisticsTptChart(dataset) {
  const canvas = document.getElementById("officialTptTpakChart");
  if (!canvas) return;

  // Sumbu tahun dibuat rapat supaya tahun yang tidak dirilis BPS (mis. 2016)
  // tampil sebagai putus garis, bukan tersamar jadi tren mulus.
  const points = dataset.series || [];
  const years = points.map((point) => point.year);
  const axisYears = [];
  for (let year = Math.min(...years); year <= Math.max(...years); year += 1) {
    axisYears.push(year);
  }
  const valueAt = (year, field) => {
    const point = points.find((item) => item.year === year);
    const value = point ? point[field] : null;
    return typeof value === "number" ? value : null;
  };

  _createOfficialStatisticsChart("officialTptTpakChart", canvas, {
    type: "line",
    data: {
      labels: axisYears.map(String),
      datasets: [
        {
          label: "TPAK",
          data: axisYears.map((year) => valueAt(year, "tpak")),
          borderColor: "rgba(13, 148, 136, 1)",
          backgroundColor: "rgba(13, 148, 136, 0.12)",
          pointStyle: "circle",
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
          tension: 0.25,
          spanGaps: false,
          fill: false,
        },
        {
          label: "TPT",
          data: axisYears.map((year) => valueAt(year, "tpt")),
          borderColor: "rgba(190, 24, 93, 1)",
          backgroundColor: "rgba(190, 24, 93, 0.12)",
          pointStyle: "triangle",
          pointRadius: 4,
          pointHoverRadius: 6,
          borderWidth: 2,
          borderDash: [6, 3],
          tension: 0.25,
          spanGaps: false,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "bottom",
          labels: { boxWidth: 12, usePointStyle: true },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const value = context.parsed.y;
              if (value === null || value === undefined) return `${context.dataset.label}: tidak dirilis`;
              return `${context.dataset.label}: ${_formatAxisNumber(value)}%`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false } },
        y: {
          beginAtZero: false,
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
