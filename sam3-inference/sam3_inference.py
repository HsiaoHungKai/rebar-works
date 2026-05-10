import torch
import numpy as np
from typing import Union, List, Optional, Tuple, Dict, Any
from PIL import Image
from transformers import Sam3Model, Sam3Processor, Sam3TrackerModel, Sam3TrackerProcessor
import requests
from io import BytesIO
import argparse
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime

# Enable HEIC/HEIF support for iPhone photos
from pillow_heif import register_heif_opener
register_heif_opener()


class SAM3Inference:
    """
    General-purpose prompt inference class for SAM3.

    Args:
        model_id: HuggingFace model identifier
        device: Device to run inference on ('cuda', 'cpu', or None for auto-detect)
        half_precision: Use FP16 for faster inference (requires CUDA)
    """

    def __init__(
        self,
        model_id: str = "facebook/sam3",
        device: Optional[str] = None,
        half_precision: bool = True
    ):
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.use_fp16 = half_precision and self.device == "cuda"

        print(f"Loading SAM3 model to {self.device} (FP16: {self.use_fp16})...")

        # Load model and processor
        self.model = Sam3Model.from_pretrained(model_id).to(self.device)
        self.processor = Sam3Processor.from_pretrained(model_id)
        self.tracker_model: Optional[Sam3TrackerModel] = None
        self.tracker_processor: Optional[Sam3TrackerProcessor] = None

        # Optimize model
        self.model.eval()
        if self.use_fp16:
            self.model = self.model.half()

        # Compile model for faster inference (PyTorch 2.0+)
        self.model = self._maybe_compile_model(self.model, model_name="SAM3 text model")

    def _maybe_compile_model(self, model: torch.nn.Module, model_name: str) -> torch.nn.Module:
        """Compile a CUDA model when torch.compile is available."""
        if hasattr(torch, 'compile') and self.device == "cuda":
            try:
                model = torch.compile(model, mode="reduce-overhead")
                print(f"{model_name} compiled with torch.compile")
            except Exception as e:
                print(f"Could not compile {model_name}: {e}")
        return model

    def _load_tracker_components(self):
        """Lazily load the tracker model/processor used for point prompts."""
        if self.tracker_model is not None and self.tracker_processor is not None:
            return

        print(f"Loading SAM3 tracker model to {self.device} (FP16: {self.use_fp16})...")

        self.tracker_model = Sam3TrackerModel.from_pretrained(self.model_id).to(self.device)
        self.tracker_processor = Sam3TrackerProcessor.from_pretrained(self.model_id)

        self.tracker_model.eval()
        if self.use_fp16:
            self.tracker_model = self.tracker_model.half()

        self.tracker_model = self._maybe_compile_model(
            self.tracker_model,
            model_name="SAM3 tracker model"
        )

    def _normalize_images(
        self,
        images: Union[np.ndarray, List[np.ndarray], Image.Image, List[Image.Image]]
    ) -> List[Image.Image]:
        """Convert various image formats to list of PIL Images."""
        # Handle single image
        if isinstance(images, (np.ndarray, Image.Image)):
            images = [images]

        pil_images = []
        for img in images:
            if isinstance(img, np.ndarray):
                # Handle different numpy array shapes
                if img.ndim == 2:  # Grayscale
                    img = np.stack([img] * 3, axis=-1)
                elif img.shape[-1] == 4:  # RGBA
                    img = img[..., :3]

                # Ensure uint8
                if img.dtype != np.uint8:
                    if img.max() <= 1.0:
                        img = (img * 255).astype(np.uint8)
                    else:
                        img = img.astype(np.uint8)

                pil_images.append(Image.fromarray(img))
            elif isinstance(img, Image.Image):
                pil_images.append(img.convert("RGB"))
            else:
                raise TypeError(f"Unsupported image type: {type(img)}")

        return pil_images

    def _normalize_point_inputs(
        self,
        input_points: List,
        input_labels: List
    ) -> Tuple[List, List]:
        """
        Normalize point prompts for a single image into the nested structure
        expected by ``Sam3TrackerProcessor``.

        Accepted point formats:
        - ``[[x, y], [x, y]]``
        - ``[[[x, y], [x, y]]]``
        - ``[[[[x, y], [x, y]]]]``

        Accepted label formats:
        - ``[1, 0]``
        - ``[[1, 0]]``
        - ``[[[1, 0]]]``
        """
        if not input_points:
            raise ValueError("input_points must contain at least one point")
        if not input_labels:
            raise ValueError("input_labels must contain at least one label")

        if isinstance(input_points[0][0], (int, float)):
            normalized_points = [[input_points]]
        elif isinstance(input_points[0][0][0], (int, float)):
            normalized_points = [input_points]
        else:
            normalized_points = input_points

        if isinstance(input_labels[0], int):
            normalized_labels = [[input_labels]]
        elif isinstance(input_labels[0][0], int):
            normalized_labels = [input_labels]
        else:
            normalized_labels = input_labels

        num_points = len(normalized_points[0][0])
        num_labels = len(normalized_labels[0][0])
        if num_points != num_labels:
            raise ValueError(
                f"Number of points ({num_points}) must match number of labels ({num_labels})"
            )

        return normalized_points, normalized_labels

    @torch.inference_mode()
    def text_batch_infer(
        self,
        images: Union[np.ndarray, List[np.ndarray], Image.Image, List[Image.Image]],
        text_prompts: Union[str, List[str]],
        batch_size: int = 4,
        threshold: float = 0.5,
        mask_threshold: float = 0.5
    ) -> List[List[np.ndarray]]:
        """
        Run inference on images with text prompts.

        Args:
            images: Single image or list of images (numpy arrays or PIL Images)
            text_prompts: Single prompt or list of prompts (one per image)
            batch_size: Number of images to process per batch
            threshold: Confidence threshold for instance detection
            mask_threshold: Threshold for mask binarization

        Returns:
            List of lists, where each inner list contains [masks, boxes, scores] as numpy arrays:
            - masks: Binary masks resized to original image size
            - boxes: Bounding boxes in absolute pixel coordinates (xyxy format)
            - scores: Confidence scores
        """
        # Normalize inputs
        pil_images = self._normalize_images(images)
        n_images = len(pil_images)

        # Handle text prompts
        if isinstance(text_prompts, str):
            text_prompts = [text_prompts] * n_images
        elif len(text_prompts) != n_images:
            raise ValueError(
                f"Number of text prompts ({len(text_prompts)}) must match "
                f"number of images ({n_images})"
            )

        all_results = []

        # Process in batches
        for i in range(0, n_images, batch_size):
            batch_images = pil_images[i:i + batch_size]
            batch_prompts = text_prompts[i:i + batch_size]

            # Prepare inputs
            inputs = self.processor(
                images=batch_images,
                text=batch_prompts,
                return_tensors="pt"
            ).to(self.device)

            # Convert to FP16 if enabled
            if self.use_fp16:
                inputs = {
                    k: v.half() if v.dtype == torch.float32 else v
                    for k, v in inputs.items()
                }

            # Run inference
            outputs = self.model(**inputs)

            # Post-process results
            batch_results = self.processor.post_process_instance_segmentation(
                outputs,
                threshold=threshold,
                mask_threshold=mask_threshold,
                target_sizes=inputs.get("original_sizes").tolist()
            )

            # Convert to list format [masks, boxes, scores]
            batch_results = [
                [
                    r['masks'].cpu().numpy().astype(np.uint8) if 'masks' in r else np.array([]),
                    r['boxes'].cpu().numpy() if 'boxes' in r else np.array([]),
                    r['scores'].cpu().numpy() if 'scores' in r else np.array([])
                ]
                for r in batch_results
            ]

            all_results.extend(batch_results)

        return all_results

    @torch.inference_mode()
    def point_prompt_infer_single(
        self,
        input_points: List,
        input_labels: List,
        image: Optional[Union[np.ndarray, Image.Image]] = None,
        image_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        threshold: Optional[float] = None,
        mask_threshold: Optional[float] = None
    ) -> List[List[np.ndarray]]:
        """
        Run single-image mask refinement using positive/negative point prompts.

        Label semantics:
        - ``1``: positive point
        - ``0``: negative point

        Args:
            image: Input image as a numpy array or PIL image.
            image_path: Optional path to the input image file.
            output_dir: Optional directory for saving JSON/NPZ outputs.
            threshold: Optional score threshold metadata for saved results.
            mask_threshold: Optional mask threshold metadata for saved results.
            input_points: Point coordinates for one image. Supports simplified
                formats like ``[[x, y], [x, y]]`` and the fully nested
                processor format ``[[[[x, y], [x, y]]]]``.
            input_labels: Point labels aligned with ``input_points``. Supports
                ``[1, 0]`` as well as nested processor-compatible forms.

        Returns:
            A single-item batch matching ``text_batch_infer()`` output format:
            ``[[masks, boxes, scores]]`` where:
            - ``masks``: Post-processed masks in original image resolution.
            - ``boxes``: Empty array placeholder, since point prompting does
              not produce box outputs in this path.
            - ``scores``: Predicted mask quality / IoU scores when available.
        """
        empty_result = [[np.array([], dtype=np.uint8), np.array([]), np.array([])]]
        start_time = time.time()

        try:
            normalized_image_path: Optional[Path] = None
            if image is None:
                if image_path is None:
                    raise ValueError("Provide either image or image_path.")

                normalized_image_path = Path(image_path)
                if not normalized_image_path.exists():
                    raise FileNotFoundError(f"Test image not found: {normalized_image_path}")

                image = Image.open(normalized_image_path).convert("RGB")
            else:
                image = self._normalize_images([image])[0]
                if image_path is not None:
                    normalized_image_path = Path(image_path)

            normalized_points, normalized_labels = self._normalize_point_inputs(
                input_points=input_points,
                input_labels=input_labels
            )

            self._load_tracker_components()

            inputs = self.tracker_processor(
                images=image,
                input_points=normalized_points,
                input_labels=normalized_labels,
                return_tensors="pt"
            ).to(self.device)

            if self.use_fp16:
                inputs = {
                    k: v.half() if v.dtype == torch.float32 else v
                    for k, v in inputs.items()
                }

            outputs = self.tracker_model(**inputs)

            masks = self.tracker_processor.post_process_masks(
                outputs.pred_masks.detach().cpu(),
                inputs["original_sizes"].detach().cpu()
            )[0]

            if isinstance(masks, torch.Tensor):
                masks = masks.numpy()
            else:
                masks = np.asarray(masks)
            masks = (masks > 0).astype(np.uint8)

            scores = np.array([])
            if hasattr(outputs, "iou_scores") and outputs.iou_scores is not None:
                scores = outputs.iou_scores.detach().cpu().numpy()[0]

            result = [[masks, np.array([]), scores]]
            processing_time = time.time() - start_time

            if normalized_image_path is not None and output_dir is not None:
                output_path = save_result(
                    result=result[0],
                    image_path=normalized_image_path,
                    prompt=None,
                    output_dir=Path(output_dir),
                    model_id=self.model_id,
                    threshold=threshold,
                    mask_threshold=mask_threshold,
                    processing_time=processing_time,
                    prompt_type="point_prompt",
                    input_points=input_points,
                    input_labels=input_labels,
                    output_label="point_prompt"
                )
                print(f"Saved point prompt result: {output_path.with_suffix('.npz')}")

            print(f"Point prompt processing time: {processing_time:.2f}s")
            return result
        except Exception as e:
            print(f"Point prompt inference failed: {e}")
            return empty_result

    def infer_single(
        self,
        image: Union[np.ndarray, Image.Image],
        text_prompt: str,
        threshold: float = 0.5,
        mask_threshold: float = 0.5
    ) -> List[np.ndarray]:
        """
        Convenience method for single image inference.

        Returns:
            List containing [masks, boxes, scores] as numpy arrays
        """
        results = self.text_batch_infer(
            images=[image],
            text_prompts=[text_prompt],
            batch_size=1,
            threshold=threshold,
            mask_threshold=mask_threshold
        )
        return results[0]

    def get_memory_stats(self) -> dict:
        """Get current GPU memory usage (if using CUDA)."""
        if self.device == "cuda":
            return {
                'allocated_gb': torch.cuda.memory_allocated() / 1e9,
                'reserved_gb': torch.cuda.memory_reserved() / 1e9,
                'max_allocated_gb': torch.cuda.max_memory_allocated() / 1e9
            }
        return {}

    def clear_cache(self):
        """Clear GPU cache to free memory."""
        if self.device == "cuda":
            torch.cuda.empty_cache()


