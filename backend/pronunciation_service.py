"""Runtime inference adapter for the Mandarin Hybrid DNN-HMM + GOP/GOT model.

The service consumes the deployment bundle exported by notebook 04. It does not
train or recalibrate at request time; threshold values come from calibration only.
"""
from __future__ import annotations

import math
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any


class ModelArtifactError(RuntimeError):
    """Raised when the trained model, phone lexicon, or thresholds are unavailable."""


class SenoneVocabulary:
    def __init__(self, units: list[str], states_per_unit: int = 3):
        self.units = sorted(set(map(str, units)))
        self.states_per_unit = int(states_per_unit)
        self.unit2id = {unit: idx for idx, unit in enumerate(self.units)}
        self.senones: list[str] = []
        self.senone2id: dict[str, int] = {}
        for unit in self.units:
            for state in range(self.states_per_unit):
                name = f"{unit}_s{state}"
                self.senone2id[name] = len(self.senones)
                self.senones.append(name)

    def __len__(self) -> int:
        return len(self.senones)

    def state_ids_for_units(self, units: list[str]) -> list[int]:
        result: list[int] = []
        for unit in units:
            if unit not in self.unit2id:
                raise ValueError(f"Unit fonetik {unit!r} tidak ada dalam vocabulary model.")
            for state in range(self.states_per_unit):
                result.append(self.senone2id[f"{unit}_s{state}"])
        return result

    @staticmethod
    def base(unit: str) -> str:
        unit = str(unit)
        return unit.rsplit("_T", 1)[0] if "_T" in unit else unit

    @staticmethod
    def tone(unit: str) -> int | None:
        unit = str(unit)
        if "_T" not in unit:
            return None
        try:
            return int(unit.rsplit("_T", 1)[1])
        except ValueError:
            return None

    def tone_units_for_base(self, base: str) -> list[str]:
        return [u for u in self.units if self.base(u) == base and "_T" in u]


class AcousticDNN:
    """Small wrapper class created lazily with PyTorch available in the runtime."""
    def __new__(cls, input_dim: int, num_states: int, hidden_dim: int, hidden_layers: int, dropout: float):
        import torch.nn as nn

        class _AcousticDNN(nn.Module):
            def __init__(self):
                super().__init__()
                layers = []
                dim = int(input_dim)
                for _ in range(int(hidden_layers)):
                    layers.extend([nn.Linear(dim, int(hidden_dim)), nn.ReLU(), nn.Dropout(float(dropout))])
                    dim = int(hidden_dim)
                layers.append(nn.Linear(dim, int(num_states)))
                self.net = nn.Sequential(*layers)

            def forward(self, x):
                batch, frames, feature_dim = x.shape
                logits = self.net(x.reshape(batch * frames, feature_dim))
                return logits.reshape(batch, frames, -1)

        return _AcousticDNN()


