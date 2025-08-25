from ultralytics import YOLO
import torch
from torchvision.ops import nms
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
    results = model.predict(image, verbose=False)
    
    boxes = results[0].boxes  
    scores = boxes.conf       
    xyxy = boxes.xyxy 
    
    boxes_tensor = xyxy.detach().clone()
    scores_tensor = scores.detach().clone()
    keep = nms(boxes_tensor, scores_tensor, iou_threshold=0.3)
    filtered_boxes = boxes_tensor[keep]

    if results[0].boxes is not None:
        return filtered_boxes.cpu().numpy()
    else:
        return np.array([])

