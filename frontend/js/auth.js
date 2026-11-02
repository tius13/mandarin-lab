import {
  $, $$, api, toast, state, normalizeUser, updateUserUI, navigate,
} from "./utils.js";
import { USER_STORAGE_KEY, FLASH_MESSAGE_KEY } from "./config.js";

export function showAuth(mode = "login") {
  state.page = "auth";

  $("#authView").classList.remove("hidden");

  $$(".page").forEach((page) => {
    page.classList.add("hidden");
  });

  const modes = {
    login: {
      title: "Selamat Datang",
      subtitle: "Masuk untuk melanjutkan perjalanan belajar Mandarin-mu.",
    },
    register: {
      title: "Daftar Akun Baru",
      subtitle: "Buat akun untuk mulai belajar Mandarin.",
    },
    forgot: {
      title: "Ubah Password",
      subtitle:
        "Cocokkan email akun dan masukkan password baru. Tidak ada email yang dikirim.",
    },
  };

  const selected = modes[mode] || modes.login;

  $("#authTitle").textContent = selected.title;
  $("#authSubtitle").textContent = selected.subtitle;

  $("#loginForm").classList.toggle("hidden", mode !== "login");
  $("#registerForm").classList.toggle("hidden", mode !== "register");
  $("#forgotPasswordForm").classList.toggle("hidden", mode !== "forgot");

  document.body.classList.add("auth-mode");

  window.scrollTo({
    top: 0,
    behavior: "smooth",
  });
}

export function initAuthPage() {
$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const form = new FormData(event.currentTarget);

  const email = String(form.get("email") || "")
    .trim()
    .toLowerCase();

  const password = String(form.get("password") || "");

  const button = event.currentTarget.querySelector('button[type="submit"]');

  button.disabled = true;

  try {
    const response = await api("/api/pengguna/login", {
      method: "POST",
      body: JSON.stringify({
        email,
        kata_sandi: password,
      }),
    });

    state.user = normalizeUser(response.pengguna);

    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(state.user));

    updateUserUI();

    sessionStorage.setItem(FLASH_MESSAGE_KEY, "Login berhasil.");
    navigate("home");
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

// ============================================================
// REGISTER
// ============================================================

$("#registerForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  // Simpan referensi form sebelum await; event.currentTarget menjadi null
  // setelah callback melanjutkan secara asynchronous.
  const formElement = event.currentTarget;
  const form = new FormData(formElement);

  const nama = String(form.get("nama") || "").trim();

  const email = String(form.get("email") || "")
    .trim()
    .toLowerCase();

  const password = String(form.get("password") || "");
  const confirm = String(form.get("confirm") || "");

  if (!nama) {
    return toast("Nama pengguna wajib diisi.", true);
  }

  if (!email) {
    return toast("Email wajib diisi.", true);
  }

  if (password.length < 8) {
    return toast("Password harus minimal 8 karakter.", true);
  }

  if (password !== confirm) {
    return toast("Konfirmasi password tidak sama.", true);
  }

  const button = formElement.querySelector('button[type="submit"]');

  button.disabled = true;

  try {
    await api("/api/pengguna/register", {
      method: "POST",
      body: JSON.stringify({
        nama_pengguna: nama,
        email,
        kata_sandi: password,
      }),
    });

    formElement.reset();

    toast("Pendaftaran berhasil. Silakan masuk.");

    showAuth("login");

    $("#loginEmail").value = email;
    $("#loginPassword").value = "";
    $("#loginPassword").focus();
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#showRegister").addEventListener("click", () => {
  showAuth("register");
});

$("#showLogin").addEventListener("click", () => {
  showAuth("login");
});

$("#showForgotPassword").addEventListener("click", () => {
  $("#forgotEmail").value = $("#loginEmail").value.trim();
  showAuth("forgot");
});

$("#forgotBackLogin").addEventListener("click", () => {
  showAuth("login");
});

$("#forgotPasswordForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const formElement = event.currentTarget;
  const form = new FormData(formElement);

  const email = String(form.get("email") || "")
    .trim()
    .toLowerCase();

  const password = String(form.get("new_password") || "");
  const confirm = String(form.get("confirm_password") || "");

  if (!email) {
    return toast("Masukkan email akun terlebih dahulu.", true);
  }

  if (password.length < 8) {
    return toast("Password baru minimal 8 karakter.", true);
  }

  if (password !== confirm) {
    return toast("Konfirmasi password tidak sama.", true);
  }

  const button = formElement.querySelector('button[type="submit"]');

  button.disabled = true;

  try {
    const response = await api("/api/pengguna/reset-password-by-email", {
      method: "POST",
      body: JSON.stringify({
        email,
        new_password: password,
      }),
    });

    formElement.reset();

    // Paksa login kembali menggunakan password yang baru.
    state.user = null;
    localStorage.removeItem(USER_STORAGE_KEY);

    $("#headerAccount").classList.add("hidden");

    showAuth("login");

    $("#loginEmail").value = email;
    $("#loginPassword").value = "";

    toast(
      response.message || "Password berhasil diubah. Silakan masuk kembali.",
    );
  } catch (error) {
    toast(error.message || "Gagal mengubah password.", true);
  } finally {
    button.disabled = false;
  }
});


  // Mode login/daftar/reset ditentukan melalui query string, jika ada.
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("mode");
  showAuth(["login", "register", "forgot"].includes(mode) ? mode : "login");
  if (params.has("email") && $("#forgotEmail")) {
    $("#forgotEmail").value = params.get("email");
  }
}
