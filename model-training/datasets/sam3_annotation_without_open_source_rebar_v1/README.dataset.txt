# test_dahanxi > 2026-05-10 12:59pm
https://universe.roboflow.com/hungkais-workspace/test_dahanxi-mhbq7

Provided by a Roboflow user
License: CC BY 4.0

The dataset includes 162 images.
Intersection are annotated in YOLO26 format.

Source Images
==============================

The training images used to create this Roboflow dataset came from the following Google Drive folders:
* https://drive.google.com/drive/u/0/folders/1Y4YpGXMLsSpoMEY_lcTB--LBngSEhZep
* https://drive.google.com/drive/u/0/folders/1u65TAqbydlc8_T5WVGOroPfbsbdes0Ya
* https://drive.google.com/drive/u/0/folders/1L9SVSl0S0GDxPh3EFxshzXy29wocjC6w

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