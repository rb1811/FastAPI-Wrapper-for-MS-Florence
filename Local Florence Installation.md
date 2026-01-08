## 1. Install Git LFS

First, you need to ensure Git Large File Storage (LFS) is installed on your system to handle the large model weights.

### Update package list and install git-lfs
    sudo apt-get update
    sudo apt-get install git-lfs -y

### Initialize Git LFS for your user account
    git lfs install


## 2. Clone the Florence-2 Model
Navigate to your project directory and download the model from Hugging Face into your cache folder.

### Navigate to project directory and create cache folder
    cd ~/Documents/FastAPI-MS-Florence
    mkdir -p hf_cache

### Clone the repository into the hf_cache directory
    git clone https://huggingface.co/microsoft/Florence-2-large hf_cache/florence-2-large


## 3. Clean Up to Save Space
Florence-2 usually provides model weights in both .safetensors and .bin formats. Since most modern loaders prefer .safetensors, you can remove the redundant .bin files and the .git history to save several gigabytes of disk space

### Enter the model directory
    cd hf_cache/florence-2-large/

### Remove redundant PyTorch binary weights (SafeTensors are used instead)
    rm pytorch_model.bin

### Delete the Git history (saves significant space)
    rm -rf .git

### Remove unnecessary documentation and sample files
    rm sample_inference.ipynb README.md CODE_OF_CONDUCT.md SECURITY.md SUPPORT.md LICENSE .gitattributes

## 4. Summary of Cleanup
1. .git folder: Removing this prevents your local disk from storing the entire version history of the model weights.
2. pytorch_model.bin: This file is a duplicate of the data found in model.safetensors. Deleting it saves ~2.5GB.
3. Documentation files: These are not required for the model to run within your FastAPI wrapper.