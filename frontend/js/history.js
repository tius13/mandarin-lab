import { $, api, toast, state, escapeHtml } from "./utils.js";

export async function loadHistory() {
  if (!state.user?.id_pengguna) return;

  const body = $("#historyRows");

  body.innerHTML =
    '<tr><td colspan="4" class="empty">Memuat riwayat…</td></tr>';

  try {
    const rows = await api(
      `/api/riwayat-latihan/pengguna/${encodeURIComponent(state.user.id_pengguna)}?limit=100&offset=0`,
    );

    if (!Array.isArray(rows) || !rows.length) {
      body.innerHTML =
        '<tr><td colspan="4" class="empty">Belum ada riwayat latihan.</td></tr>';

      return;
    }

    body.innerHTML = rows
      .map((row) => {
        const date = row.waktu_latihan
          ? new Date(String(row.waktu_latihan).replace(" ", "T"))
          : null;

        const dateText =
          date && !Number.isNaN(date.getTime())
            ? date.toLocaleString("id-ID")
            : "—";

        const score = Number(row.skor_akhir);
        const incorrect = Number(row.jumlah_kurang_tepat ?? 0);
        const correct = Number(row.jumlah_tepat ?? 0);

        return `
          <tr>
            <td>${escapeHtml(dateText)}</td>
            <td>
              <span class="score-badge">
                ${Number.isFinite(score) ? `${score.toFixed(0)}/100` : "—"}
              </span>
            </td>
            <td>${Number.isFinite(incorrect) ? incorrect : 0}</td>
            <td>${Number.isFinite(correct) ? correct : 0}</td>
          </tr>
        `;
      })
      .join("");
  } catch (error) {
    body.innerHTML = `
      <tr>
        <td colspan="4" class="empty">
          ${escapeHtml(error.message)}
        </td>
      </tr>
    `;

    toast(error.message, true);
  }
}

export async function initHistoryPage() {
  $("#refreshHistory")?.addEventListener("click", loadHistory);
  await loadHistory();
}
