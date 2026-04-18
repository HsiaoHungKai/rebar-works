# Repository Guidelines

## Project Structure & Module Organization
`sam3_inference.py` is the main entrypoint and contains model loading, batch image discovery, and JSON/NPZ result serialization. `run_sam3_on_twcc.sh` automates remote execution on TWCC, while `twccli_tutorial.md` is the student-facing TWCC CLI walkthrough and should stay generic, instructional, and free of personal or account-specific information. `images/` holds local input images, `results/` stores downloaded or local inference outputs, and `visualize.ipynb` is for ad hoc inspection.

## Build, Test, and Development Commands
Create a local environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run local inference with the checked-in CLI:

```bash
python sam3_inference.py --image-dir ./images --prompt "rebar" --output-dir ./results
```

Run the TWCC workflow when `.env` is configured with `HF_TOKEN`, `PEM_LOCATION`, and `TWCC_PASSWORD`:

```bash
./run_sam3_on_twcc.sh
```

## Coding Style & Naming Conventions
Follow the existing style in `sam3_inference.py`: 4-space indentation, `snake_case` for functions and variables, `PascalCase` for classes, and type hints on public functions. Keep modules focused; this repo currently favors one clear script over a package hierarchy. Preserve shell strict mode in Bash (`set -euo pipefail`) and keep helper names verb-first, such as `require_command` or `retry_sshpass_cmd`. No formatter or linter is configured, so keep edits small and internally consistent.

## Testing Guidelines
There is no automated test suite yet. For Python changes, run a representative CLI command against files in `images/` and verify both `.json` metadata and `.npz` outputs land in `results/`. For TWCC script changes, validate argument flow and environment checks locally before running the full remote workflow. Add tests in a future `tests/` directory if logic becomes reusable enough to justify unit coverage.

## Commit & Pull Request Guidelines
Recent history uses Conventional Commit prefixes such as `feat:` and `refactor:`. Continue that format with short, imperative summaries, for example `fix: handle empty image directory`. PRs should describe the scenario tested, note any TWCC or Hugging Face assumptions, and include sample output paths or screenshots when notebook or result-format changes affect review.

## Security & Configuration Tips
Do not commit `.env`, tokens, PEM paths, downloaded secrets, or any personal TWCC identifiers such as usernames, hosts, site IDs, or ports. Keep documentation examples sanitized with placeholders. Keep large inference artifacts out of Git unless they are intentionally curated examples.
