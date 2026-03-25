# TWCC Knowledge (Context Window Snapshot)

## Scope

This document captures the technical context, observations, changes, and blockers discovered during this session while trying to run `run_sam3_twcc.sh` and make SAM3 inference work on TWCC.

## Environment and Repository Context

- Working directory: `/Users/hungkaihsiao/Documents/rebar-works/sam3-inference`
- Key files involved:
  - `run_sam3_twcc.sh`
  - `remote_sam3_infer.py`
- TWCC CLI:
  - `twccli` is installed at `/Users/hungkaihsiao/miniconda3/envs/rebar-works/bin/twccli`
  - CLI version observed: `0.6.1`
- Active project was switched successfully to:
  - `_TWCC_PROJECT_CODE_ = ACD114160`

## Goal in this Session

Run and fix the TWCC automation so this SAM3 inference flow works end-to-end:

```python
from transformers import Sam3Processor, Sam3Model
import torch
from PIL import Image
import requests

device = "cuda" if torch.cuda.is_available() else "cpu"
model = Sam3Model.from_pretrained("facebook/sam3").to(device)
processor = Sam3Processor.from_pretrained("facebook/sam3")

image_url = "http://images.cocodataset.org/val2017/000000077595.jpg"
image = Image.open(requests.get(image_url, stream=True).raw).convert("RGB")

inputs = processor(images=image, text="ear", return_tensors="pt").to(device)
with torch.no_grad():
    outputs = model(**inputs)

results = processor.post_process_instance_segmentation(
    outputs,
    threshold=0.5,
    mask_threshold=0.5,
    target_sizes=inputs.get("original_sizes").tolist()
)[0]
print(f"Found {len(results['masks'])} objects")
```

## `remote_sam3_infer.py` State

`remote_sam3_infer.py` was already aligned with the target inference logic:

- Loads model/processor from `facebook/sam3`
- Supports URL or local image input
- Runs prompt-based instance segmentation
- Writes artifacts:
  - `input.png`
  - `overlay.png` (if masks exist)
  - `mask_*.png`
  - `result.json`
- Prints JSON summary (includes mask count)

No direct functional changes were required in `remote_sam3_infer.py` during this session.

## Failures Reproduced (Chronological)

### 1) Keypair creation failed when passing `-pub` path

Original script behavior:

- Generated local key with `ssh-keygen`
- Called: `twccli mk key -n <name> -pub <path-to-pub>`

Observed error:

- `[TWCC-CLI] Error-50301: Keypair data is invalid: failed to generate fingerprint`

Conclusion:

- In this environment/project, that `-pub` workflow failed repeatedly.

### 2) Retrying `mk vcs` triggered duplicate SG name errors

Observed error:

- `The Security group name clisg_<api-prefix> is duplicate`

Conclusion:

- Generic retries for non-idempotent create flow (`mk vcs`) can cause duplicate SG collisions.

### 3) `mk vcs` key validation mismatch

Observed error:

- `ValueError: keypair: <new-key> is not validated. Avbl: kp175..., kp177..., ...`

Important detail:

- Even after waiting and retries, newly created key names were not accepted by `mk vcs` validation list (`x-extra-property-keypair`) in this project context.

## Changes Applied to `run_sam3_twcc.sh`

### Change A: Use TWCC-generated keypair material

Updated flow:

- Replaced `twccli mk key -n ... -pub ...` with `twccli mk key -n ...`
- Uses generated PEM from:
  - `~/.twcc_data/<keypair_name>.pem`

Also added cleanup of this local PEM when `--cleanup-keypair` is enabled.

### Change B: Add keypair readiness wait

Added logic to wait for keypair visibility before VCS create attempt.

### Change C: Avoid unsafe generic retries for create operations

Introduced a single-shot helper for create commands (`run_twcc_capture_once`) to avoid blind retries on non-idempotent actions.

### Change D: Add SG orphan cleanup helper

Added `cleanup_orphan_cli_security_group` to remove orphan default CLI SG (`clisg_<api-prefix>`) when duplicate-name error appears and SG is unassociated.

### Change E: Add VCS create recovery loop

Added `create_vcs_with_recovery` with targeted handling:

- duplicate SG name -> cleanup + retry
- keypair not validated -> wait + retry
- unknown error -> fail fast with logs

## Current Blocker

Despite targeted recovery logic, `mk vcs` still fails because TWCC validation for keypairs in `ACD114160` only accepts a fixed pre-validated set (e.g. `kp175...`, `kp177...`) and does not include newly created keys.

This blocks end-to-end completion because SSH access to the new instance depends on using a keypair that TWCC accepts for `mk vcs` and for which we also have the corresponding private key locally.

## Practical Unblock Paths

### Option 1 (preferred)

Provide one TWCC keypair that is already validated for VCS creation in this project, plus matching local private key PEM path.

Then run script with:

- `--keypair-name <validated_keypair_name>`

(and adjust script behavior to skip creating a new key if a keypair name is provided and PEM exists, if desired)

### Option 2

Switch automation to password-based login for VCS (if image/account policy allows), and use SSH password auth instead of keypair-based auth.

## TWCC CLI/Behavior Notes Found

- `twccli config init` behavior can be sticky if credential state is stale; credential reset/re-init fixed project switch.
- `twccli mk key` succeeded without `-pub` in this environment.
- `twccli ls key` listing and `mk vcs` accepted-key validation list are not necessarily the same set in this project context.
- Default SG naming in twccli internals uses API-key prefix: `clisg_<first8>`.

## Security Note

Sensitive values (API keys, secrets, full credential contents) are intentionally not copied into this file.
