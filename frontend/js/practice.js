import {
  $, $$, api, toast, state, escapeHtml, normalizeNFC,
  setRecordState, cleanupAudio, navigate,
} from "./utils.js";
import { loadStats } from "./home.js";
import { FLASH_MESSAGE_KEY, EVALUATION_TIMEOUT_MS } from "./config.js";

function updateTestProgress() {
  const node = $("#testProgress");

  if (node) {
    node.textContent = `Tes ${state.testCount} dari 10`;
  }

  const progressBar = $("#testProgressBar");

  if (progressBar) {
    progressBar.style.width = `${Math.min(100, state.testCount * 10)}%`;
  }

  const progressTrack = $(".test-progress-track");

  if (progressTrack) {
    progressTrack.setAttribute("aria-valuenow", String(state.testCount));
  }

  const finishPracticeButton = $("#finishPracticeBtn");

  if (finishPracticeButton) {
    const complete = state.testCount >= 10;

    finishPracticeButton.disabled = !complete;

    finishPracticeButton.textContent = complete
      ? "Selesai · Buka Riwayat →"
      : `Selesaikan 10 Tes (${state.testCount}/10)`;

    finishPracticeButton.title = complete
      ? "Buka riwayat latihan"
      : `Selesaikan ${10 - state.testCount} tes lagi untuk membuka riwayat`;

    finishPracticeButton.setAttribute("aria-label", finishPracticeButton.title);

    finishPracticeButton.classList.toggle("is-ready", complete);
  }
}

function resetResultView(showResult = false) {
  $("#levelPicker").classList.toggle("hidden", showResult);
  $(".practice-layout").classList.toggle("hidden", showResult);
  $("#evalUnavailablePanel").classList.toggle("hidden", !showResult);
}

// Gunakan SATU tombol untuk mulai dan berhenti merekam.
// Label tombol berubah mengikuti status, tetapi elemen tombolnya tetap sama.
function setRecordingControls(mode = "ready") {
  const button = $("#recordBtn");
  if (!button) return;

  const title = button.querySelector("strong");
  const hint = button.querySelector("small");
  const icon = button.querySelector(".round-icon");
  const complete = state.testCount >= 10;

  button.classList.remove("hidden");
  button.style.removeProperty("display");
  button.classList.toggle("is-recording", mode === "recording");

  if (mode === "requesting") {
    button.disabled = true;
    if (icon) icon.textContent = "🎙";
    if (title) title.textContent = "Menyiapkan Mikrofon…";
    if (hint) hint.textContent = "Izinkan akses mikrofon untuk melanjutkan";
    return;
  }

  if (mode === "recording") {
    button.disabled = false;
    if (icon) icon.textContent = "■";
    if (title) title.textContent = "Berhenti & Nilai";
    if (hint) hint.textContent = "Tekan tombol ini setelah selesai mengucapkan kata";
    button.setAttribute("aria-label", "Berhenti merekam dan nilai pelafalan");
    return;
  }

  if (mode === "processing") {
    button.disabled = true;
    if (icon) icon.textContent = "…";
    if (title) title.textContent = "Menilai Rekaman…";
    if (hint) hint.textContent = "Tunggu hasil sebelum tes berikutnya";
    button.setAttribute("aria-label", "Rekaman sedang dinilai");
    return;
  }

  button.classList.remove("is-recording");
  button.classList.toggle("hidden", complete);
  button.disabled = complete;
  if (icon) icon.textContent = "🎙";
  if (title) title.textContent = "Mulai Merekam";
  if (hint) hint.textContent = "Ucapkan kata di layar";
  button.setAttribute("aria-label", "Mulai merekam pelafalan");
}

