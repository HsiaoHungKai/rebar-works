#!/usr/bin/env bash

###############################################################################
# train_rebar_seg_yolo26.sh - Automated TWCC CCS Container Setup and YOLO Training
#
# Usage:
#   ./rebar-segementation-yolo26/train_rebar_seg_yolo26.sh
#   ./rebar-segementation-yolo26/train_rebar_seg_yolo26.sh --execute
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"

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

shell_quote() {
    printf '%q' "$1"
}

retry_sshpass_cmd() {
    local max_attempts=5
    local delays=(1 2 4 8)
    local attempt=1
    local cmd=("$@")

    while [ "$attempt" -le "$max_attempts" ]; do
        local display_cmd=("${cmd[@]}")
        local i
        for i in "${!display_cmd[@]}"; do
            if [[ "${display_cmd[$i]}" == "-p" && $((i + 1)) -lt ${#display_cmd[@]} ]]; then
                display_cmd[$((i + 1))]="********"
            fi
        done
        log "Attempt $attempt/$max_attempts: ${display_cmd[*]}"

        if "${cmd[@]}"; then
            log "Command succeeded on attempt $attempt"
            return 0
        fi

        if [ "$attempt" -lt "$max_attempts" ]; then
            local delay=${delays[$((attempt - 1))]}
            log "Command failed, retrying in ${delay}s..."
            sleep "$delay"
        else
            log "Command failed after $max_attempts attempts"
            return 1
        fi

        ((attempt++))
    done
}

load_and_validate_env() {
    [[ -f "$ENV_FILE" ]] || fail ".env file not found at ${ENV_FILE}"
    # shellcheck disable=SC1090
    source "$ENV_FILE"

    [[ -n "${PEM_LOCATION:-}" ]] || fail "PEM_LOCATION not set in .env"
    [[ -n "${TWCC_PASSWORD:-}" ]] || fail "TWCC_PASSWORD not set in .env"
    [[ -n "${TWCC_USERNAME:-}" ]] || fail "TWCC_USERNAME not set in .env. Find your username from NCHC iService: https://iservice.nchc.org.tw/nchc_service/ (會員中心 -> 主機帳號資訊)"
}

orchestrator_mode() {
    log "Starting orchestrator mode"
    load_and_validate_env
    log "Environment variables loaded from .env"
    log "PEM_LOCATION: ${PEM_LOCATION}"

    OS_TYPE="$(uname -s)"
    case "$OS_TYPE" in
        Darwin)
            log "Detected macOS - launching Terminal.app"
            osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
end tell
EOF
            log "Terminal launched. Orchestrator exiting."
            ;;
        Linux)
            log "Detected Linux - launching terminal emulator"
            if command -v gnome-terminal >/dev/null 2>&1; then
                gnome-terminal -- bash -c "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute; exec bash"
            elif command -v xterm >/dev/null 2>&1; then
                xterm -hold -e "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
            elif command -v x-terminal-emulator >/dev/null 2>&1; then
                x-terminal-emulator -e "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
            else
                fail "No suitable terminal emulator found. Please install gnome-terminal or xterm."
            fi
            log "Terminal launched. Orchestrator exiting."
            ;;
        *)
            fail "Unsupported operating system: $OS_TYPE"
            ;;
    esac
}

