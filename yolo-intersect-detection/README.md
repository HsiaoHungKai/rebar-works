# Rebar Intersection Detection and Line Extraction

This project provides tools for detecting rebar intersections in images and extracting their structural connections using Principal Component Analysis (PCA). The core functionality is provided by the `get_lines` function in `rebar_object_detection.py`.

---

## Main Function: `get_lines`

### Purpose

`get_lines` detects rebar intersection points in an image (using a YOLO model), analyzes their geometric arrangement, and generates a set of line connections that represent the dominant structural directions (such as horizontal and vertical rebar grids).

### How It Works

1. **Detection:**  
   Uses a YOLO model to detect intersection points (bounding boxes) in the input image.

2. **Vertex Extraction:**  
   Extracts the center points of each bounding box as vertices.

3. **PCA Alignment:**  
   Applies PCA to the set of vertices to determine the two main directions (principal components) in the grid.

4. **Neighbor Search:**  
   For each vertex, finds the nearest neighbor in each principal direction (PC1 and PC2) within a specified angular tolerance.

5. **Outlier Removal:**  
   Optionally removes outlier connections using circular statistics on the angles of the detected lines.

6. **Line Generation:**  
   Generates line segments connecting the edges of bounding boxes in the detected directions.

7. **Output:**  
   Returns a JSON string describing all detected line segments, suitable for visualization or further analysis.

---

## Example Usage

```python
from rebar_object_detection import get_lines

image_path = "path/to/image.jpg"
model_path = "path/to/yolo_model.pt"

json_lines = get_lines(image_path, model_path, threshold=1.5)

# The output is a JSON string:
# {
#   "shapes": [
#     {
#       "points": [[x1, y1], [x2, y2]],
#       "orientation": "horizontal" | "vertical",
#       "shape_type": "line"
#     },
#     ...
#   ]
# }

```

---

## Additional Notes

- The function supports outlier removal using the `threshold` parameter (higher values = more tolerant).
- The bounding box edge points are chosen so that lines connect at the edges, not the centers, for better visualization.

--- 

## Requirements

- Python 3.7+
- ultralytics (YOLO)
- torch
- torchvision
- numpy
- scipy

---

## Author
HungKai Hsiao