async function startTestSession() {
  // Token baru membatalkan efek UI dari proses sesi sebelumnya yang masih berjalan.
  const sessionId = (state.sessionId || 0) + 1;
  state.sessionId = sessionId;

  // Sesi baru harus bisa merekam lagi, meskipun proses sesi lama baru saja selesai.
  state.recording = false;
  state.busy = false;
  state.requestingRecording = false;
  state.samples = [];

  // Selalu bersihkan sumber audio lama; aman dipanggil walaupun sudah berhenti.
  await cleanupAudio();
  if (sessionId !== state.sessionId) return;


  const sampleAudio = $("#sampleAudio");
  if (sampleAudio) {
    sampleAudio.pause();
    sampleAudio.removeAttribute("src");
    sampleAudio.load();
    sampleAudio.classList.add("hidden");
  }

  if (state.recordingUrl) {
    URL.revokeObjectURL(state.recordingUrl);
    state.recordingUrl = null;
  }

  state.testCount = 0;
  state.testResults = [];
  updateTestProgress();
  setRecordingControls("ready");
  resetResultView(false);
  setRecordState("Siap merekam");

  await loadLevelsAndWords();
  if (sessionId !== state.sessionId) return;

  // Tegaskan ulang kontrol setelah pemuatan level/kata selesai.
  setRecordingControls("ready");
  resetResultView(false);
  setRecordState("Siap merekam");
}

async function loadLevelsAndWords() {
  try {
    if (!state.levels.length) {
      const levels = await api("/api/level-latihan");

      if (!Array.isArray(levels)) {
        throw new Error("API level tidak mengembalikan daftar level.");
      }

      state.levels = levels;

      if (
        !state.levelId ||
        !levels.some((item) => Number(item.id_level) === Number(state.levelId))
      ) {
        state.levelId = levels.length ? Number(levels[0].id_level) : null;
      }
    }

    renderLevels();

    await loadWords();
  } catch (error) {
    toast(error.message, true);
  }
}

function renderLevels() {
  const picker = $("#levelPicker");

  if (!state.levels.length) {
    picker.innerHTML =
      '<p class="muted">API belum mengembalikan level latihan.</p>';
    return;
  }

  picker.innerHTML = state.levels
    .map((level, index) => {
      const id = Number(level.id_level);

      const selected = id === Number(state.levelId) ? " selected" : "";

      const name = escapeHtml(level.nama_level || `Level ${index + 1}`);

      const number = String(index + 1).padStart(2, "0");

      return `
        <button
          class="level-option${selected}"
          data-level="${id}"
          type="button"
        >
          <span>${number}</span>
          <strong>${name}</strong>
          <small>ID level ${id}</small>
        </button>
      `;
    })
    .join("");

  $$("[data-level]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.levelId = Number(button.dataset.level);

      state.testCount = 0;
      state.testResults = [];

      updateTestProgress();
      resetResultView(false);
      renderLevels();

      await loadWords();
    });
  });
}

async function loadWords() {
  if (state.levelId == null) {
    $("#wordCounter").textContent = "Belum ada level";

    $("#wordDisplay").innerHTML =
      '<span class="meaning">Pilih level latihan yang tersedia.</span>';

    return;
  }

  $("#wordCounter").textContent = "Memuat kata…";

  try {
    const words = await api(
      `/api/kata-acuan/acak/${encodeURIComponent(state.levelId)}?jumlah=10`,
    );

    state.words = Array.isArray(words) ? words : [];
    state.wordIndex = 0;

    renderWord();

    $("#evalUnavailablePanel").classList.add("hidden");
  } catch (error) {
    state.words = [];
    renderWord();

    toast(error.message, true);
  }
}

function renderWord() {
  const word = state.words[state.wordIndex];

  if (!word) {
    $("#wordDisplay").innerHTML =
      '<span class="meaning">Tidak ada kata acuan pada level ini.</span>';

    $("#wordCounter").textContent = "0 kata";
    $("#prevWord").disabled = true;
    $("#nextWord").disabled = true;

    return;
  }

  $("#wordDisplay").innerHTML = `
    <span class="hanzi">${escapeHtml(word.hanzi)}</span>
    <span class="pinyin">${escapeHtml(normalizeNFC(word.pinyin))}</span>
    <span class="meaning">Ucapkan kata di atas</span>
  `;

  $("#wordCounter").textContent =
    `Kata ${state.wordIndex + 1} dari ${state.words.length}`;

  updateTestProgress();

  $("#prevWord").disabled = state.wordIndex === 0;

  $("#nextWord").disabled = state.wordIndex >= state.words.length - 1;
}

function downsample(input, fromRate, toRate) {
  if (fromRate === toRate) return input;

  const ratio = fromRate / toRate;

  const out = new Float32Array(Math.floor(input.length / ratio));

  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);

    const end = Math.min(Math.floor((i + 1) * ratio), input.length);

    let sum = 0;

    for (let j = start; j < end; j++) {
      sum += input[j];
    }

    out[i] = end > start ? sum / (end - start) : 0;
  }

  return out;
}

