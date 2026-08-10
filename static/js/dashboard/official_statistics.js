const OFFICIAL_STATISTICS_YEARS = ["2025", "2024"];

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
  [
    "officialPdrbAdhkBody",
    "officialPdrbAdhbBody",
    "officialTptTpakBody",
    "officialKemiskinanBody",
    "officialPdrbPengeluaranAdhkBody",
    "officialPdrbPengeluaranAdhbBody",
  ].forEach((id) => {
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
  [
    "officialPdrbAdhkBody",
    "officialPdrbAdhbBody",
    "officialTptTpakBody",
    "officialKemiskinanBody",
    "officialPdrbPengeluaranAdhkBody",
    "officialPdrbPengeluaranAdhbBody",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = `<div class="official-stat-empty"><strong>Gagal memuat data.</strong><span>${escapeHtml(message)}</span></div>`;
  });

  const status = document.getElementById("officialStatsStatusText");
  if (status) status.textContent = "Terjadi kendala saat mengambil statistik resmi BPS.";

  _destroyOfficialStatisticsCharts();
}

function renderOfficialStatistics(payload) {
  const datasets = payload.datasets || {};
  const year = String(payload.year || _officialStatsYear || OFFICIAL_STATISTICS_YEARS[0]);
  _officialStatsYear = year;

  const yearSelect = document.getElementById("officialStatsYearSelect");
  if (yearSelect) yearSelect.value = year;

  const availableCount = Number(payload.available_count || 0);
  const datasetCount = Number(payload.dataset_count || Object.keys(datasets).length || 0);
  const status = document.getElementById("officialStatsStatusText");
  if (status) {
    status.textContent = `${availableCount}/${datasetCount} tabel resmi berhasil dimuat untuk tahun ${year}.`;
  }

  _renderPdrbCard("officialPdrbAdhkBody", datasets.pdrb_adhk, {
    chartId: "officialPdrbAdhkChart",
    toneClass: "tone-orange",
  });
  _renderPdrbCard("officialPdrbAdhbBody", datasets.pdrb_adhb, {
    chartId: "officialPdrbAdhbChart",
    toneClass: "tone-blue",
  });
  _renderTptTpakCard("officialTptTpakBody", datasets.tpt_tpak);
  _renderKemiskinanCard("officialKemiskinanBody", datasets.kemiskinan);
  _renderPdrbPengeluaranCard("officialPdrbPengeluaranAdhkBody", datasets.pdrb_pengeluaran_adhk, {
    chartId: "officialPdrbPengeluaranAdhkChart",
    toneClass: "tone-orange",
  });
  _renderPdrbPengeluaranCard("officialPdrbPengeluaranAdhbBody", datasets.pdrb_pengeluaran_adhb, {
    chartId: "officialPdrbPengeluaranAdhbChart",
    toneClass: "tone-blue",
  });
}

