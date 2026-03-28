from transformers import Sam3Processor, Sam3Model
import torch
from PIL import Image
import requests
import json
import numpy as np

device = "cuda" if torch.cuda.is_available() else "cpu"

model = Sam3Model.from_pretrained("facebook/sam3").to(device)
processor = Sam3Processor.from_pretrained("facebook/sam3")

# Load image
image_url = "http://images.cocodataset.org/val2017/000000077595.jpg"
image = Image.open(requests.get(image_url, stream=True).raw).convert("RGB")

# Segment using text prompt
inputs = processor(images=image, text="ear", return_tensors="pt").to(device)

with torch.no_grad():
    outputs = model(**inputs)

# Post-process results
results = processor.post_process_instance_segmentation(
    outputs,
    threshold=0.5,
    mask_threshold=0.5,
    target_sizes=inputs.get("original_sizes").tolist()
)[0]

print(f"Found {len(results['masks'])} objects")

# Prepare results for JSON output
output_data = {
    "num_objects": len(results['masks']),
    "device_used": device,
    "image_url": image_url,
    "text_prompt": "ear",
    "objects": []
}

# Add each detected object
for i in range(len(results['masks'])):
    obj = {
        "object_id": i,
        "score": float(results['scores'][i]),
        "bounding_box": {
            "x1": float(results['boxes'][i][0]),
            "y1": float(results['boxes'][i][1]),
            "x2": float(results['boxes'][i][2]),
            "y2": float(results['boxes'][i][3])
        },
        "mask_shape": list(results['masks'][i].shape)
    }
    output_data["objects"].append(obj)

# Save results to JSON file
output_file = "sam3_results.json"
with open(output_file, 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"Results saved to {output_file}")
print(f"Summary: {output_data['num_objects']} objects detected with scores: {[obj['score'] for obj in output_data['objects']]}")

