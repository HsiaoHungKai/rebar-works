# sam3_inference.sh - Usage Guide

## Overview
`sam3_inference.sh` is an automated script that sets up a TWCC CCS container, runs SAM3 inference, and cleans up resources. It opens a new terminal window to visualize all commands as they execute.

## Prerequisites

### Required
- **TWCC CLI** (`twccli`) - must be installed and configured
- **Conda** - Anaconda or Miniconda with `rebar-works` environment
- **SSH/SCP** - for connecting to the container
- **.env file** - must contain:
  ```
  HF_TOKEN=your_huggingface_token
  PEM_LOCATION=/path/to/your/key.pem
  TWCC_PASSWORD=your_twcc_password
  ```

### Optional but Recommended
- **sshpass** - for automated SSH password entry
  - macOS: `brew install hudochenkov/sshpass/sshpass`
  - Linux: `sudo apt-get install sshpass`
  - Without this, you'll need to manually enter the password when prompted

## Usage

### Basic Usage
Simply run the script from the directory:
```bash
./sam3_inference.sh
```

This will:
1. Load environment variables from `.env`
2. Open a new terminal window
3. Execute the full TWCC workflow with verbose output
4. Clean up the container automatically when done

### What the Script Does

#### Step 1: Environment Setup
- Validates `.env` file exists
- Loads `HF_TOKEN`, `PEM_LOCATION`, `TWCC_PASSWORD`
- Checks for required commands (`twccli`, `ssh`, `scp`, `conda`)

#### Step 2: Terminal Launching
- Detects OS (macOS or Linux)
- Opens a new terminal window
- Reruns itself in execution mode

#### Step 3: Conda Activation
- Navigates to the script directory
- Activates the `rebar-works` conda environment

#### Step 4: TWCC Container Creation
- Creates a CCS container named `sam3-test`
- Uses PyTorch image: `pytorch-26.02-py3:latest`
- Allocates 1 GPU
- Waits for container to be ready

#### Step 5: Connection Info Retrieval
- Lists container information
- Extracts SITE_ID, IP address, and SSH port
- Displays connection details

#### Step 6: SSH Key Permissions
- Sets correct permissions on the SSH key (chmod 400)

#### Step 7: Script Upload
- Uploads `sam3_inference.py` to the container via SCP
- Uses `sshpass` for automated password entry (if available)

#### Step 8: Remote Setup & Inference
- SSHs into the container
- Downloads and installs Miniconda
- Initializes Conda
- Installs required Python packages (`transformers`, `Pillow`, `requests`)
- Exports `HF_TOKEN`
- Runs `sam3_inference.py`

#### Step 9: Cleanup
- Automatically deletes the TWCC container
- Shows completion status
- Waits for user to press Enter before closing

## Manual Execution Mode

If you need to run the script directly in your current terminal (for debugging):
```bash
source .env
./sam3_inference.sh --execute
```

## Troubleshooting

### "sshpass not found" Warning
The script will still work, but you'll need to manually enter the TWCC password when prompted. Install `sshpass` for full automation.

### "conda not found" Error
Make sure Anaconda or Miniconda is installed and the conda command is in your PATH. The script attempts to source conda from standard locations (`~/miniconda3` or `~/anaconda3`).

### "twccli not found" Error
Install and configure the TWCC CLI tool. See TWCC documentation for setup instructions.

### Container Creation Fails
- Check your TWCC account has available quota
- Verify you're logged into `twccli` with valid credentials
- Check that the `sam3-test` container name isn't already in use

### SSH Connection Timeout
The script waits 10 seconds after container creation before attempting SCP. If this isn't enough time, the container might not be fully ready. You can manually increase the sleep time in the script.

## Customization

### Changing Container Name
Edit line with `twccli mk ccs -n "sam3-test"` to use a different name.

### Changing GPU Count
Edit the `-gpu 1` parameter in the `twccli mk ccs` command.

### Changing PyTorch Image
Edit the `-img "pytorch-26.02-py3:latest"` parameter.

### Disabling Auto-Cleanup
Comment out or remove the `cleanup()` function trap to keep the container running after the script finishes.

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `HF_TOKEN` | Hugging Face API token for accessing SAM3 model | `hf_xxxxx...` |
| `PEM_LOCATION` | Path to TWCC SSH private key | `/Users/you/.twcc_data/key1.pem` |
| `TWCC_PASSWORD` | Password for SSH authentication to container | `YourPassword123` |

## Script Modes

### Orchestrator Mode (Default)
- Triggered when script is run without arguments
- Loads `.env` and validates variables
- Spawns a new terminal window
- Exits after launching terminal

### Execution Mode (--execute)
- Triggered with `--execute` flag
- Runs the full TWCC workflow
- Shows verbose output (`set -x`)
- Handles cleanup on exit

## Exit Codes

- `0` - Success
- `1` - Error (see error message for details)

Common error scenarios:
- Missing `.env` file
- Missing required environment variables
- Missing required commands (`twccli`, `ssh`, `scp`, `conda`)
- Container creation failure
- SSH connection failure

## Security Notes

- The `.env` file contains sensitive credentials - never commit it to version control
- SSH key permissions must be 400 (the script sets this automatically)
- The HF_TOKEN is exported in the remote container for model access
- TWCC_PASSWORD is used by `sshpass` or manual entry

## Support

For TWCC-related issues, consult the TWCC documentation or support channels.
For script bugs or improvements, contact the script maintainer.