function encodeWav(samples, sampleRate = 16000) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);

  const view = new DataView(buffer);

  const write = (offset, string) => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  };

  write(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);

  write(8, "WAVE");
  write(12, "fmt ");

  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);

  write(36, "data");
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;

  for (const value of samples) {
    const sample = Math.max(-1, Math.min(1, value));

    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);

    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

async function evaluateWavWithModel(wav, word) {
  const form = new FormData();

  form.append("file", wav, "practice.wav");
  form.append("hanzi", String(word.hanzi || ""));
  form.append("pinyin", String(word.pinyin || ""));

  return api("/api/evaluate", {
    method: "POST",
    body: form,
    timeoutMs: EVALUATION_TIMEOUT_MS,
  });
}

function setAudioPreview(audioFile) {
  if (state.recordingUrl) {
    URL.revokeObjectURL(state.recordingUrl);
  }

  state.recordingUrl = URL.createObjectURL(audioFile);

  const audio = $("#sampleAudio");

  audio.src = state.recordingUrl;
  audio.classList.remove("hidden");
}

function normalizeEvaluationStatus(value) {
  if (value === true) return "correct";
  if (value === false) return "incorrect";

  const status = String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ");

  if ([
    "correct", "benar", "tepat", "cocok", "match", "matched",
    "pass", "passed", "accepted", "acceptable", "accurate",
    "success", "succeeded", "all correct",
  ].includes(status)) {
    return "correct";
  }

  if ([
    "incorrect", "salah", "kurang tepat", "tidak cocok", "mismatch",
    "unmatched", "not matched", "fail", "failed", "wrong",
    "rejected", "unacceptable", "inaccurate", "mispronounced",
  ].includes(status)) {
    return "incorrect";
  }

  return null;
}

function resolveEvaluationStatus(modelResult) {
  // Baca status eksplisit dari beberapa bentuk respons backend yang umum.
  const explicitStatusFields = [
    modelResult?.status,
    modelResult?.pronunciation_status,
    modelResult?.result_status,
    modelResult?.classification,
    modelResult?.label,
  ];

  for (const value of explicitStatusFields) {
    const status = normalizeEvaluationStatus(value);
    if (status) return status;
  }

  // Field boolean hanya ditafsirkan jika nama field-nya menyatakan hasil.
  for (const key of ["is_correct", "correct", "passed", "is_match", "matched"]) {
    if (typeof modelResult?.[key] === "boolean") {
      return modelResult[key] ? "correct" : "incorrect";
    }
  }

  const syllables = Array.isArray(modelResult?.syllables)
    ? modelResult.syllables
    : [];

  if (!syllables.length) return "pending";

  const syllableStatuses = syllables.map((item) => {
    const candidates = [
      item?.status,
      item?.gop_status,
      item?.got_status,
      item?.pronunciation_status,
      item?.tone_status,
      item?.classification,
      item?.label,
    ];
    const statuses = candidates.map(normalizeEvaluationStatus).filter(Boolean);

    if (statuses.includes("incorrect")) return "incorrect";
    if (statuses.includes("correct")) return "correct";

    for (const key of ["is_correct", "correct", "passed", "is_match", "matched"]) {
      if (typeof item?.[key] === "boolean") {
        return item[key] ? "correct" : "incorrect";
      }
    }

    return "pending";
  });

  if (syllableStatuses.includes("incorrect")) return "incorrect";
  if (syllableStatuses.length && syllableStatuses.every((status) => status === "correct")) return "correct";
  return "pending";
}

