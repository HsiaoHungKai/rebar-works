import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

import torch
from ultralytics import YOLO


DATA = ROOT / "datasets" / "sam3_annotation_without_open_source_rebar_v1" / "data.yaml"


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
    return parser.parse_args()


def resolve_device(device: str) -> str:
    requested = device.strip().lower()
    if requested != "auto":
        return device

    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    args = parse_args()
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
    )


if __name__ == "__main__":
    main()
