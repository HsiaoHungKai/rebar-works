# TWCC CLI Tutorial

This tutorial walks through a basic `twccli` workflow for creating a TWCC container, connecting to it, preparing the environment, running a Python script, and cleaning up when finished.

## Prerequisites

Before you start, make sure you have:

- `twccli` installed and authenticated on your local machine
- a PEM key file for SSH access
- a Python script you want to test, for example `script.py`
- any credentials or API tokens your script requires

The following sections walk through how to get or prepare these prerequisites before creating the container.

### Install `twccli`

The key setup points from the official guide are:

- `twccli` can be installed on Linux or macOS
- some TWCC Linux environments already include `twccli`
- install it with:

```bash
pip install TWCC-CLI
```

If your environment uses Python 3, use:

```bash
pip3 install TWCC-CLI
```

After installation, confirm the CLI version:

```bash
twccli config version
```

For a clearer step-by-step guide with UI screenshots, see:

- https://man.twcc.ai/@twccdocs/guide-cli-install-linux-zh

### Sign in to `twccli`

Before signing in, prepare:

- your TWCC project ID
- your TWCC API key

For a clearer sign-in guide with UI screenshots, see:

- https://man.twcc.ai/@twccdocs/guide-cli-signin-zh

Then initialize the CLI:

```bash
twccli config init
```

You can verify the active account and project after login with:

```bash
twccli config whoami
```

### Get a PEM Key

Before you connect to a TWCC Linux container, you need a key pair. This key pair is the credential used to log in to Linux virtual compute instances.

You can create the key pair in either of these ways:

- through the TWCC web UI when creating a virtual compute instance
- through the Key Pair management page in the TWCC web UI
- through the CLI with:

```bash
twccli mk key -n key1
```

You can check existing key pairs with:

```bash
twccli ls key
```

After creating a key pair, download the `.pem` file immediately and keep it safe. TWCC does not keep or manage the private key for you, and without that `.pem` file you will not be able to connect to the Linux instance.

For a clearer guide with UI screenshots and the full key-pair workflow, see:

- https://man.twcc.ai/@twccdocs/guide-vcs-keypair-zh

## 1. Create a TWCC Container

Run these commands on your local machine:

```bash
twccli ls ccs -itype
twccli ls ccs -img
```

These two commands list available instance types and container images. After checking the options, create your container with `twccli mk ccs`.

```bash
twccli mk ccs \
  -n "twccli-tutorial" \
  -itype "PyTorch" \
  -img "pytorch-26.02-py3:latest" \
  -gpu 1 \
  -wait \
  -table
```

This creates a GPU container named `twccli-tutorial` and waits until it is ready.

After `twccli mk ccs` finishes, TWCC shows the site ID in the output table. For example:

```text
Passing current credential information to new computing resources.
+ CCS Site:<SITE_ID> ---------+--------+
| id        | name            | status |
+-----------+-----------------+--------+
| <SITE_ID> | twccli-tutorial | Ready  |
+-----------+-----------------+--------+
```

In this example, `<SITE_ID>` is the site ID you will use in later commands.

You can also check currently running CCS resources with:

```bash
twccli ls ccs
```

## 2. Get Connection Information

List the container details and note the TWCC host and SSH port:

```bash
twccli ls ccs -s <SITE_ID> -gssh -table
```

Command output:

```text
<TWCC_USERNAME>@<TWCC_HOST> -p <PORT>
```

In this example:

- `<TWCC_USERNAME>@<TWCC_HOST>` is the SSH login target
- `<PORT>` is the SSH port

If needed, fix your key permissions once:

```bash
chmod 400 <PEM_LOCATION>
```

## 3. Upload the Script and Connect

Upload your Python script from your local machine to the TWCC container:

```bash
scp -i <PEM_LOCATION> -P <PORT> script.py <TWCC_USERNAME>@<TWCC_HOST>:~/
```

Then connect to the container:

```bash
ssh -p <PORT> <TWCC_USERNAME>@<TWCC_HOST>
```

## 4. Prepare the Remote Environment

Run these commands inside the TWCC container:

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p $HOME/miniconda3

$HOME/miniconda3/bin/conda init bash
source ~/.bashrc

pip install <REQUIRED_PYTHON_PACKAGES>
```

This installs Miniconda, initializes Conda for the shell, and installs example Python packages you may need. Adjust the package list for your own script.

## 5. Run Your Script

Still inside the TWCC container, run your script:

```bash
python script.py
```

If your script depends on secrets such as `HF_TOKEN`, export them before running:

```bash
export HF_TOKEN="HF_TOKEN"
python script.py
```

## 6. Clean Up the Container

When you are finished, delete the container from your local machine to avoid extra billing:

```bash
twccli rm ccs --site-id <SITE_ID> --force
```

## Quick Summary

The end-to-end flow is:

1. Create a container with `twccli mk ccs`
2. Get the TWCC host and port with `twccli ls ccs -s <SITE_ID> -gssh -table`
3. Upload `script.py` with `scp`
4. Connect with `ssh`
5. Install dependencies inside the container
6. Export any required environment variables and run your script
7. Remove the container when done
