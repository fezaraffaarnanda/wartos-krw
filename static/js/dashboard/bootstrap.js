async function bootstrapDashboard() {
  if (typeof initAppShell === "function") {
    initAppShell();
  }

  if (typeof showPageLoadingOverlay === "function") {
    showPageLoadingOverlay({
      title: "Menyiapkan dashboard...",
      subtitle: "Ringkasan dan data berita sedang dimuat agar tampilan siap digunakan.",
    });
  }

  startRealtimeClock();

  try {
    await loadUserInfo();
    await loadNewsSources();
    renderSourceChips("welcomeSourceChips");
    renderSourceCount("sourceCountInline");
    renderSourceCount("scrapeSourceCount");
    renderSourceListInline("scrapeSourceList");
    renderProgressRows("progressRows");
    initSidebarNavigation();
    initOfficialStatisticsControls();
    initFloatingChat();
    _filterOptions = buildMasterFilterOptions();
    await loadOverviewSummary();
    await loadBerita();
    loadLastScrape();
    loadAIInsights();
    animateCards();
    startAutoRefresh();
  } finally {
    if (typeof hidePageLoadingOverlay === "function") {
      hidePageLoadingOverlay();
    }
  }
}

function registerDashboardTooltipDelegation() {
  document.addEventListener("mouseover", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _showKbliTooltip(btn);
  });
  document.addEventListener("mouseout", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _hideKbliTooltip();
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  registerDashboardTooltipDelegation();
  await bootstrapDashboard();
});
