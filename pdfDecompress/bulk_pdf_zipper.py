import csv
import hashlib
import re
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path


def ask_yes_no(prompt):
    while True:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no", ""):
            return False
        print("Error, responder y o n.")


def ask_folder():
    while True:
        raw = input("ruta con los archivos (Enter = este directorio): ").strip()
        path = Path(raw) if raw else Path.cwd()
        if not path.exists():
            print(f"  carpeta No exite: {path}")
            continue
        if not path.is_dir():
            print(f"  No es una carpeta: {path}")
            continue
        return path


def file_sha256(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def transform_name(filename):
    stem = filename.stem
    if "_" in stem:
        stem = stem.split("_", 1)[0]
    cleaned = re.sub(r"[^A-Za-z0-9]", "", stem)
    if not cleaned:
        cleaned = filename.stem
    return cleaned + filename.suffix.lower()


def unique_name(base, target_dir):
    candidate = target_dir / base
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    ext = candidate.suffix
    n = 1
    while True:
        candidate = target_dir / f"{stem}_{n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def extract_zips(source_dir, extracted_dir):
    zips = sorted(p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".zip")
    if not zips:
        print("No se encontraron .zip en la carpeta.")
        return None

    print(f"\nencontrado: {len(zips)} zips:")
    for z in zips:
        print(f"  - {z.name}")

    if not ask_yes_no(f"Extraer {len(zips)} archivo(s)?"):
        print("Aborted.")
        return None

    if extracted_dir.exists():
        if not ask_yes_no(f"  Folder {extracted_dir} existe por ejecucion previa. Usar/sobreescribir?"):
            print("Aborted.")
            return None
        for item in extracted_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    extracted_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for z in zips:
        target = extracted_dir / z.stem
        target.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(z) as archive:
                archive.extractall(target)
            ok += 1
            print(f"  Extracted: {z.name}")
        except zipfile.BadZipFile:
            print(f"  Saltado (zip no valido): {z.name}")
        except Exception as exc:
            print(f"  ERROR extrayendo {z.name}: {exc}")
    print(f"Extraido {ok}/{len(zips)} archivo(s) en {extracted_dir}")
    return ok


def collect_pdfs(extracted_dir, collected_dir):
    collected_dir.mkdir(parents=True, exist_ok=True)
    moves = 0
    duplicates = 0
    hash_duplicates = 0
    skipped = 0
    seen_hashes = set()

    pdflist = sorted(p for p in extracted_dir.rglob("*.pdf") if p.is_file())
    
    for pdf in pdflist:
        content_hash = file_sha256(pdf)
        if content_hash in seen_hashes:
            pdf.unlink()
            hash_duplicates += 1
            print(f"  DUPLICADO (eliminado): {pdf}")
            continue
        seen_hashes.add(content_hash)
        base = transform_name(pdf)
        dest = unique_name(base, collected_dir)
        if dest.name != base:
            duplicates += 1
        shutil.move(str(pdf), str(dest))
        moves += 1
    for other in sorted(p for p in extracted_dir.rglob("*") if p.is_file() and p.suffix.lower() != ".pdf"):
        skipped += 1
        print(f"  IGNORADO (not PDF): {other}")
    print(
        f"Movido {moves} PDF(s) en {collected_dir} ({duplicates} colisione(s) renombradas, "
        f"{skipped} non-PDF file(s) skipped, {hash_duplicates} duplicate(s) de contenido eliminados)."
    )
    return moves


def write_manifest(collected_dir, source_dir):
    files = sorted(p.name for p in collected_dir.iterdir() if p.is_file())
    out = source_dir / "manifest.csv"
    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        for name in files:
            writer.writerow([name])
    return out, len(files)


def make_single_zip(collected_dir, source_dir):
    files = sorted(p for p in collected_dir.iterdir() if p.is_file())
    if not files:
        print("No PDFs to zip.")
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = source_dir / f"merged_pdfs_{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for f in files:
            archive.write(f, arcname=f.name)
    return out


def main():
    print("=== Bulk PDF zipper ===")
    source_dir = ask_folder()
    extracted_dir = source_dir / "extracted"
    collected_dir = source_dir / "collected"

    if extract_zips(source_dir, extracted_dir) is None:
        sys.exit(1)

    if collect_pdfs(extracted_dir, collected_dir) == 0:
        print("No PDFs were found inside the archives.")
        sys.exit(1)

    manifest, manifest_count = write_manifest(collected_dir, source_dir)

    out_zip = make_single_zip(collected_dir, source_dir)
    if out_zip is None:
        sys.exit(1)

    print(f"\nDone. Final archive: {out_zip}")
    print(f"  Files collected in: {collected_dir}")
    print(f"  Manifest ({manifest_count} filename(s)): {manifest}")
    print("  Intermediate folders were kept (no cleanup performed).")


if __name__ == "__main__":
    main()