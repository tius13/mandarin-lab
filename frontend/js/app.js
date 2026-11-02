import { USER_STORAGE_KEY, FLASH_MESSAGE_KEY, API_TIMEOUT_MS } from "./config.js";
import { $, state, api, toast, normalizeUser, updateUserUI, navigate, bindSharedNavigation, checkBackend } from "./utils.js";
import { initAuthPage } from "./auth.js";
import { initHomePage } from "./home.js";
import { initPracticePage } from "./practice.js";
import { initHistoryPage } from "./history.js";
import { initProfilePage } from "./profile.js";

async function restoreUser() {
  let saved;
  try {
    saved = JSON.parse(localStorage.getItem(USER_STORAGE_KEY) || "null");
  } catch {
    localStorage.removeItem(USER_STORAGE_KEY);
    return false;
  }

  if (!saved?.id_pengguna || !saved?.email) return false;

  try {
    const remote = normalizeUser(
      await api(`/api/pengguna/${encodeURIComponent(saved.id_pengguna)}`, {
        timeoutMs: API_TIMEOUT_MS,
      }),
    );
    state.user = remote;
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(remote));
    updateUserUI();
    return true;
  } catch (error) {
    if (error.status === 404) {
      localStorage.removeItem(USER_STORAGE_KEY);
    }
    state.user = null;
    return false;
  }
}

function showFlashMessage() {
  const message = sessionStorage.getItem(FLASH_MESSAGE_KEY);
  if (!message) return;
  sessionStorage.removeItem(FLASH_MESSAGE_KEY);
  toast(message);
}

async function initApp() {
  const page = document.body.dataset.page || "auth";
  state.page = page;
  bindSharedNavigation();
  void checkBackend();

  const loggedIn = await restoreUser();

  if (page === "auth") {
    if (loggedIn) {
      navigate("home");
      return;
    }
    initAuthPage();
    showFlashMessage();
    return;
  }

  if (!loggedIn) {
    navigate("auth");
    return;
  }

  switch (page) {
    case "home":
      await initHomePage();
      break;
    case "practice":
      await initPracticePage();
      break;
    case "history":
      await initHistoryPage();
      break;
    case "profile":
      await initProfilePage();
      break;
    default:
      navigate("home");
      return;
  }

  showFlashMessage();
}

void initApp();
