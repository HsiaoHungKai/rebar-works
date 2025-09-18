from ultralytics import YOLO
import torch
from torchvision.ops import nms
import numpy as np
import cv2
from skimage.transform import hough_line, hough_line_peaks
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
    scores = boxes.conf.detach().clone()
    xyxy = boxes.xyxy.detach().clone()

    # Apply Non-Maximum Suppression (NMS)
    # Removes redundant bounding boxes that detect the same object multiple times, keeping only the best detection
    mask = nms(xyxy, scores, iou_threshold=0.3)
    filtered_boxes = xyxy[mask]

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
    angler = angle * np.pi / 180
    newx = x * np.cos(angler) - y * np.sin(angler)
    newy = x * np.sin(angler) + y * np.cos(angler)
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


def norm_radian(radian, pi=np.pi):
    """
    Normalizes an angle in radians to the range [-π, π].

    This function ensures that any input angle (in radians) is wrapped into the standard interval
    from -π to π. This is useful for comparing angles and performing circular statistics,
    as angles outside this range are equivalent to some angle within it.

    Args:
        radian (float): The angle in radians to normalize.
        pi (float, optional): The value of π to use (default: math.pi).

    Returns:
        float: The normalized angle in radians, guaranteed to be within [-π, π].

    Example:
        >>> norm_radian(4)
        -2.2831853071795862
        >>> norm_radian(-4)
        2.2831853071795862
        >>> norm_radian(3.14)
        3.14
    """
    radian = radian % (2 * pi)
    return radian if abs(radian) <= pi else radian - (1 if radian >= 0 else -1) * 2 * pi


def get_circular_outlier_indices(radians, threshold: float = 1.5):
    """
    Identifies outlier indices in a list of angles using circular statistics.

    This function computes the circular mean and circular standard deviation of the input angles,
    then flags as outliers any angles whose deviation from the mean exceeds (threshold * circular std).
    Useful for filtering out lines or vectors whose orientation is inconsistent with the main group.

    Args:
        radians (list or np.ndarray): List/array of angles in radians (e.g., from np.arctan2).
        threshold (float): Multiplier for the circular standard deviation to set the outlier threshold. Default is 1.5.

    Returns:
        list: Indices of input angles that are considered outliers.

    Example:
        >>> radians = [0.1, 0.2, 0.15, 3.0]
        >>> outliers = get_circular_outlier_indices(radians, threshold=1.5)
        >>> print(outliers)
        [3]
    """
    if threshold == 0:
        return []

    radians = [2 * radian for radian in radians]
    mean = circmean(radians, high=np.pi, low=-np.pi)
    maxdelta = threshold * circstd(radians, high=np.pi, low=-np.pi)
    deltas = [norm_radian(radian - mean) for radian in radians]
    outlier_indices = [
        i for i, z in enumerate(zip(radians, deltas)) if abs(z[1]) > maxdelta
    ]

    return outlier_indices


def get_mode_outlier_indices(radians, threshold: float = 10):
    """
    Identifies outlier indices in a list of angles using histogram-based mode detection.

    This function computes a histogram of the input angles, finds the mode (most frequent bin),
    and flags as outliers any angles whose deviation from the mode exceeds the specified threshold.
    This approach is useful for filtering out lines or vectors whose orientation is inconsistent
    with the most common direction in the dataset.

    Args:
        radians (list or np.ndarray): List/array of angles in radians (e.g., from np.arctan2).
        threshold (float, optional): Angular threshold in degrees from the mode. Default is 10.

    Returns:
        list: Indices of input angles that are considered outliers.

    Example:
        >>> radians = [0.1, 0.15, 0.12, 1.5, 0.11]  # Most angles around 0.1, one at 1.5
        >>> outliers = get_mode_outlier_indices(radians, threshold=15)
        >>> print(outliers)
        [3]  # Index of the 1.5 radian angle
    """
    if threshold == 0:
        return []

    bins = 36
    # Compute histogram
    hist, bin_edges = np.histogram(radians, bins=bins, range=(-np.pi, np.pi))
    # Find the index of the bin with the most values
    max_bin_index = np.argmax(hist)
    mode = bin_edges[max_bin_index] + (np.pi / bins)  # Center of the mode bin

    threshold = threshold * np.pi / 180
    outlier_indices = [
        i
        for i, radian in enumerate(radians)
        if abs(norm_radian(radian - mode)) > threshold
    ]

    return outlier_indices


