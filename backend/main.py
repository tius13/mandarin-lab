from io import BytesIO
import logging
import os
import re
from pathlib import Path
import tempfile
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import get_db
from .models import KataAcuan, LevelLatihan, Pengguna, RiwayatLatihan
from .schemas import (
    KataAcuanOut,
    LevelLatihanOut,
    PenggunaLogin,
    PenggunaOut,
    PenggunaRegister,
    RiwayatLatihanCreate,
    RiwayatLatihanOut,
)

app = FastAPI(
    title="Backend Mandarin Pronunciation",
    description="REST API Python yang terhubung ke database MySQL mandarin_pronunciation.",
    version="1.0.0",
)

# 2. TAMBAHAN: Konfigurasi CORS Middleware agar FastAPI menerima request dari Ngrok/Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mengizinkan semua domain luar agar testing skripsi lancar
    allow_credentials=True,
    allow_methods=["*"],  # Mengizinkan GET, POST, PUT, DELETE, dll
    allow_headers=["ngrok-skip-browser-warning", "*"],  # Mengizinkan header bypass proteksi Ngrok
)

DbSession = Annotated[Session, Depends(get_db)]

PROJECT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = PROJECT_DIR / "frontend"
logger = logging.getLogger("mandarin_lab")


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class EmailUpdateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Format email tidak valid")
        return value


