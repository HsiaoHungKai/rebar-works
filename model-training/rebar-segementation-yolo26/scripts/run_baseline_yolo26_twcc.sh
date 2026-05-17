#!/usr/bin/env bash

###############################################################################
# run_baseline_yolo26_twcc.sh - Run YOLO26 baseline matrix on one TWCC CCS node.
#
# Usage:
#   ./rebar-segementation-yolo26/scripts/run_baseline_yolo26_twcc.sh
#   ./rebar-segementation-yolo26/scripts/run_baseline_yolo26_twcc.sh --execute
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"
ENV_FILE="${WORKSPACE_ROOT}/.env"
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
    log "Starting TWCC YOLO26 Baseline Matrix"
    log "==================================================================="

    load_and_validate_env

    require_command twccli
    require_command ssh
    require_command scp
    require_command sshpass

    [[ -f "${REPO_ROOT}/train.py" ]] || fail "train.py not found"
    [[ -f "${REPO_ROOT}/dataset.py" ]] || fail "dataset.py not found"
    [[ -f "${REPO_ROOT}/requirements.txt" ]] || fail "requirements.txt not found"
    [[ -f "${WORKSPACE_ROOT}/docs/baseline-plan.md" ]] || fail "docs/baseline-plan.md not found"
    [[ -d "${WORKSPACE_ROOT}/datasets/ds-a-open-rebar-v1" ]] || fail "datasets/ds-a-open-rebar-v1 not found"
    [[ -d "${WORKSPACE_ROOT}/datasets/ds-b-custom-sam3-v1" ]] || fail "datasets/ds-b-custom-sam3-v1 not found"
    [[ -d "${WORKSPACE_ROOT}/datasets/ds-c-open-sam3-v1" ]] || fail "datasets/ds-c-open-sam3-v1 not found"

    TWCC_CONTAINER_NAME="${TWCC_CONTAINER_NAME:-yolo26-baseline}"
    TWCC_IMAGE="${TWCC_IMAGE:-pytorch-26.02-py3:latest}"
    TWCC_GPU="${TWCC_GPU:-1}"
    REMOTE_WORKDIR="${REMOTE_WORKDIR:-/tmp/rebar-baseline-yolo26}"
    TRAIN_MODEL="${TRAIN_MODEL:-yolo26x-seg.pt}"
    TRAIN_EPOCHS="${TRAIN_EPOCHS:-50}"
    TRAIN_IMGSZ="${TRAIN_IMGSZ:-640}"
    TRAIN_BATCH="${TRAIN_BATCH:-16}"
    TRAIN_DEVICE="${TRAIN_DEVICE:-0}"
    TRAIN_PATIENCE="${TRAIN_PATIENCE:-30}"
    TRAIN_WORKERS="${TRAIN_WORKERS:-0}"
    LOCAL_RESULTS_DIR="${LOCAL_RESULTS_DIR:-${REPO_ROOT}/results/baseline_yolo26_twcc}"

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

    log "Baseline Configuration:"
    log "  Container Name: ${TWCC_CONTAINER_NAME}"
    log "  Image Type: PyTorch"
    log "  Image: ${TWCC_IMAGE}"
    log "  GPU Flavor: ${TWCC_GPU}"
    log "  Remote Workdir: ${REMOTE_WORKDIR}"
    log "  Model: ${TRAIN_MODEL}"
    log "  Epochs: ${TRAIN_EPOCHS}"
    log "  Image Size: ${TRAIN_IMGSZ}"
    log "  Batch: ${TRAIN_BATCH}"
    log "  Device: ${TRAIN_DEVICE}"
    log "  Patience: ${TRAIN_PATIENCE}"
    log "  Workers: ${TRAIN_WORKERS}"
    log "  Dataset Combinations: 7"
    log "  Training Jobs: 14"
    log "  Local Results Dir: ${LOCAL_RESULTS_DIR}"

    cd "$WORKSPACE_ROOT"

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
    log "Step 4: Uploading training code, plan, and datasets"
    log "==================================================================="

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${SSH_BASE[@]}" \
        "rm -rf $(shell_quote "$REMOTE_WORKDIR") && mkdir -p $(shell_quote "$REMOTE_WORKDIR")/rebar-segementation-yolo26 $(shell_quote "$REMOTE_WORKDIR")/docs $(shell_quote "$REMOTE_WORKDIR")/datasets"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" \
        rebar-segementation-yolo26/train.py \
        rebar-segementation-yolo26/dataset.py \
        rebar-segementation-yolo26/requirements.txt \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/rebar-segementation-yolo26/"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" \
        docs/baseline-plan.md \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/docs/"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" -r \
        datasets/ds-a-open-rebar-v1 \
        datasets/ds-b-custom-sam3-v1 \
        datasets/ds-c-open-sam3-v1 \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/datasets/"

    log "==================================================================="
    log "Step 5: Installing dependencies, building datasets, and training"
    log "==================================================================="

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