def remove_outliers(operation, points, threshold):
    """
    Removes outlier line segments based on their angular orientation using statistical methods.

    This function calculates the angle of each line segment and applies a specified outlier
    detection algorithm to identify and filter out lines whose orientations deviate
    significantly from the main directional pattern in the dataset.

    Args:
        operation (callable): Outlier detection function that takes (radians, threshold)
                             and returns indices of outlier angles.
                             Examples: get_circular_outlier_indices, get_mode_outlier_indices
        points (list): List of line segments where each segment is [[x1, y1], [x2, y2]]
        threshold (float or None): Statistical threshold for outlier detection.
                                  - For circular method: multiplier for circular std deviation
                                  - For mode method: angular threshold in degrees from mode
                                  - If None or 0, no filtering is performed

    Returns:
        list: Filtered list of line segments with outliers removed, preserving the original
              [[x1, y1], [x2, y2]] format

    Example:
        >>> lines = [[[0, 0], [10, 1]], [[0, 0], [10, 0]], [[0, 0], [1, 10]]]
        >>> filtered = remove_outliers(get_mode_outlier_indices, lines, 15)
        # Removes the nearly vertical line [[[0, 0], [1, 10]]] if it deviates
        # more than 15° from the dominant horizontal direction

    Note:
        - Line angles are computed using np.arctan2(dy, dx) from start to end point
        - Returns original list unchanged if threshold is None or 0
        - Preserves order of remaining line segments after outlier removal
    """
    if threshold:
        radians = []
        for shape in points:
            point1 = np.array(shape[0])
            point2 = np.array(shape[1])
            # Because we detect vertex using pc, so the direction will be pretty much same
            vector = point2 - point1
            radian = np.arctan2(vector[1], vector[0])
            radians.append(radian)
        # Remove outliers
        outlier_indices = operation(radians, threshold=threshold)
        points = [points[i] for i in range(len(points)) if i not in outlier_indices]

    return points


def prune_lines_using_hough_transform(image, pc_points, pc_direction, threshold):
    # Perform Hough Transform pruning on pc
    # lines = []
    pruned_pc = remove_outliers(get_mode_outlier_indices, pc_points, threshold)

    image = cv2.imread(image)
    height, width = image.shape[:2]
    canvas = np.zeros((height, width), dtype=np.float32)
    for points in pruned_pc:
        pt1 = (int(points[0][0]), int(points[0][1]))
        pt2 = (int(points[1][0]), int(points[1][1]))

        # Draw line on canvas with thickness
        cv2.line(canvas, pt1, pt2, 255, thickness=3)

    # Get Hough Transform data
    hspace, angles, dists = hough_line(canvas)
    # Find peaks
    _, angles_peaks, dists_peaks = hough_line_peaks(
        hspace, angles, dists, threshold=0.5 * np.max(hspace)
    )

    radians = []
    for theta in angles_peaks:
        radian = norm_radian(theta + np.pi / 2, pi=np.pi)
        radians.append(radian)
    diff = np.ptp(radians)
    if diff > np.pi / 2:
        for i in range(len(radians)):
            if radians[i] > np.pi / 2:
                radians[i] = norm_radian(radians[i] + np.pi, pi=np.pi)
    min_radian, max_radian = np.min(radians), np.max(radians)
    print(pc_direction)
    # print(radians)
    print(angles_peaks)
    print("min radian: ", min_radian)
    print("max radian: ", max_radian)

    tolerance_degrees = 5
    tolerance_rad = tolerance_degrees * np.pi / 180
    expanded_min = min_radian - tolerance_rad
    expanded_max = max_radian + tolerance_rad
    print("expanded min: ", expanded_min)
    print("expanded max: ", expanded_max)

    # print(pc_direction, pc_points)
    indices = []
    for i, points in enumerate(pc_points):
        point1 = np.array(points[0])
        point2 = np.array(points[1])
        # Calculate the angle of the line
        vector = point2 - point1
        radian = np.arctan2(vector[1], vector[0])
        if (
            expanded_min <= radian <= expanded_max
            or expanded_min <= norm_radian(radian + np.pi, np.pi) <= expanded_max
        ):
            indices.append(i)
    print(indices)
    pc_points = [pc_points[i] for i in range(len(pc_points)) if i in indices]

    print("Detected lines (rho, theta):")
    for rho, theta in zip(dists_peaks, angles_peaks):
        # a = np.cos(theta)
        # b = np.sin(theta)

        # x0 = rho * a
        # y0 = rho * b

        # # Calculate line endpoints
        # x1 = int(x0 + width * (-b))
        # y1 = int(y0 + height * (a))
        # x2 = int(x0 - width * (-b))
        # y2 = int(y0 - height * (a))

        # # Draw the line on top of the original image
        # plt.plot([x1, x2], [y1, y2], '-r', linewidth=0.5, alpha=0.8)

        print(f"Line: rho={rho:.2f}, theta={theta:.2f}")

    # print(pc_points)

    return pc_points


