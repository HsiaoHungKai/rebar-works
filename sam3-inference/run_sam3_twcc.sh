#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/twcc-artifacts"
REMOTE_HELPER="${ROOT_DIR}/remote_sam3_infer.py"

IMAGE_INPUT=""
PROMPT=""
OUTPUT_DIR=""

INSTANCE_NAME=""
KEYPAIR_NAME=""
SSH_USER="ubuntu"
NETWORK_NAME="default_network"
VCS_IMAGE_TYPE="Ubuntu"
VCS_IMAGE_NAME="Ubuntu-24.04-20251128"
PRODUCT_TYPE="vgv.xsuper"
SYSTEM_VOLUME_TYPE="HDD"
SYSTEM_DISK_SIZE="100"
DATA_DISK_TYPE="HDD"
DATA_DISK_SIZE="0"
REMOTE_WORKDIR="/home/ubuntu/sam3-run"
SSH_READY_RETRIES="40"
SSH_READY_SLEEP="15"
KEY_READY_RETRIES="20"
KEY_READY_SLEEP="3"
VCS_CREATE_RETRIES="10"
VCS_CREATE_RETRY_SLEEP="6"
CLEANUP_INSTANCE="0"
CLEANUP_KEYPAIR="0"
VALIDATE_ONLY="0"

RUN_ID="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="${ARTIFACT_DIR}/sam3-${RUN_ID}"
SSH_KEY_PATH="${RUN_DIR}/twcc_sam3_ed25519"
TEMP_TWCC_DATA_DIR=""
KEYPAIR_CREATED="0"
TWCC_RETRIES="3"
TWCC_RETRY_SLEEP="5"
TWCC_API_KEY_PREFIX=""

usage() {
  cat <<'EOF'
Usage:
  ./run_sam3_twcc.sh --image <local-path-or-url> --prompt <text> [options]

Required:
  --image PATH_OR_URL          Local image file or HTTP(S) URL to segment.
  --prompt TEXT                SAM3 text prompt.

Options:
  --output-dir PATH            Local directory for downloaded results.
  --instance-name NAME         TWCC VCS name. Default: generated.
  --keypair-name NAME          TWCC keypair name. Default: generated.
  --ssh-user USER              Remote SSH user. Default: ubuntu
  --network NAME               TWCC VCS network. Default: default_network
  --vcs-image-type NAME        TWCC VCS image type. Default: Ubuntu
  --vcs-image-name NAME        TWCC VCS image. Default: Ubuntu-24.04-20251128
  --product-type NAME          TWCC VCS flavor. Default: vgv.xsuper
  --system-volume-type TYPE    TWCC system volume type. Default: HDD
  --system-disk-size GB        TWCC system disk size. Default: 100
  --data-disk-type TYPE        TWCC data disk type. Default: HDD
  --data-disk-size GB          TWCC data disk size. Default: 0
  --remote-workdir PATH        Remote working directory. Default: /home/ubuntu/sam3-run
  --ssh-ready-retries N        SSH retry count after provisioning. Default: 40
  --ssh-ready-sleep SEC        SSH retry interval. Default: 15
  --cleanup-instance           Delete the VCS after the run completes.
  --cleanup-keypair            Delete the TWCC keypair after the run completes.
                                Implies --cleanup-instance.
  --validate-only              Check the command path this script depends on and exit.
  -h, --help                   Show this help.

Notes:
  - The generated TWCC resource names must match ^[a-z][a-z-_0-9]{5,15}$.
  - Default flavor is GPU-backed and will consume TWCC quota.
  - By default the script keeps the instance and keypair so you can inspect them.
EOF
}

