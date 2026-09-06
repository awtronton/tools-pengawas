# Dokumentasi Proyek Dashboard BPR / Data Warehouse

## 1. Ringkasan Proyek

Proyek ini merupakan aplikasi web berbasis **React.js + Vite** untuk frontend dan **FastAPI + Python/Pandas** untuk backend. Tujuan utamanya adalah membangun dashboard pengawasan dan data warehouse yang dapat:

- menerima unggahan data Excel (`.xls` / `.xlsx`);
- membaca struktur workbook dan sheet secara otomatis;
- membersihkan serta menormalkan data menjadi format yang siap disimpan ke database;
- menambahkan metadata periode berupa bulan dan tahun;
- menampilkan preview hasil cleaning sebelum data disimpan;
- memungkinkan pengguna menghapus baris yang tidak ingin disimpan;
- mendukung pembuatan tabel baru maupun penambahan data ke tabel yang sudah ada;
- menyediakan fondasi untuk Table Explorer, pengelolaan schema, visualisasi, perbandingan, detail BPR, serta laporan pengawasan.

Tampilan aplikasi mengikuti gaya dashboard referensi `dashboard-Kakegyn`, dengan sidebar gelap, aksen biru/merah, dan layout dashboard pengawasan.

---

## 2. Arsitektur Aplikasi

Arsitektur saat ini:

```text
Browser
  │
  │  http://localhost:5173
  ▼
React + Vite
Frontend
  │
  │ HTTP / FormData
  ▼
FastAPI
Backend Python
  │
  ├── membaca XLS/XLSX
  ├── mendeteksi sheet
  ├── cleaning dengan Pandas
  ├── normalisasi nama kolom
  ├── menambahkan metadata periode
  └── menghasilkan preview SQL-ready
  │
  ▼
Database
[belum diaktifkan pada tahap saat ini]
```

Target arsitektur berikutnya:

```text
React/Vite
    │
    ▼
FastAPI
    │
    ├── Pandas / Excel Processor
    │
    ▼
PostgreSQL / Supabase atau DB pilihan final
    │
    ├── Data Tables
    ├── Table Explorer
    ├── Schema Manager
    └── Data untuk Visualisasi
```

Backend Python dipilih agar logic cleaning Excel yang sebelumnya dibuat menggunakan Python/Streamlit dapat digunakan kembali dengan lebih mudah.

---

## 3. Teknologi yang Digunakan

### Frontend

- React.js
- Vite
- JavaScript
- Lucide React untuk ikon
- Utility CSS/Tailwind-style classes yang sudah aktif di project
- Fetch API untuk komunikasi ke FastAPI

### Backend

- Python
- FastAPI
- Uvicorn
- Pandas
- OpenPyXL
- xlrd
- python-multipart
- FastAPI CORS Middleware

### Database

Belum diaktifkan.

Rencana database akan diputuskan pada tahap penyimpanan data. Arsitektur saat ini disiapkan agar dapat menggunakan PostgreSQL/Supabase atau database relasional lain sesuai kebutuhan.

---

## 4. Struktur Folder Proyek

Workspace utama sebaiknya dibuka pada folder `versi react`, karena frontend dan backend berada sebagai sibling folder.

```text
versi react/
│
├── dashboard-bpr/
│   ├── node_modules/
│   ├── public/
│   │
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   ├── layouts/
│   │   │   └── DashboardLayout.jsx
│   │   ├── lib/
│   │   ├── pages/
│   │   │   └── UploadData.jsx
│   │   ├── services/
│   │   │   └── dataWarehouseService.js
│   │   ├── App.css
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   │
│   ├── .gitignore
│   ├── .oxlintrc.json
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── README.md
│   └── vite.config.js
│
├── backend/
│   ├── venv/
│   ├── main.py
│   │
│   └── services/
│       ├── __init__.py
│       └── excel_processor.py
│
└── PROJECT_STATUS.md
```

Folder dapat berkembang pada tahap berikutnya, khususnya ketika modul database, schema manager, dan visualisasi mulai ditambahkan.

---

## 5. Modul Frontend yang Sudah Dibuat

### 5.1 Dashboard Layout

Frontend sudah memiliki layout dashboard dengan:

- sidebar;
- header;
- navigasi modul;
- area konten utama;
- gaya visual yang mengikuti dashboard referensi.

