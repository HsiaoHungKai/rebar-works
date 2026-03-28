### 1. Local Setup & Container Creation
Run these on your local Mac:

```bash
# 1. Go to your working directory and activate your local conda environment
cd <CURRENT_DIR>
conda activate rebar-works

# 2. Create the TWCC container
twccli mk ccs \
  -n "sam3-inference" \
  -itype "PyTorch" \
  -img "pytorch-26.02-py3:latest" \
  -gpu 1 \
  -wait \
  -table

# 3. List the container info to get your IP, and <PORT>
twccli ls ccs -s <SITE_ID> -gssh -table

# 4. Ensure your SSH key has the correct permissions (you likely only need to do this once)
chmod 400 <PEM_LOCATION>
```

### 2. Upload Script & Connect
Still on your local Mac, using the IP and `<PORT>` you got from step 3:

```bash
# 1. Upload your Python script to the container's home directory
scp -i <PEM_LOCATION> -P <PORT> sam3_inference.py u7740467@<IP_ADDRESS>:~/

# 2. SSH into the container
ssh -p <PORT> u7740467@<IP_ADDRESS>
``` 

### 3. Remote Environment Setup
Run these inside the TWCC container (Ubuntu):

```bash
# 1. Download and install Miniconda quietly
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
bash miniconda.sh -b -p $HOME/miniconda3

# 2. Initialize Conda and reload your shell to apply changes
$HOME/miniconda3/bin/conda init bash
source ~/.bashrc

# 3. Install the required Python packages
pip install transformers Pillow requests
```

### 4. Run the Inference
Still inside the TWCC container:

```bash
# 1. Export your Hugging Face token (so it can access the gated SAM3 model)
export HF_TOKEN="HF_TOKEN"

# 2. Run the script!
python sam3_inference.py
```
*(Note: You received a warning about the NVIDIA driver being too old for the PyTorch version, but the script still successfully executed and found 2 objects. If you want to optimize for GPU speed later, you might need an older PyTorch version or a newer container image).*

### 5. Cleanup
Back on your local Mac (open a new terminal tab or `exit` the SSH session):

```bash
# Delete the container to stop billing
twccli rm ccs --site-id <SITE_ID> --force
```

---