log() {
  printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

json_get() {
  local json_file="$1"
  local key="$2"
  python3 - "$json_file" "$key" <<'PY'
import json
import sys

path = sys.argv[1]
key = sys.argv[2]

with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

if isinstance(data, list):
    if not data:
        raise SystemExit("")
    data = data[0]

value = data
for part in key.split("."):
    if isinstance(value, dict):
        value = value.get(part, "")
    else:
        value = ""
        break

if value is None:
    value = ""

if isinstance(value, (dict, list)):
    print(json.dumps(value))
else:
    print(value)
PY
}

make_name() {
  local prefix="$1"
  local suffix
  suffix="$(date +%m%d%H%M)"
  printf '%s%s\n' "$prefix" "$suffix"
}

is_url() {
  case "$1" in
    http://*|https://*) return 0 ;;
    *) return 1 ;;
  esac
}

run_and_capture() {
  local output_file="$1"
  shift
  "$@" >"$output_file"
}

run_quiet() {
  "$@" >/dev/null
}

assert_no_twcc_error() {
  local output_file="$1"
  local context="$2"

  if grep -Eq '^\[TWCC-CLI\] Error-|Traceback \(most recent call last\):|^ValueError: ' "$output_file"; then
    sed -n '1,200p' "$output_file" >&2 || true
    fail "${context} failed"
  fi
}

has_twcc_app_error() {
  local output_file="$1"
  grep -Eq '^\[TWCC-CLI\] Error-' "$output_file"
}

has_twcc_retryable_error() {
  local output_file="$1"
  grep -Eq 'Traceback \(most recent call last\):|requests\.exceptions\.(ConnectionError|ReadTimeout)|RemoteDisconnected|MaxRetryError|Connection aborted|Failed to establish a new connection' "$output_file"
}

run_twcc_capture() {
  local output_file="$1"
  local context="$2"
  local retries="$3"
  shift 3

  local attempt rc
  for attempt in $(seq 1 "$retries"); do
    rc=0
    if ! "$@" >"$output_file" 2>&1; then
      rc=$?
    fi

    if has_twcc_app_error "$output_file"; then
      sed -n '1,200p' "$output_file" >&2 || true
      fail "${context} failed"
    fi

    if [[ "$rc" == "0" ]] && ! has_twcc_retryable_error "$output_file"; then
      return 0
    fi

    if [[ "$attempt" -lt "$retries" ]] && has_twcc_retryable_error "$output_file"; then
      log "${context} hit a transient TWCC/API error; retrying (${attempt}/${retries})"
      sleep "$TWCC_RETRY_SLEEP"
      continue
    fi

    sed -n '1,200p' "$output_file" >&2 || true
    fail "${context} failed"
  done
}

run_twcc_capture_once() {
  local output_file="$1"
  local context="$2"
  shift 2

  if ! "$@" >"$output_file" 2>&1; then
    sed -n '1,200p' "$output_file" >&2 || true
    fail "${context} failed"
  fi

  if has_twcc_app_error "$output_file"; then
    sed -n '1,200p' "$output_file" >&2 || true
    fail "${context} failed"
  fi
}

wait_for_keypair_ready() {
  local key_name="$1"
  local attempt output_file
  output_file="${RUN_DIR}/ls-key.txt"

  for attempt in $(seq 1 "$KEY_READY_RETRIES"); do
    if twccli ls key >"$output_file" 2>&1 && grep -qE "^[[:space:]]*\\|[[:space:]]*${key_name}[[:space:]]*\\|" "$output_file"; then
      return 0
    fi
    sleep "$KEY_READY_SLEEP"
  done

  sed -n '1,200p' "$output_file" >&2 || true
  fail "TWCC keypair ${key_name} did not become ready after ${KEY_READY_RETRIES} attempts"
}

twcc_keypair_exists() {
  local key_name="$1"
  local output_file
  output_file="${RUN_DIR}/ls-key.txt"
  twccli ls key >"$output_file" 2>&1 || return 1
  grep -qE "^[[:space:]]*\\|[[:space:]]*${key_name}[[:space:]]*\\|" "$output_file"
}

detect_twcc_api_key_prefix() {
  local credential_path
  credential_path="${TWCC_DATA_PATH:-${HOME}/.twcc_data}/credential"
  [[ -f "$credential_path" ]] || return 0

  TWCC_API_KEY_PREFIX="$(python3 - "$credential_path" <<'PY'
import sys
import yaml

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
api_key = (data.get("_default", {}) or {}).get("twcc_api_key", "")
print(api_key[:8] if isinstance(api_key, str) else "")
PY
)"
}

