# YOLO26 Rebar Segmentation Training Walkthrough

This walkthrough trains and tunes a YOLO26 segmentation model for rebar images
using three dataset sources:

- Dataset A: open-source Roboflow-style rebar segmentation dataset, about 1000
  images.
- Dataset B: custom rebar images labeled with SAM3, about 60 images.
- Dataset C: open-source rebar images relabeled with SAM3, about 40 images.

The final model should work on the future deployment domain, so Dataset B is the
source of the final custom test set. Never tune on the custom test set.

## 1. Version Names

Use stable names for every source dataset, mixed dataset, augmentation variant,
and model run. These names should appear in folder names, `data.yaml` paths,
training run names, result tables, and final reports.

### Source Dataset Versions

| Dataset | Version Name | Description | Expected Count |
|---|---|---|---:|
| A | `ds-a-open-rebar-v1` | Open-source rebar segmentation dataset | about 1000 |
| B | `ds-b-custom-sam3-v1` | Custom deployment-style rebar images labeled with SAM3 | about 60 |
| C | `ds-c-open-sam3-v1` | Open-source rebar images relabeled with SAM3 | about 40 |

Because those defaults may not match the dataset you want to train, always pass
the dataset YAML explicitly with `--data` locally or `TRAIN_DATA` on TWCC.

### Mixed Dataset Recipe Names

| Recipe | Version Name | Training Data | Purpose |
|---|---|---|---|
| R1 | `mix-r1-a-v1` | A only | Large open-source baseline |
| R2 | `mix-r2-a-b-v1` | A + B | Check whether custom data improves deployment performance |
| R3 | `mix-r3-a-c-v1` | A + C | Check whether SAM3 relabeling helps |
| R4 | `mix-r4-a-b-c-v1` | A + B + C | Full mixed dataset |
| R5 | `mix-r5-a-boversample-c-v1` | A + oversampled B + C | Prioritize the custom deployment domain |
| R6 | `mix-r6-b-c-v1` | B + C only | Small-domain-only baseline |

### Augmentation Variant Names

| Variant | Name Suffix | Description |
|---|---|---|
| Aug0 | `aug0` | No offline augmentation; train only on original training images |
| Aug3x | `aug3x` | Offline augment training images only until the training set is 3x size |

Name dataset variants by appending the augmentation suffix:

```text
mix-r4-a-b-c-v1-aug0
mix-r4-a-b-c-v1-aug3x
```

### Model Version Names

Use this pattern:

```text
<model-size>-<recipe>-<augmentation>-<stage>-v<version>
```

Examples:

```text
yolo26l-r4-aug0-baseline-v1
yolo26l-r4-aug3x-baseline-v1
yolo26l-r4-aug3x-tune-v1
yolo26l-r4-aug3x-final-v1
yolo26x-r5-aug3x-final-v1
```

Use `baseline` for first-round fixed-hyperparameter experiments, `tune` for Ray
Tune trials, and `final` for full retraining after tuning.

## 2. Prepare the Environment

Work from the repo root:

```bash
cd /Users/hungkaihsiao/Documents/rebar-works
```

Create and activate a Python environment, then install the training
dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r model-training/rebar-segementation-yolo26/requirements.txt
```

For Ray Tune, add Ray separately:

```bash
python -m pip install "ray[tune]"
```

Confirm the training entrypoint is available:

```bash
python model-training/rebar-segementation-yolo26/train.py --help
```

## 3. Prepare Each Source Dataset

Each source dataset must be converted to YOLO segmentation format before mixing
recipes. The expected structure is:

```text
<dataset-name>/
  data.yaml
  train/
    images/
    labels/
  valid/
    images/
    labels/
  test/
    images/
    labels/
