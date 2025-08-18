from ultralytics import YOLO
import torch
import numpy as np


def get_bounding_boxes(image, model_path):
    """
    Args:
        image: Input image (can be file path string, numpy array, or PIL image)
        model_path: Path to the YOLO model weights file

    Returns:
        numpy.ndarray: Array of bounding boxes in xyxy format
    """
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    model = YOLO(model_path).to(device)
    results = model(image, verbose=False)

    if results[0].boxes is not None:
        return results[0].boxes.xyxy.cpu().numpy()
    else:
        return np.array([])