cleanup_orphan_cli_security_group() {
  local secg_name output_file secg_id
  [[ -n "$TWCC_API_KEY_PREFIX" ]] || return 0
  secg_name="clisg_${TWCC_API_KEY_PREFIX}"
  output_file="${RUN_DIR}/ls-secg.json"

  if ! twccli ls secg -json >"$output_file" 2>&1; then
    return
  fi

  secg_id="$(python3 - "$output_file" "$secg_name" <<'PY'
import json
import sys

path = sys.argv[1]
target = sys.argv[2]

with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)

for item in data:
    if item.get("name") == target and int(item.get("associated_server_count", 0)) == 0:
        print(item.get("id", ""))
        break
PY
)"

  if [[ -n "$secg_id" ]]; then
    log "Deleting orphan TWCC security group ${secg_name} (${secg_id})"
    twccli rm secg -f -id "$secg_id" >/dev/null 2>&1 || true
  fi
}

ensure_network_available() {
  local output_file
  output_file="${RUN_DIR}/ls-vnet.json"

  if ! twccli ls vnet -json >"$output_file" 2>&1; then
    sed -n '1,200p' "$output_file" >&2 || true
    fail "twccli ls vnet failed"
  fi

  if ! python3 - "$output_file" "$NETWORK_NAME" <<'PY'
import json
import sys

path = sys.argv[1]
target = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
for item in data:
    if item.get("name") == target:
        raise SystemExit(0)
raise SystemExit(1)
PY
  then
    fail "network '${NETWORK_NAME}' is not available in this project. Ask a TWCC project admin to create/share a VNet and re-run with --network <name>."
  fi
}

create_vcs_with_recovery() {
  local output_file attempt
  output_file="${RUN_DIR}/mk-vcs.json"

  for attempt in $(seq 1 "$VCS_CREATE_RETRIES"); do
    if twccli mk vcs -json -wait \
      -n "$INSTANCE_NAME" \
      -itype "$VCS_IMAGE_TYPE" \
      -img "$VCS_IMAGE_NAME" \
      -key "$KEYPAIR_NAME" \
      -net "$NETWORK_NAME" \
      -ptype "$PRODUCT_TYPE" \
      -fip \
      -sys-vol "$SYSTEM_VOLUME_TYPE" \
      -sys-size "$SYSTEM_DISK_SIZE" \
      -dd-type "$DATA_DISK_TYPE" \
      -dd-size "$DATA_DISK_SIZE" >"$output_file" 2>&1; then
      return 0
    fi

    if grep -Eq 'The Security group name .* is duplicate' "$output_file"; then
      cleanup_orphan_cli_security_group
    elif grep -Eq 'keypair: .* is not validated' "$output_file"; then
      log "TWCC keypair is not validated yet; retrying VCS create (${attempt}/${VCS_CREATE_RETRIES})"
    else
      sed -n '1,200p' "$output_file" >&2 || true
      fail "twccli mk vcs failed"
    fi

    if [[ "$attempt" -lt "$VCS_CREATE_RETRIES" ]]; then
      sleep "$VCS_CREATE_RETRY_SLEEP"
      continue
    fi

    sed -n '1,200p' "$output_file" >&2 || true
    fail "twccli mk vcs failed after recovery retries"
  done
}

ssh_opts() {
  printf '%s\n' \
    -i "$SSH_KEY_PATH" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o BatchMode=yes \
    -o ConnectTimeout=10
}

