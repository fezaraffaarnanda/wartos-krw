async function bootstrapDashboard() {
  if (typeof initAppShell === "function") {
    initAppShell();
  }

  if (typeof showPageLoadingOverlay === "function") {
    showPageLoadingOverlay({
      title: "Menyiapkan dashboard...",
      subtitle: "Ringkasan dashboard sedang dimuat agar tampilan siap digunakan.",
    });
  }

  startRealtimeClock();

  try {
    // Dua fetch ini independen, jadi jalan paralel.
    await Promise.all([loadUserInfo(), loadNewsSources()]);

    renderSourceChips("welcomeSourceChips");
    renderSourceCount("sourceCountInline");
    renderSourceCount("scrapeSourceCount");
    renderSourceListInline("scrapeSourceList");
    renderProgressRows("progressRows");
    _filterOptions = buildMasterFilterOptions();
    initOfficialStatisticsControls();
    initFloatingChat();

    // Dipanggil setelah kontrol siap: resolusi hash di sini yang men-trigger
    // lazy loader view aktif (mis. deep link ke #data atau #insight).
    initSidebarNavigation();

    // Overlay hanya menunggu data overview. Data tab lain menyusul lewat
    // lazy loader-nya masing-masing di navigation.js.
    await loadOverviewSummary();
  } finally {
    if (typeof hidePageLoadingOverlay === "function") {
      hidePageLoadingOverlay();
    }
  }

  loadLastScrape();
  animateCards();
  startAutoRefresh();
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