Konsep menu yang sedang digunakan:

```text
MODULE PENGAWASAN
├── Dashboard Utama

DATA WAREHOUSE
├── Upload Data
├── Data Tables
├── Table Explorer
└── Schema Manager

ANALYSIS
├── Visualisasi
├── Perbandingan
└── Detail BPR

OUTPUT
├── Laporan Pengawasan
└── Dokumen
```

---

## 6. Modul Upload Data

Halaman `UploadData.jsx` merupakan modul yang saat ini paling berkembang.

### 6.1 Upload XLS/XLSX

Pengguna dapat:

- drag & drop file;
- klik area upload untuk memilih file;
- mengunggah `.xls`;
- mengunggah `.xlsx`.

Frontend melakukan validasi ekstensi file sebelum mengirimkannya ke backend.

---

### 6.2 Deteksi Sheet Otomatis

Setelah file dipilih:

1. frontend mengirim file ke endpoint:

```text
POST /excel/sheets
```

2. FastAPI membaca workbook;
3. backend mengembalikan daftar nama sheet;
4. frontend menampilkan sheet pada dropdown.

Dengan demikian nama sheet tidak perlu lagi ditulis manual.

---

### 6.3 Penentuan Tabel Tujuan

Terdapat dua mode:

#### Existing Table

Pengguna memilih tabel yang sudah tersedia.

Target perilaku:

- data baru akan di-append ke tabel;
- struktur kolom existing menjadi acuan;
- nama kolom tidak dapat diedit saat preview.

#### New Table

Pengguna dapat menentukan nama tabel baru.

Target perilaku:

- tabel akan dibuat ketika data disimpan;
- nama kolom hasil cleaning dapat diedit pada tahap preview;
- validasi nama kolom dilakukan sebelum database table dibuat.

---

## 7. Metadata Periode

Setiap proses upload memiliki:

- bulan;
- tahun.

Contoh:

```text
Bulan : Mei
Tahun : 2025
```

Backend menambahkan metadata periode tersebut ke hasil cleaning sehingga data yang masuk database nantinya memiliki informasi periode yang konsisten.

---

## 8. Struktur Excel

Pengguna dapat menentukan:

- nama sheet;
- baris header.

Contoh:

```text
Sheet       : LBBPRK-1300
Baris Header: 17
```

Baris header menggunakan perspektif pengguna Excel, yaitu baris pertama = `1`.

Processor backend bertanggung jawab mengkonversinya sesuai indexing yang dibutuhkan Pandas.

---

## 9. Excel Processor

`backend/services/excel_processor.py` bertanggung jawab terhadap pemrosesan Excel.

Fungsi utamanya mencakup:

- membaca workbook;
- mendapatkan daftar sheet;
- membaca sheet tertentu;
- menggunakan header row yang dipilih;
- menghapus row kosong;
- menghapus column kosong;
- membersihkan nama column;
- membuat nama column unik;
- membersihkan nilai;
- menangani tanggal;
- menangani nilai kosong/NaN;
- menambahkan bulan;
- menambahkan tahun;
- menghasilkan DataFrame SQL-ready.

Konsep normalisasi nama kolom:

```text
Nama Kolom Asli
"Nominal Yang Dibayar"

menjadi

nominal_yang_dibayar
```

Nama kolom diarahkan menggunakan format `snake_case`.

---

## 10. API Backend yang Sudah Tersedia

### Health Check

```text
GET /
```

Digunakan untuk memastikan API aktif.

Contoh response:

```json
{
  "status": "ok",
  "message": "OJK Data Warehouse API running"
}
```

---

### Deteksi Sheet

```text
POST /excel/sheets
```

Input:

```text
file
```

Output utama:

```json
{
  "filename": "1300_source.xls",
  "sheets": [
    "LBBPRK-1300"
  ]
}
```

---

### Preview Excel

```text
POST /excel/preview
```

Input:

```text
file
table_name
month
year
sheet_name
header_row
```

Response dikontrakkan dalam bentuk:

```json
{
  "filename": "...",
  "table_name": "...",
  "month": 5,
  "year": 2025,
  "sheet_name": "...",
  "header_row": 17,
  "row_count": 26,
  "column_count": 17,
  "columns": [],
  "preview": []
}
```

