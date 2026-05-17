# YOLO26 Rebar Segmentation Scripts

This directory contains two entrypoints for building a training dataset and
training a YOLO segmentation model:

- `dataset.py` combines multiple YOLO segmentation datasets into one dataset.
- `train.py` trains a YOLO26 segmentation model with Ultralytics.

Run commands from the `model-training` directory unless noted otherwise.

## Expected Dataset Layout

Each source dataset must use YOLO segmentation format:

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

Every image must have a same-stem `.txt` label file. For example,
`train/images/example.jpg` must have `train/labels/example.txt`.

All source datasets passed to `dataset.py` must use the same class schema in
`data.yaml`, such as:

```yaml
nc: 1
names: ['rebar']
```

Missing split folders are allowed. For example, a dataset can omit `test/` if
it has no test images.

## Combine Datasets With `dataset.py`

Use `dataset.py` to combine source datasets into a new YOLO dataset folder.
The script validates class schemas and image-label pairing before copying.
Copied files are prefixed with the source dataset folder name to avoid filename
collisions.

```bash
python rebar-segementation-yolo26/dataset.py \
  --sources datasets/ds-a-open-rebar-v1 \
            datasets/ds-b-custom-sam3-v1 \
            datasets/ds-c-open-sam3-v1 \
  --output datasets/mix-r4-a-b-c-v1-aug0 \
  --overwrite
```

Useful flags:

- `--sources`: required list of source dataset directories.
- `--output`: required output dataset directory.
- `--splits`: optional split list, defaults to `train valid test`.
- `--overwrite`: replace the output directory if it already exists.

The generated dataset will contain:

```text
datasets/mix-r4-a-b-c-v1-aug0/
  data.yaml
  train/images/
  train/labels/
  valid/images/
  valid/labels/
  test/images/
  test/labels/
```

## Train Locally With `train.py`

Install dependencies first:

```bash
python -m pip install --upgrade pip
python -m pip install -r rebar-segementation-yolo26/requirements.txt
```

Train with the combined dataset:

```bash
python rebar-segementation-yolo26/train.py \
  --model yolo26l-seg.pt \
  --data datasets/mix-r4-a-b-c-v1-aug0/data.yaml \
  --epochs 50 \
  --imgsz 640 \
  --batch 4 \
  --device auto \
  --project rebar-segementation-yolo26/results \
  --name yolo26l-r4-aug0-baseline-v1 \
  --patience 20 \
  --workers 0
```

Core training flags:

- `--model`: model checkpoint, such as `yolo26l-seg.pt` or `yolo26x-seg.pt`.
- `--data`: path to the dataset `data.yaml`.
- `--epochs`: training epoch count.
- `--imgsz`: training image size.
- `--batch`: batch size.
- `--device`: `auto`, `cpu`, `mps`, `cuda`, `0`, or a GPU list.
- `--project`: output parent directory for Ultralytics runs.
- `--name`: run name under `--project`.
- `--patience`: early stopping patience.
- `--workers`: dataloader worker count.

## Train-Time Augmentation

`train.py` enables conservative train-time augmentation by default. Disable it
for a clean baseline with:

```bash
python rebar-segementation-yolo26/train.py \
  --data datasets/mix-r4-a-b-c-v1-aug0/data.yaml \
  --no-augmentation
```

Common augmentation overrides:

- `--hsv-h`, `--hsv-s`, `--hsv-v`: color jitter.
- `--degrees`, `--translate`, `--scale`, `--shear`, `--perspective`: geometry.
- `--fliplr`, `--flipud`: flip probabilities.
- `--mosaic`, `--mixup`, `--copy-paste`: composite augmentation.
- `--close-mosaic`: disable mosaic for the final N epochs.

Example with lighter mosaic and no mixup:

```bash
python rebar-segementation-yolo26/train.py \
  --data datasets/mix-r4-a-b-c-v1-aug0/data.yaml \
  --mosaic 0.25 \
  --mixup 0.0
```

## TWCC Training

The TWCC helper uploads source datasets, runs `dataset.py` inside the container,
then trains using the generated combined dataset.

Set `DATASET_SOURCES` to source dataset folder names or paths. If a name is
given, the script looks under `datasets/`.

```bash
DATASET_SOURCES="ds-a-open-rebar-v1 ds-b-custom-sam3-v1 ds-c-open-sam3-v1" \
DATASET_OUTPUT_NAME="mix-r4-a-b-c-v1-aug0" \
TRAIN_MODEL="yolo26x-seg.pt" \
TRAIN_EPOCHS="100" \
TRAIN_BATCH="16" \
TRAIN_NAME="yolo26x-r4-aug0-final-v1" \
./rebar-segementation-yolo26/scripts/train_rebar_seg_yolo26_v3.sh
```

By default, the TWCC script trains from:

```text
/tmp/rebar-training/datasets/${DATASET_OUTPUT_NAME}/data.yaml
```

Override `TRAIN_DATA` only if you want to train from a different dataset YAML.

Useful TWCC environment variables:

- `DATASET_SOURCES`: required source datasets to upload and combine.
- `DATASET_OUTPUT_NAME`: output dataset folder name, default `combined-rebar`.
- `TRAIN_MODEL`: YOLO checkpoint, default `yolo26x-seg.pt`.
- `TRAIN_EPOCHS`: epoch count, default `100`.
- `TRAIN_IMGSZ`: image size, default `640`.
- `TRAIN_BATCH`: batch size, default `16`.
- `TRAIN_DEVICE`: training device inside TWCC, default `0`.
- `TRAIN_NAME`: Ultralytics run name.
- `TRAIN_PATIENCE`: early stopping patience, default `30`.
- `TRAIN_WORKERS`: dataloader workers, default `0`.
- `LOCAL_RESULTS_DIR`: local folder for downloaded results.

## Quick Checks

Inspect script options:

```bash
python rebar-segementation-yolo26/dataset.py --help
python rebar-segementation-yolo26/train.py --help
```

Check image and label counts after combining:

```bash
find datasets/mix-r4-a-b-c-v1-aug0 -type f -path "*/images/*" | wc -l
find datasets/mix-r4-a-b-c-v1-aug0 -type f -path "*/labels/*" | wc -l
sed -n '1,40p' datasets/mix-r4-a-b-c-v1-aug0/data.yaml
```
