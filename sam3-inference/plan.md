# Labelme Bridge Plan for SAM3 Text and Point Annotation

## Summary

Build a Labelme-centered workflow where users can request SAM3 text-prompt segmentation on TWCC, inspect the result directly in Labelme, and optionally add positive/negative point prompts in Labelme for a second SAM3 refinement pass.

TWCC remains the inference backend. Labelme becomes the human-facing annotation and review UI.

## Goals

- Let users start from a text prompt, such as `rebar`, when they know what object they want annotated.
- Let users inspect SAM3 masks in Labelme instead of relying on notebooks or raw `.npz` files.
- Let users add point prompts in Labelme when the text-prompt result needs refinement.
- Keep the existing metadata JSON and `.npz` result outputs for reproducibility and exact mask data.
- Add Labelme JSON output as the bridge between model inference and manual review.

## Workflow

### 1. Text-Prompt Inference

Users run SAM3 text-prompt inference locally or through TWCC:

```bash
python sam3_inference.py \
  --image-dir ./images \
  --prompt "rebar" \
  --output-dir ./results \
  --export-labelme
```

Expected outputs:

- Existing metadata JSON files in `results/`.
- Existing compressed mask arrays in `results/*.npz`.
- Labelme-openable result files in `results/labelme/`.

### 2. Labelme Review

Users open the images and generated Labelme annotations:

```bash
labelme ./images --output ./results/labelme
```

Users can inspect the predicted masks visually and decide whether refinement is needed.

### 3. Point-Prompt Refinement

If refinement is needed, users create point shapes in Labelme:

- `positive`: a foreground point inside the target object.
- `negative`: a background point outside the target object.

Then they run:

```bash
python sam3_inference.py \
  --image-dir ./images \
  --prompt "rebar" \
  --point-labelme-dir ./annotations \
  --output-dir ./results \
  --export-labelme
```

The script reads point annotations from `./annotations/<image_stem>.json`, runs SAM3 point-prompt inference, and writes refined Labelme mask JSON files under `results/labelme/`.

## CLI Changes

Add these arguments to `sam3_inference.py`:

- `--export-labelme`: Write Labelme JSON files for model outputs.
- `--point-labelme-dir PATH`: Directory containing Labelme JSON files with point prompts.
- `--labelme-output-dir PATH`: Optional explicit Labelme output directory. Defaults to `<output-dir>/labelme`.

Restore normal text-prompt inference as the default `main()` behavior. Remove the current hardcoded point-prompt test path from `main()`.

## Labelme Input Contract

Point prompt JSON files use normal Labelme point shapes.

Supported point labels:

- `positive` maps to SAM3 point label `1`.
- `negative` maps to SAM3 point label `0`.

Rules:

- Ignore non-point shapes when reading point prompts.
- Skip an image with a warning if its Labelme JSON contains no valid point prompts.
- Raise a clear validation error if a point shape has an unsupported label.
- Keep labels generic as `positive` and `negative`, not object-specific labels like `rebar_positive`, so the same UI works for future objects.

## Labelme Output Contract

The generated Labelme JSON should include:

- `version`
- `flags: {}`
- `shapes`
- `imagePath`
- `imageData: null`
- `imageHeight`
- `imageWidth`

Each SAM3 mask should be exported as a native Labelme mask shape:

- `label`: the semantic prompt, such as `rebar`.
- `shape_type`: `mask`.
- `points`: bounding box corners for the cropped mask, `[[x1, y1], [x2, y2]]`.
- `mask`: base64-encoded cropped binary mask image.
- `group_id`: unique per instance when multiple masks exist.
- `description`: optional score or provenance text.

Use the existing `.npz` output as the exact numeric source of truth. The Labelme JSON is for visual review and manual correction.

## Implementation Details

Add focused helpers in `sam3_inference.py`:

- `load_labelme_point_prompts(labelme_json_path) -> tuple[list[list[float]], list[int]]`
- `mask_to_labelme_shape(mask, label, score=None, group_id=None) -> dict`
- `save_labelme_result(image_path, masks, scores, output_path, label) -> Path`

For text-prompt outputs:

- Create one Labelme mask shape per detected SAM3 instance.
- Use `--prompt` as the output label.
- Preserve scores when available.

For point-prompt outputs:

- Parse `positive` and `negative` point shapes from Labelme JSON.
- Run `point_prompt_infer_single()`.
- Use `--prompt` as the output mask label.
- Save refined masks to Labelme JSON and keep the existing metadata/NPZ outputs.

When both text prompt and point prompt inputs are available:

- Run point-prompt inference for images with a matching point JSON.
- Run text-prompt inference for images without a matching point JSON.

## TWCC Script Changes

Update `run_sam3_on_twcc.sh` so it can support the Labelme bridge workflow:

- Upload `annotations/` when it exists.
- Pass `SAM3_POINT_LABELME_DIR` to the remote command when configured.
- Pass `--export-labelme` when `SAM3_EXPORT_LABELME=1`.
- Download all result files, including `results/labelme/`.

Keep existing `.env` requirements unchanged:

- `HF_TOKEN`
- `PEM_LOCATION`
- `TWCC_PASSWORD`

Do not add personal TWCC identifiers, usernames, hosts, ports, or site IDs to documentation.

## Documentation Updates

Update the README or repository notes with:

- How to install and launch Labelme.
- How to annotate `positive` and `negative` point prompts.
- How to run text-prompt inference.
- How to run point-prompt refinement.
- Where outputs are written.
- How to open generated Labelme JSON files for review.

Keep examples generic and free of personal account information.

## Test Plan

### Local Text-Prompt Test

Run:

```bash
python sam3_inference.py \
  --image-dir ./images \
  --prompt "rebar" \
  --output-dir ./results \
  --export-labelme \
  --no-interactive
```

Verify:

- Metadata JSON files are created.
- `.npz` files are created.
- Labelme JSON files are created under `results/labelme/`.
- Generated Labelme JSON opens in Labelme and displays mask shapes.

### Local Point-Prompt Test

Create a Labelme JSON with at least one `positive` point and optionally one `negative` point.

Run:

```bash
python sam3_inference.py \
  --image-dir ./images \
  --prompt "rebar" \
  --point-labelme-dir ./annotations \
  --output-dir ./results \
  --export-labelme \
  --no-interactive
```

Verify:

- Point prompts are parsed correctly.
- SAM3 point-prompt inference runs for matching images.
- Refined metadata JSON and `.npz` files are created.
- Refined Labelme JSON opens in Labelme.

### TWCC Text-Prompt Test

Run the TWCC workflow with only `SAM3_PROMPT=rebar`.

Verify:

- Existing text-prompt behavior still works.
- Results download to `results/`.
- Labelme outputs download when enabled.

### TWCC Point-Prompt Test

Run the TWCC workflow with an `annotations/` directory and `SAM3_POINT_LABELME_DIR` configured.

Verify:

- Annotation JSON files upload to TWCC.
- Point-prompt inference runs remotely.
- Refined results download locally.

## Assumptions

- V1 uses open-source Labelme as the UI, not Labelme's paid built-in AI features.
- Native Labelme mask shapes are preferred over polygon approximations.
- Point prompt labels are exactly `positive` and `negative`.
- `--prompt` remains the semantic output label, even when point prompts drive the actual segmentation.
- Existing `.npz` outputs remain the exact mask artifact.
- Labelme JSON is the review and correction bridge.
