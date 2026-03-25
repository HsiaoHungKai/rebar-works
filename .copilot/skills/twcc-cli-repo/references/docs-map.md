# TWCC CLI Docs Map

The requested docs entrypoint is `https://twcc-cli.readthedocs.io/en/latest/index.html`, but the site resolves to the `en/master/` documentation tree. Use that tree as the canonical structure when browsing.

## Site Sections

The documentation root has two layers:

1. A walkthrough/manual section labeled `TWCC-CLI α`
2. Dedicated CLI reference pages for `ch`, `config`, `cp`, `info`, `ls`, `mk`, `net`, and `rm`

## `TWCC-CLI α` Walkthrough Coverage

Use this section when the user wants tutorials, service-level walkthroughs, or setup guidance rather than a raw command page.

The table of contents covers:

- Environment deployment and installation
  - Open a TWCC development container
  - Install TWCC CLI
  - Enter the TWCC CLI environment and start using services
  - Switch project/plan
  - Update the TWCC CLI version
- CCS workflows
  - Create a container
  - Inspect container information
  - List container flavors/specs
  - Build a specified container environment
  - Inspect connection information
  - Request duplication, check duplication status, and build from a duplicate
  - Open and close public service ports
  - Delete containers
- VCS workflows
  - Create and inspect key pairs
  - Create instances, including public IP setup
  - Inspect instance information and flavors/specs
  - Snapshot-related flows, including request/status/list/delete
  - Security-group management
  - Delete instances and key pairs
- COS workflows
  - Create buckets
  - List buckets
  - Upload a file with `-sync to-cos`
  - List bucket files
  - Download files or buckets with `-sync from-cos`
  - Delete COS data and buckets
- Virtual Network workflows
  - Create, inspect, and delete virtual networks
- Virtual Disk Service workflows
  - Create, inspect, and delete virtual disks
- Supplemental VCS-hosted CLI usage
  - Open a VCS instance
  - Install TWCC CLI inside VCS
  - Enter TWCC CLI user information

## Command Reference Coverage

The dedicated command pages cover these families:

- `twccli ch`
- `twccli config`
- `twccli cp`
- `twccli info`
- `twccli ls`
- `twccli mk`
- `twccli net`
- `twccli rm`

## Gaps And Working Rules

The `ls` documentation page is skeletal. When the user needs exact `ls` subcommands or options, prefer local `twccli ls --help` output.

Some wording in the docs is dated or typo-prone. Preserve the documented flag names exactly, but do not treat the prose wording as authoritative when the installed CLI help says otherwise.
