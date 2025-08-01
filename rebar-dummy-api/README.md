# Rebar Distance API

A Flask API for calculating rebar distances from construction images using depth reconstruction.

## Features

- Image upload and processing
- Bearer token authentication
- Camera metadata validation
- Depth reconstruction simulation
- Distance calculation between points

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your configuration:
   ```
   TOKENS=["your_token_1", "your_token_2"]
   ```

## Usage

### Endpoint: POST /

Processes an uploaded image and returns distance measurements between detected points.

#### Required Headers
- `Authorization: Bearer <token>`

#### Required Form Data
- `caseID` (string): Unique case identifier
- `focal_length` (float): Camera focal length
- `image_width` (int): Image width in pixels
- `image_height` (int): Image height in pixels
- `iso` (int): Camera ISO setting
- `aperture` (float): Camera aperture value
- `exposure_time` (float): Camera exposure time
- `ev` (float): Exposure value
- `f35mm` (boolean): 35mm equivalent flag
- `image` (file): Image file (PNG or JPG)

#### Optional Form Data
- `sensor_width` (float): Camera sensor width
- `device-model` (string): Camera device model

*Note: Either `sensor_width` or `device-model` must be provided.*

#### Response Format
```json
{
  "caseID": "string",
  "timestamp": "ISO 8601 timestamp",
  "status": 200,
  "message": "深度重建成功",
  "pairs": [
    {
      "start_point": {"x": 100, "y": 200},
      "end_point": {"x": 300, "y": 400},
      "distance": 25.67
    }
  ]
}
```

## Running the Application

```bash
python app.py
```

The API will be available at `http://localhost:5000`

## Development

- The application currently returns simulated data for development purposes
- Authentication tokens should be stored in environment variables
- Ensure proper error handling for production use

## API Configuration

Camera metadata and validation rules are defined in `config.py`.