async function processAudioResult(
  recordedWav,
  word,
  sessionId = state.sessionId,
) {
  const modelResult = await evaluateWavWithModel(recordedWav, word);

  // Jangan masukkan hasil dari request sesi lama ke sesi yang baru diulang.
  if (sessionId !== state.sessionId) return;

  const syllables = Array.isArray(modelResult.syllables)
    ? modelResult.syllables
    : [];

  // Ubah keluaran numerik GOP/GOT menjadi diagnosis yang mudah dipahami.
  // Nilai GOP/GOT tetap digunakan oleh backend/model, tetapi tidak ditampilkan
  // sebagai angka pada ringkasan latihan.
  const scoreText = syllables
    .map((item) => {
      const hanzi = String(item.hanzi || word.hanzi || "Suku kata");
      const pronunciationWrong = item.gop_status === "incorrect";
      const toneWrong = item.got_status === "incorrect";

      if (pronunciationWrong && toneWrong) {
        return `${hanzi}: pelafalan dan nada salah`;
      }

      if (pronunciationWrong) {
        return `${hanzi}: pelafalan salah`;
      }

      if (toneWrong) {
        return `${hanzi}: nada salah`;
      }

      if (
        item.status === "correct" ||
        (item.gop_status === "correct" && item.got_status === "correct")
      ) {
        return `${hanzi}: pelafalan dan nada benar`;
      }

      if (item.status === "incorrect") {
        return `${hanzi}: ada kesalahan, tetapi jenisnya belum teridentifikasi`;
      }

      return `${hanzi}: belum dapat dinilai`;
    })
    .join(" | ");

  state.testCount += 1;

  state.testResults.push({
    number: state.testCount,
    wordId: word.id_kata,
    hanzi: word.hanzi,
    pinyin: normalizeNFC(word.pinyin),
    status: resolveEvaluationStatus(modelResult),
    scoreText:
      scoreText || "Rincian pelafalan atau nada belum tersedia dari model.",
    score: Number(modelResult.score || 0),
    gop: modelResult.gop,
    got: modelResult.got,
    thresholds: modelResult.thresholds || null,
    modelWarning: modelResult.warning || "",
  });

  updateTestProgress();

  if (state.testCount >= 10) {
    await finishTestSession(sessionId);
    return;
  }

  if (state.words.length > 0) {
    state.wordIndex = (state.wordIndex + 1) % state.words.length;
  }

  renderWord();
  setRecordState("Siap merekam");

  const statusText =
    modelResult.status === "correct"
      ? "cocok"
      : modelResult.status === "incorrect"
        ? "tidak cocok"
        : "belum dinilai";

  toast(
    `Rekaman mikrofon: tes ${state.testCount} dari 10 selesai (${statusText}).`,
  );
}

function getUserMediaWithTimeout(constraints, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    let settled = false;

    const timeoutId = window.setTimeout(() => {
      settled = true;
      reject(
        new Error(
          "Permintaan akses mikrofon terlalu lama. Periksa izin mikrofon browser lalu coba lagi.",
        ),
      );
    }, timeoutMs);

    navigator.mediaDevices
      .getUserMedia(constraints)
      .then((stream) => {
        window.clearTimeout(timeoutId);

        // Jika izin baru diberikan setelah timeout, jangan biarkan mikrofon aktif.
        if (settled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        settled = true;
        resolve(stream);
      })
      .catch((error) => {
        window.clearTimeout(timeoutId);
        if (settled) return;
        settled = true;

        if (error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError") {
          reject(new Error("Akses mikrofon ditolak. Izinkan mikrofon untuk situs ini."));
        } else if (error?.name === "NotFoundError") {
          reject(new Error("Mikrofon tidak ditemukan. Periksa perangkat input audio."));
        } else {
          reject(error);
        }
      });
  });
}

async function stopRecordingAndProcess() {
  if (!state.recording || state.busy) return;

  const sessionId = state.sessionId;
  state.busy = true;
  state.recording = false;

  setRecordingControls("processing");

  const rate = state.sampleRate;
  const chunks = state.samples;
  state.samples = [];
  setRecordState("Menyiapkan audio untuk penilaian…");

  try {
    // Letakkan cleanup di dalam try agar finally tetap berjalan jika cleanup gagal.
    await cleanupAudio();
    if (sessionId !== state.sessionId) return;

    const totalSamples = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    if (!totalSamples) {
      throw new Error("Tidak ada audio yang terekam. Coba rekam ulang.");
    }

    const merged = new Float32Array(totalSamples);
    let offset = 0;
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }

    const wav = encodeWav(downsample(merged, rate, 16000), 16000);
    const word = state.words[state.wordIndex];
    if (!word) {
      throw new Error("Kata acuan tidak tersedia.");
    }

    if (sessionId !== state.sessionId) return;

    setAudioPreview(wav);
    setRecordState("Menilai rekaman dengan Hybrid DNN-HMM…");
    await processAudioResult(wav, word, sessionId);
  } catch (error) {
    if (sessionId === state.sessionId) {
      toast(error.message || "Audio gagal diproses.", true);
      setRecordState("Siap merekam");
    }
  } finally {
    // Selalu pulihkan kontrol untuk sesi yang sama, termasuk setelah timeout/error.
    if (sessionId === state.sessionId) {
      state.busy = false;

      setRecordingControls("ready");

      if (state.testCount < 10) {
        setRecordState("Siap merekam");
      }
    }
  }
}