execution_mode() {
    log "==================================================================="
    log "Starting TWCC CCS Container Setup and YOLO Training"
    log "==================================================================="

    load_and_validate_env

    require_command twccli
    require_command ssh
    require_command scp
    require_command sshpass

    [[ -f "${SCRIPT_DIR}/train.py" ]] || fail "train.py not found"
    [[ -d "${REPO_ROOT}/datasets/sam3_annotation_without_open_source_rebar_v1" ]] || fail "dataset directory not found"

    TWCC_CONTAINER_NAME="${TWCC_CONTAINER_NAME:-yolo26-train}"
    TWCC_IMAGE="${TWCC_IMAGE:-pytorch-26.02-py3:latest}"
    TWCC_GPU="${TWCC_GPU:-1}"
    REMOTE_WORKDIR="${REMOTE_WORKDIR:-/tmp/rebar-training}"

    TRAIN_MODEL="${TRAIN_MODEL:-yolo26l-seg.pt}"
    TRAIN_DATA="${TRAIN_DATA:-${REMOTE_WORKDIR}/datasets/sam3_annotation_without_open_source_rebar_v1/data.yaml}"
    TRAIN_EPOCHS="${TRAIN_EPOCHS:-200}"
    TRAIN_IMGSZ="${TRAIN_IMGSZ:-640}"
    TRAIN_BATCH="${TRAIN_BATCH:-16}"
    TRAIN_DEVICE="${TRAIN_DEVICE:-0}"
    TRAIN_NAME="${TRAIN_NAME:-yolo26l_sam3_rebar_v2}"
    TRAIN_PATIENCE="${TRAIN_PATIENCE:-30}"
    TRAIN_WORKERS="${TRAIN_WORKERS:-0}"

    SITE_ID=""
    CONTAINER_CREATED=0

    cleanup() {
        set +x
        local exit_code=$?

        if [[ "$CONTAINER_CREATED" == "1" && -n "$SITE_ID" ]]; then
            log "==================================================================="
            log "Cleaning up TWCC container: ${SITE_ID}"
            log "==================================================================="
            twccli rm ccs --site-id "$SITE_ID" --force || true
        fi

        log "==================================================================="
        if [[ "$exit_code" -eq 0 ]]; then
            log "Workflow completed successfully!"
        else
            log "Workflow failed with exit code: $exit_code"
        fi
        log "==================================================================="

        log "Press Enter to close this window..."
        read -r || true
        exit "$exit_code"
    }

    trap cleanup EXIT

    log "Training Configuration:"
    log "  Container Name: ${TWCC_CONTAINER_NAME}"
    log "  Image: ${TWCC_IMAGE}"
    log "  GPU Count: ${TWCC_GPU}"
    log "  Remote Workdir: ${REMOTE_WORKDIR}"
    log "  Model: ${TRAIN_MODEL}"
    log "  Data: ${TRAIN_DATA}"
    log "  Epochs: ${TRAIN_EPOCHS}"
    log "  Image Size: ${TRAIN_IMGSZ}"
    log "  Batch: ${TRAIN_BATCH}"
    log "  Device: ${TRAIN_DEVICE}"
    log "  Run Name: ${TRAIN_NAME}"
    log "  Patience: ${TRAIN_PATIENCE}"
    log "  Workers: ${TRAIN_WORKERS}"

    cd "$REPO_ROOT"

    log "==================================================================="
    log "Step 1: Creating TWCC CCS container"
    log "==================================================================="

    TEMP_CREATE=$(mktemp)
    twccli mk ccs \
        -n "$TWCC_CONTAINER_NAME" \
        -itype "PyTorch" \
        -img "$TWCC_IMAGE" \
        -gpu "$TWCC_GPU" \
        -wait \
        -table | tee "$TEMP_CREATE"

    CONTAINER_CREATED=1

    log "==================================================================="
    log "Step 2: Extracting container connection info"
    log "==================================================================="

    if grep -q "CCS Site:" "$TEMP_CREATE"; then
        SITE_ID=$(grep "CCS Site:" "$TEMP_CREATE" | sed -E 's/.*CCS Site:([0-9]+).*/\1/' || true)
    else
        SITE_ID=$(grep "$TWCC_CONTAINER_NAME" "$TEMP_CREATE" | grep -v "name" | awk '{print $2}' || true)
    fi
    [[ -n "$SITE_ID" ]] || fail "Failed to extract SITE_ID from container creation output"

    TEMP_INFO=$(mktemp)
    twccli ls ccs -s "$SITE_ID" -gssh > "$TEMP_INFO" 2>&1 || true
    cat "$TEMP_INFO"

    if grep -q "@" "$TEMP_INFO"; then
        IP_ADDRESS=$(grep "@" "$TEMP_INFO" | grep -v "User" | head -n 1 | sed -E 's/.*@([^ ]+).*/\1/' || true)
    else
        IP_ADDRESS=$(grep -oE "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}" "$TEMP_INFO" | grep -v "^0\." | head -n 1 || true)
    fi

    if grep -q "\-p" "$TEMP_INFO"; then
        PORT=$(grep "\-p" "$TEMP_INFO" | sed -E 's/.*-p[[:space:]]*([0-9]+).*/\1/' || true)
    else
        PORT=$(grep -oE "port[[:space:]]*:?[[:space:]]*[0-9]{2,5}" "$TEMP_INFO" -i | grep -oE "[0-9]{2,5}" | head -n 1 || true)
        PORT="${PORT:-22}"
    fi

    rm -f "$TEMP_CREATE" "$TEMP_INFO"

    [[ -n "$IP_ADDRESS" ]] || fail "Failed to extract IP_ADDRESS"
    [[ -n "$PORT" ]] || fail "Failed to extract PORT"

    REMOTE_TARGET="${TWCC_USERNAME}@${IP_ADDRESS}"
    log "Container Info:"
    log "  SITE_ID: ${SITE_ID}"
    log "  SSH User: ${TWCC_USERNAME}"
    log "  IP: ${IP_ADDRESS}"
    log "  PORT: ${PORT}"

    log "==================================================================="
    log "Step 3: Preparing SSH access"
    log "==================================================================="
    chmod 400 "$PEM_LOCATION"
    sleep 10

    SSH_BASE=(
        -i "$PEM_LOCATION"
        -p "$PORT"
        -o StrictHostKeyChecking=no
        -o UserKnownHostsFile=/dev/null
        "$REMOTE_TARGET"
    )

    SCP_BASE=(
        -i "$PEM_LOCATION"
        -P "$PORT"
        -o StrictHostKeyChecking=no
        -o UserKnownHostsFile=/dev/null
    )

    log "==================================================================="
    log "Step 4: Uploading training code and dataset"
    log "==================================================================="

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${SSH_BASE[@]}" \
        "rm -rf $(shell_quote "$REMOTE_WORKDIR") && mkdir -p $(shell_quote "$REMOTE_WORKDIR")/rebar-segementation-yolo26 $(shell_quote "$REMOTE_WORKDIR")/datasets"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" \
        rebar-segementation-yolo26/train.py \
        rebar-segementation-yolo26/requirements.txt \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/rebar-segementation-yolo26/"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" -r \
        datasets/sam3_annotation_without_open_source_rebar_v1 \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/datasets/"

    log "==================================================================="
    log "Step 5: Installing dependencies and running training"
    log "==================================================================="

    REMOTE_PROJECT="${REMOTE_WORKDIR}/runs/segment"
    REMOTE_RUN_DIR="${REMOTE_PROJECT}/${TRAIN_NAME}"

    REMOTE_SCRIPT=$(cat <<REMOTE_EOF
set -euo pipefail
set -x

export MPLCONFIGDIR=$(shell_quote "${REMOTE_WORKDIR}/.cache/matplotlib")
mkdir -p "\$MPLCONFIGDIR"
cd $(shell_quote "$REMOTE_WORKDIR")

python -m pip install --upgrade pip
python -m pip install --upgrade -r rebar-segementation-yolo26/requirements.txt
python -m pip uninstall -y opencv-python opencv-contrib-python || true
python -m pip install --upgrade --force-reinstall opencv-python-headless
python - <<'PY'
import cv2
print(f"OpenCV import OK: {cv2.__version__}")
PY

python rebar-segementation-yolo26/train.py \\
    --model $(shell_quote "$TRAIN_MODEL") \\
    --data $(shell_quote "$TRAIN_DATA") \\
    --epochs $(shell_quote "$TRAIN_EPOCHS") \\
    --imgsz $(shell_quote "$TRAIN_IMGSZ") \\
    --batch $(shell_quote "$TRAIN_BATCH") \\
    --device $(shell_quote "$TRAIN_DEVICE") \\
    --project $(shell_quote "$REMOTE_PROJECT") \\
    --name $(shell_quote "$TRAIN_NAME") \\
    --patience $(shell_quote "$TRAIN_PATIENCE") \\
    --workers $(shell_quote "$TRAIN_WORKERS")
REMOTE_EOF
)

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${SSH_BASE[@]}" "$REMOTE_SCRIPT"

    log "==================================================================="
    log "Step 6: Downloading training outputs"
    log "==================================================================="

    mkdir -p "${REPO_ROOT}/results"
    if [[ -e "${REPO_ROOT}/results/${TRAIN_NAME}" ]]; then
        BACKUP_PATH="${REPO_ROOT}/results/${TRAIN_NAME}.backup_$(date +%Y%m%d_%H%M%S)"
        log "Existing local result found; moving it to: ${BACKUP_PATH}"
        mv "${REPO_ROOT}/results/${TRAIN_NAME}" "$BACKUP_PATH"
    fi

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" -r \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_RUN_DIR")" \
        "${REPO_ROOT}/results/"

    if [[ -d "${REPO_ROOT}/results/${TRAIN_NAME}" ]]; then
        log "Results downloaded to: ${REPO_ROOT}/results/${TRAIN_NAME}"
    else
        fail "Training completed, but results were not downloaded"
    fi

    log "Container will be cleaned up automatically..."
}

main() {
    if [[ "${1:-}" == "--execute" ]]; then
        execution_mode
    else
        orchestrator_mode
    fi
}

main "$@"
