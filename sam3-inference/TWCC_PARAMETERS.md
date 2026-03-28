# TWCC SAM3 Inference - Parameter Configuration

This document explains how to customize SAM3 inference parameters when running `run_sam3_on_twcc.sh`.

## Default Configuration

The script uses these default values:

```bash
SAM3_IMAGE_DIR="/tmp/sam3/images"      # Directory containing images on TWCC container
SAM3_PROMPT="rebar"                     # Text prompt for segmentation
SAM3_OUTPUT_DIR="/tmp/sam3/results"    # Output directory for results
SAM3_BATCH_SIZE="4"                     # Number of images per batch
SAM3_THRESHOLD="0.5"                    # Detection confidence threshold
SAM3_MODEL_ID="facebook/sam3"           # HuggingFace model identifier
```

## Customizing Parameters

### Method 1: Environment Variables (Recommended)

Set environment variables before running the script:

```bash
# Change the prompt to detect "dog"
export SAM3_PROMPT="dog"
./run_sam3_on_twcc.sh

# Change multiple parameters
export SAM3_PROMPT="person"
export SAM3_THRESHOLD="0.7"
export SAM3_BATCH_SIZE="8"
./run_sam3_on_twcc.sh
```

### Method 2: Add to .env File

Add parameters to your `.env` file:

```bash
# Add these lines to your .env file
SAM3_PROMPT="dog ear"
SAM3_THRESHOLD="0.6"
SAM3_BATCH_SIZE="8"
```

Then run the script normally:
```bash
./run_sam3_on_twcc.sh
```

### Method 3: Inline with Script

Set variables inline when running:

```bash
SAM3_PROMPT="cat" SAM3_THRESHOLD="0.7" ./run_sam3_on_twcc.sh
```

## Parameter Descriptions

### `SAM3_IMAGE_DIR`
- **Type:** String (path)
- **Default:** `/tmp/sam3/images`
- **Description:** Directory on the TWCC container containing images to process
- **Example:** `/tmp/sam3/images`

### `SAM3_PROMPT`
- **Type:** String
- **Default:** `"rebar"`
- **Description:** Text prompt for segmentation (what object to detect)
- **Examples:** 
  - `"dog"`
  - `"person"`
  - `"ear"`
  - `"rebar"`
  - `"cat face"`

### `SAM3_OUTPUT_DIR`
- **Type:** String (path)
- **Default:** `/tmp/sam3/results`
- **Description:** Directory where JSON results will be saved
- **Example:** `/tmp/sam3/results`

### `SAM3_BATCH_SIZE`
- **Type:** Integer
- **Default:** `4`
- **Description:** Number of images to process per batch. Increase for better GPU utilization (if you have enough memory)
- **Range:** 1-32 (depends on GPU memory)
- **Examples:**
  - `2` - For limited GPU memory
  - `4` - Default, balanced
  - `8` - For larger GPU memory
  - `16` - For very large GPU memory

### `SAM3_THRESHOLD`
- **Type:** Float
- **Default:** `0.5`
- **Description:** Confidence threshold for object detection. Higher values = more selective (fewer, higher-confidence detections)
- **Range:** 0.0-1.0
- **Examples:**
  - `0.3` - More detections (less selective)
  - `0.5` - Balanced (default)
  - `0.7` - Fewer detections (more selective)
  - `0.9` - Very selective (only high-confidence detections)

### `SAM3_MODEL_ID`
- **Type:** String
- **Default:** `"facebook/sam3"`
- **Description:** HuggingFace model identifier
- **Example:** `"facebook/sam3"`

## Usage Examples

### Example 1: Detect dogs with high confidence
```bash
export SAM3_PROMPT="dog"
export SAM3_THRESHOLD="0.8"
./run_sam3_on_twcc.sh
```

### Example 2: Detect rebar with custom batch size
```bash
export SAM3_PROMPT="rebar"
export SAM3_BATCH_SIZE="8"
export SAM3_THRESHOLD="0.6"
./run_sam3_on_twcc.sh
```

### Example 3: Multiple object types (run script multiple times)
```bash
# First run: detect dogs
export SAM3_PROMPT="dog"
./run_sam3_on_twcc.sh

# Second run: detect cats
export SAM3_PROMPT="cat"
./run_sam3_on_twcc.sh

# Third run: detect people
export SAM3_PROMPT="person"
./run_sam3_on_twcc.sh
```

### Example 4: Quick one-liner
```bash
SAM3_PROMPT="ear" SAM3_THRESHOLD="0.7" ./run_sam3_on_twcc.sh
```

## Viewing Configuration

When the script runs, it will display the current configuration:

```
[12:34:56] SAM3 Inference Configuration:
[12:34:56]   Image Directory: /tmp/sam3/images
[12:34:56]   Prompt: 'rebar'
[12:34:56]   Output Directory: /tmp/sam3/results
[12:34:56]   Batch Size: 4
[12:34:56]   Threshold: 0.5
[12:34:56]   Model ID: facebook/sam3
```

This lets you verify the parameters before the inference runs.

## Tips

1. **Start with defaults** - The default values work well for most cases
2. **Adjust threshold** - If you're getting too many/few detections, adjust `SAM3_THRESHOLD`
3. **Increase batch size** - If you have a powerful GPU, increase `SAM3_BATCH_SIZE` for faster processing
4. **Experiment with prompts** - Try different text prompts to see what works best for your images

## Troubleshooting

**Q: I changed the parameters but nothing happened**
A: Make sure you're exporting the variables (`export VAR=value`) or adding them to `.env`

**Q: Out of memory errors**
A: Reduce `SAM3_BATCH_SIZE` to 2 or 1

**Q: Too many false detections**
A: Increase `SAM3_THRESHOLD` to 0.7 or 0.8

**Q: Missing valid detections**
A: Decrease `SAM3_THRESHOLD` to 0.3 or 0.4
