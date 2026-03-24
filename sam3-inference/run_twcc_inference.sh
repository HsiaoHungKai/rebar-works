#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/infer.py"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

SITE_NAME=""
GPU_NUMBER="1"
IMAGE_TYPE_NAME="PyTorch"
IMAGE_NAME=""
PRODUCT_TYPE=""
REUSE_SITE_ID=""
KEEP_RESOURCE="0"
REMOTE_WORKDIR="/tmp/sam3-inference"
LOCAL_OUTPUT_DIR=""
INPUT_IMAGE=""
PROMPT_TYPE=""
TEXT_PROMPT=""
POINTS_PROMPT=""
DEVICE="cuda"
TARGET_SIZE=""
MASK_THRESHOLD="0.5"
SCORE_THRESHOLD="0.5"
MULTIMASK="0"

CREATED_SITE_ID=""
RUN_ID="sam3-$(date +%Y%m%d-%H%M%S)"
REMOTE_OUTPUT_DIR=""

log() {
  printf '[sam3-twcc] %s\n' "$*" >&2
}

die() {
  printf '[sam3-twcc] ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  run_twcc_inference.sh --input-image PATH --prompt-type text --text "rebar"
  run_twcc_inference.sh --input-image PATH --prompt-type points --points "500,375,1;650,400,0"

Required:
  --input-image PATH
  --prompt-type text|points

Prompt flags:
  --text TEXT
  --points "x,y,label;x,y,label;..."

TWCC options:
  --site-name NAME
  --gpu-number N
  --image-type-name NAME
  --image-name IMAGE
  --product-type FLAVOR
  --reuse-site-id ID
  --keep-resource
  --remote-workdir DIR

Inference options:
  --local-output-dir DIR
  --device auto|cuda|cpu
  --target-size INT
  --mask-threshold FLOAT
  --score-threshold FLOAT
  --multimask

Behavior:
  Creates or reuses a TWCC CCS site, uploads the inference project and input image,
  installs dependencies remotely, runs inference, downloads output artifacts, and
  removes the created CCS site on success unless --keep-resource is set.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-image)
      INPUT_IMAGE="$2"
      shift 2
      ;;
    --prompt-type)
      PROMPT_TYPE="$2"
      shift 2
      ;;
    --text)
      TEXT_PROMPT="$2"
      shift 2
      ;;
    --points)
      POINTS_PROMPT="$2"
      shift 2
      ;;
    --site-name)
      SITE_NAME="$2"
      shift 2
      ;;
    --gpu-number)
      GPU_NUMBER="$2"
      shift 2
      ;;
    --image-type-name)
      IMAGE_TYPE_NAME="$2"
      shift 2
      ;;
    --image-name)
      IMAGE_NAME="$2"
      shift 2
      ;;
    --product-type)
      PRODUCT_TYPE="$2"
      shift 2
      ;;
    --reuse-site-id)
      REUSE_SITE_ID="$2"
      shift 2
      ;;
    --keep-resource)
      KEEP_RESOURCE="1"
      shift
      ;;
    --remote-workdir)
      REMOTE_WORKDIR="$2"
      shift 2
      ;;
    --local-output-dir)
      LOCAL_OUTPUT_DIR="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --target-size)
      TARGET_SIZE="$2"
      shift 2
      ;;
    --mask-threshold)
      MASK_THRESHOLD="$2"
      shift 2
      ;;
    --score-threshold)
      SCORE_THRESHOLD="$2"
      shift 2
      ;;
    --multimask)
      MULTIMASK="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$INPUT_IMAGE" ]] || die "--input-image is required."
[[ -f "$INPUT_IMAGE" ]] || die "Input image does not exist: $INPUT_IMAGE"
[[ -n "$PROMPT_TYPE" ]] || die "--prompt-type is required."
[[ "$PROMPT_TYPE" == "text" || "$PROMPT_TYPE" == "points" ]] || die "--prompt-type must be text or points."

if [[ "$PROMPT_TYPE" == "text" ]]; then
  [[ -n "$TEXT_PROMPT" ]] || die "--text is required when --prompt-type text is used."
  [[ -z "$POINTS_PROMPT" ]] || die "--points cannot be used when --prompt-type text is used."