def sanitize_prompt(prompt: str) -> str:
    """Convert prompt to safe filename."""
    # Remove special characters and replace spaces with underscores
    sanitized = re.sub(r'[^\w\s-]', '', prompt)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized.lower().strip('_')[:50]  # Limit length


def get_image_files(directory: str) -> List[Path]:
    """Get all image files from directory."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.heic'}
    image_dir = Path(directory)
    
    if not image_dir.exists():
        raise ValueError(f"Directory does not exist: {directory}")
    
    if not image_dir.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")
    
    image_files = [
        f for f in image_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ]
    
    return sorted(image_files)


def parse_json_list_argument(raw_value: str, argument_name: str) -> List:
    """Parse a CLI JSON argument and enforce a list payload."""
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{argument_name} must be valid JSON: {exc}") from exc

    if not isinstance(parsed, list):
        raise ValueError(f"{argument_name} must be a JSON list")

    return parsed


def normalize_point_cli_inputs(input_points: List, input_labels: List) -> Tuple[List, List]:
    """Normalize point-prompt CLI payloads into model-compatible list forms."""
    if (
        len(input_points) == 2
        and all(isinstance(value, (int, float)) for value in input_points)
    ):
        input_points = [input_points]

    if not input_points:
        raise ValueError("--input-points must contain at least one point")
    if not input_labels:
        raise ValueError("--input-labels must contain at least one label")

    return input_points, input_labels


def point_prompt_json_example() -> str:
    """Return the preferred interactive point-prompt JSON example."""
    return (
        '{"image":"./images/IMG_7578.HEIC",'
        '"positive":[[538,1077],[3154,852]],'
        '"negative":[[1021,2243]]}'
    )


def print_point_prompt_help():
    """Print instructions for the interactive point-prompt loop."""
    print("\nHow to run point prompts:")
    print("  Type one JSON object per inference. The image value must be a full or relative path.")
    print("  Positive points mark the object you want to keep.")
    print("  Negative points mark nearby regions you want to exclude.")
    print("  Each point is [x, y] in original image pixels.")
    print("\nExamples:")
    print(f"  {point_prompt_json_example()}")
    print('  {"image":"./images/IMG_7617.HEIC","positive":[[527,1083]]}')
    print("\nAlternative format:")
    print('  {"image":"./images/IMG_7578.HEIC","points":[[538,1077],[1021,2243]],"labels":[1,0]}')
    print("\nCommands:")
    print("  help               Print this guide")
    print("  quit, exit, q      Exit interactive mode\n")


def parse_point_prompt_points(point_values: Any, field_name: str) -> List[List[Union[int, float]]]:
    """Validate an interactive positive/negative point list."""
    if point_values is None:
        return []
    if not isinstance(point_values, list):
        raise ValueError(f'"{field_name}" must be a list of [x, y] points.')

    points = []
    for index, point in enumerate(point_values):
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(
                f'"{field_name}" point #{index + 1} must be [x, y], got {point!r}.'
            )

        x, y = point
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            raise ValueError(
                f'"{field_name}" point #{index + 1} must use numeric x and y values, '
                f"got {point!r}."
            )

        points.append([x, y])

    return points


def validate_point_bounds(
    points: List[List[Union[int, float]]],
    image_path: Path,
    image_size: Tuple[int, int]
):
    """Raise a detailed error when a point is outside the image."""
    width, height = image_size
    for index, point in enumerate(points):
        x, y = point
        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError(
                f"Point #{index + 1} {point} is outside {image_path}. "
                f"Valid x range is 0 to {width - 1}; valid y range is 0 to {height - 1}."
            )


def load_image_size_for_point_prompt(image_path: Path) -> Tuple[int, int]:
    """Validate an image path and return the image dimensions."""
    if not image_path.exists():
        raise ValueError(
            f"Image path not found: {image_path}. "
            "Interactive mode uses path-only image input, so provide a valid full or relative path."
        )
    if not image_path.is_file():
        raise ValueError(f"Image path is not a file: {image_path}")

    try:
        with Image.open(image_path) as image:
            return image.size
    except Exception as exc:
        raise ValueError(
            f"File exists but could not be opened as an image: {image_path}. Error: {exc}"
        ) from exc


def parse_interactive_point_prompt_request(
    raw_value: str,
    inference_engine: SAM3Inference
) -> Tuple[Path, List, List]:
    """Parse and validate one interactive point-prompt JSON object."""
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Input must be one JSON object. JSON parse error: {exc}. "
            f"Example: {point_prompt_json_example()}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"Input must be one JSON object, not {type(payload).__name__}. "
            f"Example: {point_prompt_json_example()}"
        )

    image_value = payload.get("image")
    if not isinstance(image_value, str) or not image_value.strip():
        raise ValueError('"image" is required and must be a full or relative image path string.')

    image_path = Path(image_value.strip())
    image_size = load_image_size_for_point_prompt(image_path)

    uses_named_prompts = "positive" in payload or "negative" in payload
    uses_points_labels = "points" in payload or "labels" in payload

    if uses_named_prompts and uses_points_labels:
        raise ValueError('Use either "positive"/"negative" or "points"/"labels", not both.')

    if uses_points_labels:
        if "points" not in payload:
            raise ValueError('"points" is required when using "labels".')
        if "labels" not in payload:
            raise ValueError('"labels" is required when using "points".')

        if not isinstance(payload["points"], list):
            raise ValueError('"points" must be a JSON list.')
        if not isinstance(payload["labels"], list):
            raise ValueError('"labels" must be a JSON list.')

        try:
            input_points, input_labels = normalize_point_cli_inputs(
                payload["points"],
                payload["labels"]
            )
            normalized_points, normalized_labels = inference_engine._normalize_point_inputs(
                input_points=input_points,
                input_labels=input_labels
            )
        except (TypeError, IndexError, ValueError) as exc:
            raise ValueError(f"Invalid points/labels: {exc}") from exc

        flat_points = normalized_points[0][0]
        flat_labels = normalized_labels[0][0]
        for index, label in enumerate(flat_labels):
            if label not in (0, 1):
                raise ValueError(f"Label #{index + 1} must be 1 for positive or 0 for negative.")

        validate_point_bounds(flat_points, image_path, image_size)
        return image_path, input_points, input_labels

    positive_points = parse_point_prompt_points(payload.get("positive"), "positive")
    negative_points = parse_point_prompt_points(payload.get("negative"), "negative")
    input_points = positive_points + negative_points
    input_labels = [1] * len(positive_points) + [0] * len(negative_points)

    if not input_points:
        raise ValueError('At least one "positive" or "negative" point is required.')

    validate_point_bounds(input_points, image_path, image_size)
    return image_path, input_points, input_labels


def interactive_point_prompt_mode(
    inference_engine: SAM3Inference,
    output_dir: str,
    threshold: float,
    mask_threshold: float
):
    """Interactive loop for repeated point-prompt inference from JSON requests."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print("Interactive Point Prompt Mode - Model loaded and ready!")
    print("="*60)
    print_point_prompt_help()

    while True:
        try:
            user_input = input("point-prompt> ").strip()

            if not user_input:
                continue

            command = user_input.lower()

            if command in ['quit', 'exit', 'q']:
                print("\nExiting interactive point prompt mode.")
                break

            if command == 'help':
                print_point_prompt_help()
                continue

            try:
                image_path, input_points, input_labels = parse_interactive_point_prompt_request(
                    user_input,
                    inference_engine
                )
            except ValueError as e:
                print(f"Invalid request: {e}")
                continue

            print(f"\nRunning point prompt inference on {image_path}...")
            print(f"Points: {input_points}")
            print(f"Labels: {input_labels}")
            point_result = inference_engine.point_prompt_infer_single(
                image_path=image_path,
                input_points=input_points,
                input_labels=input_labels,
                output_dir=output_path,
                threshold=threshold,
                mask_threshold=mask_threshold
            )
            masks = point_result[0][0]
            scores = point_result[0][2]
            print(f"Masks shape: {masks.shape}")
            print(f"Scores: {scores}\n")

        except KeyboardInterrupt:
            print("\n\nReceived interrupt signal. Exiting...")
            break
        except EOFError:
            print("\nExiting interactive point prompt mode.")
            break


