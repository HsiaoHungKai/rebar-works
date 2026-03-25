#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import numpy as np
import requests
import torch
from PIL import Image
from transformers import Sam3Model, Sam3Processor


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Local path or HTTP(S) URL")
    parser.add_argument("--prompt", required=True, help="SAM3 text prompt")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--mask-threshold", type=float, default=0.5)
    return parser.parse_args()


def load_image(image_arg: str) -> Image.Image:
    if image_arg.startswith(("http://", "https://")):
        response = requests.get(image_arg, stream=True, timeout=120)
        response.raise_for_status()
        return Image.open(response.raw).convert("RGB")
    return Image.open(image_arg).convert("RGB")


def tensor_to_bool_mask(mask_tensor: torch.Tensor) -> np.ndarray:
    mask = mask_tensor.detach().cpu().numpy()
    if mask.ndim > 2:
        mask = np.squeeze(mask)
    return mask.astype(bool)


def colorize_overlay(image: Image.Image, masks: list[np.ndarray]) -> Image.Image:
    base = np.array(image, dtype=np.uint8)
    overlay = base.copy()
    palette = np.array(
        [
            [255, 99, 71],
            [65, 105, 225],
            [60, 179, 113],
            [255, 215, 0],
            [186, 85, 211],
            [255, 140, 0],
        ],
        dtype=np.uint8,
    )

    for idx, mask in enumerate(masks):
        color = palette[idx % len(palette)]
        overlay[mask] = ((0.45 * overlay[mask]) + (0.55 * color)).astype(np.uint8)

    return Image.fromarray(overlay)


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    image = load_image(args.image)
    model = Sam3Model.from_pretrained("facebook/sam3").to(device)
    processor = Sam3Processor.from_pretrained("facebook/sam3")

    inputs = processor(images=image, text=args.prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    result = processor.post_process_instance_segmentation(
        outputs,
        threshold=args.threshold,
        mask_threshold=args.mask_threshold,
        target_sizes=inputs.get("original_sizes").tolist(),
    )[0]

    masks = []
    boxes = []
    scores = []

    raw_masks = result.get("masks", [])
    raw_boxes = result.get("boxes", [])
    raw_scores = result.get("scores", [])

    for idx, mask_tensor in enumerate(raw_masks):
        mask = tensor_to_bool_mask(mask_tensor)
        masks.append(mask)
        Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(
            output_dir / f"mask_{idx:02d}.png"
        )

    for box in raw_boxes:
        if isinstance(box, torch.Tensor):
            box = box.detach().cpu().tolist()
        boxes.append([float(value) for value in box])

    for score in raw_scores:
        if isinstance(score, torch.Tensor):
            score = float(score.detach().cpu().item())
        scores.append(float(score))

    image.save(output_dir / "input.png")

    if masks:
        overlay = colorize_overlay(image, masks)
        overlay.save(output_dir / "overlay.png")

    summary = {
        "device": device,
        "prompt": args.prompt,
        "image": args.image,
        "num_masks": len(masks),
        "boxes": boxes,
        "scores": scores,
    }

    with open(output_dir / "result.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
