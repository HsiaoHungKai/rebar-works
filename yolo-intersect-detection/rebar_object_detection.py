from ultralytics import YOLO
import torch
from torchvision.ops import nms
import numpy as np
import math as m
from scipy.stats import circmean, circstd
import json


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

    # Apply Non-Maximum Suppression (NMS)
    # Removes redundant bounding boxes that detect the same object multiple times, keeping only the best detection
    boxes_tensor = xyxy.detach().clone()
    scores_tensor = scores.detach().clone()
    keep = nms(boxes_tensor, scores_tensor, iou_threshold=0.3)
    filtered_boxes = boxes_tensor[keep]

    if results[0].boxes is not None:
        return filtered_boxes.cpu().numpy()
    else:
        return np.array([])


def rotate(vector, angle):
    """
    Rotates a 2D vector by a specified angle.

    Args:
        vector (list): A 2D vector [x, y]
        angle (float): Rotation angle in degrees (positive = counterclockwise)

    Returns:
        list: Rotated vector [new_x, new_y]
    """
    [x, y] = vector
    angler = angle * m.pi / 180
    newx = x * m.cos(angler) - y * m.sin(angler)
    newy = x * m.sin(angler) + y * m.cos(angler)
    return [newx, newy]


def get_cone_boundaries(vector, angle):
    """
    Creates a span (cone) around a given vector by rotating it by ±angle degrees.

    This function takes a 2D vector and creates two boundary vectors by rotating
    the original vector clockwise and counterclockwise by the specified angle.
    The resulting span represents a cone or wedge shape that can be used to
    check if other vectors fall within this angular range.

    Args:
        vector (list or np.array): A 2D vector [x, y] that serves as the center direction
        angle (float): The rotation angle in degrees (±angle creates the span width)
                      For example, angle=10 creates a 20-degree cone (±10°)

    Returns:
        np.array: A 2x2 matrix where:
                 - First column: vector rotated by +angle degrees (counterclockwise)
                 - Second column: vector rotated by -angle degrees (clockwise)

    Example:
        >>> span = get_cone_boundaries([1, 0], 30)  # 30° rotation around horizontal vector
        >>> print(span)
        [[    0.86603,     0.86603],
         [        0.5,        -0.5]]
    """
    # Rotate the input vector by +angle degrees (counterclockwise)
    positive_rotation = rotate(vector, angle)
    # Rotate the input vector by -angle degrees (clockwise)
    negative_rotation = rotate(vector, -angle)

    # Stack the two rotated vectors to form a 2x2 matrix
    # This matrix defines the boundary vectors of the span/cone
    return np.column_stack((positive_rotation, negative_rotation))


def vector_aligned_with_pc(
    vertex1, vertex2, principal_component, tolerance_angle
) -> bool:
    """
    Checks if the vector between two vertices aligns with a principal component within a tolerance angle.

    Args:
        vertex1 (np.array): First vertex coordinates [x, y] (start point)
        vertex2 (np.array): Second vertex coordinates [x, y] (end point)
        principal_component (np.array): Principal component vector [x, y] from PCA
        tolerance_angle (float): Angular tolerance in degrees (±tolerance creates acceptance cone)

    Returns:
        bool: True if vector from vertex1 to vertex2 is within the acceptance cone, False otherwise

    Example:
        >>> vector_aligned_with_pc([0, 0], [0.9, 0.2], [1, 0], 30)  # Check if vector is within ±30° of x-axis
        True
        >>> vector_aligned_with_pc([0, 0], [0.2, 0.9], [1, 0], 30)  # Vector at ~77° from x-axis
        False
    """
    # Calculate the direction vector from vertex1 to vertex2
    direction_vector = np.array(vertex2) - np.array(vertex1)

    # Create the span (cone boundaries) by rotating the principal component vector ±angle degrees
    cone = get_cone_boundaries(principal_component, tolerance_angle)

    try:
        x, y = np.linalg.solve(cone, direction_vector)
        return x >= 0 and y >= 0

    except np.linalg.LinAlgError:
        return False


