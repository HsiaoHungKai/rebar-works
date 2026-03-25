# TWCC CLI Command Reference

Use this file to map user intent to the correct command family. Prefer `twccli <group> --help` or `twccli <group> <subcommand> --help` when exact syntax matters.

## Table of Contents

- [Global Shape](#global-shape)
- [`config`](#config) - Configure CLI, authentication, and identity inspection
- [`info`](#info) - Inspect project, quota, and HFS information
- [`ls`](#ls) - List resource inventories (keys, networks, security groups, instances, storage)
- [`cp`](#cp) - Upload or download COS objects
- [`mk`](#mk) - Create resources (keys, VCS, CCS, networks, security groups, storage)
- [`ch`](#ch) - Change existing resources (flavors, images, metadata)
- [`net`](#net) - Manage ports and VCS security-group networking
- [`rm`](#rm) - Delete resources

## Global Shape

Base form:

```bash
twccli [--verbose | --show_and_verbose] <group> [subcommand] [flags]
```

Primary groups exposed by `twccli --help`:

- `ch`: change existing resources
- `config`: configure the CLI and inspect identity/version
- `cp`: upload or download COS objects
- `info`: inspect project, quota, and HFS information
- `ls`: list resource inventories
- `mk`: create resources
- `net`: manage ports and VCS security-group networking
- `rm`: delete resources

## `config`

Use for authentication, active project setup, and version/identity inspection.

Subcommands:

- `config init`
  - `--project-code`
  - `--apikey`
  - `--user-agent`
  - `--set-bashrc` / `--not-set-bashrc`
  - `--agree-ga` / `--not-agree-ga`
- `config version`
- `config whoami`

Working rule:
Use `config whoami` before `config init` unless the user explicitly asks to set up or replace credentials.

## `info`

Use for account and project state.

Subcommands:

- `info hfs`
  - `-table` / `-json`
- `info proj`
  - `-table` / `-json`
  - `-all` / `--show-all`
- `info quota`
  - `-table` / `-json`
  - `-all` / `--show-all` for tenant-admin quota views

Working rule:
Run `info proj -json` and `info quota -json` before creating resources when quota or active-project mistakes would be costly.

## `ls`

Use for resource inventories.

The docs page is sparse, but local CLI help exposes these subcommands:

- `ls ccs`
- `ls cos`
- `ls eip`
- `ls key`
- `ls secg`
- `ls ssl`
- `ls vcs`
- `ls vcsi`
- `ls vds`
- `ls vlb`
- `ls vnet`

Working rule:
Use `twccli ls --help` and subcommand help locally for exact list filters and output flags.

## `cp`

Use for COS transfer operations.

Subcommands:

- `cp cos`
  - `-sync` / `--synchronized`: `to-cos` or `from-cos`
  - `-dir` / `--directory`
  - `-okey` / `--cos-key`
  - `-fn` / `--file-name`
  - `-bkt` / `--bucket-name`

Working rule:
For uploads, stage the source file under the repository when practical. For downloads, pick a repo-local destination unless the user asked for a different path.

## `mk`

Use for resource creation.

Subcommands:

- `mk ccs`
  - Container creation and duplication
  - Notable flags: `--name`, `--site-id`, `--request-duplication`, `--gpu-number`, `--command`, `--image-name`, `--environment-keys`, `--environment-values`, `--image-type-name`, `--product-type`, `--pass-apikey` / `--no-pass-apikey`, `-table` / `-json`, `--duplication-tag`, `--wait-ready`
- `mk cos`
  - Bucket creation
  - Notable flags: `--bucket_name`
- `mk eip`
  - Fixed/public IP allocation
  - Notable flags: `-table` / `-json`, `--IP-description`
- `mk key`
  - Key-pair creation
  - Notable flags: `--name`, `--public-key`
- `mk secg`
  - Security-group creation
  - Notable flags: `-table` / `-json`, `--name`, `--secg-description`
- `mk secg-rule`
  - Security-group rule creation
  - Notable flags: `--port`, `--secg-id`, `--cidr-network`, `--ingress` / `--egress`, `--port-range`, `--protocol`, `-table` / `-json`
- `mk ssl`
  - SSL certificate creation
  - Notable flags: `--SSL-description`, `--name`, `--payload`, `--sercer-certfile`, `--inkey`, `--intermediate-CA`, `--payload-file`, `--expire-time`, `-table` / `-json`
- `mk vcs`
  - Instance creation
  - Notable flags: `--name`, `--site-id`, `--eip`, `--need-floating-ip`, `--image-name`, `--keypair`, `--network`, `--password`, `--environment-keys`, `--environment-values`, `--security-group-names`, `--image-type-name`, `--product-type`, `--pass-apikey` / `--no-pass-apikey`, `--custom-image`, `--system-volume-type`, `--system-disk-size`, `--data-disk-type`, `--data-disk-size`, `-table` / `-json`, `--wait-ready`
- `mk vds`
  - Virtual disk creation and snapshots
  - Notable flags: `-table` / `-json`, `--snapshot`, `--disk-size`, `--vds-id`, `--vds-description`, `--disk-type`, `--disk-name`
- `mk vlb`
  - Load balancer creation
  - Notable flags: `--byjson`, `-table` / `-json`, `--wait-ready`, `--template`, `--virtual_network_name`, `--members`, `--listener_port`, `--listener_type`, `--lb_method`, `--eip`, `--vlb-id`, `--load_balance_name`, `--load_balance_description`
- `mk vnet`
  - Virtual network creation
  - Notable flags: `-table` / `-json`, `--wait-ready`, `--cidr`, `--getway`, `--vnet_name`

Working rule:
Before `mk`, confirm quota and whether the requested network, keypair, or security group already exists.

## `ch`

Use for in-place mutations.

Subcommands:

- `ch ccs`
  - Update container description or termination protection
  - Notable flags: `--site-id`, `--site-desc`, `--keep` / `--nokeep`, `-table` / `-json`
- `ch cos`
  - Update bucket/object permissions and metadata
  - Notable flags: `--enable-versioning` / `--disable-versioning`, `--set-content-type`, `--set-public` / `--unset-public`, `--object-key-name`, `--bucket-name`
- `ch eip`
  - Update IP description
  - Notable flags: `-table` / `-json`, `--IP-description`, `--private-net-id`
- `ch secg`
  - Update security-group description or attach/remove groups from VCS instances
  - Notable flags: `-table` / `-json`, `--instance-type`, `--action`, `--instance-id`, `--security-group-id`, `--secg-description`
  - Documented values: `--instance-type vcs`; `--action desc|add|remove`
- `ch vcs`
  - Update instance description, termination protection, or status
  - Notable flags: `--site-desc`, `--site-id`, `--keep` / `--nokeep`, `--vcs-status`, `-table` / `-json`, `--wait`
  - Documented status values: `Ready`, `Stop`, `Reboot`
- `ch vcsi`
  - Update bootable-image description
  - Notable flags: `--vcsi-desc`, `--vcsi-id`, `-table` / `-json`
- `ch vds`
  - Attach, detach, or extend disks
  - Notable flags: `-table` / `-json`, `--wait`, `--disk-status`, `--disk-size`, `--disk-id`, `--site-id`
  - Documented status values: `attach`, `detach`, `extend`
- `ch vlb`
  - Update load balancer members or apply JSON-based changes
  - Notable flags: `--byjson`, `-table` / `-json`, `--wait`, `--template`, `--members`, `--eip-id`, `--vlb-id`

Working rule:
For `ch` requests, inspect the current resource first so that partial updates do not accidentally overwrite the wrong target.

## `net`

Use for network exposure and security-group style operations.

Subcommands:

- `net ccs`
  - Manage CCS ports
  - Notable flags: `--port`, `--site-id`, `--open-port` / `--close-port`
- `net vcs`
  - Manage VCS security-group networking and public IP behavior
  - Notable flags: `--port`, `--site-id`, `--cidr-network`, `--floating-ip` / `--no-floating-ip`, `--eip`, `--ingress` / `--egress`, `--port-range`, `--protocol`
  - Documented default protocol: `tcp`

Working rule:
Use `net` instead of broader mutation commands when the user is specifically asking about access control, published ports, or floating/EIP behavior.

## `rm`

Use for destructive operations. Confirm exact identifiers and blast radius first.

Subcommands:

- `rm ccs`
  - Delete containers
  - Notable flags: `--force`, `--site-id`
- `rm cos`
  - Delete COS objects or buckets
  - Notable flags: `--force`, `--recursively`, `--bucket_name`, `--cos_key`
- `rm eip`
  - Delete IPs
  - Notable flags: `--force`, `--ip-id`
- `rm key`
  - Delete VCS keys
  - Notable flags: `--force`, `--name`
- `rm me`
  - Shortcut delete for the current resource context
  - Notable flags: `--dry-run` / `--no-dry-run`, `--force`
- `rm secg`
  - Delete security groups
  - Notable flags: `--force`, `--secg-id`
- `rm secg-rule`
  - Delete security-group rules
  - Notable flags: `--force`, `--rule-id`
- `rm ssl`
  - Delete SSL certificates
  - Notable flags: `--force`, `--ssl-id`
- `rm vcs`
  - Delete instances, keypairs, custom images, or security groups in VCS-related contexts
  - Notable flags: `--force`, `--name`, `--site-id`, `--custom-image-id`, `--show-all`, `--keypair`, `--custom-image`, `--security-group`
- `rm vcsi`
  - Delete bootable images
  - Notable flags: `--force`, `--vcsi-id`, `--show-all`
- `rm vds`
  - Delete disks or snapshots
  - Notable flags: `--snapshot`, `--force`, `--disk-id`
- `rm vlb`
  - Delete load balancers
  - Notable flags: `--force`, `--vlb-id`
- `rm vnet`
  - Delete virtual networks
  - Notable flags: `--virtual_network_id`, `--force`

Working rule:
Prefer a dry inspection step before `rm`. For COS, pay special attention to `--recursively`; for `rm me`, keep the default dry-run behavior until the user confirms the real delete.
