// Tracking aktivitas sisi klien untuk memicu prompt feedback otomatis.
// Sengaja tanpa instrumentasi route di backend -- lihat migrasi
// 20260819_create_user_activity_state.sql. Fail-soft: gagal kirim event TIDAK
// BOLEH mengganggu aksi asli pengguna (buka berita, kirim chat, dst).

function trackEvent(eventType) {
  fetch("/api/activity/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_type: eventType }),
  })
    .then((res) => (res.ok ? res.json() : null))
    .then((json) => {
      if (json && json.should_prompt && typeof window.showFeedbackAutoPrompt === "function") {
        window.showFeedbackAutoPrompt();
      }
    })
    .catch(() => {});
}
