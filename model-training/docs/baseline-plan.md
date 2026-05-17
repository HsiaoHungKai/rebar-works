# YOLO26 Rebar Segmentation Baseline Plan

## Summary

This baseline study checks which dataset combination and augmentation setting should be used before running full Ray Tune. The training pipeline uses:

- `rebar-segementation-yolo26/dataset.py` to combine YOLO segmentation datasets.
- `rebar-segementation-yolo26/train.py` to train `yolo26x-seg.pt` with or without train-time augmentation.
- `rebar-segementation-yolo26/results/<run-name>/results.csv` for metric comparison and visualization.

All baseline models train for 50 epochs. The two runs with the best combined validation segmentation performance are selected for Ray Tune.

## Source Datasets

| ID | Path | Purpose | Split Counts |
| --- | --- | --- | --- |
| A | `datasets/ds-a-open-rebar-v1` | Roboflow open rebar segmentation dataset with varied angles and distances. | `train=928`, `valid=103`, `test=0` |
| B | `datasets/ds-b-custom-sam3-v1` | Custom real-world target dataset filmed in-house. This is closest to the deployment domain. | `train=37`, `valid=10`, `test=15` |
| C | `datasets/ds-c-open-sam3-v1` | Open-source rebar images annotated with SAM3, intended to improve robustness to complex rebar relationships. | `train=29`, `valid=10`, `test=0` |

All source datasets use the same class schema:

```yaml
nc: 1
names: ['rebar']
```

## Baseline Matrix

Run every non-empty dataset combination with augmentation disabled and enabled:

- 7 dataset combinations
- 2 augmentation modes
- 14 total baseline runs

Augmentation modes:

- `aug0`: pass `--no-augmentation` to `train.py`.
- `aug1`: use the default augmentation settings in `train.py`.

| Dataset Mix | Sources | Combined Dataset Output | No-Aug Run Name | Aug Run Name |
| --- | --- | --- | --- | --- |
| A | `ds-a-open-rebar-v1` | `datasets/baseline-a-v1` | `yolo26x-baseline-a-aug0-v1` | `yolo26x-baseline-a-aug1-v1` |
| B | `ds-b-custom-sam3-v1` | `datasets/baseline-b-v1` | `yolo26x-baseline-b-aug0-v1` | `yolo26x-baseline-b-aug1-v1` |
| C | `ds-c-open-sam3-v1` | `datasets/baseline-c-v1` | `yolo26x-baseline-c-aug0-v1` | `yolo26x-baseline-c-aug1-v1` |
| A+B | `ds-a-open-rebar-v1`, `ds-b-custom-sam3-v1` | `datasets/baseline-a-b-v1` | `yolo26x-baseline-a-b-aug0-v1` | `yolo26x-baseline-a-b-aug1-v1` |
| A+C | `ds-a-open-rebar-v1`, `ds-c-open-sam3-v1` | `datasets/baseline-a-c-v1` | `yolo26x-baseline-a-c-aug0-v1` | `yolo26x-baseline-a-c-aug1-v1` |
| B+C | `ds-b-custom-sam3-v1`, `ds-c-open-sam3-v1` | `datasets/baseline-b-c-v1` | `yolo26x-baseline-b-c-aug0-v1` | `yolo26x-baseline-b-c-aug1-v1` |
| A+B+C | `ds-a-open-rebar-v1`, `ds-b-custom-sam3-v1`, `ds-c-open-sam3-v1` | `datasets/baseline-a-b-c-v1` | `yolo26x-baseline-a-b-c-aug0-v1` | `yolo26x-baseline-a-b-c-aug1-v1` |

## Dataset Combination Commands

Run commands from the repository root: `model-training`.

```bash
python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-a-open-rebar-v1 \
  --output datasets/baseline-a-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-b-custom-sam3-v1 \
  --output datasets/baseline-b-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-c-open-sam3-v1 \
  --output datasets/baseline-c-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-a-open-rebar-v1 datasets/ds-b-custom-sam3-v1 \
  --output datasets/baseline-a-b-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-a-open-rebar-v1 datasets/ds-c-open-sam3-v1 \
  --output datasets/baseline-a-c-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-b-custom-sam3-v1 datasets/ds-c-open-sam3-v1 \
  --output datasets/baseline-b-c-v1 \
  --overwrite

python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-a-open-rebar-v1 datasets/ds-b-custom-sam3-v1 datasets/ds-c-open-sam3-v1 \
  --output datasets/baseline-a-b-c-v1 \
  --overwrite
```