cleanup_resources() {
  local site_id="${1:-}"
  if [[ -n "$site_id" && "$CLEANUP_INSTANCE" == "1" ]]; then
    log "Deleting TWCC VCS ${site_id}"
    twccli rm vcs -f -s "$site_id" >/dev/null || true
  fi

  if [[ -n "${KEYPAIR_NAME:-}" && "$KEYPAIR_CREATED" == "1" && "$CLEANUP_KEYPAIR" == "1" ]]; then
    log "Deleting TWCC keypair ${KEYPAIR_NAME}"
    twccli rm key -f -n "$KEYPAIR_NAME" >/dev/null || true
    rm -f "${HOME}/.twcc_data/${KEYPAIR_NAME}.pem" >/dev/null 2>&1 || true
  fi

  if [[ -n "$TEMP_TWCC_DATA_DIR" && -d "$TEMP_TWCC_DATA_DIR" ]]; then
    rm -rf "$TEMP_TWCC_DATA_DIR"
  fi
}

prepare_twcc_data_path() {
  local home_twcc_data="${HOME}/.twcc_data"
  local home_log_dir="${home_twcc_data}/log"
  local touch_file="${home_log_dir}/.codex-write-test"

  if [[ -d "$home_log_dir" ]] && touch "$touch_file" >/dev/null 2>&1; then
    rm -f "$touch_file"
    return
  fi

  TEMP_TWCC_DATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/twcc-data.XXXXXX")"
  if [[ -d "$home_twcc_data" ]]; then
    cp -R "${home_twcc_data}/." "${TEMP_TWCC_DATA_DIR}/"
  fi

  mkdir -p "${TEMP_TWCC_DATA_DIR}/log"

  export TWCC_DATA_PATH="$TEMP_TWCC_DATA_DIR"
}

validate_command_path() {
  mkdir -p "$RUN_DIR"

  log "Validating TWCC auth and project context"
  run_quiet twccli config whoami
  run_and_capture "${RUN_DIR}/project.json" twccli info proj -json
  run_and_capture "${RUN_DIR}/quota.json" twccli info quota -json

  log "Validating VCS discovery commands used by this script"
  run_and_capture "${RUN_DIR}/networks.txt" twccli ls vnet
  run_and_capture "${RUN_DIR}/image-types.txt" twccli ls vcs -itype
  run_and_capture "${RUN_DIR}/images.txt" twccli ls vcs -img "$VCS_IMAGE_TYPE"
  run_and_capture "${RUN_DIR}/product-types.txt" twccli ls vcs -ptype "$VCS_IMAGE_TYPE"
  run_quiet twccli mk key --help
  run_quiet twccli mk vcs --help
  run_quiet twccli net vcs --help
  run_quiet twccli rm vcs --help
  run_quiet twccli rm key --help

  log "Validation completed"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE_INPUT="${2:-}"
      shift 2
      ;;
    --prompt)
      PROMPT="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --instance-name)
      INSTANCE_NAME="${2:-}"
      shift 2
      ;;
    --keypair-name)
      KEYPAIR_NAME="${2:-}"
      shift 2
      ;;
    --ssh-user)
      SSH_USER="${2:-}"
      shift 2
      ;;
    --network)
      NETWORK_NAME="${2:-}"
      shift 2
      ;;
    --vcs-image-type)
      VCS_IMAGE_TYPE="${2:-}"
      shift 2
      ;;
    --vcs-image-name)
      VCS_IMAGE_NAME="${2:-}"
      shift 2
      ;;
    --product-type)
      PRODUCT_TYPE="${2:-}"
      shift 2
      ;;
    --system-volume-type)
      SYSTEM_VOLUME_TYPE="${2:-}"
      shift 2
      ;;
    --system-disk-size)
      SYSTEM_DISK_SIZE="${2:-}"
      shift 2
      ;;
    --data-disk-type)
      DATA_DISK_TYPE="${2:-}"
      shift 2
      ;;
    --data-disk-size)
      DATA_DISK_SIZE="${2:-}"
      shift 2
      ;;
    --remote-workdir)
      REMOTE_WORKDIR="${2:-}"
      shift 2
      ;;
    --ssh-ready-retries)
      SSH_READY_RETRIES="${2:-}"
      shift 2
      ;;
    --ssh-ready-sleep)
      SSH_READY_SLEEP="${2:-}"
      shift 2
      ;;
    --cleanup-instance)
      CLEANUP_INSTANCE="1"
      shift
      ;;
    --cleanup-keypair)
      CLEANUP_INSTANCE="1"
      CLEANUP_KEYPAIR="1"
      shift
      ;;
    --validate-only)
      VALIDATE_ONLY="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

