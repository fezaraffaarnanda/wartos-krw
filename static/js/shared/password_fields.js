
function checkStrength(pw) {
  const fill = document.getElementById("strengthFill");
  const text = document.getElementById("strengthText");
  if (!fill || !text) return;
  if (!pw) {
    fill.style.width = "0%";
    text.textContent = "";
    return;
  }

  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;

  const levels = [
    { pct: "20%", color: "#e74c3c", label: "Sangat Lemah" },
    { pct: "40%", color: "#e67e22", label: "Lemah" },
    { pct: "60%", color: "#f1c40f", label: "Cukup" },
    { pct: "80%", color: "#2ecc71", label: "Kuat" },
    { pct: "100%", color: "#27ae60", label: "Sangat Kuat" },
  ];
  const lvl = levels[Math.min(score - 1, 4)] || levels[0];
  fill.style.width = lvl.pct;
  fill.style.backgroundColor = lvl.color;
  text.textContent = lvl.label;
  text.style.color = lvl.color;
}

function togglePw(inputId, iconId) {
  const input = document.getElementById(inputId);
  const icon = document.getElementById(iconId);
  if (!input || !icon) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  icon.innerHTML = show
    ? `<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/>`
    : `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>`;
}
