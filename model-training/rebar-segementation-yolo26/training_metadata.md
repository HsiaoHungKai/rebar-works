# Rebar Segmentation YOLO26 Training Metadata

## Dataset Versions

| Dataset version | Local path | Config path | Roboflow dataset | Export date | Source images | Format | Classes | Total images | Split | License |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| dataset-v1 | `datasets/sam3_annotation_without_open_source_rebar_v1` | `datasets/sam3_annotation_without_open_source_rebar_v1/data.yaml` | `test_dahanxi - v8` | May 10, 2026 at 5:03 AM GMT | 3 Google Drive folders | YOLO26 segmentation | `rebar` | 162 | 150 train / 12 validation | CC BY 4.0 |
| dataset-v2 | `datasets/sam3_annotation_with_open_source_rebar` | `datasets/sam3_annotation_with_open_source_rebar/data.yaml` | `test_dahanxi - v10` | May 12, 2026 at 1:58 PM | 3 Google Drive folders plus 41 retained NTU open-source rebar images | YOLO26 segmentation | `rebar` | 255 | 231 train / 24 validation | CC BY 4.0 |

## Training Versions

| Training version | Automation script | Training entrypoint | Dataset version | Model | Dataset config | Epochs | Image size | Batch size | Device | Patience | Workers | Run name |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| v1 | `train_rebar_seg_yolo26.sh` | `train.py` | `dataset-v1` | `yolo26l-seg.pt` | `${REMOTE_WORKDIR}/datasets/sam3_annotation_without_open_source_rebar_v1/data.yaml` | 100 | 640 | 4 | `0` | 30 | 0 | `rebar-segementation-yolo26/train_rebar_seg_yolo26.sh` |
| v2 | `train_rebar_seg_yolo26_v2.sh` | `train.py` | `dataset-v1` | `yolo26l-seg.pt` | `${REMOTE_WORKDIR}/datasets/sam3_annotation_without_open_source_rebar_v1/data.yaml` | 126 | 640 | 16 | `0` | 30 | 0 | `rebar-segementation-yolo26/train_rebar_seg_yolo26_v2.sh` |
| v3 | `scripts/train_rebar_seg_yolo26_v3.sh` | `train.py` | `dataset-v2` | `yolo26x-seg.pt` | `${REMOTE_WORKDIR}/datasets/sam3_annotation_with_open_source_rebar/data.yaml` | 100 | 640 | 16 | `0` | 30 | 0 | `yolo26x_sam3_rebar_v3` |


## Execution Environment

- TWCC container name default: `yolo26-train`
- TWCC image default: `pytorch-26.02-py3:latest`
- GPU count default: 1
- Remote working directory default: `/tmp/rebar-training`
- Required local commands: `twccli`, `ssh`, `scp`, `sshpass`