---

## 11. CORS

FastAPI telah dikonfigurasi agar dapat menerima request dari frontend Vite:

```text
http://localhost:5173
http://127.0.0.1:5173
```

Frontend saat ini menggunakan backend:

```text
http://127.0.0.1:8000
```

`dataWarehouseService.js` juga sudah disiapkan agar ke depan URL API dapat dipindahkan ke environment variable:

```text
VITE_API_URL
```

---

## 12. Preview SQL-Ready

Preview hasil cleaning sudah berhasil berjalan.

Informasi yang ditampilkan antara lain:

- nama file;
- nama tabel;
- jumlah row;
- jumlah column;
- sheet;
- periode;
- header row;
- hasil cleaning dalam tabel.

Contoh alur:

```text
1300_source.xls
      │
      ▼
LBBPRK-1300
Header row 17
      │
      ▼
Pandas Cleaning
      │
      ▼
26 baris
17 kolom
      │
      ▼
SQL-Ready Preview
```

---

## 13. Penghapusan Row pada Preview

Fitur penghapusan row sudah dirancang/dibuat agar pengguna dapat menghapus data yang tidak ingin disimpan.

Kemampuan yang direncanakan/diterapkan:

- memilih row;
- menghapus satu row;
- memilih beberapa row;
- menghapus beberapa row sekaligus;
- melihat jumlah row yang dihapus;
- memulihkan/reset deleted rows;
- pagination untuk dataset preview.

Konsep informasi:

```text
Data awal        : 26 row
Dihapus          :  3 row
Akan disimpan    : 23 row
```

Row menggunakan identifier sementara:

```text
__row_id
```

`__row_id` hanya digunakan untuk proses preview/editing dan tidak akan disimpan sebagai kolom database.

---

## 14. Aturan Edit Nama Kolom

Aturan yang telah disepakati:

| Mode | Delete Row | Edit Column Name |
|---|---:|---:|
| Existing Table | Ya | Tidak |
| New Table | Ya | Ya |

### Existing Table

Jika pengguna mengunggah data ke tabel yang sudah tersedia:

- nama kolom mengikuti schema database;
- column name tidak dapat diubah di preview;
- user hanya dapat melakukan filtering/penghapusan row sebelum append.

Jika nama kolom existing perlu diubah, perubahan akan dilakukan melalui:

```text
Table Explorer
→ Schema
→ Rename Column
```

### New Table

Jika user membuat tabel baru:

- nama kolom dapat disesuaikan sebelum tabel dibuat;
- kolom seperti `unnamed_22` dapat diubah menjadi nama yang sesuai;
- nama baru harus SQL-safe;
- nama kolom tidak boleh kosong;
- nama kolom tidak boleh duplikat;
- format yang disarankan adalah `snake_case`.

Contoh:

```text
unnamed_22
    ↓
tanggal_jatuh_tempo
```

---

## 15. Rencana Table Explorer

Table Explorer direncanakan sebagai modul untuk mengelola tabel yang sudah tersimpan.

Konsep:

```text
Table Explorer
│
├── Data
│   ├── Browse
│   ├── Filter
│   ├── Sort
│   └── Pagination
│
└── Schema
    ├── Column Name
    ├── Data Type
    ├── Nullable
    └── Rename Column
```

Rename existing column hanya dilakukan dari modul ini dan bukan dari Upload Preview.

---

## 16. Data Tables

Menu Data Tables nantinya menjadi katalog seluruh tabel di database.

Informasi yang dapat ditampilkan:

- table name;
- jumlah row;
- jumlah column;
- periode data;
- tanggal update;
- status;
- tombol buka Table Explorer.

---

## 17. Alur Data yang Disepakati

```text
                     UPLOAD EXCEL
                          │
                          ▼
                   DETECT SHEETS
                          │
                          ▼
                 SELECT STRUCTURE
                Sheet + Header Row
                          │
                          ▼
                  PANDAS CLEANING
                          │
                          ▼
                    SQL PREVIEW
                          │
             ┌────────────┴────────────┐
             │                         │
      EXISTING TABLE               NEW TABLE
             │                         │
      Column locked               Edit columns
             │                         │
        Delete rows                Delete rows
             │                         │
        Append rows                Create table
             │                         │
             └────────────┬────────────┘
                          │
                          ▼
                       DATABASE
                          │
             ┌────────────┴────────────┐
             │                         │
        DATA TABLES              TABLE EXPLORER
                                       │
                                Schema management
                                       │
                                Rename columns
```

