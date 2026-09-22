import os
import json
from pathlib import Path
from multiprocessing import Pool, cpu_count
from PIL import Image, ImageOps
import imagehash
import rawpy
import io

# ==========================================
# 1. KONFIGURASI FOLDER & VARIABEL
# ==========================================
# Folder target tempat foto RAW berada
SOURCE_DIR = Path(r"E:\PROJECT\WEDDING\DILA & FAKHRI\P\AJAR")

# Mendapatkan lokasi folder tempat skrip ini (kodingan) disimpan
CURRENT_DIR = Path(__file__).parent

# Mengarahkan file hasil agar disimpan di folder kodingan
DUPLICATES_JSON = CURRENT_DIR / "duplicates.json"
REVIEW_ORDER_JSON = CURRENT_DIR / "review_order.json"

class UnionFind:
    """Struktur data Union-Find untuk mengelompokkan duplikat."""
    def __init__(self, elements):
        self.parent = {el: el for el in elements}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]] # path compression
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)

# ==========================================
# 2. EKSTRAKSI HASH DAN EXIF TIMESTAMP
# ==========================================
def process_photo(path_str):
    """
    Membaca foto menggunakan worker pool.
    Mengembalikan: (nama_file, nilai_dhash, timestamp_waktu)
    """
    path = Path(path_str)
    timestamp = str(os.path.getmtime(path)) # Fallback waktu file jika EXIF gagal
    h = None

    try:
        # Penanganan RAW
        if path.suffix.lower() in {".cr2", ".arw", ".nef", ".dng"}:
            with rawpy.imread(str(path)) as raw:
                try:
                    thumb = raw.extract_thumb()
                    img = Image.open(io.BytesIO(thumb.data))
                except Exception:
                    img = Image.fromarray(raw.postprocess(half_size=True))
        else:
            # Penanganan JPG/PNG biasa
            img = Image.open(path)
            
        # Ekstrak waktu asli dari EXIF (Tag 36867 = DateTimeOriginal)
        exif = img.getexif()
        if exif and 36867 in exif:
            timestamp = str(exif[36867])

        # Perbaiki rotasi dan buat dhash
        img = ImageOps.exif_transpose(img)
        h = imagehash.dhash(img)
        img.close()
        
        return (path.name, h, timestamp)
    
    except Exception as e:
        print(f"Gagal memproses {path.name}: {e}")
        return (path.name, None, timestamp)

# ==========================================
# 3. PROSES UTAMA (PHASE 1)
# ==========================================
if __name__ == "__main__":
    valid_exts = {".jpg", ".jpeg", ".png", ".cr2", ".arw", ".nef", ".dng"}
    photo_paths = [str(p) for p in SOURCE_DIR.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
    
    print(f"Memulai Phase 1: Pre-filter pada {len(photo_paths)} foto...")

    # A. Jalur Paralel: Perceptual Hashing & Pembacaan EXIF Timestamp
    hashes = {}
    timestamps = {}
    
    print(f"Menghitung dhash menggunakan {cpu_count()} CPU cores paralel...")
    with Pool(cpu_count()) as pool:
        for name, h, ts in pool.imap_unordered(process_photo, photo_paths):
            if h is not None:
                hashes[name] = h
            timestamps[name] = ts

    photos = list(hashes.keys())
    uf = UnionFind(photos)

    print("Mengelompokkan duplikat dengan Union-Find (Hamming distance <= 6)...")
    # B. Union-Find Grouping (O(n²))
    for i in range(len(photos)):
        for j in range(i + 1, len(photos)):
            if hashes[photos[i]] - hashes[photos[j]] <= 6:
                uf.union(photos[i], photos[j])

    # C. Membuat format output duplicates.json
    groups_dict = {}
    for name in photos:
        root = uf.find(name)
        if root not in groups_dict:
            groups_dict[root] = []
        groups_dict[root].append(name)

    # Hanya ambil grup yang berisi 2 foto atau lebih
    duplicate_groups = [group for group in groups_dict.values() if len(group) > 1]
    
    # Simpan duplicates.json
    with open(DUPLICATES_JSON, "w") as f:
        json.dump(duplicate_groups, f, indent=2)
    print(f"Tersimpan: {DUPLICATES_JSON} ({len(duplicate_groups)} groups)")

    # D. EXIF Timestamp Sort (Kronologis)
    print("Menyusun urutan ulasan (chronological, dupes consecutive)...")
    # Urutkan semua nama foto berdasarkan timestamp EXIF-nya secara alfabet/numerik
    time_sorted_photos = sorted(photos, key=lambda x: timestamps.get(x, ""))

    # Peta bantuan untuk mengetahui anggota grup dari sebuah file
    photo_to_group = {}
    for group in duplicate_groups:
        for photo in group:
            photo_to_group[photo] = group

    # E. Menyusun Review Order (Dupes consecutive)
    review_order = []
    visited = set()

    for photo in time_sorted_photos:
        if photo not in visited:
            if photo in photo_to_group:
                # Jika foto memiliki grup duplikat, masukkan semua anggotanya sekaligus agar berurutan
                group_members = photo_to_group[photo]
                # Urutkan anggota grup berdasarkan waktu juga agar internal grup terurut
                sorted_members = sorted(group_members, key=lambda x: timestamps.get(x, ""))
                for member in sorted_members:
                    if member not in visited:
                        review_order.append(member)
                        visited.add(member)
            else:
                # Foto tunggal tanpa duplikat
                review_order.append(photo)
                visited.add(photo)

    # Simpan review_order.json
    with open(REVIEW_ORDER_JSON, "w") as f:
        json.dump(review_order, f, indent=2)
    print(f"Tersimpan: {REVIEW_ORDER_JSON} (total {len(review_order)} foto diurutkan)")
    
    print("\nPhase 1 Selesai! Arsitektur pada diagram berhasil dieksekusi.")