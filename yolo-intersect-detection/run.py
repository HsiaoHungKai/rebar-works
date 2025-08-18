import os
import cv2
from ultralytics import YOLO

# Define paths
input_folder = "./data/test/images"
output_folder = "yolo-intersect-detection/find_intersect"

# Create output folder if not exists
os.makedirs(output_folder, exist_ok=True)

# Load YOLO model
model = YOLO("yolo-intersect-detection/runs/detect/yolo11l/weights/best.pt")

# Loop through folders and images
for folder in os.listdir(input_folder):
    folder_path = os.path.join(input_folder, folder)
    
    # Skip if not a directory (fixes .DS_Store issue)
    if not os.path.isdir(folder_path):
        print(f"Skipping {folder} (not a directory)")
        continue

    # Create corresponding output subfolder
    output_subfolder = os.path.join(output_folder, folder)
    os.makedirs(output_subfolder, exist_ok=True)

    for filename in os.listdir(folder_path):
        if filename.lower().endswith(".jpg"):
            input_path = os.path.join(folder_path, filename)
            output_path = os.path.join(output_subfolder, filename)  

            results = model(input_path)
            annotated_image = results[0].plot(
                labels=False,
                conf=False,
            )

            cv2.imwrite(output_path, annotated_image)

            print(f"Saved results for {filename} to {output_subfolder}")
