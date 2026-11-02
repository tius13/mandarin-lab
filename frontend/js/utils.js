import { API_BASE, USER_STORAGE_KEY, DISPLAY_NAME_PREFIX, PAGE_URLS, API_TIMEOUT_MS } from "./config.js";
import { state } from "./state.js";
export { state };

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => [...document.querySelectorAll(selector)];

export function normalizeNFC(value) {
  return String(value ?? "").normalize("NFC");
}

export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
}

export function displayName(user) {
  if (!user) return "Pengguna";

  return (
    String(user.nama_pengguna || "").trim() ||
    localStorage.getItem(`${DISPLAY_NAME_PREFIX}${user.id_pengguna}`) ||
    String(user.email || "Pengguna").split("@")[0] ||
    "Pengguna"
  );
}

export function normalizeUser(user) {
  const value = user?.pengguna || user;

  if (!value || value.id_pengguna == null || !value.email) {
    throw new Error("Format respons pengguna dari backend tidak sesuai.");
  }

  return {
    id_pengguna: Number(value.id_pengguna),
    nama_pengguna: String(value.nama_pengguna || "").trim(),
    email: String(value.email),
    waktu_dibuat: value.waktu_dibuat || null,
  };
}

export async function api(path, options = {}) {
  // timeoutMs hanya digunakan oleh helper frontend dan tidak dikirim ke fetch.
  const { timeoutMs = API_TIMEOUT_MS, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});

  if (
    fetchOptions.body &&
    !(fetchOptions.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  let response;

  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(
        `Permintaan ${path} melewati batas waktu ${Math.ceil(timeoutMs / 1000)} detik. Silakan coba lagi.`,
      );
    }

    throw new Error(
      "Frontend tidak dapat menghubungi API. Periksa koneksi backend/API.",
    );
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let message = `Request gagal (${response.status})`;

    try {
      const body = await response.json();

      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item.msg || "Input tidak valid")
          .join("; ");
      } else if (body.message) {
        message = body.message;
      }
    } catch {
      // Respons mungkin bukan JSON.
    }

    const error = new Error(message);
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) return null;

  const type = response.headers.get("content-type") || "";
  return type.includes("application/json") ? response.json() : response;
}

export function toast(message, isError = false) {
  const el = $("#toast");

  if (!el) {
    console[isError ? "error" : "log"](message);
    return;
  }

  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");

  clearTimeout(toast.timer);

  toast.timer = setTimeout(() => {
    el.classList.add("hidden");
  }, 5500);
}

export function setConnectionBadge(online, label) {
  const el = $("#connectionBadge");

  if (!el) return;

  el.classList.toggle("online", online);
  el.classList.toggle("offline", !online);
  el.innerHTML = `<span class="status-dot"></span>${escapeHtml(label)}`;
}

export async function checkBackend() {
  try {
    const health = await api("/health");

    setConnectionBadge(
      true,
      health.database === "connected"
        ? "API & database terhubung"
        : "API terhubung",
    );
  } catch {
    setConnectionBadge(false, "API belum terhubung");
  }
}

// Guard DOM fields because each page has its own HTML document.
export function updateUserUI() {
  if (!state.user) return;
  const name = displayName(state.user);
  const welcome = $("#welcomeTitle");
  if (welcome) welcome.textContent = `Selamat Datang dan Selamat Belajar ${name}`;
  const profileName = $("#profileName");
  if (profileName) profileName.textContent = name;
  const profileEmail = $("#profileEmail");
  if (profileEmail) profileEmail.textContent = state.user.email;
  const profileIdInput = $("#profileIdInput");
  if (profileIdInput) profileIdInput.value = state.user.id_pengguna;
  const profileEmailInput = $("#profileEmailInput");
  if (profileEmailInput) profileEmailInput.value = state.user.email;
  const createdInput = $("#profileCreatedInput");
  if (createdInput) {
    const created = state.user.waktu_dibuat ? new Date(state.user.waktu_dibuat) : null;
    createdInput.value = created && !Number.isNaN(created.getTime())
      ? created.toLocaleString("id-ID") : "—";
  }
  $("#headerAccount")?.classList.remove("hidden");
}

export function navigate(page) {
  window.location.href = PAGE_URLS[page] || PAGE_URLS.home;
}

export function setRecordState(message, recording = false) {
  const el = $("#recordState");

  if (!el) return;

  el.classList.toggle("recording", recording);
  el.textContent = message;
}

export async function cleanupAudio() {
  try {
    state.processor?.disconnect();
  } catch {
    // Abaikan apabila processor sudah terputus.
  }

  try {
    state.source?.disconnect();
  } catch {
    // Abaikan apabila source sudah terputus.
  }

  try {
    state.mediaStream?.getTracks().forEach((track) => {
      track.stop();
    });
  } catch {
    // Abaikan apabila stream sudah berhenti.
  }

  try {
    if (state.audioContext && state.audioContext.state !== "closed") {
      await state.audioContext.close();
    }
  } catch {
    // Abaikan apabila AudioContext sudah ditutup.
  }

  state.processor = null;
  state.source = null;
  state.mediaStream = null;
  state.audioContext = null;
}

export function bindSharedNavigation() {
  $("#brandHome")?.addEventListener("click", (event) => {
    event.preventDefault();
    navigate(state.user ? "home" : "auth");
  });

  $("#headerAccount")?.addEventListener("click", () => navigate("profile"));

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-goto]");
    if (!button) return;
    event.preventDefault();
    navigate(button.dataset.goto);
  });
}
