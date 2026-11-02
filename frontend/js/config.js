// Konfigurasi terpusat; endpoint sesuai kode awal.
export const API_BASE = "https://duller-deskwork-emblaze.ngrok-free.dev";
export const USER_STORAGE_KEY = "capt_api_user";
export const DISPLAY_NAME_PREFIX = "capt_local_display_name_";
export const FLASH_MESSAGE_KEY = "capt_flash_message";
export const API_TIMEOUT_MS = 30000;
export const EVALUATION_TIMEOUT_MS = 120000;
export const PAGE_URLS = Object.freeze({
  auth: "/static/index.html",
  home: "/static/home.html",
  practice: "/static/practice.html",
  history: "/static/history.html",
  profile: "/static/profile.html",
});
