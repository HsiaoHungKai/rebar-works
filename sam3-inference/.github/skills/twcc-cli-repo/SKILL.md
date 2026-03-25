---
name: twcc-cli-repo
description: Repository-local guidance for using the TWCC CLI (`twccli`) to inspect, create, modify, network-configure, copy, and remove TWCC resources. Use when Copilot needs to map a user request to `twccli` command families, work from the TWCC CLI documentation, or keep TWCC-related notes and artifacts scoped to the current repository instead of global skill state.
---

# TWCC CLI Repo

Use this skill to operate `twccli` from the current repository and to ground command choices in the TWCC CLI documentation.

## Workflow

1. Verify local availability before planning around the CLI.
   Run `command -v twccli` and `twccli --help`.
   If the binary is missing, stop and tell the user what is unavailable.

2. Establish identity and project context before changing resources.
   Prefer `twccli config whoami`, `twccli info proj -json`, and `twccli info quota -json`.
   Treat `twccli config init` as a user-sensitive, non-repo change because it updates CLI configuration and API-key usage outside this repository.

3. Map the request to the smallest command family that fits.
   Use `mk` to create resources.
   Use `ls` and `info` to inspect resources and account/project state.
   Use `ch`, `net`, and `cp` to mutate existing resources or transfer COS objects.
   Use `rm` only after confirming the exact target and intended impact.

4. Prefer machine-readable output when the result will be reused.
   Use `-json` variants where documented.
   Use `-wait` or `-wait-ready` only when the user needs provisioning or status changes to finish before the next step.

5. Handle command drift and unexpected errors explicitly.
   If a command errors or appears outdated, rerun `twccli <group> --help` or `twccli <group> <subcommand> --help` before changing the command.
   Treat installed CLI help and observed runtime behavior as the source of truth when they conflict with the docs.
   If the failure may be caused by auth, project selection, or quota state, check `twccli config whoami`, `twccli info proj`, and `twccli info quota`.
   If the command still fails, capture the exact command, stderr, and relevant context under `.github/twcc/`.
   After confirming the correct command path, update only the smallest relevant part of this skill or its reference docs in this repository.

6. Keep transient artifacts repository-local.
   Write captured JSON, command transcripts, generated templates, or working notes under repo-local paths such as `.github/twcc/`.
   Do not store API keys, long-lived credentials, or copied shell history in the repository.

## Command Selection

Use [docs-map.md](references/docs-map.md) when the user needs setup guidance, service walkthroughs, or documentation coverage.

Use [command-reference.md](references/command-reference.md) when the user needs command-family selection, subcommand discovery, or flag reminders.

Prefer local `twccli ... --help` over memory whenever exact syntax matters. The docs are useful for structure and coverage, but some pages are sparse.

## Repo Scope Rules

Keep the skill itself under this repository and avoid assuming the user wants a global `~/.github/skills` install.

Treat TWCC account state, active project selection, quotas, and CLI auth as external state. Inspect first; do not assume current values from prior runs.

Ask before destructive operations, especially `rm`, recursive COS deletes, or security-group and port changes that affect running services.

Record enough context for repeatability.
At minimum, preserve the exact command, the intended resource identifiers, and any generated JSON or template files inside the repo when that output will matter later.

## Common Requests

For "set up TWCC CLI", start with `config whoami`; only use `config init` if auth or project configuration is missing or the user explicitly wants to reconfigure it.

For "show what project or quota I have", use `info proj` and `info quota`.

For "create a resource", inspect existing resources first when name collisions or quota constraints are plausible, then use the narrowest `mk` subcommand.

For "open a port" or "attach networking", use `net ccs` or `net vcs` rather than broader mutation commands.

For "upload/download files", use `cp cos` and keep local staging paths inside the repository when feasible.
