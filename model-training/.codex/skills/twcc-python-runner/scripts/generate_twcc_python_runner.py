#!/usr/bin/env python3
"""Generate a Bash runner for Python jobs on TWCC CCS."""

from __future__ import annotations

import argparse
import ast
import shlex
from pathlib import Path
from textwrap import dedent


IMPORT_TO_PACKAGE = {
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "sklearn": "scikit-learn",
    "yaml": "pyyaml",
    "numpy": "numpy",
    "pandas": "pandas",
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
    "matplotlib": "matplotlib",
    "tqdm": "tqdm",
    "scipy": "scipy",
    "transformers": "transformers",
    "datasets": "datasets",
    "accelerate": "accelerate",
}

STDLIB_MODULES = set(getattr(__import__("sys"), "stdlib_module_names", ()))


def q(value: str | Path) -> str:
    return shlex.quote(str(value))


def bash_array(values: list[str]) -> str:
    if not values:
        return "()"
    return "(\n" + "\n".join(f"    {q(v)}" for v in values) + "\n)"


def rel_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def parse_imports(py_file: Path) -> set[str]:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except Exception:
        return set()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def discover_python_files(entrypoint: Path, uploads: list[Path], root: Path) -> list[Path]:
    files = {entrypoint.resolve()}
    for upload in uploads:
        if upload.is_file() and upload.suffix == ".py":
            files.add(upload.resolve())
        elif upload.is_dir():
            for py_file in upload.rglob("*.py"):
                if ".git" not in py_file.parts:
                    files.add(py_file.resolve())
    return sorted(files)


def infer_requirements(entrypoint: Path, uploads: list[Path], root: Path) -> tuple[list[str], list[str]]:
    local_top_levels = {
        p.stem for p in root.glob("*.py")
    } | {
        p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    }
    modules: set[str] = set()
    for py_file in discover_python_files(entrypoint, uploads, root):
        modules.update(parse_imports(py_file))

    packages: set[str] = set()
    uncertain: set[str] = set()
    for module in sorted(modules):
        if module in STDLIB_MODULES or module in local_top_levels:
            continue
        package = IMPORT_TO_PACKAGE.get(module)
        if package:
            packages.add(package)
        elif module and not module.startswith("_"):
            uncertain.add(module)
    return sorted(packages), sorted(uncertain)