python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-a-open-rebar-v1 \\
    --output datasets/baseline-a-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-b-custom-sam3-v1 \\
    --output datasets/baseline-b-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-c-open-sam3-v1 \\
    --output datasets/baseline-c-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-a-open-rebar-v1 datasets/ds-b-custom-sam3-v1 \\
    --output datasets/baseline-a-b-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-a-open-rebar-v1 datasets/ds-c-open-sam3-v1 \\
    --output datasets/baseline-a-c-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-b-custom-sam3-v1 datasets/ds-c-open-sam3-v1 \\
    --output datasets/baseline-b-c-v1 \\
    --overwrite
python rebar-segementation-yolo26/dataset.py \\
    --sources datasets/ds-a-open-rebar-v1 datasets/ds-b-custom-sam3-v1 datasets/ds-c-open-sam3-v1 \\
    --output datasets/baseline-a-b-c-v1 \\
    --overwrite

DATASET_MIXES=(a b c a-b a-c b-c a-b-c)
DATASET_LABELS=("A" "B" "C" "A+B" "A+C" "B+C" "A+B+C")
REMOTE_PROJECT=$(shell_quote "${REMOTE_WORKDIR}/runs/segment")
mkdir -p "\$REMOTE_PROJECT"

for index in "\${!DATASET_MIXES[@]}"; do
    mix="\${DATASET_MIXES[\$index]}"
    label="\${DATASET_LABELS[\$index]}"
    data_yaml="datasets/baseline-\${mix}-v1/data.yaml"

    for aug in aug0 aug1; do
        run_name="yolo26x-baseline-\${mix}-\${aug}-v1"
        aug_args=()
        if [[ "\$aug" == "aug0" ]]; then
            aug_args=(--no-augmentation)
        fi

        echo "Running baseline: dataset=\${label} augmentation=\${aug} run=\${run_name}"
        python rebar-segementation-yolo26/train.py \\
            --model $(shell_quote "$TRAIN_MODEL") \\
            --data "\$data_yaml" \\
            --epochs $(shell_quote "$TRAIN_EPOCHS") \\
            --imgsz $(shell_quote "$TRAIN_IMGSZ") \\
            --batch $(shell_quote "$TRAIN_BATCH") \\
            --device $(shell_quote "$TRAIN_DEVICE") \\
            --project "\$REMOTE_PROJECT" \\
            --name "\$run_name" \\
            --patience $(shell_quote "$TRAIN_PATIENCE") \\
            --workers $(shell_quote "$TRAIN_WORKERS") \\
            "\${aug_args[@]}"
    done
done

python - <<'PY'
from pathlib import Path
import csv
import math

remote_workdir = Path("$(shell_quote "$REMOTE_WORKDIR")")
run_root = remote_workdir / "runs" / "segment"
summary_csv = remote_workdir / "baseline_metrics_summary.csv"
summary_md = remote_workdir / "baseline_metrics_summary.md"

runs = [
    ("yolo26x-baseline-a-aug0-v1", "A", "aug0"),
    ("yolo26x-baseline-a-aug1-v1", "A", "aug1"),
    ("yolo26x-baseline-b-aug0-v1", "B", "aug0"),
    ("yolo26x-baseline-b-aug1-v1", "B", "aug1"),
    ("yolo26x-baseline-c-aug0-v1", "C", "aug0"),
    ("yolo26x-baseline-c-aug1-v1", "C", "aug1"),
    ("yolo26x-baseline-a-b-aug0-v1", "A+B", "aug0"),
    ("yolo26x-baseline-a-b-aug1-v1", "A+B", "aug1"),
    ("yolo26x-baseline-a-c-aug0-v1", "A+C", "aug0"),
    ("yolo26x-baseline-a-c-aug1-v1", "A+C", "aug1"),
    ("yolo26x-baseline-b-c-aug0-v1", "B+C", "aug0"),
    ("yolo26x-baseline-b-c-aug1-v1", "B+C", "aug1"),
    ("yolo26x-baseline-a-b-c-aug0-v1", "A+B+C", "aug0"),
    ("yolo26x-baseline-a-b-c-aug1-v1", "A+B+C", "aug1"),
]

def parse_float(value: str) -> float:
    value = value.strip()
    if not value:
        return float("nan")
    return float(value)

def fmt(value: float) -> str:
    if math.isnan(value):
        return ""
    return f"{value:.6f}"