require_command twccli
require_command ssh
require_command scp
require_command ssh-keygen
require_command python3

[[ -f "$REMOTE_HELPER" ]] || fail "missing remote helper: $REMOTE_HELPER"

INSTANCE_NAME="${INSTANCE_NAME:-$(make_name samv)}"
KEYPAIR_NAME="${KEYPAIR_NAME:-$(make_name kp)}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/outputs/${INSTANCE_NAME}}"
SITE_ID=""

mkdir -p "$RUN_DIR"
prepare_twcc_data_path
detect_twcc_api_key_prefix
trap 'cleanup_resources "$SITE_ID"' EXIT

if [[ "$VALIDATE_ONLY" == "1" ]]; then
  validate_command_path
  exit 0
fi

[[ -n "$IMAGE_INPUT" ]] || fail "--image is required"
[[ -n "$PROMPT" ]] || fail "--prompt is required"

if ! is_url "$IMAGE_INPUT"; then
  [[ -f "$IMAGE_INPUT" ]] || fail "local image not found: $IMAGE_INPUT"
  IMAGE_INPUT="$(cd "$(dirname "$IMAGE_INPUT")" && pwd)/$(basename "$IMAGE_INPUT")"
fi

mkdir -p "$RUN_DIR" "$OUTPUT_DIR"

validate_command_path

log "Creating TWCC keypair ${KEYPAIR_NAME}"
SSH_KEY_PATH="${HOME}/.twcc_data/${KEYPAIR_NAME}.pem"
if twcc_keypair_exists "$KEYPAIR_NAME"; then
  log "Using existing TWCC keypair ${KEYPAIR_NAME}"
else
  run_twcc_capture_once "${RUN_DIR}/mk-key.txt" "twccli mk key" \
    twccli mk key -n "$KEYPAIR_NAME"
  KEYPAIR_CREATED="1"
fi

log "Waiting for TWCC keypair ${KEYPAIR_NAME} to become ready"
wait_for_keypair_ready "$KEYPAIR_NAME"

[[ -f "$SSH_KEY_PATH" ]] || fail "TWCC keypair PEM not found at ${SSH_KEY_PATH}. Use --keypair-name with a key that has a local private key file."

ensure_network_available

log "Creating TWCC VCS ${INSTANCE_NAME}"
create_vcs_with_recovery

SITE_ID="$(json_get "${RUN_DIR}/mk-vcs.json" id)"
[[ -n "$SITE_ID" ]] || fail "unable to parse VCS id from ${RUN_DIR}/mk-vcs.json"

log "Ensuring SSH access on VCS ${SITE_ID}"
if ! twccli net vcs -s "$SITE_ID" -p 22 -cidr 0.0.0.0/0 -in >"${RUN_DIR}/net-vcs-22.txt" 2>&1; then
  log "TWCC rejected an extra SSH rule. Continuing with the existing security-group state."
elif grep -Eq '^\[TWCC-CLI\] Error-' "${RUN_DIR}/net-vcs-22.txt"; then
  log "TWCC reported an SSH-rule warning. Continuing with the existing security-group state."
fi

log "Refreshing VCS connection details"
run_twcc_capture "${RUN_DIR}/ls-vcs.json" "twccli ls vcs" "$TWCC_RETRIES" \
  twccli ls vcs -json "$SITE_ID"
PUBLIC_IP="$(json_get "${RUN_DIR}/ls-vcs.json" public_ip)"
[[ -n "$PUBLIC_IP" ]] || fail "unable to parse VCS public_ip from ${RUN_DIR}/ls-vcs.json"