def find_requirements(entrypoint: Path, root: Path) -> Path | None:
    candidates = [
        entrypoint.parent / "requirements.txt",
        root / "requirements.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def write_inferred_requirements(output: Path, packages: list[str], uncertain: list[str]) -> Path:
    req_path = output.with_suffix(".requirements.txt")
    lines = [
        "# Best-effort requirements inferred from imports.",
        "# Review before running on TWCC.",
        *packages,
    ]
    if uncertain:
        lines.append("")
        lines.append("# Unmapped imports that may need packages:")
        lines.extend(f"# {name}" for name in uncertain)
    req_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return req_path


def build_script(args: argparse.Namespace, upload_paths: list[str], requirement_path: str | None) -> str:
    python_args = " ".join(q(arg) for arg in args.python_arg)
    product_type_line = f'TWCC_PRODUCT_TYPE="${{TWCC_PRODUCT_TYPE:-{args.product_type}}}"' if args.product_type else 'TWCC_PRODUCT_TYPE="${TWCC_PRODUCT_TYPE:-}"'
    image_line = f'TWCC_IMAGE="${{TWCC_IMAGE:-{args.image}}}"' if args.image else 'TWCC_IMAGE="${TWCC_IMAGE:-}"'
    req_line = f'REQUIREMENTS_FILE="${{REQUIREMENTS_FILE:-{requirement_path}}}"' if requirement_path else 'REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-}"'
    download_array = bash_array(args.download)
    upload_array = bash_array(upload_paths)

    script = dedent(f"""\
        #!/usr/bin/env bash

        set -euo pipefail

        SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
        REPO_ROOT="$(cd "${{SCRIPT_DIR}}" && pwd)"
        ENV_FILE="${{ENV_FILE:-${{REPO_ROOT}}/.env}}"
        SCRIPT_PATH="${{SCRIPT_DIR}}/$(basename "${{BASH_SOURCE[0]}}")"

        TWCC_CONTAINER_NAME="${{TWCC_CONTAINER_NAME:-{args.container_name}}}"
        TWCC_IMAGE_TYPE="${{TWCC_IMAGE_TYPE:-{args.image_type}}}"
        {image_line}
        TWCC_GPU="${{TWCC_GPU:-{args.gpu}}}"
        {product_type_line}
        REMOTE_WORKDIR="${{REMOTE_WORKDIR:-{args.remote_workdir}}}"
        LOCAL_OUTPUT_DIR="${{LOCAL_OUTPUT_DIR:-{args.local_output_dir}}}"

        PYTHON_ENTRYPOINT="${{PYTHON_ENTRYPOINT:-{args.entrypoint_rel}}}"
        PYTHON_ARGS=({python_args})
        {req_line}
        UPLOAD_PATHS={upload_array}
        DOWNLOAD_PATHS={download_array}

        log() {{
            printf '[%s] %s\\n' "$(date +%H:%M:%S)" "$*"
        }}

        fail() {{
            printf 'Error: %s\\n' "$*" >&2
            exit 1
        }}

        require_command() {{
            command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
        }}

        shell_quote() {{
            printf '%q' "$1"
        }}

        retry_sshpass_cmd() {{
            local max_attempts=5
            local delays=(1 2 4 8)
            local attempt=1
            local cmd=("$@")

            while [ "$attempt" -le "$max_attempts" ]; do
                local display_cmd=("${{cmd[@]}}")
                local i
                for i in "${{!display_cmd[@]}}"; do
                    if [[ "${{display_cmd[$i]}}" == "-p" && $((i + 1)) -lt ${{#display_cmd[@]}} ]]; then
                        display_cmd[$((i + 1))]="********"
                    fi
                done
                log "Attempt $attempt/$max_attempts: ${{display_cmd[*]}}"

                if "${{cmd[@]}}"; then
                    return 0
                fi

                if [ "$attempt" -lt "$max_attempts" ]; then
                    local delay=${{delays[$((attempt - 1))]}}
                    log "Command failed, retrying in ${{delay}}s..."
                    sleep "$delay"
                else
                    return 1
                fi
                ((attempt++))
            done
        }}

        load_and_validate_env() {{
            [[ -f "$ENV_FILE" ]] || fail ".env file not found at $ENV_FILE"
            # shellcheck disable=SC1090
            source "$ENV_FILE"

            [[ -n "${{PEM_LOCATION:-}}" ]] || fail "PEM_LOCATION not set"
            [[ -n "${{TWCC_PASSWORD:-}}" ]] || fail "TWCC_PASSWORD not set"
            [[ -n "${{TWCC_USERNAME:-}}" ]] || fail "TWCC_USERNAME not set"
        }}

        orchestrator_mode() {{
            load_and_validate_env
            case "$(uname -s)" in
                Darwin)
                    osascript <<EOF
        tell application "Terminal"
            activate
            do script "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
        end tell
        EOF
                    ;;
                Linux)
                    if command -v gnome-terminal >/dev/null 2>&1; then
                        gnome-terminal -- bash -c "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute; exec bash"
                    elif command -v xterm >/dev/null 2>&1; then
                        xterm -hold -e "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
                    elif command -v x-terminal-emulator >/dev/null 2>&1; then
                        x-terminal-emulator -e "cd '$SCRIPT_DIR' && '$SCRIPT_PATH' --execute"
                    else
                        fail "No suitable terminal emulator found. Run: $SCRIPT_PATH --execute"
                    fi
                    ;;
                *)
                    fail "Unsupported operating system: $(uname -s)"
                    ;;
            esac
        }}

        execution_mode() {{
            load_and_validate_env
            require_command twccli
            require_command ssh
            require_command scp
            require_command sshpass

            cd "$REPO_ROOT"
            [[ -f "$PYTHON_ENTRYPOINT" ]] || fail "Python entrypoint not found: $PYTHON_ENTRYPOINT"
            if [[ -n "$REQUIREMENTS_FILE" ]]; then
                [[ -f "$REQUIREMENTS_FILE" ]] || fail "requirements file not found: $REQUIREMENTS_FILE"
            fi
            for upload_path in "${{UPLOAD_PATHS[@]}}"; do
                [[ -e "$upload_path" ]] || fail "upload path not found: $upload_path"
            done

            SITE_ID=""
            CONTAINER_CREATED=0

            cleanup() {{
                local exit_code=$?
                if [[ "$CONTAINER_CREATED" == "1" && -n "$SITE_ID" ]]; then
                    log "Cleaning up TWCC container: $SITE_ID"
                    twccli rm ccs --site-id "$SITE_ID" --force || true
                fi
                if [[ "$exit_code" -eq 0 ]]; then
                    log "Workflow completed successfully"
                else
                    log "Workflow failed with exit code: $exit_code"
                fi
                log "Press Enter to close this window..."
                read -r || true
                exit "$exit_code"
            }}
            trap cleanup EXIT

            log "Container: $TWCC_CONTAINER_NAME"
            log "Image type: $TWCC_IMAGE_TYPE"
            log "Image: ${{TWCC_IMAGE:-<TWCC default>}}"
            log "GPU: $TWCC_GPU"
            log "Product type: ${{TWCC_PRODUCT_TYPE:-<TWCC default>}}"
            log "Remote workdir: $REMOTE_WORKDIR"
            log "Python entrypoint: $PYTHON_ENTRYPOINT"

            TEMP_CREATE="$(mktemp)"
            CREATE_CMD=(twccli mk ccs -n "$TWCC_CONTAINER_NAME" -itype "$TWCC_IMAGE_TYPE" -gpu "$TWCC_GPU" -wait -table)
            if [[ -n "$TWCC_IMAGE" ]]; then
                CREATE_CMD+=(-img "$TWCC_IMAGE")
            fi
            if [[ -n "$TWCC_PRODUCT_TYPE" ]]; then
                CREATE_CMD+=(-ptype "$TWCC_PRODUCT_TYPE")
            fi
            "${{CREATE_CMD[@]}}" | tee "$TEMP_CREATE"
            CONTAINER_CREATED=1

            if grep -q "CCS Site:" "$TEMP_CREATE"; then
                SITE_ID="$(grep "CCS Site:" "$TEMP_CREATE" | sed -E 's/.*CCS Site:([0-9]+).*/\\1/' || true)"
            else
                SITE_ID="$(grep "$TWCC_CONTAINER_NAME" "$TEMP_CREATE" | grep -v "name" | awk '{{print $2}}' || true)"
            fi
            [[ -n "$SITE_ID" ]] || fail "Failed to extract SITE_ID"

            TEMP_INFO="$(mktemp)"
            twccli ls ccs -s "$SITE_ID" -gssh > "$TEMP_INFO" 2>&1 || true
            cat "$TEMP_INFO"

            if grep -q "@" "$TEMP_INFO"; then
                IP_ADDRESS="$(grep "@" "$TEMP_INFO" | grep -v "User" | head -n 1 | sed -E 's/.*@([^ ]+).*/\\1/' || true)"
            else
                IP_ADDRESS="$(grep -oE "[0-9]{{1,3}}\\.[0-9]{{1,3}}\\.[0-9]{{1,3}}\\.[0-9]{{1,3}}" "$TEMP_INFO" | grep -v "^0\\." | head -n 1 || true)"
            fi

            if grep -q "\\-p" "$TEMP_INFO"; then
                PORT="$(grep "\\-p" "$TEMP_INFO" | sed -E 's/.*-p[[:space:]]*([0-9]+).*/\\1/' || true)"
            else
                PORT="$(grep -oE "port[[:space:]]*:?[[:space:]]*[0-9]{{2,5}}" "$TEMP_INFO" -i | grep -oE "[0-9]{{2,5}}" | head -n 1 || true)"
                PORT="${{PORT:-22}}"
            fi
            rm -f "$TEMP_CREATE" "$TEMP_INFO"
            [[ -n "$IP_ADDRESS" ]] || fail "Failed to extract IP_ADDRESS"
            [[ -n "$PORT" ]] || fail "Failed to extract PORT"

            REMOTE_TARGET="${{TWCC_USERNAME}}@${{IP_ADDRESS}}"
            chmod 400 "$PEM_LOCATION"
            sleep 10

            SSH_BASE=(-i "$PEM_LOCATION" -p "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$REMOTE_TARGET")
            SCP_BASE=(-i "$PEM_LOCATION" -P "$PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null)

            retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${{SSH_BASE[@]}}" \\
                "rm -rf $(shell_quote "$REMOTE_WORKDIR") && mkdir -p $(shell_quote "$REMOTE_WORKDIR")"

            for upload_path in "${{UPLOAD_PATHS[@]}}"; do
                remote_parent="$REMOTE_WORKDIR/$(dirname "$upload_path")"
                retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${{SSH_BASE[@]}}" \\
                    "mkdir -p $(shell_quote "$remote_parent")"
                retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${{SCP_BASE[@]}}" -r \\
                    "$upload_path" "${{REMOTE_TARGET}}:$(shell_quote "$remote_parent")/"
            done

            REMOTE_ENTRYPOINT="$REMOTE_WORKDIR/$PYTHON_ENTRYPOINT"
            REMOTE_REQUIREMENTS=""
            if [[ -n "$REQUIREMENTS_FILE" ]]; then
                REMOTE_REQUIREMENTS="$REMOTE_WORKDIR/$REQUIREMENTS_FILE"
            fi
            REMOTE_PYTHON_ARGS=()
            for python_arg in "${{PYTHON_ARGS[@]}}"; do
                REMOTE_PYTHON_ARGS+=("$(shell_quote "$python_arg")")
            done

            REMOTE_SCRIPT="$(cat <<REMOTE_EOF
        set -euo pipefail
        set -x
        export MPLCONFIGDIR=$(shell_quote "$REMOTE_WORKDIR/.cache/matplotlib")
        mkdir -p "\\$MPLCONFIGDIR"
        cd $(shell_quote "$REMOTE_WORKDIR")
        python -m pip install --upgrade pip
        if [[ -n $(shell_quote "$REMOTE_REQUIREMENTS") ]]; then
            python -m pip install --upgrade -r $(shell_quote "$REMOTE_REQUIREMENTS")
        fi
        python $(shell_quote "$REMOTE_ENTRYPOINT") ${{REMOTE_PYTHON_ARGS[*]}}
        REMOTE_EOF
        )"

            retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" ssh "${{SSH_BASE[@]}}" "$REMOTE_SCRIPT"

            mkdir -p "$LOCAL_OUTPUT_DIR"
            for download_path in "${{DOWNLOAD_PATHS[@]}}"; do
                local_name="$(basename "$download_path")"
                local_target="$LOCAL_OUTPUT_DIR/$local_name"
                if [[ -e "$local_target" ]]; then
                    backup_path="${{local_target}}.backup_$(date +%Y%m%d_%H%M%S)"
                    log "Existing local result found; moving it to: $backup_path"
                    mv "$local_target" "$backup_path"
                fi
                retry_sshpass_cmd sshpass -p "$TWCC_PASSWORD" scp "${{SCP_BASE[@]}}" -r \\
                    "${{REMOTE_TARGET}}:$(shell_quote "$REMOTE_WORKDIR/$download_path")" \\
                    "$LOCAL_OUTPUT_DIR/"
            done
        }}

        main() {{
            if [[ "${{1:-}}" == "--execute" ]]; then
                execution_mode
            else
                orchestrator_mode
            fi
        }}

        main "$@"
        """)
    return "\n".join(line[8:] if line.startswith("        ") else line for line in script.splitlines()) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrypoint", required=True, help="Python entrypoint to run on TWCC.")
    parser.add_argument("--output", required=True, help="Generated shell script path.")
    parser.add_argument("--upload", action="append", default=[], help="File or directory to upload. Repeatable.")
    parser.add_argument("--download", action="append", default=[], help="Remote path under workdir to download. Repeatable.")
    parser.add_argument("--python-arg", action="append", default=[], help="Argument passed to the Python entrypoint. Repeatable. Use --python-arg=--flag for dash-prefixed values.")
    parser.add_argument("--requirements", help="Requirements file to install. Use 'none' to skip.")
    parser.add_argument("--container-name", default="twcc-python-run")
    parser.add_argument("--image-type", default="PyTorch")
    parser.add_argument("--image", default="pytorch-26.02-py3:latest")
    parser.add_argument("--gpu", default="1")
    parser.add_argument("--product-type", default="")
    parser.add_argument("--remote-workdir", default="/tmp/twcc-python-runner")
    parser.add_argument("--local-output-dir", default="results")
    parser.add_argument("python_args", nargs=argparse.REMAINDER, help="Values after -- are passed to the Python entrypoint.")
    args = parser.parse_args()
    if args.python_args and args.python_args[0] == "--":
        args.python_args = args.python_args[1:]
    args.python_arg.extend(args.python_args)
    return args


def main() -> None:
    args = parse_args()
    entrypoint = Path(args.entrypoint)
    if not entrypoint.exists():
        raise SystemExit(f"entrypoint not found: {entrypoint}")

    root = Path.cwd().resolve()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    upload_paths = [Path(p) for p in args.upload]
    for path in upload_paths:
        if not path.exists():
            raise SystemExit(f"upload path not found: {path}")

    upload_rel = [rel_to_root(entrypoint, root)]
    for path in upload_paths:
        rel = rel_to_root(path, root)
        if rel not in upload_rel:
            upload_rel.append(rel)

    requirement_rel: str | None = None
    if args.requirements != "none":
        requirement_path = Path(args.requirements) if args.requirements else find_requirements(entrypoint, root)
        if requirement_path and requirement_path.exists():
            requirement_rel = rel_to_root(requirement_path, root)
        elif not args.requirements:
            packages, uncertain = infer_requirements(entrypoint, upload_paths, root)
            if packages or uncertain:
                generated_req = write_inferred_requirements(output, packages, uncertain)
                requirement_rel = rel_to_root(generated_req, root)
            else:
                requirement_rel = None
        else:
            raise SystemExit(f"requirements file not found: {requirement_path}")

    if requirement_rel and requirement_rel not in upload_rel:
        upload_rel.append(requirement_rel)

    args.entrypoint_rel = rel_to_root(entrypoint, root)
    script = build_script(args, upload_rel, requirement_rel)
    output.write_text(script, encoding="utf-8")
    output.chmod(0o755)
    print(f"Generated {output}")
    if requirement_rel:
        print(f"Using requirements: {requirement_rel}")
    if not args.download:
        print("No download paths configured; edit DOWNLOAD_PATHS before running if outputs are needed.")


if __name__ == "__main__":
    main()