else
  [[ -n "$POINTS_PROMPT" ]] || die "--points is required when --prompt-type points is used."
  [[ -z "$TEXT_PROMPT" ]] || die "--text cannot be used when --prompt-type points is used."
fi

command -v twccli >/dev/null 2>&1 || die "twccli is not installed or not on PATH."
command -v ssh >/dev/null 2>&1 || die "ssh is not installed or not on PATH."
command -v scp >/dev/null 2>&1 || die "scp is not installed or not on PATH."
command -v python3 >/dev/null 2>&1 || die "python3 is not installed or not on PATH."

log "Verifying TWCC context."
twccli config whoami >/dev/null
twccli info proj >/dev/null
twccli info quota >/dev/null

if [[ -z "$SITE_NAME" ]]; then
  SITE_NAME="$RUN_ID"
fi

if [[ -z "$LOCAL_OUTPUT_DIR" ]]; then
  LOCAL_OUTPUT_DIR="$SCRIPT_DIR/outputs/$RUN_ID"
fi
mkdir -p "$LOCAL_OUTPUT_DIR"

REMOTE_OUTPUT_DIR="$REMOTE_WORKDIR/output"

cleanup() {
  local status="$1"
  if [[ -n "$CREATED_SITE_ID" && "$KEEP_RESOURCE" != "1" && "$status" -eq 0 ]]; then
    log "Cleaning up CCS site $CREATED_SITE_ID."
    twccli rm ccs --site-id "$CREATED_SITE_ID" >/dev/null || log "Failed to remove CCS site $CREATED_SITE_ID."
  elif [[ -n "$CREATED_SITE_ID" ]]; then
    log "Keeping CCS site $CREATED_SITE_ID for debugging."
  fi
}

trap 'cleanup $?' EXIT

discover_default_image() {
  python3 - <<'PY'
import re
import subprocess
import sys

cmd = ["twccli", "ls", "ccs", "--image"]
result = subprocess.run(cmd, capture_output=True, text=True, check=True)
pattern = re.compile(r"pytorch-[^ ]+:latest")
match = pattern.search(result.stdout)
if not match:
    sys.exit("Could not discover a default PyTorch CCS image.")
print(match.group(0))
PY
}

create_site() {
  local create_json
  local -a cmd
  cmd=(twccli mk ccs --name "$SITE_NAME" --gpu-number "$GPU_NUMBER" --image-type-name "$IMAGE_TYPE_NAME" --image-name "$IMAGE_NAME" --command "bash -lc 'trap : TERM INT; sleep infinity & wait'" --wait-ready --json)
  if [[ -n "$PRODUCT_TYPE" ]]; then
    cmd+=(--product-type "$PRODUCT_TYPE")
  fi
  create_json="$("${cmd[@]}")"
  CREATED_SITE_ID="$(python3 -c '
import json
import sys

raw = sys.argv[1].strip()
if not raw:
    raise SystemExit("TWCC create command returned empty output.")
payload = json.loads(raw)
site_id = payload.get("id")
if site_id is None:
    raise SystemExit(f"TWCC create response did not include an id: {payload}")
print(site_id)
' "$create_json")"
  printf '%s' "$CREATED_SITE_ID"
}

wait_for_ssh_target() {
  local site_id="$1"
  local attempt
  local target
  for attempt in $(seq 1 30); do
    if target="$(twccli ls ccs --site-id "$site_id" --get-ssh-info 2>/dev/null)"; then
      target="$(printf '%s' "$target" | tr -d '\r' | awk 'NF {print $0; exit}')"
      if [[ -n "$target" ]]; then
        printf '%s' "$target"
        return 0
      fi
    fi
    sleep 10
  done
  return 1
}

parse_ssh_target() {
  python3 - "$1" <<'PY'
import re
import sys

raw = sys.argv[1].strip()
match = re.fullmatch(r"([^@]+)@([^ ]+) -p ([0-9]+)", raw)
if not match:
    raise SystemExit(f"Unable to parse TWCC SSH target: {raw}")
print(match.group(1))
print(match.group(2))
print(match.group(3))
PY
}