```

Each image must have a same-stem `.txt` label file. For segmentation, each label
line should contain:

```text
class_id x1 y1 x2 y2 x3 y3 ...
```

Coordinates must be normalized to `0.0-1.0`. Use one class schema across all
datasets. If the final task is simply rebar segmentation, prefer one class:

```yaml
nc: 1
names: ["rebar"]
```

If retaining the current open-source labels with both `rebar` and `rebars`, keep
that schema consistent across A, B, C, and every mixed dataset:

```yaml
nc: 2
names: ["rebar", "rebars"]
```

Do not mix class schemas between datasets.

Recommended source dataset folders:

```text
model-training/datasets/ds-a-open-rebar-v1
model-training/datasets/ds-b-custom-sam3-v1
model-training/datasets/ds-c-open-sam3-v1
```

Validate each source dataset before splitting or mixing:

```bash
find model-training/datasets/ds-a-open-rebar-v1 -type f -path "*/images/*" | wc -l
find model-training/datasets/ds-a-open-rebar-v1 -type f -path "*/labels/*" | wc -l
sed -n '1,40p' model-training/datasets/ds-a-open-rebar-v1/data.yaml
```

Repeat for `ds-b-custom-sam3-v1` and `ds-c-open-sam3-v1`. The image and label
counts should match for each dataset.

## 4. Split Before Augmentation

Split original images first. Only after the split should any offline
augmentation be created.

Correct order:

```text
original images -> train/valid/test split -> augment train only
```

Wrong order:

```text
original images -> augment all images -> random train/valid/test split
```

Recommended split:

| Dataset | Train | Validation | Test |
|---|---:|---:|---:|
| `ds-a-open-rebar-v1` | 900 | 100 | 0 |
| `ds-b-custom-sam3-v1` | 35 | 10 | 15 |
| `ds-c-open-sam3-v1` | 30 | 10 | 0 |

Use Dataset B for the final custom test distribution because it best represents
deployment images.

Track validation and test groups separately:

| Evaluation Set | Source | Use |
|---|---|---|
| `valid_all` | Validation images from A, B, and C | Secondary model selection metric |
| `valid_custom` | Validation images from B only | Primary model selection and tuning metric |
| `test_custom` | Test images from B only | Final report only |

Do not tune on `test_custom`. Do not inspect `test_custom` repeatedly during
model development.

## 5. Build Dataset Recipes

Create one folder per recipe and augmentation variant under
`model-training/datasets/`. Each folder should contain its own `data.yaml`.

Recommended folders:

```text
model-training/datasets/mix-r1-a-v1-aug0
model-training/datasets/mix-r1-a-v1-aug3x
model-training/datasets/mix-r2-a-b-v1-aug0
model-training/datasets/mix-r2-a-b-v1-aug3x
model-training/datasets/mix-r4-a-b-c-v1-aug0
model-training/datasets/mix-r4-a-b-c-v1-aug3x
model-training/datasets/mix-r5-a-boversample-c-v1-aug0
model-training/datasets/mix-r5-a-boversample-c-v1-aug3x
model-training/datasets/mix-r6-b-c-v1-aug0
model-training/datasets/mix-r6-b-c-v1-aug3x
```

For `aug0`, copy or link only the original training images. For `aug3x`,
augment training images only. Validation and test images must stay original.

Allowed offline augmentations for `aug3x`:

- Small rotation.
- Scale and crop.
- Brightness and contrast changes.
- Mild blur or noise.
- Mild perspective transform.
- Horizontal or vertical flip only if physically valid for the deployment
  camera setup.

Avoid:

- Unrealistic color changes.
- Heavy blur.
- Extreme rotations.
- Strong cutout that hides labeled rebar.
- Any augmentation of validation or test images.

For R5, oversample Dataset B by duplicating or augmenting its training images so
custom examples have more influence. Keep validation and test sets unchanged.

## 6. Run Baseline Experiments

Run short fixed-hyperparameter experiments before Ray Tune. Use the same model
size, image size, seed if supported, and training length across all baselines.

Recommended first-round experiments:

| Experiment | Dataset Variant | Model Version Name |
|---|---|---|
| E1 | `mix-r1-a-v1-aug0` | `yolo26l-r1-aug0-baseline-v1` |
| E2 | `mix-r1-a-v1-aug3x` | `yolo26l-r1-aug3x-baseline-v1` |
| E3 | `mix-r2-a-b-v1-aug0` | `yolo26l-r2-aug0-baseline-v1` |
| E4 | `mix-r2-a-b-v1-aug3x` | `yolo26l-r2-aug3x-baseline-v1` |
| E5 | `mix-r4-a-b-c-v1-aug0` | `yolo26l-r4-aug0-baseline-v1` |
| E6 | `mix-r4-a-b-c-v1-aug3x` | `yolo26l-r4-aug3x-baseline-v1` |
| E7 | `mix-r5-a-boversample-c-v1-aug0` | `yolo26l-r5-aug0-baseline-v1` |
| E8 | `mix-r5-a-boversample-c-v1-aug3x` | `yolo26l-r5-aug3x-baseline-v1` |
| E9 | `mix-r6-b-c-v1-aug0` | `yolo26l-r6-aug0-baseline-v1` |
| E10 | `mix-r6-b-c-v1-aug3x` | `yolo26l-r6-aug3x-baseline-v1` |

Local baseline command template:

```bash
python model-training/rebar-segementation-yolo26/train.py \
  --model yolo26l-seg.pt \
  --data model-training/datasets/mix-r4-a-b-c-v1-aug3x/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 4 \
  --device auto \
  --project model-training/rebar-segementation-yolo26/results \
  --name yolo26l-r4-aug3x-baseline-v1 \
  --patience 20 \
  --workers 0
