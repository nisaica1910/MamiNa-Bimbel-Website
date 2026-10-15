# Rumah Warna – Website Bimbel Mewarnai (Flask + Firebase)

## Jalankan
```
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```
Buka http://127.0.0.1:5001. Tanpa kredensial Firebase, app jalan di **mode demo** (data di memori, hilang saat restart).

## Hubungkan Firebase
1. console.firebase.google.com → buat project.
2. Build → **Firestore Database** → Create database.
3. Build → **Storage** → Get started (untuk foto karya). Salin nama bucket ke `FIREBASE_BUCKET`.
4. Project settings → Service accounts → **Generate new private key**. Simpan sebagai `serviceAccountKey.json` di folder ini (sudah di .gitignore, jangan di-commit).
5. Isi `.env`, jalankan ulang. Koleksi Firestore dibuat otomatis: classes, students, registrations, attendance, payments, artworks.

## Sesuaikan
Nama bimbel, nomor WA, alamat, testimoni: `config.py`. Warna: variabel di atas `static/style.css`.

## Deploy
PythonAnywhere / Render / Railway. Pakai `gunicorn app:app`, set env var yang sama.
