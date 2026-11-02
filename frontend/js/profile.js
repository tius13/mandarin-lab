import {
  $,
  api,
  toast,
  state,
  normalizeUser,
  updateUserUI,
  cleanupAudio,
  navigate,
} from "./utils.js";
import { USER_STORAGE_KEY, FLASH_MESSAGE_KEY } from "./config.js";

export async function loadProfile() {
  if (!state.user?.id_pengguna) return;

  try {
    const user = normalizeUser(
      await api(`/api/pengguna/${encodeURIComponent(state.user.id_pengguna)}`),
    );

    state.user = user;

    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));

    updateUserUI();
  } catch (error) {
    toast(error.message, true);
  }
}

export async function initProfilePage() {
  const updateEmailForm = $("#updateEmailForm");
  if (updateEmailForm) {
    updateEmailForm.addEventListener("submit", async (event) => {
      event.preventDefault();

      const formElement = event.currentTarget;

      if (!state.user?.id_pengguna) {
        toast("Silakan masuk kembali untuk mengubah email.", true);
        navigate("auth");
        return;
      }

      const form = new FormData(formElement);
      const email = String(form.get("email") || "")
        .trim()
        .toLowerCase();

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        toast("Format email tidak valid.", true);
        return;
      }

      const button = formElement.querySelector('button[type="submit"]');
      if (button) button.disabled = true;

      try {
        const response = await api(
          `/api/pengguna/${encodeURIComponent(state.user.id_pengguna)}/email`,
          {
            method: "PUT",
            body: JSON.stringify({ email }),
          },
        );

        const updatedUser = normalizeUser(response.pengguna);
        state.user = updatedUser;
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(updatedUser));
        updateUserUI();
        toast(response.message || "Email berhasil diperbarui.");
      } catch (error) {
        toast(error.message || "Email gagal diperbarui.", true);
      } finally {
        if (button) button.disabled = false;
      }
    });
  }
  $("#changePasswordForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const formElement = event.currentTarget;

    if (!state.user?.id_pengguna) {
      return toast("Silakan masuk kembali untuk mengubah password.", true);
    }

    const form = new FormData(formElement);

    const currentPassword = String(form.get("current_password") || "");

    const newPassword = String(form.get("new_password") || "");

    const confirmPassword = String(form.get("confirm_password") || "");

    if (newPassword.length < 8) {
      return toast("Password baru minimal 8 karakter.", true);
    }

    if (newPassword !== confirmPassword) {
      return toast("Konfirmasi password baru tidak sama.", true);
    }

    if (currentPassword === newPassword) {
      return toast("Password baru harus berbeda dari password saat ini.", true);
    }

    const button = formElement.querySelector('button[type="submit"]');

    button.disabled = true;

    try {
      const response = await api(
        `/api/pengguna/${encodeURIComponent(state.user.id_pengguna)}/ubah-password`,
        {
          method: "POST",
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
          }),
        },
      );

      formElement.reset();

      toast(response.message || "Password berhasil diperbarui.");
    } catch (error) {
      toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  const logoutButton = $("#logoutBtn");
  if (logoutButton) {
    logoutButton.addEventListener("click", () => {
      void logoutLocal();
    });
  }
  async function logoutLocal() {
    // Invalidasi proses asinkron sesi sebelumnya sebelum membersihkan audio.
    state.sessionId += 1;
    state.recording = false;
    state.busy = false;
    state.requestingRecording = false;
    try {
      await cleanupAudio();
    } catch (error) {
      console.warn("Pembersihan audio saat logout gagal:", error);
    }

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    if (state.recordingUrl) {
      URL.revokeObjectURL(state.recordingUrl);
      state.recordingUrl = null;
    }

    state.user = null;
    localStorage.removeItem(USER_STORAGE_KEY);

    const headerAccount = $("#headerAccount");
    if (headerAccount) headerAccount.classList.add("hidden");

    const loginForm = $("#loginForm");
    if (loginForm) loginForm.reset();

    const passwordForm = $("#changePasswordForm");
    if (passwordForm) passwordForm.reset();

    sessionStorage.setItem(FLASH_MESSAGE_KEY, "Kamu telah keluar dari akun.");
    navigate("auth");
  }

  $("#profileForgotPassword")?.addEventListener("click", () => {
    const email = state.user?.email || "";
    window.location.href = `/static/index.html?mode=forgot&email=${encodeURIComponent(email)}`;
  });

  await loadProfile();
}