```

TWCC baseline command template:

```bash
TRAIN_MODEL=yolo26l-seg.pt \
TRAIN_DATA=/tmp/rebar-training/datasets/mix-r4-a-b-c-v1-aug3x/data.yaml \
TRAIN_EPOCHS=50 \
TRAIN_IMGSZ=640 \
TRAIN_BATCH=16 \
TRAIN_NAME=yolo26l-r4-aug3x-baseline-v1 \
model-training/rebar-segementation-yolo26/scripts/train_rebar_seg_yolo26_v3.sh
```

The TWCC script currently uploads
`datasets/sam3_annotation_with_open_source_rebar`. If training a different
named dataset variant, update the dataset folder expected by the script or stage
the selected variant at the path the script uploads before running.

For each baseline, record:

- Model version name.
- Dataset variant name.
- Model checkpoint, image size, batch size, epoch count, and device.
- `valid_all` mAP, precision, recall, and per-class AP.
- `valid_custom` mAP, precision, recall, and per-class AP.
- Common false positives and false negatives.

Do not train every recipe for 100+ epochs in this stage. The goal is to pick the
best 1-2 dataset and augmentation combinations for tuning.

## 7. Select Recipes for Ray Tune

Rank baseline runs using this priority:

1. Best `valid_custom` performance.
2. Acceptable `valid_all` performance.
3. Error analysis on custom validation images.
4. Lower false positives and false negatives for deployment-like scenes.

Recommended outcome:

```text
selected_dataset_variant_1 = mix-r4-a-b-c-v1-aug3x
selected_model_prefix_1 = yolo26l-r4-aug3x

