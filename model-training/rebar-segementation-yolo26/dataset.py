import argparse
import ast
import shutil
import sys
from pathlib import Path


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_SPLITS = ("train", "valid", "test")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Combine multiple YOLO segmentation datasets into one dataset."
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="Source YOLO dataset directories. Each must contain data.yaml.",
    )
    parser.add_argument("--output", required=True, help="Output combined dataset directory.")
    parser.add_argument(
        "--splits",
        nargs="+",
        default=list(DEFAULT_SPLITS),
        choices=DEFAULT_SPLITS,
        help="Dataset splits to combine.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output directory if it already exists.",
    )
    return parser.parse_args()


def read_dataset_yaml(path: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            index += 1
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "nc":
            values["nc"] = int(value)
        elif key == "names":
            if value:
                values["names"] = parse_names(value)
            else:
                names, index = parse_names_block(lines, index + 1)
                values["names"] = names

        index += 1

    missing = {"nc", "names"} - values.keys()
    if missing:
        raise ValueError(f"{path} is missing required field(s): {', '.join(sorted(missing))}")

    return values


def parse_names(value: str) -> list[str]:
    parsed = ast.literal_eval(value)
    if isinstance(parsed, dict):
        return [parsed[key] for key in sorted(parsed)]
    if isinstance(parsed, list):
        return [str(name) for name in parsed]
    raise ValueError(f"Unsupported names value: {value}")


def parse_names_block(lines: list[str], start_index: int) -> tuple[list[str], int]:
    names: dict[int, str] = {}
    index = start_index
    while index < len(lines):
        raw_line = lines[index]
        if raw_line and not raw_line[0].isspace():
            break

        line = raw_line.split("#", 1)[0].strip()
        if line and ":" in line:
            raw_key, raw_value = line.split(":", 1)
            names[int(raw_key.strip())] = raw_value.strip().strip("\"'")
        index += 1

    if not names:
        raise ValueError("names block is empty")
    return [names[key] for key in sorted(names)], index - 1


def validate_source(source: Path, schema: dict[str, object], splits: list[str]) -> None:
    source_schema = read_dataset_yaml(source / "data.yaml")
    if source_schema != schema:
        raise ValueError(
            f"{source} class schema does not match the first source: "
            f"expected {schema}, got {source_schema}"
        )

    for split in splits:
        images_dir = source / split / "images"
        labels_dir = source / split / "labels"
        if not images_dir.exists() and not labels_dir.exists():
            continue
        if not images_dir.is_dir():
            raise ValueError(f"Missing images directory: {images_dir}")
        if not labels_dir.is_dir():
            raise ValueError(f"Missing labels directory: {labels_dir}")

        image_stems = {path.stem for path in iter_images(images_dir)}
        label_stems = {path.stem for path in labels_dir.glob("*.txt")}
        missing_labels = sorted(image_stems - label_stems)
        orphan_labels = sorted(label_stems - image_stems)

        if missing_labels:
            sample = ", ".join(missing_labels[:5])
            raise ValueError(f"{source}/{split} has images without labels: {sample}")
        if orphan_labels:
            sample = ", ".join(orphan_labels[:5])
            raise ValueError(f"{source}/{split} has labels without images: {sample}")


def iter_images(images_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def prepare_output(output: Path, overwrite: bool) -> None:
    if output.exists():
        if not overwrite:
            raise FileExistsError(f"Output directory already exists: {output}")
        shutil.rmtree(output)

    for split in DEFAULT_SPLITS:
        (output / split / "images").mkdir(parents=True, exist_ok=True)
        (output / split / "labels").mkdir(parents=True, exist_ok=True)


def copy_dataset(source: Path, output: Path, splits: list[str]) -> dict[str, int]:
    counts = {split: 0 for split in splits}
    prefix = source.name

    for split in splits:
        images_dir = source / split / "images"
        labels_dir = source / split / "labels"
        if not images_dir.exists() and not labels_dir.exists():
            continue

        for image_path in iter_images(images_dir):
            output_stem = f"{prefix}__{image_path.stem}"
            output_image = output / split / "images" / f"{output_stem}{image_path.suffix}"
            output_label = output / split / "labels" / f"{output_stem}.txt"
            source_label = labels_dir / f"{image_path.stem}.txt"

            shutil.copy2(image_path, output_image)
            shutil.copy2(source_label, output_label)
            counts[split] += 1

    return counts


def write_data_yaml(output: Path, schema: dict[str, object]) -> None:
    names = schema["names"]
    lines = [
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        f"nc: {schema['nc']}",
        f"names: {names!r}",
        "",
    ]
    (output / "data.yaml").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    sources = [Path(source).resolve() for source in args.sources]
    output = Path(args.output).resolve()
    splits = list(dict.fromkeys(args.splits))

    for source in sources:
        if not source.is_dir():
            raise FileNotFoundError(f"Source dataset directory not found: {source}")
        if not (source / "data.yaml").is_file():
            raise FileNotFoundError(f"Source dataset data.yaml not found: {source / 'data.yaml'}")

    schema = read_dataset_yaml(sources[0] / "data.yaml")
    for source in sources:
        validate_source(source, schema, splits)

    prepare_output(output, args.overwrite)
    total_counts = {split: 0 for split in splits}
    for source in sources:
        source_counts = copy_dataset(source, output, splits)
        for split, count in source_counts.items():
            total_counts[split] += count

    write_data_yaml(output, schema)

    print(f"Combined dataset written to: {output}")
    for split in splits:
        print(f"{split}: {total_counts[split]} images")
    print(f"data: {output / 'data.yaml'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
