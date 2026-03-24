# SAM3 Inference on TWCC

This project runs Hugging Face `facebook/sam3` image inference on TWCC CCS with either:

- a text prompt for concept-level segmentation
- point prompts for interactive object segmentation

## Files

- `infer.py`: local or remote Python inference CLI
- `run_twcc_inference.sh`: TWCC CCS orchestration script
- `requirements.txt`: runtime dependencies for the inference CLI

## Local Python Usage

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run text-prompt inference:

```bash
python3 infer.py \
  --input-image ./example.jpg \
  --prompt-type text \
  --text "rebar" \
  --output-dir ./outputs/text-run
```

Run point-prompt inference:

```bash
python3 infer.py \
  --input-image ./example.jpg \
  --prompt-type points \
  --points "500,375,1;650,400,0" \
  --output-dir ./outputs/point-run \
  --multimask
```

Artifacts:

- `mask.png`: binary mask for the selected result
- `overlay.png`: original image with the selected mask overlay
- `result.json`: prompt metadata, mask stats, and model outputs that were retained

## TWCC Usage

The shell script follows the `twcc-cli-project` workflow:

1. verifies the active TWCC identity, project, and quota access
2. creates or reuses a CCS container
3. uploads the input image and inference code
4. installs Python dependencies inside the container
5. runs inference remotely
6. downloads artifacts locally
7. removes the created CCS site on success unless `--keep-resource` is set

Text prompt example:

```bash
./run_twcc_inference.sh \
  --input-image ./example.jpg \
  --prompt-type text \
  --text "rebar"
```

Point prompt example:

```bash
./run_twcc_inference.sh \
  --input-image ./example.jpg \
  --prompt-type points \
  --points "500,375,1;650,400,0" \
  --multimask
```

Optional TWCC flags:

```bash
./run_twcc_inference.sh \
  --input-image ./example.jpg \
  --prompt-type text \
  --text "rebar" \
  --reuse-site-id 12345 \
  --local-output-dir ./outputs/remote-run \
  --keep-resource
```

## Notes

- The default CCS image is discovered from the current TWCC project by querying available PyTorch images.
- The default shell workflow targets a single-image inference run with one GPU.
- If the remote run fails, the script keeps the created CCS site by default so the container can be inspected manually.
