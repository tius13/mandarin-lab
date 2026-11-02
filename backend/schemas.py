import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PenggunaRegister(BaseModel):
    nama_pengguna: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    kata_sandi: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Format email tidak valid")
        return value


class PenggunaLogin(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    kata_sandi: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PenggunaUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=5, max_length=255)
    kata_sandi: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_updated_email(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Format email tidak valid")
        return value


class PenggunaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_pengguna: int
    nama_pengguna: str
    email: str
    waktu_dibuat: datetime


class LevelLatihanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_level: int
    nama_level: str


class KataAcuanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_kata: int
    id_level: int
    hanzi: str
    pinyin: str


class RiwayatLatihanCreate(BaseModel):
    id_pengguna: int = Field(gt=0)
    id_level: int = Field(gt=0)
    skor_akhir: Decimal = Field(ge=Decimal("0"), le=Decimal("100"), max_digits=5, decimal_places=2)
    jumlah_tepat: int = Field(default=0, ge=0)
    jumlah_kurang_tepat: int = Field(default=0, ge=0)


class RiwayatLatihanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_riwayat: int
    id_pengguna: int
    id_level: int
    waktu_latihan: datetime
    skor_akhir: Decimal
    jumlah_tepat: int
    jumlah_kurang_tepat: int