run_ssh() {
  ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p "$SSH_PORT" "$SSH_USER@$SSH_HOST" "$@"
}

run_scp_to() {
  scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$SSH_PORT" "$@" "$SSH_USER@$SSH_HOST:$REMOTE_WORKDIR/"
}

run_scp_from() {
  scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -P "$SSH_PORT" "$SSH_USER@$SSH_HOST:$1" "$2"
}

if [[ -n "$REUSE_SITE_ID" ]]; then
  SITE_ID="$REUSE_SITE_ID"
  log "Reusing CCS site $SITE_ID."
else
  if [[ -z "$IMAGE_NAME" ]]; then
    log "Discovering default PyTorch CCS image."
    IMAGE_NAME="$(discover_default_image)"
  fi
  log "Creating CCS site $SITE_NAME with image $IMAGE_NAME."
  SITE_ID="$(create_site)"
  log "Created CCS site $SITE_ID."
fi

log "Resolving SSH entrypoint for site $SITE_ID."
SSH_TARGET="$(wait_for_ssh_target "$SITE_ID")" || die "Could not resolve SSH target for site $SITE_ID."
mapfile -t SSH_PARTS < <(parse_ssh_target "$SSH_TARGET")
SSH_USER="${SSH_PARTS[0]}"
SSH_HOST="${SSH_PARTS[1]}"
SSH_PORT="${SSH_PARTS[2]}"

INPUT_IMAGE_ABS="$(cd "$(dirname "$INPUT_IMAGE")" && pwd)/$(basename "$INPUT_IMAGE")"
REMOTE_IMAGE_NAME="$(basename "$INPUT_IMAGE")"

log "Preparing remote workspace $REMOTE_WORKDIR."
run_ssh "mkdir -p '$REMOTE_WORKDIR' '$REMOTE_OUTPUT_DIR'"

log "Uploading inference code and input image."
run_scp_to "$PYTHON_SCRIPT" "$REQUIREMENTS_FILE" "$INPUT_IMAGE_ABS"

log "Installing Python dependencies in the CCS container."
run_ssh "python3 -m pip install --upgrade pip && python3 -m pip install --no-cache-dir -r '$REMOTE_WORKDIR/requirements.txt'"

REMOTE_CMD=(
  "python3" "$REMOTE_WORKDIR/infer.py"
  "--input-image" "$REMOTE_WORKDIR/$REMOTE_IMAGE_NAME"
  "--prompt-type" "$PROMPT_TYPE"
  "--output-dir" "$REMOTE_OUTPUT_DIR"
  "--device" "$DEVICE"
  "--mask-threshold" "$MASK_THRESHOLD"
  "--score-threshold" "$SCORE_THRESHOLD"
)

if [[ "$PROMPT_TYPE" == "text" ]]; then
  REMOTE_CMD+=("--text" "$TEXT_PROMPT")
else
  REMOTE_CMD+=("--points" "$POINTS_PROMPT")
fi

if [[ -n "$TARGET_SIZE" ]]; then
  REMOTE_CMD+=("--target-size" "$TARGET_SIZE")
fi
if [[ "$MULTIMASK" == "1" ]]; then
  REMOTE_CMD+=("--multimask")
fi

log "Running remote inference."
run_ssh "$(printf '%q ' "${REMOTE_CMD[@]}")"

log "Downloading output artifacts to $LOCAL_OUTPUT_DIR."
run_scp_from "$REMOTE_OUTPUT_DIR/mask.png" "$LOCAL_OUTPUT_DIR/mask.png"
run_scp_from "$REMOTE_OUTPUT_DIR/overlay.png" "$LOCAL_OUTPUT_DIR/overlay.png"
run_scp_from "$REMOTE_OUTPUT_DIR/result.json" "$LOCAL_OUTPUT_DIR/result.json"

log "Artifacts downloaded to $LOCAL_OUTPUT_DIR."
if [[ -n "$CREATED_SITE_ID" && "$KEEP_RESOURCE" != "1" ]]; then
  log "CCS site $CREATED_SITE_ID will be removed on exit."
fi
