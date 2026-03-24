#!/usr/bin/env python3
"""Run SAM3 image inference with either text or point prompts."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MODEL_ID = "facebook/sam3"


@dataclass
class ParsedPoints:
    raw: str
    points: list[list[list[list[float]]]]
    labels: list[list[list[int]]]
    flat_points: list[list[float]]
    flat_labels: list[int]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run SAM3 image inference with text or point prompts."
    )
    parser.add_argument("--input-image", required=True, help="Path to an input image.")
    parser.add_argument(
        "--prompt-type",
        required=True,
        choices=("text", "points"),
        help="Which prompt type to run.",
    )
    parser.add_argument(
        "--text",
        help="Text prompt used when --prompt-type text is selected.",
    )
    parser.add_argument(
        "--points",
        help='Point prompts as "x,y,label;x,y,label;..." where label is 0 or 1.',
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write mask.png, overlay.png, and result.json.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=("auto", "cuda", "cpu"),
        help="Execution device. auto prefers CUDA when available.",
    )
    parser.add_argument(
        "--target-size",
        type=int,
        default=None,
        help="Optional square resize size. SAM3 is designed for 1008px.",
    )
    parser.add_argument(
        "--mask-threshold",
        type=float,
        default=0.5,
        help="Mask binarization threshold.",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.5,
        help="Instance score threshold for text-prompt mode.",
    )
    parser.add_argument(
        "--multimask",
        action="store_true",
        help="Keep all SAM3 candidate masks in point mode.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    image_path = Path(args.input_image)
    if not image_path.is_file():
        raise SystemExit(f"Input image does not exist: {image_path}")

    if args.prompt_type == "text":
        if not args.text:
            raise SystemExit("--text is required when --prompt-type text is used.")
        if args.points:
            raise SystemExit("--points cannot be used when --prompt-type text is used.")
    else:
        if not args.points:
            raise SystemExit("--points is required when --prompt-type points is used.")
        if args.text:
            raise SystemExit("--text cannot be used when --prompt-type points is used.")

    if args.target_size is not None and args.target_size <= 0:
        raise SystemExit("--target-size must be a positive integer.")
    if not 0.0 <= args.mask_threshold <= 1.0:
        raise SystemExit("--mask-threshold must be between 0.0 and 1.0.")
    if not 0.0 <= args.score_threshold <= 1.0:
        raise SystemExit("--score-threshold must be between 0.0 and 1.0.")


def parse_points(points_raw: str) -> ParsedPoints:
    flat_points: list[list[float]] = []
    flat_labels: list[int] = []

    for index, chunk in enumerate(points_raw.split(";"), start=1):
        item = chunk.strip()
        if not item:
            continue

        values = [part.strip() for part in item.split(",")]
        if len(values) != 3:
            raise SystemExit(
                f"Invalid point #{index}: expected x,y,label but got {item!r}."
            )

        try:
            x = float(values[0])
            y = float(values[1])
            label = int(values[2])
        except ValueError as exc:
            raise SystemExit(
                f"Invalid point #{index}: x and y must be numbers, label must be 0 or 1."
            ) from exc

        if label not in (0, 1):
            raise SystemExit(f"Invalid point #{index}: label must be 0 or 1.")

        flat_points.append([x, y])
        flat_labels.append(label)

    if not flat_points:
        raise SystemExit("No valid points were provided in --points.")

    return ParsedPoints(
        raw=points_raw,
        points=[[flat_points]],
        labels=[[flat_labels]],
        flat_points=flat_points,
        flat_labels=flat_labels,
    )


def load_runtime(args: argparse.Namespace) -> tuple[Any, Any, str]:
    try:
        import torch
        from transformers import (
            Sam3Model,
            Sam3Processor,
            Sam3TrackerModel,
            Sam3TrackerProcessor,
        )
    except ImportError as exc:
        raise SystemExit(
            "Missing runtime dependencies. Install requirements.txt before running inference."
        ) from exc

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device

    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA was requested but no CUDA device is available.")

    if args.prompt_type == "text":
        processor_cls = Sam3Processor
        model_cls = Sam3Model
    else:
        processor_cls = Sam3TrackerProcessor
        model_cls = Sam3TrackerModel

    if args.target_size is None:
        processor = processor_cls.from_pretrained(MODEL_ID)
        model = model_cls.from_pretrained(MODEL_ID)
    else:
        processor = processor_cls.from_pretrained(
            MODEL_ID,
            size={"height": args.target_size, "width": args.target_size},
        )
        if args.prompt_type == "text":
            from transformers import Sam3Config

            config = Sam3Config.from_pretrained(MODEL_ID)
            config.image_size = args.target_size
            model = model_cls.from_pretrained(MODEL_ID, config=config)
        else:
            model = model_cls.from_pretrained(MODEL_ID)

    model = model.to(device)
    model.eval()
    return torch, processor, model


def make_output_dir(path: str) -> Path:
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def to_bool_mask(mask: Any, threshold: float) -> np.ndarray:
    import numpy as np

    if hasattr(mask, "detach"):
        mask = mask.detach().cpu().numpy()
    else:
        mask = np.asarray(mask)

    mask = np.squeeze(mask)
    if mask.dtype == np.bool_:
        return mask.astype(bool)
    return mask > threshold


def combine_masks(masks: list[np.ndarray]) -> np.ndarray:
    import numpy as np

    if not masks:
        raise SystemExit("Inference returned no masks.")
    combined = np.zeros_like(masks[0], dtype=bool)
    for mask in masks:
        combined |= mask.astype(bool)
    return combined


def compute_bbox(mask: np.ndarray) -> list[int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0 or len(ys) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def save_mask_and_overlay(image: Image.Image, mask: np.ndarray, output_dir: Path) -> None:
    import numpy as np
    from PIL import Image

    mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    mask_image.save(output_dir / "mask.png")

    image_array = np.array(image.convert("RGB"), dtype=np.uint8)
    overlay = image_array.copy().astype(np.float32)
    color = np.array([255, 80, 0], dtype=np.float32)
    overlay[mask] = (0.45 * color) + (0.55 * overlay[mask])
    overlay_image = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8), mode="RGB")
    overlay_image.save(output_dir / "overlay.png")


def run_text_inference(
    args: argparse.Namespace,
    image: Image.Image,
    torch: Any,
    processor: Any,
    model: Any,
) -> dict[str, Any]:
    inputs = processor(images=image, text=args.text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_instance_segmentation(
        outputs,
        threshold=args.score_threshold,
        mask_threshold=args.mask_threshold,
        target_sizes=inputs.get("original_sizes").tolist(),
    )[0]

    raw_masks = results.get("masks")
    if raw_masks is None:
        raw_masks = []
    bool_masks = [to_bool_mask(mask, args.mask_threshold) for mask in raw_masks]
    combined_mask = combine_masks(bool_masks)

    boxes = results.get("boxes")
    if boxes is None:
        boxes = []
    scores = results.get("scores")
    if scores is None:
        scores = []

    instances = []
    for index, mask in enumerate(bool_masks):
        instances.append(
            {
                "index": index,
                "score": maybe_float(scores[index]) if index < len(scores) else None,
                "box_xyxy": normalize_box(boxes[index]) if index < len(boxes) else compute_bbox(mask),
                "area_pixels": int(mask.sum()),
                "area_ratio": float(mask.mean()),
            }
        )

    return {
        "selected_mask": combined_mask,
        "all_masks": bool_masks,
        "metadata": {
            "mode": "text",
            "text": args.text,
            "num_instances": len(bool_masks),
            "instances": instances,
        },
    }


def normalize_box(box: Any) -> list[float] | None:
    import numpy as np

    if box is None:
        return None
    if hasattr(box, "detach"):
        box = box.detach().cpu().tolist()
    elif isinstance(box, np.ndarray):
        box = box.tolist()
    return [float(value) for value in box]


def maybe_float(value: Any) -> float | None:
    import numpy as np

    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach().cpu().item()
    elif isinstance(value, np.ndarray):
        value = value.item()
    return float(value)


def extract_point_masks(processed_masks: Any) -> list[np.ndarray]:
    import numpy as np

    if hasattr(processed_masks, "detach"):
        masks_array = processed_masks.detach().cpu().numpy()
    else:
        masks_array = np.asarray(processed_masks)

    masks_array = np.squeeze(masks_array)

    if masks_array.ndim == 2:
        return [masks_array.astype(bool)]
    if masks_array.ndim == 3:
        return [np.asarray(mask).astype(bool) for mask in masks_array]

    raise SystemExit(f"Unexpected point-mask output shape: {masks_array.shape}")


def run_point_inference(
    args: argparse.Namespace,
    image: Image.Image,
    torch: Any,
    processor: Any,
    model: Any,
    parsed_points: ParsedPoints,
) -> dict[str, Any]:
    inputs = processor(
        images=image,
        input_points=parsed_points.points,
        input_labels=parsed_points.labels,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        outputs = model(**inputs, multimask_output=args.multimask)

    processed_masks = processor.post_process_masks(
        outputs.pred_masks.cpu(), inputs["original_sizes"]
    )[0]
    candidate_masks = extract_point_masks(processed_masks)

    raw_scores = getattr(outputs, "iou_scores", None)
    score_list: list[float | None]
    if raw_scores is None:
        score_list = [None] * len(candidate_masks)
    else:
        import numpy as np

        raw_scores = np.asarray(raw_scores.detach().cpu()).reshape(-1).tolist()
        score_list = [float(score) for score in raw_scores[: len(candidate_masks)]]
        if len(score_list) < len(candidate_masks):
            score_list.extend([None] * (len(candidate_masks) - len(score_list)))

    best_index = 0
    if args.multimask and any(score is not None for score in score_list):
        best_index = max(
            range(len(candidate_masks)),
            key=lambda index: score_list[index] if score_list[index] is not None else float("-inf"),
        )

    selected_mask = candidate_masks[best_index]
    candidates = []
    for index, mask in enumerate(candidate_masks):
        candidates.append(
            {
                "index": index,
                "score": score_list[index],
                "box_xyxy": compute_bbox(mask),
                "area_pixels": int(mask.sum()),
                "area_ratio": float(mask.mean()),
            }
        )

    return {
        "selected_mask": selected_mask,
        "all_masks": candidate_masks,
        "metadata": {
            "mode": "points",
            "points": parsed_points.flat_points,
            "labels": parsed_points.flat_labels,
            "selected_index": best_index,
            "num_candidates": len(candidate_masks),
            "candidates": candidates,
        },
    }


def write_metadata(
    args: argparse.Namespace,
    output_dir: Path,
    image: Image.Image,
    selected_mask: np.ndarray,
    inference_metadata: dict[str, Any],
) -> None:
    payload = {
        "model_id": MODEL_ID,
        "prompt_type": args.prompt_type,
        "device": args.device,
        "resolved_device": inference_metadata.pop("resolved_device"),
        "target_size": args.target_size,
        "score_threshold": args.score_threshold,
        "mask_threshold": args.mask_threshold,
        "input_image": os.path.abspath(args.input_image),
        "output_dir": str(output_dir.resolve()),
        "image_size": {"width": image.width, "height": image.height},
        "selected_mask": {
            "area_pixels": int(selected_mask.sum()),
            "area_ratio": float(selected_mask.mean()),
            "box_xyxy": compute_bbox(selected_mask),
        },
        "result": inference_metadata,
    }

    with (output_dir / "result.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    from PIL import Image

    output_dir = make_output_dir(args.output_dir)
    image = Image.open(args.input_image).convert("RGB")
    parsed_points = parse_points(args.points) if args.prompt_type == "points" else None

    torch, processor, model = load_runtime(args)
    resolved_device = str(model.device)

    if args.prompt_type == "text":
        result = run_text_inference(args, image, torch, processor, model)
    else:
        assert parsed_points is not None
        result = run_point_inference(args, image, torch, processor, model, parsed_points)

    selected_mask = result["selected_mask"]
    metadata = result["metadata"]
    metadata["resolved_device"] = resolved_device

    save_mask_and_overlay(image, selected_mask, output_dir)
    write_metadata(args, output_dir, image, selected_mask, metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