def get_circular_outlier_indices(radians, coef=1.5):
    """
    Identifies outlier indices in a list of angles using circular statistics.

    This function computes the circular mean and circular standard deviation of the input angles,
    then flags as outliers any angles whose deviation from the mean exceeds (coef * circular std).
    Useful for filtering out lines or vectors whose orientation is inconsistent with the main group.

    Args:
        radians (list or np.ndarray): List/array of angles in radians (e.g., from np.arctan2).
        coef (float): Multiplier for the circular standard deviation to set the outlier threshold. Default is 1.5.

    Returns:
        list: Indices of input angles that are considered outliers.

    Example:
        >>> radians = [0.1, 0.2, 0.15, 3.0]
        >>> outliers = get_circular_outlier_indices(radians, coef=1.5)
        >>> print(outliers)
        [3]
    """
    mean = circmean(radians, high=m.pi, low=-m.pi)
    maxdelta = coef * circstd(radians, high=m.pi, low=-m.pi)
    deltas = [(radian - mean) for radian in radians]
    outlier_indices = [
        i for i, delta in enumerate(deltas) if abs(delta) > maxdelta
    ]
    return outlier_indices


def get_lines(image, model_path, threshold: float = 0) -> str:
    """
    Detects rebar intersections in an image and generates connection lines using PCA alignment.

    This function performs the following steps:
    1. Uses YOLO model to detect rebar intersection bounding boxes
    2. Extracts center points (vertices) from bounding boxes
    3. Removes statistical outliers using z-score filtering
    4. Applies Principal Component Analysis (PCA) to find dominant directions
    5. For each vertex, finds the nearest neighbors aligned with PC1 and PC2 directions
    6. Perform outlier detection to remove improper connections
    7. Generates line connections between aligned vertices

    Args:
        image: Input image (can be file path string, numpy array, or PIL image)
        model_path (str): Path to the trained YOLO model weights file (.pt format)
        threshold (float, optional): Threshold for outlier detection

    Returns:
        str: JSON string containing line shapes in the format:
             {
               "shapes": [
                 {
                   "points": [[x1, y1], [x2, y2]],
                   "orientation": "horizontal" | "vertical",
                   "shape_type": "line"
                 },
                 ...
               ]
             }
    """
    vertices = []
    shapes = []
    pc1_points = []
    pc2_points = []

    # Get bounding boxes from the image using the model
    bounding_boxes = get_bounding_boxes(image, model_path)
    vertices = []
    for box in bounding_boxes:
        x_center = (box[0] + box[2]) / 2
        y_center = (box[1] + box[3]) / 2
        vertices.append((x_center, y_center))
    vertices = np.array(vertices)

    # PCA Alignment
    mean = np.mean(vertices, axis=0)
    vc = vertices - mean
    _, _, Vh = np.linalg.svd(vc)  # Get the principal component vectors
    pc1, pc2 = Vh[0], Vh[1]
    # Get pc vector using "left", "right", "up" or "down"
    pc_direction = {
        "pc1": get_pc_direction(pc1),
        "pc2": get_pc_direction(pc2),
    }

    # Find the nearest vertices in the direction of each principal component for each vertex
    for i, vertex in enumerate(vertices):
        pc1_vertex = {
            "index": None,
            "distance": float("inf"),
        }
        pc2_vertex = {
            "index": None,
            "distance": float("inf"),
        }
        for j, other_vertex in enumerate(vertices):
            if i == j:
                continue
            # Search for closest vertex in pc1 direction
            if vector_aligned_with_pc(vertex, other_vertex, pc1, 30):
                diff = np.array(other_vertex) - np.array(vertex)
                distance = np.linalg.norm(diff, ord=2)
                if distance < pc1_vertex["distance"]:
                    # pc1_vertex["vertex"] = tuple(other_vertex)
                    pc1_vertex["index"] = j
                    pc1_vertex["distance"] = distance
            # Search for closest vertex in pc2 direction
            if vector_aligned_with_pc(vertex, other_vertex, pc2, 30):
                diff = np.array(other_vertex) - np.array(vertex)
                distance = np.linalg.norm(diff, ord=2)
                if distance < pc2_vertex["distance"]:
                    pc2_vertex["index"] = j
                    pc2_vertex["distance"] = distance

        # Store the point into pc1_points or pc2_points respectfully
        if pc1_vertex["index"] is not None:
            direction = pc_direction["pc1"]
            start = bounding_boxes[i]
            end = bounding_boxes[pc1_vertex["index"]]
            points = get_points_from_direction(start, end, direction)
            pc1_points.append(points)
        if pc2_vertex["index"] is not None:
            direction = pc_direction["pc2"]
            start = bounding_boxes[i]
            end = bounding_boxes[pc2_vertex["index"]]
            points = get_points_from_direction(start, end, direction)
            pc2_points.append(points)

    # Remove outliers depending on the radian of vector for pc1_points using circular statistics
    if threshold:
        radians = []
        for shape in pc1_points:
            point1 = np.array(shape[0])
            point2 = np.array(shape[1])
            # Because we detect vertex using pc, so the direction will be pretty much same
            vector = point2 - point1
            radian = np.arctan2(vector[1], vector[0])
            radians.append(radian)
        # Remove outliers
        outlier_indices = get_circular_outlier_indices(radians, coef=threshold)
        pc1_points = [
            pc1_points[i] for i in range(len(pc1_points)) if i not in outlier_indices
        ]
    # Add points to shapes
    for points in pc1_points:
        shapes.append(
            {
                "points": [
                    [float(points[0][0]), float(points[0][1])],
                    [float(points[1][0]), float(points[1][1])],
                ],
                "orientation": horizontal_or_vertical(pc_direction["pc1"]),
                "shape_type": "line",
            }
        )

    # Removing outliers depending on the radian of vector for pc2_points using circular statistics
    if threshold:
        radians = []
        for shape in pc2_points:
            point1 = np.array(shape[0])
            point2 = np.array(shape[1])
            # Because we detect vertex using pc, so the direction will be pretty much same
            vector = point2 - point1
            radian = np.arctan2(vector[1], vector[0])
            radians.append(radian)
        # Remove outliers
        outlier_indices = get_circular_outlier_indices(radians, coef=threshold)
        pc2_points = [
            pc2_points[i] for i in range(len(pc2_points)) if i not in outlier_indices
        ]
    # Add remaining points to shapes
    for points in pc2_points:
        shapes.append(
            {
                "points": [
                    [float(points[0][0]), float(points[0][1])],
                    [float(points[1][0]), float(points[1][1])],
                ],
                "orientation": horizontal_or_vertical(pc_direction["pc2"]),
                "shape_type": "line",
            }
        )

    return json.dumps({"shapes": shapes}, indent=2)


