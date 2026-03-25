# TWCC CLI validation notes

Date: 2026-03-25

Validated locally against `twccli` 0.6.1:

- `twccli config whoami`
- `twccli info proj -json`
- `twccli info quota -json`
- `twccli ls vnet`
- `twccli ls key`
- `twccli ls secg`
- `twccli ls vcs -itype`
- `twccli ls vcs -img Ubuntu`
- `twccli ls vcs -ptype Ubuntu`
- `twccli mk key --help`
- `twccli mk vcs --help`
- `twccli net vcs --help`
- `twccli rm vcs --help`
- `twccli rm key --help`
- `twccli ls ccs -itype`
- `twccli ls ccs -img PyTorch`
- `twccli ls ccs -ptype`

Observed CLI drift:

- `twccli ls vcs -img` fails unless an image type value is passed as a positional argument, for example `twccli ls vcs -img Ubuntu`.
- `twccli ls vcs -ptype` behaves the same way and needs a positional image type value, for example `twccli ls vcs -ptype Ubuntu`.

Design choice for `run_sam3_twcc.sh`:

- Use VCS instead of CCS for end-to-end automation because the installed CLI gives a standard, scriptable path for keypair creation, floating IP assignment, SSH, and cleanup.

Script validation outcome:

- `./run_sam3_twcc.sh --validate-only` completed successfully after running with real outbound TWCC access.
- Validation artifacts were written under `twcc-artifacts/sam3-20260325-030252/`.
- A full end-to-end inference run was not started in this session because that would allocate a live TWCC compute resource and no concrete test image/prompt was provided.

Live sample-run outcome:

- Sample input used:
  - image: `http://images.cocodataset.org/val2017/000000077595.jpg`
  - prompt: `ear`
- The script reached `twccli mk key` and failed cleanly with:
  - `[TWCC-CLI] Error-{'message': '[i-service] no quota to request resource. user: hsiaohungkai@gmail.com, quota: -109.8329'}`
- Before adding explicit output checks, one prior attempt also showed a transient transport failure from TWCC:
  - `requests.exceptions.ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))`
- The script was updated to:
  - fail on TWCC application-level errors even when `twccli` exits `0`
  - retry transient TWCC transport failures on `mk key`, `mk vcs`, and `ls vcs`
