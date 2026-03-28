# SAM3 Interactive Batch Inference

An interactive command-line tool for running batch inference with the SAM3 (Segment Anything Model 3) using text prompts. The tool loads the model once and allows you to experiment with different prompts on the same set of images without reloading the model.

## Features

- **Single Model Loading**: Load the SAM3 model once and reuse it for multiple inferences
- **Batch Processing**: Process all images in a directory with a single text prompt
- **Interactive Mode**: Enter new prompts interactively to re-run inference on the same images
- **Flexible Output**: Saves results as individual JSON files with comprehensive metadata
- **Error Handling**: Robust error handling with graceful degradation (skips failed images)
- **GPU Optimization**: Automatic FP16 support for CUDA, torch.compile optimization
- **Progress Tracking**: Clear progress indicators and summaries

## Installation

```bash
# Clone or navigate to the repository
cd sam3-inference

# Install dependencies
pip install -r requirements.txt
```

Required packages:
- torch
- torchvision
- transformers
- Pillow
- requests

## Usage

### Basic Usage

Process all images in a directory with an initial text prompt:

```bash
python sam3_inference.py --image-dir ./images --prompt "dog ear"
```

This will:
1. Load the SAM3 model once
2. Process all images in `./images` with the prompt "dog ear"
3. Save results as JSON files in the same directory
4. Enter interactive mode for additional prompts

### Specify Output Directory

```bash
python sam3_inference.py --image-dir ./images --prompt "cat" --output-dir ./results
```

### Adjust Inference Parameters

```bash
python sam3_inference.py \
  --image-dir ./images \
  --prompt "person" \
  --threshold 0.7 \
  --mask-threshold 0.6 \
  --batch-size 8
```

### Non-Interactive Mode

Exit after batch processing without entering interactive mode:

```bash
python sam3_inference.py --image-dir ./images --prompt "dog" --no-interactive
```

### Full Parameter List

```
--image-dir IMAGE_DIR       Directory containing images to process (required)
--prompt PROMPT             Initial text prompt for segmentation (required)
--output-dir OUTPUT_DIR     Directory to save JSON results (default: same as image-dir)
--batch-size BATCH_SIZE     Number of images to process per batch (default: 4)
--threshold THRESHOLD       Confidence threshold for detection (default: 0.5)
--mask-threshold MASK_THRESHOLD  Threshold for mask binarization (default: 0.5)
--model-id MODEL_ID         HuggingFace model identifier (default: facebook/sam3)
--no-fp16                   Disable FP16 half precision (use full FP32)
--no-interactive            Exit after batch processing
```

## Interactive Mode

After the initial batch processing completes, the tool enters interactive mode where you can:

1. **Enter new prompts**: Type any text prompt to re-run inference on all loaded images
2. **View help**: Type `help` to see available commands
3. **Exit**: Type `quit`, `exit`, `q`, or press `Ctrl+C` to exit

Example interactive session:

```
Enter text prompt (or 'quit' to exit): dog
Running inference with prompt: 'dog'...
✓ IMG_7566.HEIC: 2 objects
✓ IMG_7578.HEIC: 1 objects
✓ IMG_7616.HEIC: 3 objects
Complete! Processed 3 images in 2.45s

Enter text prompt (or 'quit' to exit): ear
Running inference with prompt: 'ear'...
✓ IMG_7566.HEIC: 4 objects
✓ IMG_7578.HEIC: 2 objects
✓ IMG_7616.HEIC: 5 objects
Complete! Processed 3 images in 1.89s

Enter text prompt (or 'quit' to exit): quit
Exiting interactive mode. Goodbye!
```

## Output Format

Results are saved as individual JSON files with the naming pattern:
```
{image_name}_{prompt_slug}.json
```

For example:
- `IMG_7566_dog_ear.json`
- `IMG_7566_cat.json`
- `photo_person.json`

### JSON Structure

Each JSON file contains:

```json
{
  "metadata": {
    "image_filename": "IMG_7566.HEIC",
    "image_path": "/path/to/images/IMG_7566.HEIC",
    "text_prompt": "dog ear",
    "model_id": "facebook/sam3",
    "threshold": 0.5,
    "mask_threshold": 0.5,
    "timestamp": "2026-03-28T12:00:00.000000",
    "processing_time_seconds": 0.823,
    "num_objects_detected": 2
  },
  "results": {
    "masks": [
      [[0, 0, 1, ...], ...],  // Binary masks (2D arrays)
      [[0, 1, 1, ...], ...]
    ],
    "scores": [0.95, 0.87],   // Confidence scores
    "labels": [1, 1]           // Class labels
  }
}
```

## Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- BMP (.bmp)
- TIFF (.tiff, .tif)
- WebP (.webp)
- HEIC (.heic) - if Pillow has HEIC support

## API Usage (Library Mode)

You can also import and use the `SAM3Inference` class in your own Python scripts:

```python
from sam3_inference import SAM3Inference
from PIL import Image

# Initialize model (loads once)
inference = SAM3Inference(model_id="facebook/sam3")

# Load images
images = [Image.open("img1.jpg"), Image.open("img2.jpg")]

# Run inference
results = inference.infer(
    images=images,
    text_prompts="dog",  # Single prompt for all images
    batch_size=4,
    threshold=0.5
)

# Process results
for i, result in enumerate(results):
    print(f"Image {i}: {len(result['scores'])} objects detected")
    print(f"Scores: {result['scores']}")
```

## Performance Tips

1. **Batch Size**: Increase `--batch-size` if you have sufficient GPU memory (default: 4)
2. **FP16**: Keep FP16 enabled for CUDA (default) for faster inference with minimal quality loss
3. **Threshold**: Adjust `--threshold` to control detection sensitivity (higher = more selective)
4. **Interactive Mode**: Images are cached in memory, so re-running with new prompts is very fast

## Error Handling

The tool includes comprehensive error handling:

- Invalid directory paths → Clear error message
- No images found → Informative message and graceful exit
- Corrupt image files → Skips and continues with other images
- Model inference errors → Reports error and continues
- File I/O errors → Reports error and continues

## Memory Management

For large datasets or limited memory:

```python
# In your code, you can call:
inference.clear_cache()  # Clear GPU cache
inference.get_memory_stats()  # Check GPU memory usage
```

## License

This tool uses the SAM3 model from Meta AI via HuggingFace Transformers.

## Troubleshooting

**Q: "No module named 'torchvision'"**
A: Install torchvision: `pip install torchvision`

**Q: "No images found in directory"**
A: Ensure your directory contains supported image formats (jpg, png, etc.)

**Q: Out of memory errors**
A: Reduce `--batch-size` or use `--no-fp16` to disable half precision

**Q: Interactive mode doesn't accept input**
A: Make sure you're running in an interactive terminal, not redirecting input

## Examples

### Example 1: Process dog photos
```bash
python sam3_inference.py --image-dir ./dog_photos --prompt "dog"
# Then in interactive mode:
# > ear
# > nose
# > tail
```

### Example 2: High-precision segmentation
```bash
python sam3_inference.py \
  --image-dir ./medical_images \
  --prompt "tissue" \
  --threshold 0.8 \
  --mask-threshold 0.8 \
  --no-fp16
```

### Example 3: Batch-only mode (no interaction)
```bash
python sam3_inference.py \
  --image-dir ./dataset \
  --prompt "object" \
  --output-dir ./results \
  --no-interactive
```
