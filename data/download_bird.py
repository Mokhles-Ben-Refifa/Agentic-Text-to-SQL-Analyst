"""Downloader and unpacker for the official BIRD Dev benchmark dataset (~1.5 GB uncompressed)."""
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.request
import zipfile

BIRD_DEV_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
TARGET_DIR = Path(__file__).resolve().parent / "benchmarks" / "bird"


def download_with_progress(url: str, output_path: Path):
    """Downloads a file with clean MB progress reporting."""
    print(f"Downloading BIRD Dev dataset from:\n  {url}")
    print(f"Saving to:\n  {output_path}")

    start_time = time.time()

    def report_hook(count, block_size, total_size):
        downloaded = count * block_size
        elapsed = time.time() - start_time
        speed = (downloaded / (1024 * 1024)) / max(elapsed, 0.001)

        if total_size > 0:
            percent = int(downloaded * 100 / total_size)
            sys.stdout.write(
                f"\rProgress: {percent:3d}% | "
                f"{downloaded / (1024 * 1024):6.1f} / {total_size / (1024 * 1024):6.1f} MB | "
                f"Speed: {speed:4.1f} MB/s"
            )
        else:
            sys.stdout.write(f"\rDownloaded: {downloaded / (1024 * 1024):6.1f} MB | Speed: {speed:4.1f} MB/s")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, output_path, reporthook=report_hook)
    print("\nDownload completed successfully!")


def extract_and_organize(zip_path: Path, target_dir: Path):
    """Extracts the archive and organizes databases and dev.json."""
    print(f"Extracting {zip_path.name} to {target_dir}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(target_dir)

    print("Archive extracted. Checking extracted structure...")

    # Look for dev_databases or dev.json
    extracted_db_folder = None
    for root, dirs, _ in os.walk(target_dir):
        if "financial" in dirs:
            extracted_db_folder = Path(root) / "financial"
            break

    if extracted_db_folder and extracted_db_folder.exists():
        src_sqlite = extracted_db_folder / "financial.sqlite"
        dest_sqlite = target_dir / "financial" / "financial.sqlite"
        if src_sqlite.exists() and src_sqlite != dest_sqlite:
            target_dir.joinpath("financial").mkdir(parents=True, exist_ok=True)
            print(f"Moving official financial.sqlite ({src_sqlite.stat().st_size / (1024*1024):.1f} MB) to {dest_sqlite}...")
            shutil.copy2(src_sqlite, dest_sqlite)

    # Clean up the zip file
    if zip_path.exists():
        print(f"Removing temporary archive {zip_path.name}...")
        zip_path.unlink()

    print("BIRD dataset setup completed!")


def main():
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = TARGET_DIR / "dev.zip"

    try:
        download_with_progress(BIRD_DEV_URL, zip_path)
        extract_and_organize(zip_path, TARGET_DIR)
    except Exception as e:
        print(f"\nError downloading/extracting BIRD dataset: {e}", file=sys.stderr)
        if zip_path.exists():
            zip_path.unlink()
        sys.exit(1)


if __name__ == "__main__":
    main()
