import torch
import numpy as np
from typing import Union, List, Optional, Tuple, Dict
from PIL import Image
from transformers import Sam3Model, Sam3Processor
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
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.use_fp16 = half_precision and self.device == "cuda"

        print(f"Loading SAM3 model to {self.device} (FP16: {self.use_fp16})...")

        # Load model and processor
        self.model = Sam3Model.from_pretrained(model_id).to(self.device)
        self.processor = Sam3Processor.from_pretrained(model_id)

        # Optimize model
        self.model.eval()
        if self.use_fp16:
            self.model = self.model.half()

        # Compile model for faster inference (PyTorch 2.0+)
        if hasattr(torch, 'compile') and self.device == "cuda":
            try:
                self.model = torch.compile(self.model, mode="reduce-overhead")
                print("Model compiled with torch.compile")
            except Exception as e:
                print(f"Could not compile model: {e}")

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

    @torch.inference_mode()
    def infer(
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

            print("masks")
            print("shape", batch_results[0]['masks'].shape)
            print(batch_results[0]['masks'])

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
        results = self.infer(
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


def save_result(
    result: List[np.ndarray],
    image_path: Path,
    prompt: str,
    output_dir: Path,
    model_id: str,
    threshold: float,
    mask_threshold: float,
    processing_time: float
) -> Path:
    """
    Save inference result to JSON file with metadata.
    
    Args:
        result: List containing [masks, boxes, scores] as numpy arrays
    """
    prompt_slug = sanitize_prompt(prompt)
    output_filename = f"{image_path.stem}_{prompt_slug}.json"
    output_path = output_dir / output_filename
    
    # Convert numpy arrays to lists for JSON serialization
    def convert_to_serializable(obj):
        """Convert numpy arrays to lists recursively."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (list, tuple)):
            return [convert_to_serializable(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: convert_to_serializable(value) for key, value in obj.items()}
        else:
            return obj
    
    # Unpack result list: [masks, boxes, scores]
    masks = result[0] if len(result) > 0 else np.array([])
    boxes = result[1] if len(result) > 1 else np.array([])
    scores = result[2] if len(result) > 2 else np.array([])
    
    serializable_result = {
        'metadata': {
            'image_filename': image_path.name,
            'image_path': str(image_path),
            'text_prompt': prompt,
            'model_id': model_id,
            'threshold': threshold,
            'mask_threshold': mask_threshold,
            'timestamp': datetime.now().isoformat(),
            'processing_time_seconds': round(processing_time, 3),
            'num_objects_detected': len(scores) if isinstance(scores, np.ndarray) else 0
        },
        'results': {
            'masks': convert_to_serializable(masks),
            'boxes': convert_to_serializable(boxes),
            'scores': convert_to_serializable(scores)
        }
    }
    
    with open(output_path, 'w') as f:
        json.dump(serializable_result, f, indent=2)
    
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
        results = inference_engine.infer(
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
                processing_time=per_image_time
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
                results = inference_engine.infer(
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
    """Main entry point for SAM3 batch inference."""
    parser = argparse.ArgumentParser(
        description="SAM3 Interactive Batch Inference - Load model once, run multiple inferences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with required arguments
  python sam3_inference.py --image-dir ./images --prompt "dog ear"
  
  # Specify output directory
  python sam3_inference.py --image-dir ./images --prompt "cat" --output-dir ./results
  
  # Adjust inference parameters
  python sam3_inference.py --image-dir ./images --prompt "person" --threshold 0.7 --batch-size 8
        """
    )
    
    parser.add_argument(
        '--image-dir',
        type=str,
        required=True,
        help='Directory containing images to process'
    )
    
    parser.add_argument(
        '--prompt',
        type=str,
        required=True,
        help='Initial text prompt for segmentation (e.g., "dog", "ear", "person")'
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
        help='Exit after batch processing (do not enter interactive mode)'
    )
    
    args = parser.parse_args()
    
    # Set output directory to image directory if not specified
    if args.output_dir is None:
        args.output_dir = args.image_dir
    
    try:
        # Initialize model (loads once)
        print("\n" + "="*60)
        print("SAM3 Interactive Batch Inference")
        print("="*60 + "\n")
        
        inference_engine = SAM3Inference(
            model_id=args.model_id,
            half_precision=not args.no_fp16
        )
        
        # Run initial batch inference
        image_paths, loaded_images, results = batch_infer_directory(
            inference_engine=inference_engine,
            image_dir=args.image_dir,
            prompt=args.prompt,
            output_dir=args.output_dir,
            batch_size=args.batch_size,
            threshold=args.threshold,
            mask_threshold=args.mask_threshold,
            model_id=args.model_id
        )
        
        # # We will develop interactive mode in the next step, so we will comment it out for now. The batch inference will still run and save results, but the interactive loop will be disabled until we implement it.
        # # Enter interactive mode if batch processing succeeded and not disabled
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