## Training Commands

Use the same training settings for every baseline run:

- Model: `yolo26x-seg.pt`
- Epochs: `50`
- Image size: `640`
- Batch: `16`
- Device: `auto`
- Project: `rebar-segementation-yolo26/results`
- Patience: `30`
- Workers: `0`

### A

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-aug1-v1 \
  --patience 30 \
  --workers 0
```

### B

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-b-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-b-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-b-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-b-aug1-v1 \
  --patience 30 \
  --workers 0
```

### C

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-c-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-c-aug1-v1 \
  --patience 30 \
  --workers 0
```

### A+B

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-b-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-b-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-b-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-b-aug1-v1 \
  --patience 30 \
  --workers 0
```

### A+C

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-c-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-c-aug1-v1 \
  --patience 30 \
  --workers 0
```

### B+C

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-b-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-b-c-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-b-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-b-c-aug1-v1 \
  --patience 30 \
  --workers 0
```

### A+B+C

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-b-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-b-c-aug0-v1 \
  --patience 30 \
  --workers 0 \
  --no-augmentation

python rebar-segementation-yolo26/train.py \
  --model yolo26x-seg.pt \
  --data datasets/baseline-a-b-c-v1/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 16 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26x-baseline-a-b-c-aug1-v1 \
  --patience 30 \
  --workers 0
```

## Ranking Rule

Rank all 14 runs using the combined validation metrics written by Ultralytics.

Primary ranking metric:

- Best epoch value of `metrics/mAP50-95(M)` in `results.csv`

Tie-breaker:

- Best epoch value of `metrics/mAP50(M)` in `results.csv`

Use the best epoch value, not only the final epoch value. Record both the best epoch and final epoch values in the comparison table.

Suggested comparison columns:

| Run Name | Dataset Mix | Augmentation | Best Epoch | Best Mask mAP50-95 | Best Mask mAP50 | Final Mask mAP50-95 | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Ray Tune Handoff

Select the top two baseline runs after ranking.

For Ray Tune:

- Keep the selected dataset combination fixed.
- Keep the base model as `yolo26x-seg.pt`.
- Tune augmentation hyperparameters first.
- Include `batch` and `imgsz` only if compute budget allows.

Candidate augmentation parameters for tuning:

- `hsv_s`
- `hsv_v`
- `degrees`
- `translate`
- `scale`
- `shear`
- `perspective`
- `fliplr`
- `mosaic`
- `mixup`
- `close_mosaic`

Do not tune the dataset split during this phase.

## Validation Checklist

Before training:

- Confirm each combined dataset has `data.yaml`.
- Confirm each combined dataset has `train/images`, `train/labels`, `valid/images`, and `valid/labels`.
- Confirm image counts and label counts match for each split.
- Confirm each combined `data.yaml` keeps `nc: 1` and `names: ['rebar']`.

After each training run:

- Confirm `rebar-segementation-yolo26/results/<run-name>/results.csv` exists.
- Confirm `rebar-segementation-yolo26/results/<run-name>/weights/best.pt` exists.
- Record best `metrics/mAP50-95(M)`, best epoch, final `metrics/mAP50-95(M)`, and best `metrics/mAP50(M)`.

Acceptance criteria:

- All 14 baseline runs complete, or failed runs have documented failure reasons.
- A ranked table identifies the top two runs.
- The comparison clearly shows whether default augmentation improved validation performance for each dataset combination.

## Assumptions

- Source dataset splits are preserved exactly; no re-splitting is performed.
- Combined validation mAP is the official baseline ranking metric.
- B's test split is held for later deployment-domain validation, not for baseline ranking.
- The TWCC wrapper is not changed for this baseline plan because `train.py` already supports `--no-augmentation`.
