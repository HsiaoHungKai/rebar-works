#!/usr/bin/env bash

###############################################################################
# sam3_inference.sh - Automated TWCC CCS Container Setup and SAM3 Inference
#
# This script automates the workflow from twcc_command.md:
# 1. If run without --execute: Sources .env, opens new terminal, reruns itself
# 2. If run with --execute: Executes full TWCC CCS workflow with verbose output
#
# Usage:
#   ./sam3_inference.sh           # Opens terminal and runs workflow
#   ./sam3_inference.sh --execute # Direct execution (used internally)
###############################################################################

set -euo pipefail

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"

# Log function for timestamped messages
log() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"
}

# Error function
fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

# Check if required command exists
require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

###############################################################################
# ORCHESTRATOR MODE - Runs first, spawns terminal
###############################################################################
orchestrator_mode() {
    log "Starting orchestrator mode"
    
    # Validate .env file exists
    [[ -f "$ENV_FILE" ]] || fail ".env file not found at ${ENV_FILE}"
    
    # Source .env and validate required variables
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    
    [[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN not found in .env"
    [[ -n "${PEM_LOCATION:-}" ]] || fail "PEM_LOCATION not found in .env"
    [[ -n "${TWCC_PASSWORD:-}" ]] || fail "TWCC_PASSWORD not found in .env"
    
    log "Environment variables loaded from .env"
    log "HF_TOKEN: ${HF_TOKEN:0:10}..."
    log "PEM_LOCATION: ${PEM_LOCATION}"
    
    # Detect OS and launch terminal
    OS_TYPE="$(uname -s)"
    
    case "$OS_TYPE" in
        Darwin)
            log "Detected macOS - launching Terminal.app"
            osascript <<EOF
tell application "Terminal"
    activate
    set newTab to do script "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
end tell
EOF
            log "Terminal launched. Orchestrator exiting."
            ;;
            
        Linux)
            log "Detected Linux - launching terminal emulator"
            
            # Try different terminal emulators in order of preference
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

###############################################################################
# EXECUTION MODE - Runs in the spawned terminal
###############################################################################
execution_mode() {
    log "==================================================================="
    log "Starting TWCC CCS Container Setup and SAM3 Inference"
    log "==================================================================="
    
    # Source .env file if variables are not already set
    if [[ -z "${HF_TOKEN:-}" || -z "${PEM_LOCATION:-}" || -z "${TWCC_PASSWORD:-}" ]]; then
        log "Loading environment variables from .env"
        [[ -f "$ENV_FILE" ]] || fail ".env file not found at ${ENV_FILE}"
        # shellcheck disable=SC1090
        source "$ENV_FILE"
    fi
    
    # Validate environment variables are now set
    [[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN not set in .env"
    [[ -n "${PEM_LOCATION:-}" ]] || fail "PEM_LOCATION not set in .env"
    [[ -n "${TWCC_PASSWORD:-}" ]] || fail "TWCC_PASSWORD not set in .env"
    
    log "Environment variables loaded successfully"
    
    # Enable verbose mode to show all commands
    set -x
    
    # Check for required commands
    require_command twccli
    require_command ssh
    require_command scp
    # Note: conda is checked and initialized later in Step 1
    
    # Check for sshpass
    if ! command -v sshpass >/dev/null 2>&1; then
        set +x
        log "WARNING: sshpass not found. SSH password automation may not work."
        log "To install sshpass:"
        log "  macOS: brew install hudochenkov/sshpass/sshpass"
        log "  Linux: sudo apt-get install sshpass"
        log ""
        log "Continuing without sshpass - you may need to enter password manually..."
        sleep 3
        set -x
    fi
    
    # Variables for cleanup trap
    SITE_ID=""
    CONTAINER_CREATED=0
    
    # Cleanup function
    cleanup() {
        set +x
        local exit_code=$?
        
        if [[ "$CONTAINER_CREATED" == "1" && -n "$SITE_ID" ]]; then
            log "==================================================================="
            log "Cleaning up TWCC container: ${SITE_ID}"
            log "==================================================================="
            set -x
            twccli rm ccs --site-id "$SITE_ID" --force || true
            set +x
        fi
        
        log "==================================================================="
        if [[ $exit_code -eq 0 ]]; then
            log "Workflow completed successfully!"
        else
            log "Workflow failed with exit code: $exit_code"
        fi
        log "==================================================================="
        
        log "Press Enter to close this window..."
        read -r
        
        exit "$exit_code"
    }
    
    trap cleanup EXIT ERR
    
    # =========================================================================
    # Configuration for SAM3 Inference
    # =========================================================================
    # These can be overridden via environment variables
    SAM3_IMAGE_DIR="${SAM3_IMAGE_DIR:-/tmp/sam3/images}"
    SAM3_PROMPT="${SAM3_PROMPT:-rebar}"
    SAM3_OUTPUT_DIR="${SAM3_OUTPUT_DIR:-/tmp/sam3/results}"
    
    log "SAM3 Inference Configuration:"
    log "  Image Directory: ${SAM3_IMAGE_DIR}"
    log "  Prompt: '${SAM3_PROMPT}'"
    log "  Output Directory: ${SAM3_OUTPUT_DIR}"
    log ""
    
    # Step 1: Go to working directory and activate conda environment
    set +x
    log "==================================================================="
    log "Step 1: Activating conda environment"
    log "==================================================================="
    
    cd "$SCRIPT_DIR"
    
    # Find and initialize conda
    CONDA_BASE=""
    if command -v conda >/dev/null 2>&1; then
        # conda is already in PATH, get its base
        CONDA_BASE="$(conda info --base 2>/dev/null || true)"
    fi
    
    # If conda not found or base not detected, try common locations
    if [[ -z "$CONDA_BASE" ]]; then
        if [[ -d "$HOME/miniconda3" ]]; then
            CONDA_BASE="$HOME/miniconda3"
        elif [[ -d "$HOME/anaconda3" ]]; then
            CONDA_BASE="$HOME/anaconda3"
        elif [[ -d "/opt/conda" ]]; then
            CONDA_BASE="/opt/conda"
        elif [[ -d "/usr/local/anaconda3" ]]; then
            CONDA_BASE="/usr/local/anaconda3"
        elif [[ -d "/usr/local/miniconda3" ]]; then
            CONDA_BASE="/usr/local/miniconda3"
        else
            fail "conda not found. Please install Anaconda or Miniconda."
        fi
    fi
    
    log "Found conda at: $CONDA_BASE"
    
    # Source conda.sh to enable conda commands
    if [[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]]; then
        source "$CONDA_BASE/etc/profile.d/conda.sh"
    else
        fail "conda.sh not found at $CONDA_BASE/etc/profile.d/conda.sh"
    fi
    
    # Now conda activate should work
    set -x
    conda activate rebar-works
    set +x
    log "Successfully activated conda environment: rebar-works"
    
    # Step 2: Create TWCC CCS container
    set +x
    log "==================================================================="
    log "Step 2: Creating TWCC CCS container"
    log "==================================================================="
    set -x
    
    # Capture the output to extract SITE_ID
    TEMP_CREATE=$(mktemp)
    twccli mk ccs \
        -n "sam3-test" \
        -itype "PyTorch" \
        -img "pytorch-26.02-py3:latest" \
        -gpu 1 \
        -wait \
        -table | tee "$TEMP_CREATE"
    
    CONTAINER_CREATED=1
    
    # Step 3: Extract SITE_ID from creation output
    set +x
    log "==================================================================="
    log "Step 3: Extracting container connection info"
    log "==================================================================="
    
    # Parse SITE_ID from the "CCS Site:XXXXXXX" line or from the table
    if grep -q "CCS Site:" "$TEMP_CREATE"; then
        SITE_ID=$(grep "CCS Site:" "$TEMP_CREATE" | sed -E 's/.*CCS Site:([0-9]+).*/\1/')
    else
        # Fallback: extract from table (first column after the header)
        SITE_ID=$(grep "sam3-test" "$TEMP_CREATE" | grep -v "name" | awk '{print $2}')
    fi
    
    log "Extracted SITE_ID: $SITE_ID"
    
    [[ -n "$SITE_ID" ]] || fail "Failed to extract SITE_ID from container creation output"
    
    # Get SSH connection info using the SITE_ID with -gssh flag
    log "Retrieving SSH connection details using -gssh..."
    set -x
    TEMP_INFO=$(mktemp)
    twccli ls ccs -s "$SITE_ID" -gssh > "$TEMP_INFO" 2>&1 || true
    cat "$TEMP_INFO"
    set +x
    
    # Parse IP and PORT from -gssh output
    # Expected format: ssh user@IP_ADDRESS -p PORT or similar
    log "Parsing SSH connection details from -gssh output..."
    
    # Extract IP address from user@IP format
    if grep -q "@" "$TEMP_INFO"; then
        IP_ADDRESS=$(grep "@" "$TEMP_INFO" | grep -v "User" | head -n 1 | sed -E 's/.*@([^ ]+).*/\1/')
        log "Extracted IP from user@host format: $IP_ADDRESS"
    else
        # Fallback: extract any IP address from output
        IP_ADDRESS=$(grep -oE "[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}" "$TEMP_INFO" | grep -v "^0\." | head -n 1)
        log "Extracted IP from general pattern: $IP_ADDRESS"
    fi
    
    # Extract port from -p PORT format
    if grep -q "\-p" "$TEMP_INFO"; then
        PORT=$(grep "\-p" "$TEMP_INFO" | sed -E 's/.*-p[[:space:]]*([0-9]+).*/\1/')
        log "Extracted PORT from -p flag: $PORT"
    else
        # Fallback: look for any port number pattern
        PORT=$(grep -oE "port[[:space:]]*:?[[:space:]]*[0-9]{2,5}" "$TEMP_INFO" -i | grep -oE "[0-9]{2,5}" | head -n 1)
        if [[ -z "$PORT" ]]; then
            PORT="22"  # Default SSH port
            log "No port found, using default: $PORT"
        else
            log "Extracted PORT from pattern: $PORT"
        fi
    fi
    
    rm -f "$TEMP_CREATE" "$TEMP_INFO"
    
    set +x
    log "Container Info:"
    log "  SITE_ID: $SITE_ID"
    log "  IP: $IP_ADDRESS"
    log "  PORT: $PORT"
    set -x
    
    [[ -n "$SITE_ID" ]] || fail "Failed to extract SITE_ID"
    [[ -n "$IP_ADDRESS" ]] || fail "Failed to extract IP_ADDRESS"
    [[ -n "$PORT" ]] || fail "Failed to extract PORT"
    
    # Step 4: Set SSH key permissions
    set +x
    log "==================================================================="
    log "Step 4: Setting SSH key permissions"
    log "==================================================================="
    set -x
    
    chmod 400 "$PEM_LOCATION"
    
    # Step 5: Upload Python script to container
    set +x
    log "==================================================================="
    log "Step 5: Uploading sam3_inference.py to container"
    log "==================================================================="
    set -x
    
    # Wait a bit for container to be fully ready
    sleep 10
    
    # Create /tmp/sam3 directory on remote container
    log "Creating /tmp/sam3 directory on container..."
    sshpass -p "$TWCC_PASSWORD" ssh \
        -i "$PEM_LOCATION" \
        -p "$PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        "u7740467@${IP_ADDRESS}" \
        "mkdir -p /tmp/sam3"
    log "Directory /tmp/sam3 created successfully"
    
    # Upload Python script and requirements.txt using sshpass
    log "Uploading sam3_inference.py and requirements.txt..."
    sshpass -p "$TWCC_PASSWORD" scp \
        -i "$PEM_LOCATION" \
        -P "$PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        sam3_inference.py requirements.txt "u7740467@${IP_ADDRESS}:/tmp/sam3/"
    
    # Upload images directory if it exists
    if [ -d "./images" ]; then
        log "Uploading images directory to container..."
        
        # Create /tmp/sam3/images directory on remote container
        sshpass -p "$TWCC_PASSWORD" ssh \
            -i "$PEM_LOCATION" \
            -p "$PORT" \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "u7740467@${IP_ADDRESS}" \
            "mkdir -p /tmp/sam3/images"
        
        # Upload all files from ./images to /tmp/sam3/images
        sshpass -p "$TWCC_PASSWORD" scp \
            -i "$PEM_LOCATION" \
            -P "$PORT" \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -r ./images/* "u7740467@${IP_ADDRESS}:/tmp/sam3/images/"
        
        # Validate files were uploaded to remote server
        FILE_COUNT=$(sshpass -p "$TWCC_PASSWORD" ssh \
            -i "$PEM_LOCATION" \
            -p "$PORT" \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            "u7740467@${IP_ADDRESS}" \
            "ls /tmp/sam3/images 2>/dev/null | wc -l")
        
        if [ "$FILE_COUNT" -gt 0 ]; then
            log "Images uploaded successfully ($FILE_COUNT files in /tmp/sam3/images)"
        else
            log "Warning: Upload completed but no files found in /tmp/sam3/images on remote server"
        fi
    else
        log "Warning: ./images directory not found, skipping image upload"
    fi
    
    # Step 6: SSH into container and run setup + inference
    set +x
    log "==================================================================="
    log "Step 6: SSHing into container and running setup"
    log "==================================================================="
    set -x
    
    # Create a script to run remotely
    REMOTE_SCRIPT=$(cat <<'REMOTE_EOF'
set -x
set -euo pipefail

# Change to the working directory where sam3_inference.py was uploaded
cd /tmp/sam3

# Install required packages from requirements.txt
pip install -r requirements.txt

# Export HF token and run inference
export HF_TOKEN="__HF_TOKEN_PLACEHOLDER__"
python sam3_inference.py \
    --image-dir __IMAGE_DIR_PLACEHOLDER__ \
    --prompt "__PROMPT_PLACEHOLDER__" \
    --output-dir __OUTPUT_DIR_PLACEHOLDER__ 
REMOTE_EOF
)
    
    # Replace placeholders with actual values
    REMOTE_SCRIPT="${REMOTE_SCRIPT//__HF_TOKEN_PLACEHOLDER__/$HF_TOKEN}"
    REMOTE_SCRIPT="${REMOTE_SCRIPT//__IMAGE_DIR_PLACEHOLDER__/$SAM3_IMAGE_DIR}"
    REMOTE_SCRIPT="${REMOTE_SCRIPT//__PROMPT_PLACEHOLDER__/$SAM3_PROMPT}"
    REMOTE_SCRIPT="${REMOTE_SCRIPT//__OUTPUT_DIR_PLACEHOLDER__/$SAM3_OUTPUT_DIR}"
    
    # Execute remote script
    sshpass -p "$TWCC_PASSWORD" ssh \
        -i "$PEM_LOCATION" \
        -p "$PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        "u7740467@${IP_ADDRESS}" \
        "$REMOTE_SCRIPT"
    
    set +x
    log "==================================================================="
    log "Inference completed!"
    log "==================================================================="
    
    # Step 7: Download results file
    log "==================================================================="
    log "Step 7: Downloading results from container"
    log "==================================================================="
    set -x

    # Download sam3_results.json from remote container
    sshpass -p "$TWCC_PASSWORD" scp \
        -i "$PEM_LOCATION" \
        -P "$PORT" \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        "u7740467@${IP_ADDRESS}:/tmp/sam3/sam3_results.json" \
        ./results
    
    set +x
    if [[ -f sam3_results.json ]]; then
        log "Results successfully downloaded to: $(pwd)/sam3_results.json"
    else
        log "WARNING: Failed to download results file"
    fi
    
    log "Container will be cleaned up automatically..."
    
    # Cleanup will be handled by trap
}

###############################################################################
# MAIN ENTRY POINT
###############################################################################
main() {
    # Check if --execute flag is present
    if [[ "${1:-}" == "--execute" ]]; then
        execution_mode
    else
        orchestrator_mode
    fi
}

# Run main function
main "$@"