def get_pc_direction(pc) -> str:
    """
    Determines the orientation of a principal component vector.

    This function analyzes the components of a 2D principal component vector
    to classify its orientation as either 'horizontal' or 'vertical'.
    The classification is based on the relative magnitudes of the x and y components.

    Args:
        pc (list or np.array): A 2D principal component vector [x, y]

    Returns:
        str: Orientation of the vector, one of 'horizontal' or 'vertical'

    Example:
        >>> get_pc_direction([1, 0.1])
        'horizontal'
        >>> get_pc_direction([0.1, 1])
        'vertical'
    """
    x, y = pc
    if abs(x) >= abs(y):
        return "right" if x >= 0 else "left"
    else:
        return "down" if y >= 0 else "up"


def get_points_from_direction(start, end, direction):
    """
    Returns the coordinates of two points on the edges of two bounding boxes,
    allowing a line to be drawn between the edges in a specified direction.

    Args:
        start (list or np.ndarray): The first bounding box in [x1, y1, x2, y2] format.
        end (list or np.ndarray): The second bounding box in [x1, y1, x2, y2] format.
        direction (str): The direction of the connection ("left", "right", "up", or "down").

    Returns:
        list: A list of two [x, y] points, one on the edge of each bounding box.

    Example:
        >>> get_points_from_direction([10, 20, 30, 40], [50, 60, 70, 80], "right")
        [[30, 30.0], [50, 70.0]]

    Note:
        This function is useful for visualizing connections between objects by drawing lines
        that start and end at the edges of bounding boxes, rather than at their centers.
    """
    if direction == "left":
        return [[start[0], (start[1] + start[3]) / 2], [end[2], (end[1] + end[3]) / 2]]
    elif direction == "right":
        return [
            [start[2], (start[1] + start[3]) / 2],
            [end[0], (end[1] + end[3]) / 2],
        ]
    elif direction == "up":
        return [
            [(start[0] + start[2]) / 2, start[1]],
            [(end[0] + end[2]) / 2, end[3]],
        ]
    elif direction == "down":
        return [
            [(start[0] + start[2]) / 2, start[3]],
            [(end[0] + end[2]) / 2, end[1]],
        ]


def horizontal_or_vertical(direction) -> str:
    if direction == "left" or direction == "right":
        return "horizontal"
    else:
        return "vertical"
