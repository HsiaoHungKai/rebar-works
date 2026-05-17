import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))


DATA = ROOT / "datasets" / "sam3_annotation_without_open_source_rebar_v1" / "data.yaml"

DEFAULT_AUGMENTATIONS = {
    # Color jitter: keep hue stable for rebar/concrete while allowing lighting changes.
    "hsv_h": 0.0,
    "hsv_s": 0.25,
    "hsv_v": 0.35,
    # Mild geometry for camera angle, crop, and distance variation.
    "degrees": 7.0,
    "translate": 0.10,
    "scale": 0.50,
    "shear": 2.0,
    "perspective": 0.0005,
    # Horizontal flips are usually safe; keep vertical flips opt-in.
    "fliplr": 0.50,
    "flipud": 0.0,
    # Composite augmentations. Close mosaic near the end for cleaner final epochs.
    "mosaic": 0.50,
    "mixup": 0.05,
    "copy_paste": 0.0,
    "close_mosaic": 10,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO26l segmentation on the rebar dataset.")
    parser.add_argument("--model", default="yolo26l-seg.pt")
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--device", default="auto", help="Use auto, cpu, mps, cuda, 0, or a comma-separated GPU list.")
    parser.add_argument("--project", default=str(ROOT / "runs" / "segment"))
    parser.add_argument("--name", default="yolo26l_sam3_rebar_v1")
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument(
        "--no-augmentation",
        action="store_true",
        help="Disable Ultralytics train-time augmentations for baseline comparisons.",
    )
    parser.add_argument("--hsv-h", type=float, default=DEFAULT_AUGMENTATIONS["hsv_h"])
    parser.add_argument("--hsv-s", type=float, default=DEFAULT_AUGMENTATIONS["hsv_s"])
    parser.add_argument("--hsv-v", type=float, default=DEFAULT_AUGMENTATIONS["hsv_v"])
    parser.add_argument("--degrees", type=float, default=DEFAULT_AUGMENTATIONS["degrees"])
    parser.add_argument("--translate", type=float, default=DEFAULT_AUGMENTATIONS["translate"])
    parser.add_argument("--scale", type=float, default=DEFAULT_AUGMENTATIONS["scale"])
    parser.add_argument("--shear", type=float, default=DEFAULT_AUGMENTATIONS["shear"])
    parser.add_argument("--perspective", type=float, default=DEFAULT_AUGMENTATIONS["perspective"])
    parser.add_argument("--fliplr", type=float, default=DEFAULT_AUGMENTATIONS["fliplr"])
    parser.add_argument("--flipud", type=float, default=DEFAULT_AUGMENTATIONS["flipud"])
    parser.add_argument("--mosaic", type=float, default=DEFAULT_AUGMENTATIONS["mosaic"])
    parser.add_argument("--mixup", type=float, default=DEFAULT_AUGMENTATIONS["mixup"])
    parser.add_argument("--copy-paste", type=float, default=DEFAULT_AUGMENTATIONS["copy_paste"])
    parser.add_argument("--close-mosaic", type=int, default=DEFAULT_AUGMENTATIONS["close_mosaic"])
    return parser.parse_args()


def resolve_device(device: str) -> str:
    import torch

    requested = device.strip().lower()
    if requested != "auto":
        return device

    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def augmentation_kwargs(args: argparse.Namespace) -> dict[str, float | int]:
    if args.no_augmentation:
        return {
            "hsv_h": 0.0,
            "hsv_s": 0.0,
            "hsv_v": 0.0,
            "degrees": 0.0,
            "translate": 0.0,
            "scale": 0.0,
            "shear": 0.0,
            "perspective": 0.0,
            "fliplr": 0.0,
            "flipud": 0.0,
            "mosaic": 0.0,
            "mixup": 0.0,
            "copy_paste": 0.0,
            "close_mosaic": 0,
        }

    return {
        "hsv_h": args.hsv_h,
        "hsv_s": args.hsv_s,
        "hsv_v": args.hsv_v,
        "degrees": args.degrees,
        "translate": args.translate,
        "scale": args.scale,
        "shear": args.shear,
        "perspective": args.perspective,
        "fliplr": args.fliplr,
        "flipud": args.flipud,
        "mosaic": args.mosaic,
        "mixup": args.mixup,
        "copy_paste": args.copy_paste,
        "close_mosaic": args.close_mosaic,
    }


def main() -> None:
    args = parse_args()

    from ultralytics import YOLO

    device = resolve_device(args.device)
    print(f"Using device: {device}")

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        project=args.project,
        name=args.name,
        exist_ok=True,
        patience=args.patience,
        workers=args.workers,
        **augmentation_kwargs(args),
    )


if __name__ == "__main__":
    main()
