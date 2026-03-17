---
name: twcc-cli
description: 'Manage Taiwan Computing Cloud (TWCC) resources using the command line interface'
---

Use this skill when the user asks to manage resources on Taiwan Computing Cloud (TWCC), such as creating containers (CCS), virtual machines (VCS), object storage (COS), or virtual networks.

## Installation & Configuration

1.  **Install**: `pip install TWCC-CLI` (or `pip3 install TWCC-CLI`)
2.  **Initialize**: Run `twccli config init`. You will need your **TWCC API Key** and **Project ID** (found in the TWCC user portal under "API Key Management").
3.  **Check Config**: `twccli config whoami`

## CCS: Container Computer Service (开发型容器)

Manage GPU/CPU containers for development.

### Create & List
-   **List Containers**: `twccli ls ccs` (Add `-all` for all project resources)
-   **Create Default**: `twccli mk ccs` (Creates TensorFlow environment with 1 GPU)
-   **Create Custom**:
    ```bash
    # List image types and images first
    twccli ls ccs -itype
    twccli ls ccs -img
    # Create with specific image and GPU count
    twccli mk ccs -itype "PyTorch" -img "pytorch-20.10-py3:latest" -gpu 1 -n my-container
    ```

### Networking & Connection
-   **Get SSH Connection**: `twccli ls ccs -s <ID> -gssh`
-   **Get Jupyter Notebook URL**: `twccli ls ccs -s <ID> -gjpnb`
-   **Open Ports**:
    ```bash
    # Open port 5000 for container ID 12345
    twccli net ccs -s 12345 -p 5000 -open
    # Close port
    twccli net ccs -s 12345 -p 5000 -close
    ```

### Snapshots (Duplicates)
-   **Create Snapshot**: `twccli mk ccs -s <ID> -dup -tag <TAG_NAME>`
-   **List Snapshots**: `twccli ls ccs -dup`
-   **Create from Snapshot**:
    ```bash
    twccli mk ccs -itype "Custom Image" -img "my-image:my-tag" -n my-custom-container
    ```

### Remove
-   **Delete Container**: `twccli rm ccs -s <ID>`

---

## VCS: Virtual Computer Service (虚拟运算服务)

Manage Virtual Machines (VMs).

### Keys & Creation
-   **Create Key Pair** (Required for VM): `twccli mk key -n <KEY_NAME>`
-   **List Keys**: `twccli ls key`
-   **Create VM**: `twccli mk vcs -key <KEY_NAME> -n <VM_NAME>` (Default: Ubuntu 16.04, 8 CPU, 64GB RAM)
-   **List VMs**: `twccli ls vcs`

### Networking
-   **Attach Floating IP** (Public IP): `twccli net vcs -s <ID> -fip`
-   **Security Groups (Firewall)**:
    -   **List**: `twccli ls vcs -secg -s <ID>`
    -   **Add Rule** (e.g., allow TCP port 80 from anywhere):
        ```bash
        twccli net vcs -secg -s <ID> -cidr 0.0.0.0/0 -in -proto tcp -p 80
        ```
    -   **Remove Group**: `twccli rm vcs -secg <GROUP_ID>`

### Snapshots
-   **Create Snapshot**: `twccli mk vcs -s <ID> -snap`
-   **List Snapshots**: `twccli ls vcs -snap`
-   **Delete Snapshot**: `twccli rm vcs -snap -snap-id <ID>`

### Remove
-   **Delete VM**: `twccli rm vcs -s <ID>`

---

## COS: Cloud Object Storage (云端物件储存)

Manage S3-compatible object storage.

### Buckets
-   **List Buckets**: `twccli ls cos`
-   **Create Bucket**: `twccli mk cos -bkt <BUCKET_NAME>`
-   **Delete Bucket**: `twccli rm cos -bkt <BUCKET_NAME>` (Use `-r` if not empty)

### Files (Upload/Download)
-   **Upload File**:
    ```bash
    twccli cp cos -bkt <BUCKET> -fn <LOCAL_FILE> -sync to-cos
    ```
-   **Upload Directory**:
    ```bash
    twccli cp cos -bkt <BUCKET> -dir <LOCAL_DIR> -sync to-cos
    ```
-   **Download File**:
    ```bash
    twccli cp cos -bkt <BUCKET> -okey <OBJECT_KEY> -sync from-cos
    ```
-   **List Files in Bucket**: `twccli ls cos -bkt <BUCKET>`
-   **Delete Object**: `twccli rm cos -bkt <BUCKET> -okey <OBJECT_KEY>`

---

## Other Services

### VNET (Virtual Network)
-   **List**: `twccli ls vnet`
-   **Create**: `twccli mk vnet -cidr <CIDR> -gw <GATEWAY>`
-   **Delete**: `twccli rm vnet -id <ID>`

### VDS (Virtual Disk Service)
-   **List**: `twccli ls vds`
-   **Create**: `twccli mk vds -n <NAME> -sz <SIZE_GB>`
-   **Delete**: `twccli rm vds -id <ID>`