def save_result(
    result: List[np.ndarray],
    image_path: Path,
    prompt: Optional[str],
    output_dir: Path,
    model_id: str,
    threshold: Optional[float],
    mask_threshold: Optional[float],
    processing_time: float,
    prompt_type: str = "text",
    input_points: Optional[List] = None,
    input_labels: Optional[List] = None,
    output_label: Optional[str] = None
) -> Path:
    """
    Save inference result to JSON (metadata) and NPZ (numpy arrays) files.
    
    Args:
        result: List containing [masks, boxes, scores] as numpy arrays
        
    Returns:
        Path to the JSON file (metadata with reference to NPZ file)
    """
    if output_label is not None:
        prompt_slug = sanitize_prompt(output_label)
    elif prompt is not None:
        prompt_slug = sanitize_prompt(prompt)
    else:
        prompt_slug = sanitize_prompt(prompt_type)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"{image_path.stem}_{prompt_slug}.json"
    output_path = output_dir / output_filename
    
    # Generate NPZ filename (same stem, different extension)
    npz_filename = f"{image_path.stem}_{prompt_slug}.npz"
    npz_path = output_dir / npz_filename
    
    # Unpack result list: [masks, boxes, scores]
    masks = result[0] if len(result) > 0 else np.array([])
    boxes = result[1] if len(result) > 1 else np.array([])
    scores = result[2] if len(result) > 2 else np.array([])
    
    # Save numpy arrays to compressed NPZ file
    np.savez_compressed(npz_path, masks=masks, boxes=boxes, scores=scores)
    
    # Save metadata to JSON with reference to NPZ file
    metadata: Dict[str, Union[str, float, int, List]] = {
        'prompt_type': prompt_type,
        'image_filename': image_path.name,
        'image_path': str(image_path),
        'model_id': model_id,
        'timestamp': datetime.now().isoformat(),
        'processing_time_seconds': round(processing_time, 3),
        'num_objects_detected': len(scores) if isinstance(scores, np.ndarray) else 0,
        'npz_filename': npz_filename,
    }

    if threshold is not None:
        metadata['threshold'] = threshold
    if mask_threshold is not None:
        metadata['mask_threshold'] = mask_threshold

    if prompt_type == "text":
        metadata['text_prompt'] = prompt or ""
    elif prompt_type == "point_prompt":
        metadata['input_points'] = input_points or []
        metadata['input_labels'] = input_labels or []

    json_data = {'metadata': metadata}
    
    with open(output_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    return output_path


def batch_infer_directory(
    inference_engine: SAM3Inference,
    image_dir: str,
    prompt: str,
    output_dir: str,
    batch_size: int,
    threshold: float,
    mask_threshold: float,
    model_id: str
) -> Tuple[List[Path], List[Image.Image], List[List[np.ndarray]]]:
    """
    Process all images in a directory with a text prompt.
    
    Returns:
        Tuple of (image_paths, loaded_images, results)
        where results is a list of lists containing [masks, boxes, scores] for each image
    """
    print(f"\n{'='*60}")
    print(f"Starting batch inference")
    print(f"{'='*60}")
    print(f"Image directory: {image_dir}")
    print(f"Text prompt: '{prompt}'")
    print(f"Output directory: {output_dir}")
    print(f"Batch size: {batch_size}")
    print(f"{'='*60}\n")
    
    # Get all image files
    try:
        image_files = get_image_files(image_dir)
    except Exception as e:
        print(f"Error scanning directory: {e}")
        return [], [], []
    
    if not image_files:
        print(f"No image files found in {image_dir}")
        return [], [], []
    
    print(f"Found {len(image_files)} images to process\n")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load all images
    loaded_images = []
    valid_image_paths = []
    
    for img_path in image_files:
        try:
            # Open and convert to RGB (supports JPEG, PNG, HEIC, HEIF, WebP, etc.)
            img = Image.open(img_path).convert("RGB")
            loaded_images.append(img)
            valid_image_paths.append(img_path)
            print(f"✓ Loaded: {img_path.name} ({img.size[0]}x{img.size[1]})")
            
        except Exception as e:
            print(f"✗ Failed to load {img_path.name}: {e}")
    
    if not loaded_images:
        print("\nNo images could be loaded successfully")
        return [], [], []
    
    print(f"\nSuccessfully loaded {len(loaded_images)} images")
    
    # Run batch inference
    print(f"\nRunning inference with prompt: '{prompt}'...")
    start_time = time.time()
    
    try:
        results = inference_engine.text_batch_infer(
            images=loaded_images,
            text_prompts=prompt,
            batch_size=batch_size,
            threshold=threshold,
            mask_threshold=mask_threshold
        )
    except Exception as e:
        print(f"\nError during inference: {e}")
        return valid_image_paths, loaded_images, []
    
    total_time = time.time() - start_time
    
    # Save results
    print(f"\nSaving results...")
    saved_count = 0
    
    for img_path, result in zip(valid_image_paths, results):
        try:
            per_image_time = total_time / len(results)
            output_file = save_result(
                result=result,
                image_path=img_path,
                prompt=prompt,
                output_dir=output_path,
                model_id=model_id,
                threshold=threshold,
                mask_threshold=mask_threshold,
                processing_time=per_image_time,
                output_label="text_batch"
            )
            # result is now a list [masks, boxes, scores]
            num_objects = len(result[2]) if len(result) > 2 and isinstance(result[2], np.ndarray) else 0
            print(f"✓ Saved: {output_file.name} ({num_objects} objects detected)")
            saved_count += 1
        except Exception as e:
            print(f"✗ Failed to save result for {img_path.name}: {e}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Batch inference complete!")
    print(f"{'='*60}")
    print(f"Total images processed: {len(results)}")
    print(f"Results saved: {saved_count}")
    print(f"Total processing time: {total_time:.2f}s")
    print(f"Average time per image: {total_time/len(results):.2f}s")
    print(f"{'='*60}\n")
    
    return valid_image_paths, loaded_images, results


def interactive_mode(
    inference_engine: SAM3Inference,
    image_paths: List[Path],
    loaded_images: List[Image.Image],
    output_dir: str,
    batch_size: int,
    threshold: float,
    mask_threshold: float,
    model_id: str
):
    """
    Interactive loop for running inference with different prompts.
    """
    if not loaded_images:
        print("No images loaded. Exiting interactive mode.")
        return
    
    print("\n" + "="*60)
    print("Interactive Mode - Model loaded and ready!")
    print("="*60)
    print(f"{len(loaded_images)} images loaded in memory")
    print("\nCommands:")
    print("  - Enter a text prompt to run inference on all loaded images")
    print("  - Type 'help' for this message")
    print("  - Type 'quit', 'exit', or 'q' to exit")
    print("  - Press Ctrl+C to exit")
    print("="*60 + "\n")
    
    output_path = Path(output_dir)
    
    while True:
        try:
            user_input = input("Enter text prompt (or 'quit' to exit): ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nExiting interactive mode. Goodbye!")
                break
            
            if user_input.lower() == 'help':
                print("\nCommands:")
                print("  - Enter a text prompt to run inference on all loaded images")
                print("  - Type 'quit', 'exit', or 'q' to exit")
                print("  - Press Ctrl+C to exit\n")
                continue
            
            # Run inference with new prompt
            print(f"\nRunning inference with prompt: '{user_input}'...")
            start_time = time.time()
            
            try:
                results = inference_engine.text_batch_infer(
                    images=loaded_images,
                    text_prompts=user_input,
                    batch_size=batch_size,
                    threshold=threshold,
                    mask_threshold=mask_threshold
                )
                
                total_time = time.time() - start_time
                
                # Save results
                print(f"Saving results...")
                saved_count = 0
                total_objects = 0
                
                for img_path, result in zip(image_paths, results):
                    try:
                        per_image_time = total_time / len(results)
                        output_file = save_result(
                            result=result,
                            image_path=img_path,
                            prompt=user_input,
                            output_dir=output_path,
                            model_id=model_id,
                            threshold=threshold,
                            mask_threshold=mask_threshold,
                            processing_time=per_image_time
                        )
                        # result is now a list [masks, boxes, scores]
                        num_objects = len(result[2]) if len(result) > 2 and isinstance(result[2], np.ndarray) else 0
                        total_objects += num_objects
                        print(f"✓ {img_path.name}: {num_objects} objects")
                        saved_count += 1
                    except Exception as e:
                        print(f"✗ Failed to save result for {img_path.name}: {e}")
                
                print(f"\nComplete! Processed {len(results)} images in {total_time:.2f}s")
                print(f"Total objects detected: {total_objects}\n")
                
            except Exception as e:
                print(f"\nError during inference: {e}\n")
        
        except KeyboardInterrupt:
            print("\n\nReceived interrupt signal. Exiting...")
            break
        except EOFError:
            print("\nExiting interactive mode.")
            break


def main():
    """Main entry point for SAM3 inference."""
    parser = argparse.ArgumentParser(
        description="SAM3 Interactive Batch Inference - Load model once, run multiple inferences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Text batch inference (default mode)
  python sam3_inference.py --image-dir ./images --prompt "dog ear"
   
  # Explicitly specify text mode
  python sam3_inference.py --mode text-batch --image-dir ./images --prompt "cat"
   
  # Interactive point prompt mode (loads the model once, then waits for commands)
  python sam3_inference.py --mode point-prompt --output-dir ./results

  # One-shot point prompt mode (requires --no-interactive, --point-image, and --input-points)
  python sam3_inference.py --mode point-prompt --no-interactive --point-image ./images/IMG_7578.HEIC --input-points "[1094, 1021]"

Interactive point-prompt input:
  Type one JSON object per inference:
  {"image":"./images/IMG_7578.HEIC","positive":[[538,1077],[3154,852]],"negative":[[1021,2243]]}

  Positive points mark the object to keep; negative points mark regions to exclude.
  Use help for examples, or quit/exit/q to exit.
        """
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['text-batch', 'point-prompt'],
        default='text-batch',
        help='Inference mode (default: text-batch)'
    )
    
    parser.add_argument(
        '--image-dir',
        type=str,
        default=None,
        help='Directory containing images to process (required for --mode text-batch)'
    )
    
    parser.add_argument(
        '--prompt',
        type=str,
        default=None,
        help='Text prompt for segmentation (required for --mode text-batch)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='Directory to save JSON results (default: same as image-dir)'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=4,
        help='Number of images to process per batch (default: 4)'
    )
    
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.5,
        help='Confidence threshold for instance detection (default: 0.5)'
    )
    
    parser.add_argument(
        '--mask-threshold',
        type=float,
        default=0.5,
        help='Threshold for mask binarization (default: 0.5)'
    )
    
    parser.add_argument(
        '--model-id',
        type=str,
        default='facebook/sam3',
        help='HuggingFace model identifier (default: facebook/sam3)'
    )
    
    parser.add_argument(
        '--no-fp16',
        action='store_true',
        help='Disable FP16 half precision (use full FP32)'
    )
    
    parser.add_argument(
        '--no-interactive',
        action='store_true',
        help='Exit after text-batch processing, or run one-shot point-prompt inference'
    )

    parser.add_argument(
        '--point-image',
        type=str,
        default=None,
        help='Path to one image for one-shot point prompt inference (required with --mode point-prompt --no-interactive)'
    )

    parser.add_argument(
        '--input-points',
        type=str,
        default=None,
        help='Point coordinates as JSON list, e.g. "[[1094, 1021]]" (required with --mode point-prompt --no-interactive)'
    )

    parser.add_argument(
        '--input-labels',
        type=str,
        default='[1]',
        help='Point labels as JSON list, e.g. "[1]" (default: [1])'
    )
    
    args = parser.parse_args()

    parsed_points: Optional[List] = None
    parsed_labels: Optional[List] = None
    if args.mode == 'text-batch':
        if args.image_dir is None:
            parser.error("--image-dir is required when --mode text-batch")
        if not args.prompt:
            parser.error("--prompt is required when --mode text-batch")
    elif args.no_interactive:
        if args.point_image is None:
            parser.error("--point-image is required when --mode point-prompt --no-interactive")
        if args.input_points is None:
            parser.error("--input-points is required when --mode point-prompt --no-interactive")

        try:
            parsed_points = parse_json_list_argument(args.input_points, "--input-points")
            parsed_labels = parse_json_list_argument(args.input_labels, "--input-labels")
            parsed_points, parsed_labels = normalize_point_cli_inputs(parsed_points, parsed_labels)
        except ValueError as e:
            parser.error(str(e))
    
    # Set output directory based on selected mode when not specified
    if args.output_dir is None:
        if args.mode == 'text-batch':
            args.output_dir = args.image_dir
        elif args.point_image is not None:
            args.output_dir = str(Path(args.point_image).parent)
        else:
            args.output_dir = "./results"
    
    try:
        # Initialize model (loads once)
        print("\n" + "="*60)
        print("SAM3 Interactive Batch Inference")
        print("="*60 + "\n")
        

        inference_engine = SAM3Inference(
            model_id=args.model_id,
            half_precision=not args.no_fp16
        )
        
        if args.mode == 'text-batch':

            image_paths, loaded_images, _ = batch_infer_directory(
                inference_engine=inference_engine,
                image_dir=args.image_dir,
                prompt=args.prompt,
                output_dir=args.output_dir,
                batch_size=args.batch_size,
                threshold=args.threshold,
                mask_threshold=args.mask_threshold,
                model_id=args.model_id
            )

            # if loaded_images and not args.no_interactive:
            #     interactive_mode(
            #         inference_engine=inference_engine,
            #         image_paths=image_paths,
            #         loaded_images=loaded_images,
            #         output_dir=args.output_dir,
            #         batch_size=args.batch_size,
            #         threshold=args.threshold,
            #         mask_threshold=args.mask_threshold,
            #         model_id=args.model_id
            #     )
        else:
            output_path = Path(args.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            if not args.no_interactive:
                interactive_point_prompt_mode(
                    inference_engine=inference_engine,
                    output_dir=args.output_dir,
                    threshold=args.threshold,
                    mask_threshold=args.mask_threshold
                )
                return 0

            point_image_path = Path(args.point_image)

            print("\n" + "="*60)
            print("Running point prompt inference")
            print("="*60)
            print(f"Image: {point_image_path}")
            print(f"Points: {parsed_points}")
            print(f"Labels: {parsed_labels}")

            point_result = inference_engine.point_prompt_infer_single(
                image_path=point_image_path,
                input_points=parsed_points if parsed_points is not None else [],
                input_labels=parsed_labels if parsed_labels is not None else [],
                output_dir=output_path,
                threshold=args.threshold,
                mask_threshold=args.mask_threshold
            )

            masks = point_result[0][0]
            scores = point_result[0][2]
            print(f"Masks shape: {masks.shape}")
            print(f"Scores: {scores}")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