function _renderPdrbCard(bodyId, dataset, { chartId, toneClass }) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  if (!dataset || !dataset.available) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(dataset?.message || "Tidak ada data untuk tabel ini pada tahun terpilih.");
    _destroyOfficialStatisticsChart(chartId);
    return;
  }

  const highlights = [
    _buildOfficialStatisticsMetricHtml("Total PDRB", `${dataset.total_display} miliar`),
    _buildOfficialStatisticsMetricHtml("Sektor Terbesar", dataset.top_rows?.[0]?.label || "—"),
    _buildOfficialStatisticsMetricHtml("Catatan Nilai", dataset.value_note || dataset.latest_change || "—"),
  ].join("");

  const rowsHtml = (dataset.rows || [])
    .map(
      (row, index) => `
        <tr>
          <td>${index + 1}</td>
          <td><strong>${escapeHtml(row.code || "—")}</strong> ${escapeHtml(row.label || "—")}</td>
          <td>${escapeHtml(row.display_value || "—")}</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row">${highlights}</div>
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    <div class="official-stat-chart-card ${toneClass}">
      <div class="official-stat-chart-head">
        <strong>Lapangan Usaha Dominan</strong>
        <span>${escapeHtml(dataset.unit || "—")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="${escapeAttr(chartId)}"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Peringkat Lapangan Usaha",
      subtitle: "Seluruh sektor pada tahun terpilih.",
      tableHead: `
        <tr>
          <th>No</th>
          <th>Lapangan Usaha</th>
          <th>Nilai</th>
        </tr>
      `,
      tableBody: rowsHtml,
      wrapClassName: "official-stat-table-wrap compact-scroll",
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.value_note || dataset.latest_change || dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsBarChart(chartId, dataset.top_rows || [], toneClass);
}

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
        <span>Eks Karesidenan Pekalongan</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="officialKemiskinanChart"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Perbandingan Wilayah",
      subtitle: "Kabupaten/kota di Eks Karesidenan Pekalongan.",
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

function _renderPdrbPengeluaranCard(bodyId, dataset, { chartId, toneClass }) {
  const body = document.getElementById(bodyId);
  if (!body) return;

  if (!dataset || !dataset.available) {
    body.innerHTML = _buildOfficialStatisticsEmptyHtml(dataset?.message || "Tidak ada data PDRB pengeluaran untuk tahun terpilih.");
    _destroyOfficialStatisticsChart(chartId);
    return;
  }

  const comparison = dataset.comparison || {};
  const annualSummary = comparison.annual_summary || {};
  const strongestGrowth = comparison.strongest_growth || {};
  const topComponent = dataset.top_components?.[0] || {};
  const rowsHtml = (dataset.component_rows || [])
    .map(
      (row, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${escapeHtml(row.label || "—")}</td>
          <td>${escapeHtml(row.displays?.q1 || "—")}</td>
          <td>${escapeHtml(row.displays?.q2 || "—")}</td>
          <td>${escapeHtml(row.displays?.q3 || "—")}</td>
          <td>${escapeHtml(row.displays?.q4 || "—")}</td>
          <td>${escapeHtml(row.total_display || "—")}</td>
        </tr>
      `,
    )
    .join("");

  body.innerHTML = `
    <div class="official-stat-metric-row official-stat-metric-row-tight">
      ${_buildOfficialStatisticsMetricHtml("Total Tahunan", `${dataset.annual_total_display || "—"} miliar`)}
      ${_buildOfficialStatisticsMetricHtml("Komponen Terbesar", topComponent.label || "—")}
      ${_buildOfficialStatisticsMetricHtml("Perubahan YoY", annualSummary.delta_percentage_display || "—")}
    </div>
    ${_buildOfficialStatisticsCardMetaHtml(dataset)}
    ${_buildOfficialStatisticsQuarterSummaryHtml(comparison.comparison_quarters || [], comparison.previous_year)}
    <div class="official-stat-chart-card ${toneClass}">
      <div class="official-stat-chart-head">
        <strong>Perbandingan Total per Triwulan</strong>
        <span>${escapeHtml(dataset.unit || "—")}</span>
      </div>
      <div class="official-stat-chart-wrap official-stat-chart-wrap-wide">
        <canvas id="${escapeAttr(chartId)}"></canvas>
      </div>
    </div>
    ${_buildOfficialStatisticsTablePanelHtml({
      title: "Rincian Komponen Pengeluaran",
      subtitle: strongestGrowth.label
        ? `${strongestGrowth.label} mencatat kenaikan terkuat dibanding ${comparison.previous_year || "tahun sebelumnya"}.`
        : "Komponen pengeluaran per triwulan dan total tahunan.",
      tableHead: `
        <tr>
          <th>No</th>
          <th>Komponen</th>
          <th>TW I</th>
          <th>TW II</th>
          <th>TW III</th>
          <th>TW IV</th>
          <th>Jumlah</th>
        </tr>
      `,
      tableBody: rowsHtml,
      wrapClassName: "official-stat-table-wrap compact-scroll",
    })}
    <div class="official-stat-footnote">
      <span>${escapeHtml(dataset.source || "Web API BPS")}</span>
    </div>
  `;

  _renderOfficialStatisticsQuarterlyChart(chartId, dataset);
}

function _renderOfficialStatisticsBarChart(chartId, rows, toneClass) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;

  const values = rows.map((row) => row.value);
  const tone = toneClass === "tone-blue"
    ? { red: 37, green: 99, blue: 235 }
    : { red: 234, green: 88, blue: 12 };
  const backgroundColors = _buildValueDrivenColors(values, tone);

  _createOfficialStatisticsChart(chartId, canvas, {
    type: "bar",
    data: {
      labels: rows.map((row) => _truncateLabel(row.label, 42)),
      datasets: [
        {
          data: values,
          backgroundColor: backgroundColors,
          borderRadius: 10,
          borderSkipped: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      layout: {
        padding: {
          left: 8,
          right: 8,
          top: 4,
          bottom: 4,
        },
      },
      plugins: {
        legend: { display: false },
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
          ticks: {
            color: "#475569",
            font: {
              size: 12,
              weight: "600",
            },
          },
        },
      },
    },
  });
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
          backgroundColor: _buildValueDrivenColors([tpak.male, tpak.female, tpak.total], {
            red: 13,
            green: 148,
            blue: 136,
          }),
          borderRadius: 10,
        },
        {
          label: "TPT",
          data: [tpt.male, tpt.female, tpt.total],
          backgroundColor: _buildValueDrivenColors([tpt.male, tpt.female, tpt.total], {
            red: 244,
            green: 114,
            blue: 182,
          }),
          borderRadius: 10,
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
          borderRadius: 10,
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

function _renderOfficialStatisticsQuarterlyChart(chartId, dataset) {
  const canvas = document.getElementById(chartId);
  if (!canvas) return;

  const quarterRows = (dataset.quarter_series || []).filter((row) => row.quarter_key !== "total");
  const comparisonRows = (dataset.comparison?.comparison_quarters || []).filter((row) => row.quarter_key !== "total");
  const previousValuesByQuarter = Object.fromEntries(
    comparisonRows.map((row) => [row.quarter_key, row.previous_value]),
  );

  const currentValues = quarterRows.map((row) => row.value);
  const previousValues = quarterRows.map((row) => previousValuesByQuarter[row.quarter_key] ?? null);
  const currentTone = chartId === "officialPdrbPengeluaranAdhbChart"
    ? { red: 37, green: 99, blue: 235 }
    : { red: 234, green: 88, blue: 12 };

  _createOfficialStatisticsChart(chartId, canvas, {
    type: "bar",
    data: {
      labels: quarterRows.map((row) => row.label),
      datasets: [
        {
          label: String(dataset.year || "Tahun Terpilih"),
          data: currentValues,
          backgroundColor: _buildValueDrivenColors(currentValues, currentTone),
          borderRadius: 10,
          borderSkipped: false,
        },
        {
          label: String(dataset.comparison?.previous_year || "Tahun Sebelumnya"),
          data: previousValues,
          backgroundColor: "rgba(148, 163, 184, 0.28)",
          borderColor: "rgba(100, 116, 139, 0.45)",
          borderWidth: 1,
          borderRadius: 10,
          borderSkipped: false,
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
              return _formatAxisNumber(value);
            },
          },
        },
      },
    },
  });
}

