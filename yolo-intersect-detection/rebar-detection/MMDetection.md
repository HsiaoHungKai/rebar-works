cuda 12.6.3
torch 2.6.0
torchvision  0.21.0
```
pip install torch==2.6.0 torchvision==0.21.0
```

# 1. 下載mmcv
失敗因為沒到cuda126
[mmcv](https://mmcv.readthedocs.io/en/latest/get_started/installation.html)
```
pip install mmcv-full -f https://download.openmmlab.com/mmcv/dist/cu126/torch2.6.0/index.html
```
## mim方法
- 要先降版本3.12到3.10|3.11
```
python --version
conda install python==3.10
```
- 把舊的mim卸載乾淨
```
which mim #/home/主機名/.local/bin/mim 代表有殘留
rm -f ~/.local/bin/mim

```
- 
```
pip install openmim
mim install mmcv
mim install mmengine
mim install mmdet
mim install mmpretrain

```
- libGL.so缺失
```
sudo apt-get update
sudo apt-get install -y libgl1
```
# 下載mmdetection
```
git clone https://github.com/open-mmlab/mmdetection.git
cd mmdetection
pip install -r requirements/build.txt
```
# 下載prtrain model
```
wget https://download.openmmlab.com/mmclassification/v1/vit_sam/vit-base-p16_sam-pre_3rdparty_sa1b-1024px_20230411-2320f9cc.pth
```
[[Mask R-CNN ConvNeXt]]

[[MM_SAM]]