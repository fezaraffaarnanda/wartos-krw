// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  if (typeof initAppShell === "function") {
    initAppShell();
  }
  startRealtimeClock();
  await loadUserInfo();
  initSidebarNavigation();
  initFloatingChat();
  _filterOptions = buildMasterFilterOptions();
  await loadOverviewSummary();
  await loadBerita();
  loadLastScrape();
  loadAIInsights();
  animateCards();
  startAutoRefresh();

  // ── Tooltip KBLI: delegasi event ke dokumen ───────────────────────────────
  document.addEventListener("mouseover", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _showKbliTooltip(btn);
  });
  document.addEventListener("mouseout", (e) => {
    const btn = e.target.closest(".kbli-info-btn");
    if (btn) _hideKbliTooltip();
  });
});
