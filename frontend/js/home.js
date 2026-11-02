import { $, api, state } from "./utils.js";

export async function loadStats() {
  if (!state.user?.id_pengguna) return;

  try {
    const rows = await api(
      `/api/riwayat-latihan/pengguna/${encodeURIComponent(state.user.id_pengguna)}?limit=200&offset=0`,
    );

    $("#statSessions").textContent = rows.length;

    $("#statCorrect").textContent = rows.reduce(
      (total, row) => total + Number(row.jumlah_tepat || 0),
      0,
    );

    $("#statBest").textContent = rows.length
      ? Math.max(
          ...rows
            .map((row) => Number(row.skor_akhir || 0))
            .filter(Number.isFinite),
        ).toFixed(0)
      : "—";
  } catch (error) {
    console.warn("Tidak dapat memuat statistik:", error.message);
  }
}

export async function initHomePage() {
  await loadStats();
}