log "Waiting for SSH on ${PUBLIC_IP}"
for attempt in $(seq 1 "$SSH_READY_RETRIES"); do
  if ssh $(ssh_opts) "${SSH_USER}@${PUBLIC_IP}" 'echo ok' >/dev/null 2>&1; then
    break
  fi

  if [[ "$attempt" == "$SSH_READY_RETRIES" ]]; then
    fail "SSH did not become ready after ${SSH_READY_RETRIES} attempts"
  fi

  sleep "$SSH_READY_SLEEP"
done

log "Preparing remote workspace"
ssh $(ssh_opts) "${SSH_USER}@${PUBLIC_IP}" "mkdir -p '${REMOTE_WORKDIR}/output'"

log "Uploading inference helper"
scp $(ssh_opts) "$REMOTE_HELPER" "${SSH_USER}@${PUBLIC_IP}:${REMOTE_WORKDIR}/remote_sam3_infer.py" >/dev/null

REMOTE_IMAGE_INPUT="$IMAGE_INPUT"
if ! is_url "$IMAGE_INPUT"; then
  REMOTE_IMAGE_INPUT="${REMOTE_WORKDIR}/$(basename "$IMAGE_INPUT")"
  log "Uploading input image"
  scp $(ssh_opts) "$IMAGE_INPUT" "${SSH_USER}@${PUBLIC_IP}:${REMOTE_IMAGE_INPUT}" >/dev/null
fi

PROMPT_B64="$(printf '%s' "$PROMPT" | base64 | tr -d '\n')"
REMOTE_IMAGE_B64="$(printf '%s' "$REMOTE_IMAGE_INPUT" | base64 | tr -d '\n')"
REMOTE_WORKDIR_B64="$(printf '%s' "$REMOTE_WORKDIR" | base64 | tr -d '\n')"

log "Running SAM3 inference remotely"
ssh $(ssh_opts) "${SSH_USER}@${PUBLIC_IP}" \
  "PROMPT_B64='${PROMPT_B64}' REMOTE_IMAGE_B64='${REMOTE_IMAGE_B64}' REMOTE_WORKDIR_B64='${REMOTE_WORKDIR_B64}' bash -lc '
set -euo pipefail
prompt=\$(printf %s \"\$PROMPT_B64\" | base64 -d)
image_input=\$(printf %s \"\$REMOTE_IMAGE_B64\" | base64 -d)
remote_workdir=\$(printf %s \"\$REMOTE_WORKDIR_B64\" | base64 -d)

export DEBIAN_FRONTEND=noninteractive
if ! command -v pip3 >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y python3-pip python3-venv
fi

if [[ ! -d \"\$HOME/sam3-venv\" ]]; then
  if ! python3 -m venv --help >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3-venv
  fi
  python3 -m venv \"\$HOME/sam3-venv\"
fi

source \"\$HOME/sam3-venv/bin/activate\"
python -m pip install --upgrade pip
python -m pip install torch torchvision \"transformers>=4.57.0\" pillow requests numpy safetensors

python \"\$remote_workdir/remote_sam3_infer.py\" \
  --image \"\$image_input\" \
  --prompt \"\$prompt\" \
  --output-dir \"\$remote_workdir/output\"
' " | tee "${RUN_DIR}/remote-run.log"

log "Downloading results to ${OUTPUT_DIR}"
scp -r $(ssh_opts) "${SSH_USER}@${PUBLIC_IP}:${REMOTE_WORKDIR}/output/." "$OUTPUT_DIR/" >/dev/null

printf '%s\n' "$SITE_ID" >"${RUN_DIR}/site_id.txt"
printf '%s\n' "$PUBLIC_IP" >"${RUN_DIR}/public_ip.txt"

log "Completed"
log "Site ID: ${SITE_ID}"
log "Public IP: ${PUBLIC_IP}"
log "Results: ${OUTPUT_DIR}"

if [[ "$CLEANUP_INSTANCE" != "1" ]]; then
  log "Instance kept. Delete it later with: twccli rm vcs -f -s ${SITE_ID}"
fi

if [[ "$CLEANUP_KEYPAIR" != "1" ]]; then
  log "Keypair kept. Delete it later with: twccli rm key -f -n ${KEYPAIR_NAME}"
fi