async function finishTestSession(sessionId = state.sessionId) {
  if (sessionId !== state.sessionId) return;

  const correct = state.testResults.filter(
    (result) => result.status === "correct",
  ).length;

  const incorrect = state.testResults.filter(
    (result) => result.status === "incorrect",
  ).length;

  const pending = state.testResults.filter(
    (result) => result.status === "pending",
  ).length;

  const assessed = correct + incorrect;

  const score = assessed ? Math.round((correct / assessed) * 100) : null;

  $("#resultScore").textContent = score == null ? "—" : String(score);

  $("#resultCorrect").textContent = String(correct);
  $("#resultIncorrect").textContent = String(incorrect);
  $("#resultPending").textContent = String(pending);

  $("#detailsList").innerHTML = state.testResults
    .map((result) => {
      const rowClass =
        result.status === "correct"
          ? "correct"
          : result.status === "incorrect"
            ? "incorrect"
            : "pending";

      const label =
        result.status === "correct"
          ? "✓ Tepat"
          : result.status === "incorrect"
            ? "✕ Kurang Tepat"
            : "Belum dinilai";

      return `
        <div class="detail-row ${rowClass}">
          <span class="result-number">
            ${String(result.number).padStart(2, "0")}
          </span>
          <div class="result-word">
            <strong class="detail-hanzi">
              ${escapeHtml(result.hanzi)}
            </strong>
            <span class="detail-pinyin">
              ${escapeHtml(result.pinyin)}
            </span>
            <small class="recognition-text">
              ${escapeHtml(result.scoreText || "Belum ada rincian kesalahan.")}
            </small>
          </div>
          <span class="status-tag">${label}</span>
        </div>
      `;
    })
    .join("");

  let saveMessage = "";

  if (score != null && state.user?.id_pengguna && state.levelId) {
    try {
      await api("/api/riwayat-latihan", {
        method: "POST",
        body: JSON.stringify({
          id_pengguna: state.user.id_pengguna,
          id_level: state.levelId,
          skor_akhir: Number(((correct / assessed) * 100).toFixed(2)),
          jumlah_tepat: correct,
          jumlah_kurang_tepat: incorrect,
        }),
      });

      saveMessage = " Ringkasan sesi disimpan.";
    } catch (error) {
      saveMessage = ` Hasil tampil di sini, tetapi riwayat tidak tersimpan: ${error.message}`;
    }
  }

  // Jika pengguna sudah memulai ulang sesi, jangan tampilkan hasil sesi sebelumnya.
  if (sessionId !== state.sessionId) return;

  $("#resultNotice").textContent =
    "Sesi selesai" +
    saveMessage;

  $("#levelPicker").classList.add("hidden");
  $(".practice-layout").classList.add("hidden");
  $("#evalUnavailablePanel").classList.remove("hidden");

  $("#evalUnavailablePanel").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });

  await loadStats();
  if (sessionId !== state.sessionId) return;

  toast("10 tes selesai. Hasil pelafalan ditampilkan.");
}

