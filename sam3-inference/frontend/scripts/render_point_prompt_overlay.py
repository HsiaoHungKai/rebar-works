#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def load_image(path: Path) -> Image.Image:
    if path.suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except ModuleNotFoundError:
            with tempfile.NamedTemporaryFile(suffix=".jpg") as converted_file:
                subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(path), "--out", converted_file.name],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return Image.open(converted_file.name).convert("RGB").copy()

    return Image.open(path).convert("RGB")


def normalize_masks(masks: np.ndarray) -> np.ndarray:
    if masks.size == 0:
        return np.empty((0, 0, 0), dtype=bool)

    if masks.ndim == 2:
        masks = masks[np.newaxis, :, :]
    elif masks.ndim == 4 and masks.shape[0] == 1:
        masks = masks[0]

    if masks.ndim != 3:
        raise ValueError(f"Expected masks with 2, 3, or leading-singleton 4 dimensions, got {masks.shape}")

    return masks.astype(bool)


def render_overlay(image_path: Path, npz_path: Path, output_path: Path) -> None:
    image = load_image(image_path)
    masks = normalize_masks(np.load(npz_path)["masks"])

    if masks.size == 0:
        output = image
    else:
        output = image.convert("RGBA")
        overlay_color = np.array([37, 99, 235, 128], dtype=np.uint8)

        for mask in masks:
            if mask.shape != (image.height, image.width):
                mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
                mask_image = mask_image.resize((image.width, image.height), Image.Resampling.NEAREST)
                mask = np.asarray(mask_image) > 0

            overlay = np.zeros((image.height, image.width, 4), dtype=np.uint8)
            overlay[mask] = overlay_color
            output = Image.alpha_composite(output, Image.fromarray(overlay, mode="RGBA"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, format="PNG")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--npz", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    render_overlay(args.image, args.npz, args.output)


if __name__ == "__main__":
    main()
