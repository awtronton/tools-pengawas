# Existing Table Schema Update

Perubahan utama:

1. Tabel baru tetap menggunakan `Baris Header`.
2. Saat tabel baru pertama kali disimpan, mapping ordinal kolom sumber ke nama kolom database disimpan pada tabel internal `warehouse_schema_mapping`.
3. Tabel existing tidak lagi membaca header dari XLS/XLSX.
4. Untuk tabel existing user mengisi `Baris Pertama Data`.
5. Data existing dibaca dengan `header=None` lalu nama kolom diambil dari schema tabel yang sudah tersimpan.
6. `bank_id`, `bulan`, dan `tahun` tetap merupakan system columns.
7. Jumlah kolom sumber wajib sama dengan jumlah kolom bisnis pada schema existing. Jika berbeda, preview/save diblokir.
8. Tabel lama yang sudah ada tetapi belum mempunyai schema mapping akan di-bootstrap otomatis dari urutan kolom database existing.
9. Tabel internal `warehouse_schema_mapping` tidak ditampilkan pada dropdown tabel user.

Catatan:
- Existing table memakai urutan/ordinal kolom sebagai acuan.
- Jika template XLS resmi berubah urutan kolom tetapi jumlah kolom tetap sama, perubahan tersebut belum dapat dideteksi otomatis karena header file sengaja tidak digunakan pada existing upload.
- Perubahan schema resmi nantinya dikelola melalui Schema Manager/Table Explorer.
