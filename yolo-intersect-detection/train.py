from ultralytics import YOLO
import torch

torch.cuda.set_device(0)
model = YOLO("yolo11n.pt", device="gpu")


search_space = {
    "lr0": (1e-5, 1e-1),
    "translate": (0.1, 0.9),
    "scale": (0.1, 0.9),
    "fliplr": (0.3, 1.0),
    "mosaic": (0.5, 1.0),
}

model.tune(
    data="data/data.yaml",
    epochs=100,
    iterations=30,
    optimizer="AdamW",
    space=search_space,
    plots=True,
    save=True,
    val=True,
)
