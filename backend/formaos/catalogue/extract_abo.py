import argparse
import tarfile
from pathlib import Path


def extract_archive(archive: Path, output_dir: Path) -> None:
    if not archive.exists():
        raise SystemExit(f"Archive not found: {archive}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {archive.name}")
    print(f"  Source: {archive}")
    print(f"  Target: {output_dir}")

    with tarfile.open(archive, "r") as tar:
        members = tar.getmembers()

        for member in members:
            member_path = Path(member.name)

            # Protect against paths escaping the extraction directory.
            target = (output_dir / member_path).resolve()
            output_root = output_dir.resolve()

            if target != output_root and output_root not in target.parents:
                raise SystemExit(
                    f"Unsafe archive path detected in {archive.name}: "
                    f"{member.name}"
                )

        tar.extractall(output_dir, filter="data")

    print(f"Completed extraction of {archive.name}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract downloaded Amazon Berkeley Objects archives."
    )

    parser.add_argument(
        "--input",
        default="data/raw/abo",
        help="Directory containing downloaded ABO .tar archives",
    )

    parser.add_argument(
        "--output",
        default="data/external/abo",
        help="Directory where ABO archives should be extracted",
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    listings_archive = input_dir / "abo-listings.tar"
    images_archive = input_dir / "abo-images-small.tar"

    if not listings_archive.exists():
        raise SystemExit(
            f"Listings archive not found: {listings_archive}\n"
            "Run abo_downloader.py first."
        )

    if not images_archive.exists():
        raise SystemExit(
            f"Images archive not found: {images_archive}\n"
            "Run abo_downloader.py first."
        )

    extract_archive(listings_archive, output_dir)
    extract_archive(images_archive, output_dir)

    print("ABO extraction completed successfully.")
    print(f"Extracted data: {output_dir}")


if __name__ == "__main__":
    main()