export async function initPracticePage() {
$("#prevWord").addEventListener("click", () => {
  if (state.wordIndex > 0) {
    state.wordIndex--;
    renderWord();
  }
});

$("#nextWord").addEventListener("click", () => {
  if (state.wordIndex < state.words.length - 1) {
    state.wordIndex++;
    renderWord();
  }
});
$("#listenBtn").addEventListener("click", () => {
  const word = state.words[state.wordIndex];

  if (!word) {
    return toast("Tidak ada kata yang dapat diputar.", true);
  }

  if (
    !("speechSynthesis" in window) ||
    !("SpeechSynthesisUtterance" in window)
  ) {
    return toast(
      "Fitur suara tidak tersedia di browser atau perangkat ini.",
      true,
    );
  }

  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(word.hanzi);

  utterance.lang = "zh-CN";
  utterance.rate = 0.82;

  const voices = window.speechSynthesis.getVoices();

  const chineseVoice = voices.find((voice) => /^zh(-|_|$)/i.test(voice.lang));

  if (chineseVoice) {
    utterance.voice = chineseVoice;
  }

  utterance.onerror = () => {
    toast("Suara Mandarin tidak tersedia di browser/perangkat ini.", true);
  };

  window.speechSynthesis.speak(utterance);
});
$("#recordBtn").addEventListener("click", async () => {
  // Tombol yang sama berfungsi sebagai tombol berhenti saat sedang merekam.
  if (state.recording) {
    await stopRecordingAndProcess();
    return;
  }

  if (state.busy || state.requestingRecording) return;

  if (state.testCount >= 10) {
    return toast(
      "10 tes sudah selesai. Pilih Ulangi 10 Tes untuk memulai lagi.",
      true,
    );
  }

  if (!state.words.length || !state.words[state.wordIndex]) {
    return toast("Tidak ada kata untuk direkam.", true);
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    return toast("Browser tidak mendukung perekaman mikrofon.", true);
  }

  const sessionId = state.sessionId;
  state.requestingRecording = true;
  setRecordingControls("requesting");
  setRecordState("Meminta akses mikrofon…");

  try {
    const stream = await getUserMediaWithTimeout(
      {
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      },
      30000,
    );

    // Jangan gunakan stream dari sesi lama jika pengguna berpindah/mengulang halaman.
    if (sessionId !== state.sessionId) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    state.mediaStream = stream;

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      throw new Error("Browser tidak mendukung perekaman audio.");
    }

    state.audioContext = new AudioCtx();
    await state.audioContext.resume();

    if (sessionId !== state.sessionId) {
      await cleanupAudio();
      return;
    }

    state.sampleRate = state.audioContext.sampleRate;
    state.samples = [];
    state.source = state.audioContext.createMediaStreamSource(state.mediaStream);
    state.processor = state.audioContext.createScriptProcessor(4096, 1, 1);

    state.processor.onaudioprocess = (event) => {
      if (state.recording && sessionId === state.sessionId) {
        state.samples.push(
          new Float32Array(event.inputBuffer.getChannelData(0)),
        );
      }
    };

    const mute = state.audioContext.createGain();
    mute.gain.value = 0;

    state.source.connect(state.processor);
    state.processor.connect(mute);
    mute.connect(state.audioContext.destination);

    state.recording = true;
    setRecordingControls("recording");

    setRecordState(`Merekam tes ${state.testCount + 1} dari 10…`, true);
    toast("Perekaman dimulai.");
  } catch (error) {
    if (sessionId === state.sessionId) {
      state.recording = false;
      await cleanupAudio();
      toast(error.message || "Tidak dapat mengakses mikrofon.", true);
      setRecordState("Siap merekam");
    }
  } finally {
    // Sesi baru mengatur kontrolnya sendiri; proses lama tidak boleh menimpanya.
    if (sessionId === state.sessionId) {
      state.requestingRecording = false;
      if (!state.recording && !state.busy) {
        setRecordingControls("ready");
      }
    }
  }
});

$("#repeatBtn").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (button.dataset.restarting === "true") return;

  button.dataset.restarting = "true";
  button.disabled = true;
  try {
    await startTestSession();
  } finally {
    // Lepas lock cepat; sessionId menjaga proses lama agar tidak mengubah UI baru.
    window.setTimeout(() => {
      button.dataset.restarting = "false";
      button.disabled = false;
    }, 300);
  }
});

async function finishPracticeAndOpenHistory() {
  if (state.testCount < 10) {
    toast(
      "Selesaikan 10 tes terlebih dahulu untuk membuka riwayat sesi ini.",
      true,
    );

    return;
  }

  if (state.busy) {
    toast("Sedang memproses tes terakhir. Tunggu sampai hasil muncul.", true);

    return;
  }

  if (state.recording) {
    state.recording = false;

    await cleanupAudio();
  }

  setRecordingControls("ready");

  sessionStorage.setItem(FLASH_MESSAGE_KEY, "Sesi selesai. Riwayat latihan dibuka.");
  navigate("history");
}

$("#finishBtn").addEventListener("click", finishPracticeAndOpenHistory);

$("#finishPracticeBtn").addEventListener("click", finishPracticeAndOpenHistory);

  await startTestSession();
}