rows = []
missing = []
for run_name, dataset_mix, aug_mode in runs:
    results_path = run_root / run_name / "results.csv"
    if not results_path.is_file():
        missing.append(str(results_path))
        continue

    with results_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        result_rows = [
            {key.strip(): value for key, value in row.items()}
            for row in reader
        ]

    if not result_rows:
        raise RuntimeError(f"results.csv is empty: {results_path}")

    required = {"epoch", "metrics/mAP50-95(M)", "metrics/mAP50(M)"}
    available = set(result_rows[0])
    missing_columns = required - available
    if missing_columns:
        raise RuntimeError(
            f"{results_path} missing required columns: {', '.join(sorted(missing_columns))}"
        )

    best = max(
        result_rows,
        key=lambda row: (
            parse_float(row["metrics/mAP50-95(M)"]),
            parse_float(row["metrics/mAP50(M)"]),
        ),
    )
    final = result_rows[-1]
    rows.append(
        {
            "run name": run_name,
            "dataset mix": dataset_mix,
            "augmentation mode": aug_mode,
            "best epoch": int(float(best["epoch"])),
            "best mask mAP50-95": parse_float(best["metrics/mAP50-95(M)"]),
            "best mask mAP50": parse_float(best["metrics/mAP50(M)"]),
            "final mask mAP50-95": parse_float(final["metrics/mAP50-95(M)"]),
            "results path": str(results_path),
        }
    )

if missing:
    raise FileNotFoundError(
        "Missing expected results.csv file(s):\n" + "\n".join(f"- {path}" for path in missing)
    )

rows.sort(
    key=lambda row: (
        row["best mask mAP50-95"],
        row["best mask mAP50"],
    ),
    reverse=True,
)
for rank, row in enumerate(rows, start=1):
    row["rank"] = rank

fieldnames = [
    "rank",
    "run name",
    "dataset mix",
    "augmentation mode",
    "best epoch",
    "best mask mAP50-95",
    "best mask mAP50",
    "final mask mAP50-95",
    "results path",
]
with summary_csv.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: fmt(row[key]) if isinstance(row[key], float) else row[key]
                for key in fieldnames
            }
        )

md_lines = [
    "# YOLO26 Baseline Metrics Summary",
    "",
    "| Rank | Run Name | Dataset Mix | Augmentation Mode | Best Epoch | Best Mask mAP50-95 | Best Mask mAP50 | Final Mask mAP50-95 | Results Path |",
    "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
]
for row in rows:
    md_lines.append(
        "| {rank} | {run} | {mix} | {aug} | {epoch} | {best_5095} | {best_50} | {final_5095} | {path} |".format(
            rank=row["rank"],
            run=row["run name"],
            mix=row["dataset mix"],
            aug=row["augmentation mode"],
            epoch=row["best epoch"],
            best_5095=fmt(row["best mask mAP50-95"]),
            best_50=fmt(row["best mask mAP50"]),
            final_5095=fmt(row["final mask mAP50-95"]),
            path=row["results path"],
        )
    )
summary_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

print(f"Wrote {summary_csv}")
print(f"Wrote {summary_md}")
print("Top two runs:")
for row in rows[:2]:
    print(
        f"{row['rank']}. {row['run name']} "
        f"best_mAP50-95={fmt(row['best mask mAP50-95'])} "
        f"best_mAP50={fmt(row['best mask mAP50'])}"
    )
PY
REMOTE_EOF
)

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${SSH_BASE[@]}" "$REMOTE_SCRIPT"

    log "==================================================================="
    log "Step 6: Downloading baseline outputs"
    log "==================================================================="

    if [[ -e "$LOCAL_RESULTS_DIR" ]]; then
        BACKUP_PATH="${LOCAL_RESULTS_DIR}.backup_$(date +%Y%m%d_%H%M%S)"
        log "Existing local result directory found; moving it to: ${BACKUP_PATH}"
        mv "$LOCAL_RESULTS_DIR" "$BACKUP_PATH"
    fi
    mkdir -p "$LOCAL_RESULTS_DIR"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" -r \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/runs" \
        "$LOCAL_RESULTS_DIR/"

    retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${SCP_BASE[@]}" \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/baseline_metrics_summary.csv" \
        "${REMOTE_TARGET}:$(shell_quote "$REMOTE_WORKDIR")/baseline_metrics_summary.md" \
        "$LOCAL_RESULTS_DIR/"

    [[ -d "${LOCAL_RESULTS_DIR}/runs/segment" ]] || fail "Downloaded runs/segment directory not found"
    [[ -f "${LOCAL_RESULTS_DIR}/baseline_metrics_summary.csv" ]] || fail "Downloaded baseline_metrics_summary.csv not found"
    [[ -f "${LOCAL_RESULTS_DIR}/baseline_metrics_summary.md" ]] || fail "Downloaded baseline_metrics_summary.md not found"

    log "Results downloaded to: ${LOCAL_RESULTS_DIR}"
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