selected_dataset_variant_2 = mix-r5-a-boversample-c-v1-aug3x
selected_model_prefix_2 = yolo26l-r5-aug3x
```

Use the actual winners from the baseline table. Do not include `test_custom` in
this decision.

## 8. Run Ray Tune

Run Ray Tune only after selecting the best dataset recipe and augmentation mode.
Use short trials first, usually `20-40` epochs, and use ASHA early stopping.

Primary tuning metric:

```text
valid_custom mAP
```

Secondary metric:

```text
valid_all mAP
```

Initial search space:

```python
{
    "lr0": tune.loguniform(1e-5, 1e-2),
    "weight_decay": tune.loguniform(1e-6, 1e-3),
    "mosaic": tune.uniform(0.0, 1.0),
    "mixup": tune.uniform(0.0, 0.3),
    "hsv_h": tune.uniform(0.0, 0.05),
    "scale": tune.uniform(0.2, 0.9),
}
```

If compute allows, include the selected dataset variant as a categorical
parameter:

```python
{
    "dataset_variant": tune.choice([
        "mix-r4-a-b-c-v1-aug3x",
        "mix-r5-a-boversample-c-v1-aug3x",
    ]),
}
```

Name Ray Tune runs with the same model naming convention:

```text
yolo26l-r4-aug3x-tune-v1-trial-0001
yolo26l-r5-aug3x-tune-v1-trial-0002
```

A practical trainable function should:

1. Receive the Ray config.
2. Resolve the `data.yaml` path from the named dataset variant.
3. Run `YOLO(...).train(...)` with the trial hyperparameters.
4. Evaluate on `valid_custom`.
5. Report `valid_custom_map` to Ray.

Keep Ray Tune outputs in a separate folder:

```text
model-training/rebar-segementation-yolo26/results/ray-tune-v1
```

After tuning, export a compact table with:

- Trial name.
- Dataset variant.
- Hyperparameters.
- Best epoch.
- `valid_custom` metrics.
- `valid_all` metrics.
- Checkpoint path.

## 9. Final Training

After Ray Tune:

1. Select the top 3 configurations by `valid_custom`.
2. Retrain each selected configuration from the base YOLO26 checkpoint.
3. Use full training length, usually `100-300` epochs depending on convergence.
4. Pick the best final model using validation metrics and error analysis.
5. Evaluate the selected model once on `test_custom`.

Final model version names:

```text
yolo26l-r4-aug3x-final-v1
yolo26l-r5-aug3x-final-v1
yolo26x-r5-aug3x-final-v1
```

Final training command template:

```bash
python model-training/rebar-segementation-yolo26/train.py \
  --model yolo26l-seg.pt \
  --data model-training/datasets/mix-r4-a-b-c-v1-aug3x/data.yaml \
  --epochs 200 \
  --imgsz 640 \
  --batch 4 \
  --device auto \
  --project model-training/rebar-segementation-yolo26/results \
  --name yolo26l-r4-aug3x-final-v1 \
  --patience 50 \
  --workers 0
```

Save the final selected checkpoint as:

```text
model-training/rebar-segementation-yolo26/results/final/yolo26l-r4-aug3x-final-v1.pt
```

## 10. Final Report

The final report should include separate metrics for:

- `valid_all`
- `valid_custom`
- `test_custom`

Include this table:

| Model Version | Dataset Variant | Stage | mAP50 | mAP50-95 | Precision | Recall | Notes |
|---|---|---|---:|---:|---:|---:|---|
| `yolo26l-r4-aug3x-baseline-v1` | `mix-r4-a-b-c-v1-aug3x` | baseline |  |  |  |  |  |
| `yolo26l-r4-aug3x-tune-v1` | `mix-r4-a-b-c-v1-aug3x` | tune |  |  |  |  |  |
| `yolo26l-r4-aug3x-final-v1` | `mix-r4-a-b-c-v1-aug3x` | final |  |  |  |  |  |

Also include qualitative error review:

- Custom validation images with false positives.
- Custom validation images with false negatives.
- Cases where open-source performance improves but custom performance drops.
- Deployment-like scenes where segmentation masks are incomplete or noisy.

The selected model is successful if:

- It improves or maintains `valid_custom` performance compared with the
  baseline.
- It performs acceptably on `test_custom`.
- It does not only improve on open-source data while hurting custom rebar
  images.
- False positives and false negatives are acceptable for the deployment use
  case.