---

## 18. Status Implementasi

### Sudah Berfungsi

- React + Vite frontend
- Dashboard layout
- Data Warehouse menu
- Upload `.xls`
- Upload `.xlsx`
- Drag & drop
- FastAPI backend
- CORS frontend/backend
- Excel sheet detection
- Sheet dropdown otomatis
- Pemilihan header row
- Pemilihan bulan
- Pemilihan tahun
- Pemilihan target table
- Existing/new table mode
- Pandas Excel cleaning
- SQL-ready preview
- Row count
- Column count
- Preview tabel
- Dasar penghapusan row preview
- Dasar edit nama kolom untuk new table

### Belum Diaktifkan

- database persistence;
- create table database;
- append existing table;
- duplicate period protection;
- schema compatibility validation;
- Data Tables dari database;
- Table Explorer;
- rename existing DB column;
- Schema Manager;
- dashboard visualisasi dari database;
- laporan;
- authentication/authorization.

---

## 19. Tahap Berikutnya

Prioritas pengembangan berikutnya:

### Tahap 1 — Database Persistence

Membuat koneksi database dan endpoint:

```text
POST /excel/save
```

Fungsi:

- membuat tabel baru;
- append ke tabel existing;
- menyimpan row yang sudah lolos preview;
- mengabaikan deleted rows;
- menggunakan edited column names untuk new table;
- validasi schema existing table.

### Tahap 2 — Duplicate Protection

Sebelum append:

```text
table_name + bulan + tahun
```

diperiksa agar data periode yang sama tidak masuk dua kali tanpa konfirmasi.

### Tahap 3 — Data Tables

Menampilkan katalog seluruh tabel database.

### Tahap 4 — Table Explorer

Menampilkan data dan schema tabel serta menyediakan rename existing column.

### Tahap 5 — Visualisasi

Membaca tabel database dan membuat grafik/dashboard dinamis.

---

## 20. Cara Menjalankan Project

### Backend

Buka terminal:

```bash
cd backend
source venv/bin/activate
python -m uvicorn main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

### Frontend

Buka terminal kedua:

```bash
cd dashboard-bpr
npm run dev
```

Frontend:

```text
http://localhost:5173
```

---

## 21. Catatan Git dan GitHub

Direkomendasikan melakukan version control dari folder:

```text
versi react/
```

dan bukan hanya dari `dashboard-bpr/`, karena frontend dan backend harus berada dalam repository yang sama.

Folder/files lokal yang tidak seharusnya masuk Git antara lain:

```text
dashboard-bpr/node_modules/
dashboard-bpr/dist/
backend/venv/
backend/__pycache__/
*.pyc
.env
.env.*
.DS_Store
```

Untuk proyek pengawasan/data warehouse, file data mentah juga sebaiknya tidak masuk repository:

```text
*.xls
*.xlsx
*.csv
uploads/
data/
```

Jika suatu saat diperlukan sample data untuk pengembangan, gunakan data dummy yang telah dipastikan aman dan simpan pada folder terpisah.

---

## 22. Convention Commit yang Disarankan

Contoh:

```text
feat: add excel upload and preview
feat: add row deletion in upload preview
feat: allow column rename for new tables
fix: resolve frontend backend cors
fix: normalize preview response
refactor: clean upload data state handling
docs: add project documentation
```

Format ini akan memudahkan riwayat perkembangan project untuk dibaca di GitHub.

---

## 23. Posisi Proyek Saat Dokumen Ini Dibuat

Pada tahap ini pipeline utama berikut telah berhasil:

```text
Excel
  → React Upload
  → FastAPI
  → Pandas Cleaning
  → SQL-Ready Preview
```

Fokus pengembangan berikutnya adalah:

```text
SQL-Ready Preview
  → Validation
  → Save/Create/Append
  → Database
  → Data Tables
  → Table Explorer
  → Visualization
```

Dokumen ini dapat diperbarui setiap kali terdapat milestone baru agar perubahan arsitektur dan fungsi project tetap terdokumentasi.