class PronunciationService:
    def __init__(self, model_path: str | Path, lexicon_path: str | Path, thresholds_path: str | Path | None = None):
        try:
            import librosa
            import numpy as np
            import torch
            from scipy.special import logsumexp
        except ImportError as exc:
            raise ModelArtifactError(
                "Dependensi model belum terpasang. Jalankan: pip install -r requirements-ml.txt"
            ) from exc

        self.np = np
        self.torch = torch
        self.librosa = librosa
        self.logsumexp = logsumexp
        self.model_path = Path(model_path)
        self.lexicon_path = Path(lexicon_path)
        if thresholds_path:
            self.thresholds_path = Path(thresholds_path)
        else:
            candidates = [
                self.model_path.parent / "thresholds.json",
                self.model_path.parent / "hanzi_proxy_thresholds.json",
            ]
            self.thresholds_path = next((p for p in candidates if p.is_file()), candidates[0])

        if not self.model_path.is_file():
            raise ModelArtifactError(
                f"Paket model tidak ditemukan: {self.model_path}. Ekspor dari notebook 04 lalu salin ke backend/model/."
            )
        if not self.lexicon_path.is_file():
            raise ModelArtifactError(
                f"Kamus Pinyin-ke-phone tidak ditemukan: {self.lexicon_path}. Salin pinyin2phone.tone.txt dari bundle deployment."
            )

        try:
            try:
                payload = torch.load(self.model_path, map_location="cpu", weights_only=False)
            except TypeError:  # compatibility with older PyTorch versions
                payload = torch.load(self.model_path, map_location="cpu")
        except Exception as exc:
            raise ModelArtifactError(f"Paket model gagal dibaca: {exc}") from exc

        self.config = dict(payload.get("config") or {})
        self.sample_rate = int(payload.get("sample_rate", self.config.get("sample_rate", 16000)))
        self.silence_top_db = int(self.config.get("silence_top_db", 30))
        self.n_fft = int(self.config.get("n_fft", 400))
        self.win_length = int(self.config.get("win_length", 400))
        self.hop_length = int(self.config.get("hop_length", 160))
        self.n_mels = int(self.config.get("n_mels", 26))
        # Training menggunakan 13 MFCC + 3 fitur prosodi pYIN = 16 fitur/frame.
        self.n_mfcc = int(payload.get("mfcc_dimension", self.config.get("n_mfcc", 13)))
        self.pitch_feature_count = int(
            payload.get("pitch_feature_count", self.config.get("pitch_feature_count", 3))
        )
        self.input_dimension = int(
            payload.get("input_dimension", self.n_mfcc + self.pitch_feature_count)
        )
        expected_dimension = self.n_mfcc + self.pitch_feature_count
        if self.input_dimension != expected_dimension:
            raise ModelArtifactError(
                f"Dimensi fitur paket tidak konsisten: input_dimension={self.input_dimension}, "
                f"MFCC={self.n_mfcc}, pitch={self.pitch_feature_count}."
            )
        self.pitch_enabled = bool(self.config.get("pitch_enabled", True))
        self.pitch_fmin = float(self.config.get("pitch_fmin", 60.0))
        self.pitch_fmax = float(self.config.get("pitch_fmax", 600.0))
        self.pitch_n_thresholds = int(self.config.get("pitch_n_thresholds", 25))
        self.pitch_frame_length = int(self.config.get("pitch_frame_length", 640))
        self.states_per_unit = int(payload.get("states_per_unit", self.config.get("states_per_unit", 3)))
        self.hmm_self_loop = float(self.config.get("hmm_self_loop_init", 0.65))
        # Use the same GOP aggregation as the model's calibration.
        # Exp03 uses gop_mean; only use min if the bundle explicitly requests it.
        self.gop_aggregation = str(
            payload.get("gop_aggregation", self.config.get("gop_aggregation", "gop_mean"))
        ).strip().lower()
        if self.gop_aggregation not in {"gop_mean", "mean", "gop_min", "min"}:
            raise ModelArtifactError(
                f"Metode agregasi GOP tidak dikenal: {self.gop_aggregation!r}. "
                "Gunakan 'gop_mean' atau 'gop_min'."
            )

        vocab_units = payload.get("vocab_units")
        if not vocab_units:
            raise ModelArtifactError("Paket model tidak berisi 'vocab_units'. Ekspor ulang melalui notebook 04.")
        self.vocab = SenoneVocabulary(list(vocab_units), self.states_per_unit)
        self.priors = np.asarray(payload.get("state_priors"), dtype=np.float64)
        if self.priors.size != len(self.vocab):
            raise ModelArtifactError(
                f"Ukuran state_priors ({self.priors.size}) tidak cocok dengan vocabulary ({len(self.vocab)})."
            )

        # Gunakan threshold yang disimpan bersama checkpoint sebagai sumber utama,
        # karena nilainya berasal dari kalibrasi model yang sama. JSON hanya fallback.
        bundle_gop = payload.get("gop_threshold")
        bundle_got = payload.get("got_threshold")
        self.threshold_source = None

        if bundle_gop is not None and bundle_got is not None:
            self.gop_threshold = float(bundle_gop)
            self.got_threshold = float(bundle_got)
            self.threshold_source = f"deployment bundle: {self.model_path}"

            # Laporkan bila JSON berbeda jangan diam-diam mencampur threshold eksperimen.
            if self.thresholds_path.is_file():
                try:
                    threshold_obj = json.loads(
                        self.thresholds_path.read_text(encoding="utf-8")
                    )
                    json_gop = threshold_obj.get("gop")
                    json_got = threshold_obj.get("got")
                    if (
                        json_gop is not None and json_got is not None
                        and (
                            not math.isclose(float(json_gop), self.gop_threshold, rel_tol=0.0, abs_tol=1e-9)
                            or not math.isclose(float(json_got), self.got_threshold, rel_tol=0.0, abs_tol=1e-9)
                        )
                    ):
                        print(
                            "[PronunciationService] PERINGATAN: threshold JSON berbeda "
                            "dari bundle model threshold bundle yang digunakan."
                        )
                except (OSError, ValueError, TypeError):
                    print(
                        "[PronunciationService] PERINGATAN: threshold JSON tidak terbaca; "
                        "threshold bundle yang digunakan."
                    )
        elif self.thresholds_path.is_file():
            try:
                threshold_obj = json.loads(
                    self.thresholds_path.read_text(encoding="utf-8")
                )
                self.gop_threshold = threshold_obj.get("gop")
                self.got_threshold = threshold_obj.get("got")
                if self.gop_threshold is not None and self.got_threshold is not None:
                    self.threshold_source = str(self.thresholds_path)
            except (OSError, ValueError, TypeError) as exc:
                raise ModelArtifactError(
                    f"File threshold tidak dapat dibaca: {self.thresholds_path}: {exc}"
                ) from exc
        else:
            self.gop_threshold = None
            self.got_threshold = None

        if self.gop_threshold is None or self.got_threshold is None:
            raise ModelArtifactError(
                "Threshold GOP/GOT tidak ditemukan di deployment bundle maupun JSON."
            )
        self.gop_threshold = float(self.gop_threshold)
        self.got_threshold = float(self.got_threshold)
        if not (math.isfinite(self.gop_threshold) and math.isfinite(self.got_threshold)):
            raise ModelArtifactError("Threshold GOP/GOT harus berupa angka finite.")

        state_dict = payload.get("dnn_state_dict") or payload.get("state_dict")
        if state_dict is None:
            raise ModelArtifactError("Paket model tidak berisi bobot DNN ('dnn_state_dict').")
        self.model = AcousticDNN(
            input_dim=self.input_dimension,
            num_states=len(self.vocab),
            hidden_dim=int(self.config.get("hidden_dim", 256)),
            hidden_layers=int(self.config.get("hidden_layers", 3)),
            dropout=float(self.config.get("dropout", 0.10)),
        )
        try:
            self.model.load_state_dict(state_dict, strict=True)
        except Exception as exc:
            raise ModelArtifactError(f"Bobot DNN tidak sesuai dengan arsitektur/config model: {exc}") from exc
        self.model.eval()
        self.model.to("cpu")
        self.lexicon = self._load_lexicon(self.lexicon_path)
        if not self.lexicon:
            raise ModelArtifactError(f"Kamus Pinyin-ke-phone kosong/tidak terbaca: {self.lexicon_path}")

        print("[PronunciationService] Model:", self.model_path)
        print("[PronunciationService] Lexicon:", self.lexicon_path)
        print("[PronunciationService] Threshold source:", self.threshold_source)
        print("[PronunciationService] GOP threshold:", self.gop_threshold)
        print("[PronunciationService] GOT threshold:", self.got_threshold)
        print("[PronunciationService] Feature dimension:", self.input_dimension,
              f"(MFCC={self.n_mfcc}, pitch={self.pitch_feature_count})")
        print("[PronunciationService] Senones:", len(self.vocab))

    @staticmethod
    def _normalize_pinyin(token: str) -> tuple[str, int]:
        np_token = unicodedata.normalize("NFC", str(token).strip().lower())
        np_token = "".join(
            ch for ch in unicodedata.normalize("NFD", np_token)
            if ch.isalpha() or ch in "12345:\u0304\u0301\u030c\u0300\u0308"
        )
        m = re.fullmatch(r"(.+?)([1-5])", np_token)
        if m:
            base, tone = m.group(1), int(m.group(2))
        else:
            base_chars: list[str] = []
            tone = 5
            tone_marks = {"\u0304": 1, "\u0301": 2, "\u030c": 3, "\u0300": 4}
            for ch in unicodedata.normalize("NFD", np_token):
                if ch in tone_marks:
                    tone = tone_marks[ch]
                elif unicodedata.combining(ch):
                    if ch == "\u0308" and base_chars and base_chars[-1] == "u":
                        base_chars[-1] = "v"
                else:
                    base_chars.append(ch)
            base = "".join(base_chars)
        base = base.replace("ü", "v").replace(":", "")
        if not base or not re.fullmatch(r"[a-zv]+", base):
            raise ValueError(f"Pinyin tidak dikenali: {token!r}")
        return base, tone

    @staticmethod
    def _normalize_phone(token: str) -> str:
        token = str(token).strip().lower()
        suffix = re.fullmatch(r"(.+)_t([1-5])", token)
        if suffix:
            return f"{suffix.group(1)}_T{suffix.group(2)}"
        m = re.fullmatch(r"(.+?)([0-5])", token)
        if m:
            tone = "5" if m.group(2) == "0" else m.group(2)
            return f"{m.group(1)}_T{tone}"
        return token

    @classmethod
    def _load_lexicon(cls, path: Path) -> dict[tuple[str, int], list[list[str]]]:
        lexicon: dict[tuple[str, int], list[list[str]]] = {}
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                try:
                    key = cls._normalize_pinyin(parts[0])
                except ValueError:
                    continue
                phones = [cls._normalize_phone(x) for x in parts[1:]]
                lexicon.setdefault(key, []).append(phones)
        return lexicon

    @staticmethod
    def _pinyin_key_candidates(token: str) -> list[tuple[str, int]]:
        base, tone = PronunciationService._normalize_pinyin(token)
        bases = [base]
        if base.startswith(("j", "q", "x", "y")) and "v" in base:
            bases.append(base.replace("v", "u"))
        return [(candidate, tone) for candidate in dict.fromkeys(bases)]

    def _phones_for_pinyin(self, token: str) -> list[str]:
        candidates: list[list[str]] = []
        for key in self._pinyin_key_candidates(token):
            candidates.extend(self.lexicon.get(key, []))
        if not candidates:
            raise ValueError(f"Pinyin '{token}' tidak ditemukan pada kamus phone.")
        unknown_seen: list[str] = []
        for phones in candidates:
            unknown = [phone for phone in phones if phone not in self.vocab.unit2id]
            if not unknown:
                return phones
            unknown_seen.extend(unknown)
        raise ValueError(
            f"Phone untuk Pinyin '{token}' tidak ada di vocabulary model: {', '.join(sorted(set(unknown_seen)))}"
        )

    def _preprocess(self, wav_path: str | Path):
        """Ekstraksi fitur sesuai notebook training: MFCC13 + pYIN3."""
        np, librosa = self.np, self.librosa
        y = librosa.load(str(wav_path), sr=self.sample_rate, mono=True)[0]
        if y.size == 0:
            raise ValueError("Audio kosong atau tidak dapat dibaca.")

        y_trim, index = librosa.effects.trim(
            y, top_db=self.silence_top_db, frame_length=400, hop_length=160
        )
        if len(y_trim) < 400:
            raise ValueError(
                "Audio terlalu pendek rekam ulang dengan ucapan yang cukup jelas."
            )

        mfcc = librosa.feature.mfcc(
            y=y_trim, sr=self.sample_rate, n_mfcc=self.n_mfcc,
            n_fft=self.n_fft, win_length=self.win_length,
            hop_length=self.hop_length, n_mels=self.n_mels,
            fmin=0, fmax=self.sample_rate // 2,
            window="hamming", center=True,
        ).T.astype(np.float32)

        if self.pitch_enabled and self.pitch_feature_count == 3:
            f0, voiced_flag, voiced_prob = librosa.pyin(
                y_trim, fmin=self.pitch_fmin, fmax=self.pitch_fmax,
                sr=self.sample_rate, frame_length=self.pitch_frame_length,
                hop_length=self.hop_length, n_thresholds=self.pitch_n_thresholds,
                center=True, fill_na=0.0,
            )
            n_frames = len(mfcc)
            f0 = np.asarray(f0 if f0 is not None else [], dtype=np.float32)
            voiced_flag = np.asarray(
                voiced_flag if voiced_flag is not None else [], dtype=bool
            )
            voiced_prob = np.asarray(
                voiced_prob if voiced_prob is not None else [], dtype=np.float32
            )

            def fit_length(values, length, pad_value=0):
                values = values[:length]
                if len(values) < length:
                    values = np.pad(
                        values, (0, length - len(values)), constant_values=pad_value
                    )
                return values

            f0 = fit_length(f0, n_frames)
            voiced_flag = fit_length(voiced_flag, n_frames, False).astype(bool)
            voiced_prob = fit_length(voiced_prob, n_frames)
            voiced_prob = np.nan_to_num(
                voiced_prob, nan=0.0, posinf=0.0, neginf=0.0
            )

            f0_valid = voiced_flag & np.isfinite(f0) & (f0 > 0)
            pitch_semitone = np.zeros(n_frames, dtype=np.float32)
            pitch_semitone[f0_valid] = 12.0 * np.log2(f0[f0_valid] / 200.0)
            pitch_delta = np.zeros(n_frames, dtype=np.float32)
            if n_frames > 1:
                voiced_pairs = f0_valid[1:] & f0_valid[:-1]
                delta = np.diff(pitch_semitone)
                pitch_delta[1:][voiced_pairs] = delta[voiced_pairs]

            prosody = np.column_stack(
                [pitch_semitone, voiced_prob, pitch_delta]
            ).astype(np.float32)
            features = np.concatenate([mfcc, prosody], axis=1)
        elif self.pitch_feature_count == 0:
            features = mfcc
        else:
            raise ModelArtifactError(
                f"Konfigurasi pitch tidak didukung: pitch_enabled={self.pitch_enabled}, "
                f"pitch_feature_count={self.pitch_feature_count}; "
                "pipeline ini mengharapkan MFCC13 + pYIN3."
            )

        if features.ndim != 2 or features.shape[1] != self.input_dimension:
            raise ModelArtifactError(
                f"Dimensi fitur inferensi salah: {features.shape}; "
                f"model mengharapkan {self.input_dimension} fitur per frame."
            )
        if not np.isfinite(features).all():
            raise ValueError("Ekstraksi fitur menghasilkan NaN/Inf.")
        return features.astype(np.float32), int(index[0])

    def _log_likelihood(self, features):
        torch, np = self.torch, self.np
        with torch.no_grad():
            logits = self.model(torch.tensor(features, dtype=torch.float32).unsqueeze(0)).squeeze(0)
            log_posterior = torch.log_softmax(logits, dim=-1).cpu().numpy()
        log_prior = np.log(np.maximum(self.priors, 1e-12))[None, :]
        return log_posterior - log_prior

    def _transition_matrix(self, num_states: int):
        np = self.np
        self_loop = float(np.clip(self.hmm_self_loop, 0.05, 0.95))
        log_a = np.full((num_states, num_states), -np.inf, dtype=np.float64)
        for state in range(num_states):
            if state < num_states - 1:
                log_a[state, state] = math.log(self_loop)
                log_a[state, state + 1] = math.log(1.0 - self_loop)
            else:
                log_a[state, state] = 0.0
        return log_a

    def _viterbi(self, log_emission, log_a):
        np = self.np
        frames, states = log_emission.shape
        dp = np.full((frames, states), -np.inf, dtype=np.float64)
        back = np.full((frames, states), -1, dtype=np.int32)
        dp[0, 0] = log_emission[0, 0]
        for t in range(1, frames):
            candidates = dp[t - 1][:, None] + log_a
            back[t] = np.argmax(candidates, axis=0)
            dp[t] = np.max(candidates, axis=0) + log_emission[t]
        path = np.empty(frames, dtype=np.int32)
        path[-1] = states - 1
        for t in range(frames - 1, 0, -1):
            path[t - 1] = back[t, path[t]]
        return path

    def _unit_log_likelihood(self, log_like, units, start: int, end: int) -> float:
        np = self.np
        x = log_like[start:end]
        if len(x) == 0:
            return -np.inf
        state_ids = []
        for unit in units:
            for state in range(self.vocab.states_per_unit):
                state_ids.append(self.vocab.senone2id[f"{unit}_s{state}"])
        return float(self.logsumexp(x[:, state_ids], axis=1).sum())

    def _gop(self, log_like, unit: str, start: int, end: int) -> float:
        np = self.np
        base = self.vocab.base(unit)
        target_units = [u for u in self.vocab.units if self.vocab.base(u) == base]
        target_ll = self._unit_log_likelihood(log_like, target_units, start, end)
        competitor_bases = sorted({self.vocab.base(u) for u in self.vocab.units} - {base})
        competitor_scores = [
            self._unit_log_likelihood(log_like, [u for u in self.vocab.units if self.vocab.base(u) == cb], start, end)
            for cb in competitor_bases
        ]
        n_frames = max(end - start, 1)
        if not competitor_scores:
            return float(target_ll / n_frames)
        return float((target_ll - max(competitor_scores)) / n_frames)

    def _got(self, log_like, unit: str, start: int, end: int) -> float | None:
        np = self.np
        base = self.vocab.base(unit)
        tone_units = self.vocab.tone_units_for_base(base)
        if self.vocab.tone(unit) is None or not any(u != unit for u in tone_units):
            return None
        target_ll = self._unit_log_likelihood(log_like, [unit], start, end)
        competitors = [
            self._unit_log_likelihood(log_like, [other], start, end)
            for other in tone_units if other != unit
        ]
        return float((target_ll - max(competitors)) / max(end - start, 1))

    def score(self, wav_path: str | Path, hanzi_text: str, pinyin_text: str) -> dict[str, Any]:
        np = self.np
        chars = [ch for ch in str(hanzi_text) if "\u4e00" <= ch <= "\u9fff"]
        tokens = [t for t in str(pinyin_text).split() if t.strip()]
        if not chars:
            raise ValueError("Hanzi acuan kosong atau tidak memuat karakter Hanzi yang didukung.")
        if len(chars) != len(tokens):
            raise ValueError(
                f"Jumlah Hanzi ({len(chars)}) dan token Pinyin ({len(tokens)}) berbeda. Berikan satu Pinyin per Hanzi."
            )

        syllables = []
        all_units: list[str] = []
        for idx, (char, token) in enumerate(zip(chars, tokens)):
            phones = self._phones_for_pinyin(token)
            start = len(all_units)
            all_units.extend(phones)
            syllables.append({"hanzi_index": idx, "hanzi": char, "pinyin": token, "unit_start": start, "unit_end": len(all_units), "units": phones})

        features, trim_start_sample = self._preprocess(wav_path)
        state_ids = self.vocab.state_ids_for_units(all_units)
        if len(features) < len(state_ids):
            raise ValueError(
                f"Audio terlalu singkat untuk urutan target: {len(features)} frame tersedia, sedangkan {len(state_ids)} state dibutuhkan."
            )
        log_like = self._log_likelihood(features)
        local_emission = np.ascontiguousarray(log_like[:, state_ids], dtype=np.float64)
        local_path = self._viterbi(local_emission, self._transition_matrix(len(state_ids)))

        phone_segments = []
        for unit_index, unit in enumerate(all_units):
            mask = (local_path >= unit_index * self.states_per_unit) & (local_path < (unit_index + 1) * self.states_per_unit)
            idxs = np.flatnonzero(mask)
            if len(idxs) == 0:
                continue
            start_frame, end_frame = int(idxs.min()), int(idxs.max() + 1)
            phone_segments.append({
                "unit_index": unit_index, "unit": unit,
                "start_frame": start_frame, "end_frame": end_frame,
                "start_ms": (trim_start_sample + start_frame * self.hop_length) / self.sample_rate * 1000.0,
                "end_ms": (trim_start_sample + end_frame * self.hop_length) / self.sample_rate * 1000.0,
                "gop": self._gop(log_like, unit, start_frame, end_frame),
                "got": self._got(log_like, unit, start_frame, end_frame),
            })

        syllable_results = []
        passed_count = 0
        gop_aggregate, got_aggregate = [], []
        for syllable in syllables:
            segment_list = [r for r in phone_segments if syllable["unit_start"] <= r["unit_index"] < syllable["unit_end"]]
            gop_values = [float(r["gop"]) for r in segment_list if math.isfinite(float(r["gop"]))]
            got_values = [float(r["got"]) for r in segment_list if r["got"] is not None and math.isfinite(float(r["got"]))]
            if not gop_values:
                gop = None
            elif self.gop_aggregation in {"gop_min", "min"}:
                gop = float(min(gop_values))
            else:
                # Exp03 threshold calibration specifies gop_mean.
                gop = float(np.mean(gop_values))
            got = float(np.mean(got_values)) if got_values else None
            gop_ok = gop is not None and gop >= self.gop_threshold
            got_ok = got is None or got >= self.got_threshold
            is_correct = bool(gop_ok and got_ok)
            if is_correct:
                passed_count += 1
            if gop is not None:
                gop_aggregate.append(gop)
            if got is not None:
                got_aggregate.append(got)
            syllable_results.append({
                "hanzi_index": int(syllable["hanzi_index"]),
                "hanzi": syllable["hanzi"], "pinyin": syllable["pinyin"],
                "gop": float(gop) if gop is not None else None,
                "got": float(got) if got is not None else None,
                "gop_status": "correct" if gop_ok else "incorrect",
                "got_status": "correct" if got is not None and got_ok else ("incorrect" if got is not None else "unavailable"),
                "status": "correct" if is_correct else "incorrect",
                "start_ms": min((r["start_ms"] for r in segment_list), default=None),
                "end_ms": max((r["end_ms"] for r in segment_list), default=None),
                "phone_scores": [
                    {"unit": r["unit"], "start_ms": r["start_ms"], "end_ms": r["end_ms"], "gop": r["gop"], "got": r["got"]}
                    for r in segment_list
                ],
            })

        score_percent = round(passed_count / len(syllable_results) * 100.0, 2)
        status = "correct" if passed_count == len(syllable_results) else "incorrect"
        return {
            "status": status,
            "score": score_percent,
            "correct_syllables": int(passed_count),
            "total_syllables": int(len(syllable_results)),
            "gop": float(np.mean(gop_aggregate)) if gop_aggregate else None,
            "got": float(np.mean(got_aggregate)) if got_aggregate else None,
            "thresholds": {"gop": self.gop_threshold, "got": self.got_threshold},
            "threshold_source": self.threshold_source,
            "gop_aggregation": self.gop_aggregation,
            "feature_dimension": self.input_dimension,
            "syllables": syllable_results,
 }
