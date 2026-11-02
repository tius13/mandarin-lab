## 1. Ringkasan proyek

Proyek ini terdiri dari:
- **Backend**: FastAPI, layanan scoring DNN-HMM/GOP/GOT, koneksi MySQL, autentikasi pengguna, dan endpoint API.
- **Frontend**: HTML, CSS, dan JavaScript untuk UI latihan Mandarin.
- **Model deployment**: checkpoint final, konfigurasi threshold, dan kamus Pinyin-ke-phone yang disiapkan oleh skrip.
- **Notebook penelitian**: pemeriksaan input, preprocessing, training, fine-tuning, kalibrasi/evaluasi, serta uji checkpoint yang sudah ada.
- **Checkpoint penelitian**: checkpoint per-round, checkpoint fine-tuning LATIC, state priors, vocabulary, dan status training.
```


## 2. Prasyarat

- Windows 10/11 dan PowerShell.
- Python **3.11 direkomendasikan** untuk kompatibilitas dependency audio/ML. Jika environment yang sudah ada berjalan dengan baik, jangan membuat ulang `.venv` tanpa kebutuhan.
- MySQL Server untuk fitur login, level latihan, dan riwayat.
- VS Code dengan ekstensi Python dan Jupyter jika ingin menjalankan notebook.
- Koneksi internet diperlukan oleh `gTTS` dan skrip persiapan untuk mengunduh kamus jika kamus belum tersedia.

## 3. Setup pertama kali

Buka folder `skripsii` di VS Code. Jalankan perintah berikut di terminal PowerShell pada folder root proyek.

###  Setup 

Gunakan Python 3.11 jika tersedia:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ipykernel install --user --name skripsi-capt --display-name "Python (Skripsi CAPT)"
```

Jika `.venv` sudah dibuat, lewati perintah pembuatan environment dan gunakan Python yang ada. Jangan menghapus `.venv` hanya untuk mengganti nama folder proyek.

### Siapkan file `.env`

Salin `.env.example` menjadi `.env`, lalu isi kredensial MySQL lokal:

```powershell
Copy-Item .env.example .env
```

Edit `.env` dan isi setidaknya `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, dan `DB_NAME`. Jangan membagikan `.env` yang berisi password.

## 4. Menyiapkan model deployment

Paket model sudah ditempatkan di:

```text
backend/model/mandarin_hybrid_dnn_hmm_final.pt
backend/model/thresholds.json
```

Kamus `pinyin2phone.tone.txt` dibutuhkan untuk memetakan Pinyin ke unit fonetik. File kamus tidak ada di ZIP yang diserahkan; skrip akan mencoba mengunduhnya ke folder model.

Jalankan:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_deployment.py
```

Periksa pesan `[OK]` untuk jumlah senone, unit, prior, MFCC, sample rate, threshold, dan kecocokan contoh `bān`. Jika unduhan kamus gagal, pastikan internet aktif atau tempatkan file kamus yang benar di `backend/model/pinyin2phone.tone.txt`.

Nilai threshold di `thresholds.json` disalin dari paket model; skrip tidak melakukan kalibrasi ulang. Jangan menganggap threshold tervalidasi secara ilmiah hanya karena file tersedia.

## 5. Menjalankan aplikasi frontend + backend

### 5.1 Siapkan database MySQL

Buat database `mandarin_pronunciation` di MySQL. Jalankan `sql/schema.sql` untuk membuat tabel. `sql/seed_demo.sql` dapat digunakan jika ingin mengisi data demo yang disediakan.

Pastikan kredensial di `.env` cocok dengan MySQL yang aktif.

### 5.2 Jalankan backend

Dari folder root `skripsi`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Jangan menjalankan perintah dari dalam folder `backend`; jalankan dari root agar `.env` dan path relatif konsisten.

### 5.3 Buka frontend

Buka:
- Aplikasi: http://127.0.0.1:8000/
- Dokumentasi API: http://127.0.0.1:8000/docs
- Status file model: http://127.0.0.1:8000/api/evaluate/health
- Status aplikasi/database: http://127.0.0.1:8000/health (memerlukan MySQL aktif)

Frontend disajikan oleh FastAPI dari folder `frontend/` melalui URL `/static/`; tidak perlu menjalankan server frontend terpisah.

Endpoint scoring utama adalah `POST /api/evaluate`, dengan field multipart `file` (WAV), `hanzi`, dan `pinyin`. Hasil health `ready` hanya berarti file model dan kamus ditemukan, bukan bahwa akurasi GOP/GOT sudah terbukti.

## 6. Memilih kernel notebook di VS Code

1. Buka folder root `skripsi` di VS Code.
2. Buka file notebook di `notebooks/`.
3. Klik **Select Kernel** di pojok kanan atas.
4. Pilih `Python (Skripsi CAPT)` atau interpreter:
   `skripsi\.venv\Scripts\python.exe`.
5. Jalankan cell dari atas ke bawah sesuai urutan notebook.

Jika kernel belum tersedia, jalankan kembali perintah `ipykernel install` dari bagian setup manual. Periksa interpreter di notebook dengan:

```python
import sys
print(sys.executable)
```

Path yang diharapkan berakhir dengan `skripsi\\.venv\\Scripts\\python.exe`.