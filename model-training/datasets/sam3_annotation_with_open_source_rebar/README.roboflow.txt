
test_dahanxi - v10 2026-05-12 1:58pm
==============================

This dataset was exported via roboflow.com on May 12, 2026 at 5:59 AM GMT

Roboflow is an end-to-end computer vision platform that helps you
* collaborate with your team on computer vision projects
* collect & organize images
* understand and search unstructured image data
* annotate, and create datasets
* export, train, and deploy computer vision models
* use active learning to improve your dataset over time

For state of the art Computer Vision training notebooks you can use with this dataset,
visit https://github.com/roboflow/notebooks

To find over 100k other datasets and pre-trained models, visit https://universe.roboflow.com

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


