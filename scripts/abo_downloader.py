from tqdm import tqdm
import requests
from pathlib import Path

BYTES_IN_AN_MB = 1024 * 1024

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data" / "raw" / "abo"

DATA_DIR.mkdir(parents=True, exist_ok=True)

urls = {
    "https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-listings.tar",
    "https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-images-small.tar"
}

for url in urls:
    file_name = url.split("/")[-1]
    destination = DATA_DIR / file_name

    print(f"Saving {url} to {destination}")

    with requests.get(url, stream=True) as response:
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with destination.open("wb") as f:
            with tqdm(
                total = total_size,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=file_name
            ) as progress:
                for chunk in response.iter_content(chunk_size=(8 * BYTES_IN_AN_MB)):
                    if chunk:
                        f.write(chunk)
                        progress.update(len(chunk))

    print(f"Completed downloading {file_name}")