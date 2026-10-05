const B = window.API_BASE || "";

async function j(url, opts) {
  const r = await fetch(B + url, opts);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Something went wrong. Try again.");
  return d;
}
const post = (url, body) =>
  j(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  dashboard: () => j("/dashboard"),
  clients: () => j("/clients"),
  forecast: () => j("/forecast"),
  demo: () => j("/demo", { method: "POST" }),
  upload: (files) => {
    const f = new FormData();
    files.forEach((x) => f.append("files", x));
    return j("/upload", { method: "POST", body: f });
  },
  manual: (rows) => post("/manual-entry", { rows }),
  ask: (question) => post("/ask", { question }),
  auth: (mode, body) => post(`/auth/${mode}`, body),
  csvUrl: B + "/download-clients",
};

export const usd = (n, compact) =>
  new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: compact ? 1 : 0,
    notation: compact ? "compact" : "standard",
  }).format(n);