function _createOfficialStatisticsChart(chartId, canvas, config) {
  _destroyOfficialStatisticsChart(chartId);

  if (!window.Chart) return null;

  const chart = new Chart(canvas, config);
  _assignOfficialStatisticsChart(chartId, chart);
  return chart;
}

function _assignOfficialStatisticsChart(chartId, chart) {
  if (chartId === "officialPdrbAdhkChart") _officialStatsChartPdrbAdhk = chart;
  if (chartId === "officialPdrbAdhbChart") _officialStatsChartPdrbAdhb = chart;
  if (chartId === "officialTptTpakChart") _officialStatsChartTptTpak = chart;
  if (chartId === "officialKemiskinanChart") _officialStatsChartKemiskinan = chart;
  if (chartId === "officialPdrbPengeluaranAdhkChart") _officialStatsChartPdrbPengeluaranAdhk = chart;
  if (chartId === "officialPdrbPengeluaranAdhbChart") _officialStatsChartPdrbPengeluaranAdhb = chart;
}

function _destroyOfficialStatisticsChart(chartId) {
  const chart =
    chartId === "officialPdrbAdhkChart" ? _officialStatsChartPdrbAdhk
    : chartId === "officialPdrbAdhbChart" ? _officialStatsChartPdrbAdhb
    : chartId === "officialTptTpakChart" ? _officialStatsChartTptTpak
    : chartId === "officialKemiskinanChart" ? _officialStatsChartKemiskinan
    : chartId === "officialPdrbPengeluaranAdhkChart" ? _officialStatsChartPdrbPengeluaranAdhk
    : _officialStatsChartPdrbPengeluaranAdhb;

  if (chart) chart.destroy();

  if (chartId === "officialPdrbAdhkChart") _officialStatsChartPdrbAdhk = null;
  if (chartId === "officialPdrbAdhbChart") _officialStatsChartPdrbAdhb = null;
  if (chartId === "officialTptTpakChart") _officialStatsChartTptTpak = null;
  if (chartId === "officialKemiskinanChart") _officialStatsChartKemiskinan = null;
  if (chartId === "officialPdrbPengeluaranAdhkChart") _officialStatsChartPdrbPengeluaranAdhk = null;
  if (chartId === "officialPdrbPengeluaranAdhbChart") _officialStatsChartPdrbPengeluaranAdhb = null;
}

function _destroyOfficialStatisticsCharts() {
  [
    "officialPdrbAdhkChart",
    "officialPdrbAdhbChart",
    "officialTptTpakChart",
    "officialKemiskinanChart",
    "officialPdrbPengeluaranAdhkChart",
    "officialPdrbPengeluaranAdhbChart",
  ].forEach(_destroyOfficialStatisticsChart);
}

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

function _buildOfficialStatisticsQuarterSummaryHtml(rows, previousYear) {
  const quarterRows = rows.filter((row) => row.quarter_key !== "total");
  if (!quarterRows.length) return "";

  const itemsHtml = quarterRows
    .map(
      (row) => `
        <div class="official-stat-quarter-item">
          <span class="official-stat-quarter-label">${escapeHtml(row.label || "—")}</span>
          <strong class="official-stat-quarter-value">${escapeHtml(row.current_display || "—")}</strong>
          <span class="official-stat-quarter-delta">vs ${escapeHtml(String(previousYear || "tahun lalu"))}: ${escapeHtml(row.delta_percentage_display || "—")}</span>
        </div>
      `,
    )
    .join("");

  return `<div class="official-stat-quarter-grid">${itemsHtml}</div>`;
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
