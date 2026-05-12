# test_dahanxi > 2026-05-12 1:58pm
https://universe.roboflow.com/hungkais-workspace/test_dahanxi-mhbq7

Provided by a Roboflow user
License: CC BY 4.0

Source Images
==============================

The training images used to create this Roboflow dataset came from the following Google Drive folders:
* https://drive.google.com/drive/u/0/folders/1Y4YpGXMLsSpoMEY_lcTB--LBngSEhZep
* https://drive.google.com/drive/u/0/folders/1u65TAqbydlc8_T5WVGOroPfbsbdes0Ya
* https://drive.google.com/drive/u/0/folders/1L9SVSl0S0GDxPh3EFxshzXy29wocjC6w

 Additional source images were added from the NTU "rebar segment" Roboflow Universe dataset: * https://universe.roboflow.com/ntu-ks0ac/rebar-segment-ysgc1  
 The NTU source dataset contains 100 images and is licensed under CC BY 4.0. It was originally published as an object detection dataset with intersection and spacing classes. 
 For this rebar segmentation dataset, masks were generated with SAM3 and then manually reviewed. 
 Manual adjustments included removing masks that covered non-rebar objects, excluding rebar that was too far away, and dropping images or masks that were too poor to use. After review, 41 of the 100 NTU source images were retained.  The retained NTU images use the same pre-processing and augmentation pipeline listed below.

The following pre-processing was applied to each image:
* Auto-orientation of pixel data (with EXIF-orientation stripping)
* Resize to 512x512 (Stretch)
* Auto-contrast via adaptive equalization

The following augmentation was applied to create 3 versions of each source image:
* 50% probability of horizontal flip
* Equal probability of one of the following 90-degree rotations: none, clockwise, counter-clockwise
* Randomly crop between 0 and 20 percent of the image
* Random rotation of between -15 and +15 degrees
* Random shear of between -10° to +10° horizontally and -10° to +10° vertically
* Random exposure adjustment of between -10 and +10 percent