class DirectPasswordResetRequest(BaseModel):
    """Permintaan reset lokal melalui email terdaftar dan password baru.

    Email saja bukan bukti kepemilikan akun. Endpoint ini hanya untuk demo lokal.
    """
    email: str = Field(min_length=5, max_length=255)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Format email tidak valid")
        return value


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.get("/", tags=["Frontend"], include_in_schema=False)
def root():
    """Serve the single-page frontend from the same FastAPI origin."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Hilangkan request 404 ikon tab jika belum ada favicon khusus.
    return Response(status_code=204)


@app.get("/health", tags=["Status"])
def health(db: DbSession):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected", "name": "mandarin_pronunciation"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database MySQL tidak dapat dihubungi. Periksa .env dan server MySQL.") from exc


# -------------------- PENGGUNA --------------------
@app.post("/api/pengguna/register", response_model=PenggunaOut, status_code=status.HTTP_201_CREATED, tags=["Pengguna"])
def register(data: PenggunaRegister, db: DbSession):
    email = data.email
    existing = db.scalar(select(Pengguna).where(Pengguna.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah terdaftar")

    pengguna = Pengguna(
        nama_pengguna=data.nama_pengguna,
        email=email,
        kata_sandi=data.kata_sandi,  # plaintext: hanya untuk demo lokal
    )
    db.add(pengguna)
    try:
        db.commit()
        db.refresh(pengguna)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email sudah terdaftar") from exc
    return pengguna


@app.post("/api/pengguna/login", tags=["Pengguna"])
def login(data: PenggunaLogin, db: DbSession):
    pengguna = db.scalar(select(Pengguna).where(func.lower(Pengguna.email) == data.email))
    if not pengguna or data.kata_sandi != pengguna.kata_sandi:
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")

    return {
        "message": "Login berhasil",
        "pengguna": PenggunaOut.model_validate(pengguna),
    }


@app.get("/api/pengguna/{id_pengguna}", response_model=PenggunaOut, tags=["Pengguna"])
def get_pengguna(id_pengguna: int, db: DbSession):
    pengguna = db.get(Pengguna, id_pengguna)
    if not pengguna:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    return pengguna


@app.put("/api/pengguna/{id_pengguna}/email", tags=["Pengguna"])
def update_pengguna_email(id_pengguna: int, data: EmailUpdateRequest, db: DbSession):
    """Perbarui email pada satu-satunya tabel akun: pengguna."""
    pengguna = db.get(Pengguna, id_pengguna)
    if not pengguna:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    existing = db.scalar(
        select(Pengguna).where(
            func.lower(Pengguna.email) == data.email,
            Pengguna.id_pengguna != id_pengguna,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email sudah digunakan akun lain")

    pengguna.email = data.email
    try:
        db.commit()
        db.refresh(pengguna)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email sudah digunakan akun lain") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Gagal memperbarui email pengguna %s", id_pengguna)
        if os.getenv("APP_ENV", "development").strip().lower() != "production":
            detail = f"Email gagal diperbarui: {getattr(exc, 'orig', exc)}"
        else:
            detail = "Email gagal diperbarui karena kesalahan database. Periksa log server."
        raise HTTPException(status_code=500, detail=detail) from exc

    return {
        "message": "Email berhasil diperbarui",
        "pengguna": PenggunaOut.model_validate(pengguna),
    }


@app.post("/api/pengguna/{id_pengguna}/ubah-password", tags=["Pengguna"])
def change_password(id_pengguna: int, data: PasswordChangeRequest, db: DbSession):
    """Ubah password akun yang sedang digunakan (mode demo lokal)."""
    pengguna = db.get(Pengguna, id_pengguna)
    if not pengguna:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if data.current_password != pengguna.kata_sandi:
        raise HTTPException(status_code=400, detail="Password saat ini tidak sesuai")

    pengguna.kata_sandi = data.new_password
    try:
        db.commit()
        db.refresh(pengguna)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Gagal memperbarui password pengguna %s", id_pengguna)
        if os.getenv("APP_ENV", "development").strip().lower() != "production":
            detail = f"Password gagal diperbarui: {getattr(exc, 'orig', exc)}"
        else:
            detail = "Password gagal diperbarui karena kesalahan database. Periksa log server."
        raise HTTPException(status_code=500, detail=detail) from exc

    return {"message": "Password berhasil diperbarui"}


@app.post("/api/pengguna/reset-password-by-email", tags=["Pengguna"])
def reset_password_by_email(data: DirectPasswordResetRequest, db: DbSession):
    """Ubah password dengan mencocokkan email (mode demo lokal)."""
    pengguna = db.scalar(select(Pengguna).where(func.lower(Pengguna.email) == data.email))
    if not pengguna:
        raise HTTPException(
            status_code=404,
            detail="Email tidak ditemukan. Periksa email akun.",
        )

    pengguna.kata_sandi = data.new_password
    try:
        db.commit()
        db.refresh(pengguna)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Gagal memperbarui password melalui email")
        raise HTTPException(
            status_code=500,
            detail="Password gagal diperbarui",
        ) from exc

    return {"message": "Password berhasil diubah. Silakan login kembali."}


@app.post("/api/tts", tags=["Audio"], response_class=StreamingResponse)
def text_to_speech(data: TTSRequest):
    """Return Mandarin sample speech as an in-memory MP3 stream (gTTS needs internet)."""
    try:
        from gtts import gTTS
        audio_buffer = BytesIO()
        gTTS(text=data.text, lang="zh-cn").write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        return StreamingResponse(
            audio_buffer,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=mandarin-sample.mp3", "Cache-Control": "no-store"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Layanan TTS tidak dapat dihubungi. Periksa koneksi internet atau gunakan fallback suara browser.",
        ) from exc




# -------------------- EVALUASI AUDIO DNN-HMM + GOP/GOT --------------------
_pronunciation_scorer = None


def _get_pronunciation_scorer():
    """Load the trained model lazily so the rest of the application can start without model weights."""
    global _pronunciation_scorer
    if _pronunciation_scorer is None:
        from .pronunciation_service import PronunciationService
        model_dir = Path(os.getenv("CAPT_MODEL_DIR", str(Path(__file__).resolve().parent / "model")))
        model_path = Path(os.getenv("CAPT_MODEL_PATH", str(model_dir / "mandarin_hybrid_dnn_hmm_final.pt")))
        lexicon_path = Path(os.getenv("CAPT_PINYIN_LEXICON_PATH", str(model_dir / "pinyin2phone.tone.txt")))
        thresholds_path = Path(os.getenv("CAPT_THRESHOLDS_PATH", str(model_dir / "thresholds.json")))
        _pronunciation_scorer = PronunciationService(model_path, lexicon_path, thresholds_path)
    return _pronunciation_scorer


@app.get("/api/evaluate/health", tags=["Evaluasi Model"])
def evaluate_model_health():
    """Check whether deployment files exist; does not claim that quality is validated."""
    model_dir = Path(os.getenv("CAPT_MODEL_DIR", str(Path(__file__).resolve().parent / "model")))
    model_path = Path(os.getenv("CAPT_MODEL_PATH", str(model_dir / "mandarin_hybrid_dnn_hmm_final.pt")))
    lexicon_path = Path(os.getenv("CAPT_PINYIN_LEXICON_PATH", str(model_dir / "pinyin2phone.tone.txt")))
    ready = model_path.is_file() and lexicon_path.is_file()
    return {
        "status": "ready" if ready else "model_artifacts_missing",
        "model_package_found": model_path.is_file(),
        "pinyin_lexicon_found": lexicon_path.is_file(),
        "model_package_path": str(model_path),
        "note": "Kesiapan file tidak sama dengan validasi akurasi model.",
    }


@app.post("/api/evaluate", tags=["Evaluasi Model"])
async def evaluate_pronunciation_audio(
    file: UploadFile = File(...),
    hanzi: str = Form(..., min_length=1, max_length=100),
    pinyin: str = Form(..., min_length=1, max_length=300),
):
    """Evaluate a single recorded WAV against reference Hanzi/Pinyin using the trained DNN-HMM + GOP/GOT bundle."""
    filename = (file.filename or "recording.wav").lower()
    if not filename.endswith(".wav"):
        raise HTTPException(status_code=415, detail="Audio harus dikirim sebagai file WAV PCM.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File audio kosong.")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ukuran audio maksimal 15 MB.")

    tmp_path = None
    try:
        try:
            scorer = _get_pronunciation_scorer()
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="Dependensi ML belum terpasang. Jalankan pip install -r requirements-ml.txt.") from exc
        except Exception as exc:
            logger.exception("Model GOP/GOT belum siap")
            message = str(exc) if isinstance(exc, (FileNotFoundError, RuntimeError, ValueError)) else "Model belum siap. Periksa artefak deployment."
            raise HTTPException(status_code=503, detail=message) from exc

        with tempfile.NamedTemporaryFile(prefix="mandarin_eval_", suffix=".wav", delete=False) as handle:
            handle.write(raw)
            tmp_path = Path(handle.name)
        result = scorer.score(tmp_path, hanzi, pinyin)
        return result
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Evaluasi audio gagal")
        raise HTTPException(status_code=500, detail="Evaluasi audio gagal. Periksa log backend untuk detail teknis.") from exc
    finally:
        try:
            await file.close()
        except Exception:
            pass
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Temporary audio tidak bisa dihapus: %s", tmp_path)


# -------------------- LEVEL LATIHAN --------------------
@app.get("/api/level-latihan", response_model=list[LevelLatihanOut], tags=["Level Latihan"])
def list_level(db: DbSession):
    return list(db.scalars(select(LevelLatihan).order_by(LevelLatihan.id_level)).all())


@app.get("/api/level-latihan/{id_level}", response_model=LevelLatihanOut, tags=["Level Latihan"])
def get_level(id_level: int, db: DbSession):
    level = db.get(LevelLatihan, id_level)
    if not level:
        raise HTTPException(status_code=404, detail="Level latihan tidak ditemukan")
    return level


# -------------------- KATA ACUAN --------------------
@app.get("/api/kata-acuan", response_model=list[KataAcuanOut], tags=["Kata Acuan"])
def list_kata_acuan(
    db: DbSession,
    id_level: int | None = Query(default=None, gt=0),
    q: str | None = Query(default=None, max_length=200, description="Cari berdasarkan Hanzi atau Pinyin"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(KataAcuan)
    if id_level is not None:
        stmt = stmt.where(KataAcuan.id_level == id_level)
    if q and q.strip():
        keyword = f"%{q.strip()}%"
        stmt = stmt.where(or_(KataAcuan.hanzi.like(keyword), KataAcuan.pinyin.like(keyword)))
    stmt = stmt.order_by(KataAcuan.id_kata).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@app.get("/api/kata-acuan/acak/{id_level}", response_model=list[KataAcuanOut], tags=["Kata Acuan"])
def random_kata_acuan(
    id_level: int,
    db: DbSession,
    jumlah: int = Query(default=10, ge=1, le=100),
):
    if not db.get(LevelLatihan, id_level):
        raise HTTPException(status_code=404, detail="Level latihan tidak ditemukan")
    stmt = (
        select(KataAcuan)
        .where(KataAcuan.id_level == id_level)
        .order_by(func.rand())
        .limit(jumlah)
    )
    return list(db.scalars(stmt).all())


@app.get("/api/kata-acuan/{id_kata}", response_model=KataAcuanOut, tags=["Kata Acuan"])
def get_kata_acuan(id_kata: int, db: DbSession):
    kata = db.get(KataAcuan, id_kata)
    if not kata:
        raise HTTPException(status_code=404, detail="Kata acuan tidak ditemukan")
    return kata


# -------------------- RIWAYAT LATIHAN --------------------
@app.post(
    "/api/riwayat-latihan",
    response_model=RiwayatLatihanOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Riwayat Latihan"],
)
def create_riwayat(data: RiwayatLatihanCreate, db: DbSession):
    """Simpan satu ringkasan sesi latihan dan kembalikan baris yang sudah tersimpan."""
    # Validasi tambahan sebelum membaca/menulis tabel relasional.
    score = data.skor_akhir
    if score < 0 or score > 100:
        raise HTTPException(status_code=422, detail="Skor harus berada pada rentang 0 sampai 100")
    if data.jumlah_tepat < 0 or data.jumlah_kurang_tepat < 0:
        raise HTTPException(status_code=422, detail="Jumlah jawaban tidak boleh negatif")

    riwayat = RiwayatLatihan(
        id_pengguna=data.id_pengguna,
        id_level=data.id_level,
        skor_akhir=score,
        jumlah_tepat=data.jumlah_tepat,
        jumlah_kurang_tepat=data.jumlah_kurang_tepat,
    )
    try:
        pengguna = db.get(Pengguna, data.id_pengguna)
        if not pengguna:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

        level = db.get(LevelLatihan, data.id_level)
        if not level:
            raise HTTPException(status_code=404, detail="Level latihan tidak ditemukan")

        db.add(riwayat)
        db.flush()
        db.commit()
        db.refresh(riwayat)
        return riwayat
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Constraint database menolak riwayat latihan")
        raise HTTPException(
            status_code=400,
            detail="Database menolak riwayat. Periksa ID pengguna, ID level, dan struktur tabel riwayat_latihan.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Gagal menyimpan riwayat latihan")
        # Dalam mode lokal tampilkan penyebab DB yang spesifik; jangan tampilkan di production.
        if os.getenv("APP_ENV", "development").strip().lower() != "production":
            db_message = str(getattr(exc, "orig", exc))
            detail = f"Gagal menyimpan riwayat latihan: {db_message}"
        else:
            detail = "Gagal menyimpan riwayat latihan karena kesalahan database. Periksa log server."
        raise HTTPException(status_code=500, detail=detail) from exc


@app.get("/api/riwayat-latihan/pengguna/{id_pengguna}", response_model=list[RiwayatLatihanOut], tags=["Riwayat Latihan"])
def list_riwayat_pengguna(
    id_pengguna: int,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    if not db.get(Pengguna, id_pengguna):
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    stmt = (
        select(RiwayatLatihan)
        .where(RiwayatLatihan.id_pengguna == id_pengguna)
        .order_by(RiwayatLatihan.waktu_latihan.desc(), RiwayatLatihan.id_riwayat.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@app.get("/api/riwayat-latihan/{id_riwayat}", response_model=RiwayatLatihanOut, tags=["Riwayat Latihan"])
def get_riwayat(id_riwayat: int, db: DbSession):
    riwayat = db.get(RiwayatLatihan, id_riwayat)
    if not riwayat:
        raise HTTPException(status_code=404, detail="Riwayat latihan tidak ditemukan")
    return riwayat


# UI assets use the same origin as the API, so local development does not require CORS.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
