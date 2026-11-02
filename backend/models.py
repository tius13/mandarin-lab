from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    TIMESTAMP,
    DATETIME,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Pengguna(Base):
    """Mapping tabel SQL: pengguna."""
    __tablename__ = "pengguna"

    id_pengguna: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    nama_pengguna: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    kata_sandi: Mapped[str] = mapped_column(String(255), nullable=False)
    waktu_dibuat: Mapped[object] = mapped_column(
        TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    riwayat: Mapped[list["RiwayatLatihan"]] = relationship(back_populates="pengguna")


class LevelLatihan(Base):
    """Mapping tabel SQL: level_latihan."""
    __tablename__ = "level_latihan"

    id_level: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    nama_level: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    kata_acuan: Mapped[list["KataAcuan"]] = relationship(back_populates="level")
    riwayat: Mapped[list["RiwayatLatihan"]] = relationship(back_populates="level")


class KataAcuan(Base):
    """Mapping tabel SQL: kata_acuan."""
    __tablename__ = "kata_acuan"
    __table_args__ = (
        UniqueConstraint("id_level", "hanzi", "pinyin", name="uq_kata_acuan_level_hanzi_pinyin"),
        Index("idx_kata_acuan_level", "id_level"),
    )

    id_kata: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    id_level: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("level_latihan.id_level", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    hanzi: Mapped[str] = mapped_column(String(500), nullable=False)
    pinyin: Mapped[str] = mapped_column(String(500), nullable=False)

    level: Mapped["LevelLatihan"] = relationship(back_populates="kata_acuan")


class RiwayatLatihan(Base):
    """Mapping tabel SQL: riwayat_latihan."""
    __tablename__ = "riwayat_latihan"
    __table_args__ = (
        CheckConstraint("skor_akhir >= 0 AND skor_akhir <= 100", name="chk_skor"),
    )

    id_riwayat: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    id_pengguna: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("pengguna.id_pengguna", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    id_level: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("level_latihan.id_level", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    waktu_latihan: Mapped[object] = mapped_column(
        DATETIME, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    skor_akhir: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    jumlah_tepat: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default=text("0"))
    jumlah_kurang_tepat: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default=text("0"))
    pengguna: Mapped["Pengguna"] = relationship(back_populates="riwayat")
    level: Mapped["LevelLatihan"] = relationship(back_populates="riwayat")
