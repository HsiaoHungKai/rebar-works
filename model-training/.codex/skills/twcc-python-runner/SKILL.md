---
name: twcc-python-runner
description: Create robust shell scripts that run Python entrypoints on TWCC CCS containers. Use when a user wants to train, infer, batch-process, or otherwise execute a local Python file on TWCC by creating a container, uploading code/data, installing requirements, running the script, downloading outputs, and cleaning up the container.
---

# TWCC Python Runner

Use this skill to generate Bash scripts for one-off Python jobs on TWCC CCS. The script should follow the lifecycle proven by `rebar-segementation-yolo26/train_rebar_seg_yolo26.sh`: create a CCS container, extract SSH info, upload local inputs to a `/tmp` workdir, install dependencies, run Python, download requested outputs, and remove the container with a trap.

If available, also use the `twcc-cli-project` skill for TWCC CLI context, exact flags, and safety checks.

## Workflow

1. Inspect the target Python entrypoint and nearby project files before asking questions.
2. Confirm any high-impact missing inputs:
   - Python entrypoint and arguments.
   - Files or folders to upload, especially datasets, configs, weights, and package modules.
   - Outputs to download after the run.
   - TWCC image type/image/GPU/product type if defaults are not suitable.
3. Prefer `.env` for secrets and connection settings. Required defaults:
   - `PEM_LOCATION`
   - `TWCC_USERNAME`
   - `TWCC_PASSWORD`
4. Discover current TWCC options when recommending a container:
   - `twccli mk ccs --help`
   - `twccli ls ccs -itype`
   - `twccli ls ccs -img`
   - `twccli ls ccs -gpu`
   - `twccli ls ccs -ptype`
5. Generate the run script with `scripts/generate_twcc_python_runner.py` whenever possible.
6. Validate with `bash -n <generated-script>` and review the displayed config before telling the user it is ready.

## Defaults

- Use `.env` by default; do not hardcode TWCC credentials unless the user explicitly requests it.
- Default image type is `PyTorch`.
- If the user wants a PyTorch model workflow and does not specify an image, recommend the latest listed PyTorch image, such as `pytorch-26.02-py3:latest` when available.
- Default GPU flavor is `1`.
- Default remote workdir should be under `/tmp`, for example `/tmp/twcc-python-runner`.
- Always remove the container on script exit using a Bash `trap`, even if the Python command fails.
- Use `sshpass`, `ssh`, `scp`, and `twccli`; fail early if any are missing.

## Dependency Handling

Prefer existing dependency files in this order:

1. User-specified requirements file.
2. `requirements.txt` near the entrypoint or repo root.
3. `pyproject.toml` or local install command if the project already defines packaging.
4. Best-effort generated requirements from imports.

When inferring requirements, map only known imports confidently and leave uncertain modules as comments for user review. Never claim the inferred file is complete without review.

## Script Requirements

Generated scripts should include:

- `set -euo pipefail`, `log`, `fail`, `require_command`, `shell_quote`, and retry helpers.
- Orchestrator mode and `--execute` mode when matching the local pattern is useful.
- Clear config variables near the top for container name, image type, image, GPU flavor, product type, remote workdir, entrypoint, Python args, upload paths, install commands, and download paths.
- `twccli mk ccs ... -wait -table`, then robust parsing of `SITE_ID`.
- `twccli ls ccs -s "$SITE_ID" -gssh` and parsing for IP/port.
- `scp` upload of each requested file/folder into the remote workdir, preserving relative paths.
- Remote install and run block executed over SSH.
- Download of requested outputs into a local output directory, with backups when a target already exists.
- Cleanup with `twccli rm ccs --site-id "$SITE_ID" --force || true`.

## Generator

Use the bundled generator for the initial script shape:

```bash
python .codex/skills/twcc-python-runner/scripts/generate_twcc_python_runner.py \
  --entrypoint path/to/run.py \
  --output run_on_twcc.sh \
  --upload path/to/config.yaml \
  --upload path/to/data \
  --download outputs \
  --python-arg=--config \
  --python-arg path/to/config.yaml
```

After generation, inspect the shell script and adjust any job-specific details rather than rewriting the whole lifecycle.