def add_points_to_shapes(shapes, points, pc_direction):
    """
    Adds line segments to the shapes list in JSON-compatible format.

    This function takes a list of line segments defined by their endpoints and appends
    them to the provided shapes list. Each line segment is represented as a dictionary
    containing the points, orientation (horizontal or vertical), and shape type.

    Args:
        shapes (list): The list to which line dictionaries will be appended.
        points (list): List of line segments, each as [[x1, y1], [x2, y2]].
        pc_direction (str): Principal component direction ("left", "right", "up", or "down").

    Returns:
        list: The updated 'shapes' list with the new line segments added.

    Example:
        >>> shapes = []
        >>> points = [[[0, 0], [1, 0]], [[0, 0], [0, 1]]]
        >>> add_points_to_shapes(shapes, points, "right")
        # shapes now contains the two lines with appropriate orientation

    Note:
        - All coordinates are converted to float for JSON serialization
        - The orientation is determined by horizontal_or_vertical(pc_direction)
    """
    for points in points:
        shapes.append(
            {
                "points": [
                    [float(points[0][0]), float(points[0][1])],
                    [float(points[1][0]), float(points[1][1])],
                ],
                "orientation": horizontal_or_vertical(pc_direction),
                "shape_type": "line",
            }
        )

    return shapes


def get_lines(image, model_path, threshold=None) -> str:
    """
    Detects rebar intersections in an image and generates connection lines using PCA alignment.

    This function performs the following steps:
    1. Uses YOLO model to detect rebar intersection bounding boxes
    2. Extracts center points (vertices) from bounding boxes
    3. Applies Principal Component Analysis (PCA) to find dominant directions
    4. For each vertex, finds the nearest neighbors aligned with PC1 and PC2 directions
    5. Perform outlier detection to remove improper connections
    6. Generates line connections between aligned vertices

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

    # Removing outliers depending on the radian of vector for pc1_points and pc2_points using get_circular_outlier_indices or get_mode_outlier_indices
    # pc1_points = remove_outliers(
    #     get_circular_outlier_indices, pc1_points, threshold
    # )
    # pc2_points = remove_outliers(
    #     get_circular_outlier_indices, pc2_points, threshold
    # )
    # pc1_points = remove_outliers(
    #     get_mode_outlier_indices, pc1_points, threshold
    # )
    # pc2_points = remove_outliers(
    #     get_mode_outlier_indices, pc2_points, threshold
    # )

    # Perform Hough Transform pruning on pc1_points and pc2_points
    pc1_points = prune_lines_using_hough_transform(
        image, pc1_points, pc_direction["pc1"], threshold=0
    )
    pc2_points = prune_lines_using_hough_transform(
        image, pc2_points, pc_direction["pc2"], threshold=0
    )

    add_points_to_shapes(shapes, pc1_points, pc_direction["pc1"])
    add_points_to_shapes(shapes, pc2_points, pc_direction["pc2"])

    return json.dumps({"shapes": shapes}, indent=2)


def point_on_hough_line(x, y, theta, rho, tolerance=1e-2):
    return abs(x * np.cos(theta) + y * np.sin(theta) - rho) < tolerance


def get_pc_direction(pc) -> str:
    """
    Determines the directional orientation of a principal component vector.

    This function analyzes the components of a 2D principal component vector
    to classify its direction as one of four cardinal directions: "left", "right", "up", or "down".
    The classification is based on which component (x or y) has the larger absolute value,
    and the sign of that component.

    Args:
        pc (list or np.array): A 2D principal component vector [x, y]

    Returns:
        str: Direction of the vector, one of "left", "right", "up", or "down"

    Example:
        >>> get_pc_direction([1, 0.1])
        'right'
        >>> get_pc_direction([-1, 0.1])
        'left'
        >>> get_pc_direction([0.1, 1])
        'down'
        >>> get_pc_direction([0.1, -1])
        'up'

    Note:
        - If |x| >= |y|: returns "right" (x >= 0) or "left" (x < 0)
        - If |y| > |x|: returns "down" (y >= 0) or "up" (y < 0)
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
