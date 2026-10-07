# NOAA NMFS Optics Video Web-Optimization Pipeline

Welcome! This repository houses the Video Web-Optimization pipeline for the Optics SI Airflow ecosystem. It runs as an isolated Docker container, exposes an HTTP endpoint, and communicates with Google Cloud Storage (GCS).

This pipeline automatically inspects video files (e.g., `.avi`, `.mkv`, `.mov`, `.mp4`). If the video is already `h.264`, it quickly remuxes it. If it is another codec, it transcodes it to `h.264`. It guarantees `aac` audio (if an audio track exists) and applies `-movflags +faststart` so the resulting `.mp4` file is optimized for immediate web streaming.

## 🏁 Step 1: Clone the Repository

Clone this repository to your local machine (or Google Cloud Workstation). All subsequent commands assume you are running them from the root of this cloned directory.

```bash
git clone https://github.com/csbrown-noaa/optics-models-web-optimizer.git
cd optics-models-web-optimizer
```

## 💻 Step 2: Test Locally

Before deploying to the cloud, verify the pipeline works on your laptop/workstation. We recommend using Google Cloud workstations for this, as they already have Docker and `gcloud` installed.

We will test the pipeline exactly as it runs in the cloud: by passing a JSON payload URI and routing variables to the `inference_runner.py` bridge.

**1. Authenticate with Google Cloud**
Ensure you have Google Cloud credentials available locally so the container can download and upload test files:

```bash
gcloud auth application-default login
```

**2. Build the Docker Container**

```bash
docker build -t video-optimizer:latest .
```

**3. Prepare Your Test Payload**
Create a minimal JSON payload file locally named `test_payload.json`. Notice there are no output parameters here—those are handled by the infrastructure environment variables!

🛑 **[ACTION REQUIRED]**: Replace the `gs://.../test.avi` string below with the actual Cloud Storage URI of a video you want to process!

```json
{
  "instances": [
    {
      "input_path": "gs://nmfs-dev-uc1-sefsc/GFISHER/Video_data/2025/test.avi"
    }
  ]
}
```

**4. Upload Your Payload to GCS**
Because the inference runner downloads the payload from the cloud, you must upload this JSON file to a bucket you control before testing.

🛑 **[ACTION REQUIRED]**: Upload `test_payload.json` to a folder in your GCP bucket (e.g., `gs://ggn-nmfs-osi-dev-1-data/my-user/inputs/test_payload.json`).

**5. Run the Container**
We will now execute the container, overriding the default command to run the `inference_runner.py` directly, just like Cloud Batch does. We will also inject the required environment variables.

🛑 **[ACTION REQUIRED]**: Update the `INPUT_FILE` path to point to the JSON file you just uploaded, and change the `OUTPUT_FOLDER` to a location where you want the resulting `.mp4` saved.

```bash
docker run \
  -u root \
  -v ~/.config/gcloud:/tmp/.config/gcloud \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/.config/gcloud/application_default_credentials.json \
  -e GOOGLE_CLOUD_PROJECT=ggn-nmfs-osi-dev-1 \
  -e INPUT_FILE="gs://ggn-nmfs-osi-dev-1-data/my-user/inputs/test_payload.json" \
  -e OUTPUT_BUCKET="ggn-nmfs-osi-dev-1-data" \
  -e OUTPUT_FOLDER="my-user/output/" \
  video-optimizer:latest python /workspace/inference_runner.py
```

If successful, your terminal will log the runner downloading the JSON, the local web server spinning up, `ffmpeg` optimizing the video, and the new `.mp4` file being uploaded to your destination GCS folder!

## ☁️ Step 3: Deploy to Cloud

Once you are happy with local testing, push this container to the Google Artifact Registry.

***!!!!NB!!!!*** The Artifact Registry is where everyone's models live. Be careful not to overwrite a production image.

**1. Authenticate with Google Cloud**

```bash
gcloud auth login
```

**2. Tag and Push**

```bash
# Tag your image for the registry
docker tag video-optimizer:latest us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/video-optimizer:latest

# Push it
docker push us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/video-optimizer:latest
```

## ⚙️ Step 4: Hook it into Airflow

To make this pipeline available in the system, you must register it in the Airflow configuration.

Download GCS `gs://ggn-nmfs-osi-dev-1-data/configs/model_runtime_definitions.json`

The entries in the JSON are for the various models and pipelines. Add the `video-optimizer` block to the JSON file, save, and upload it back to the original GCS folder.

```json
    "video-optimizer": {
        "region": "us-central1",
        "image": "us-central1-docker.pkg.dev/ggn-nmfs-osi-dev-1/nmfs-dev-uc1-docker-repository/video-optimizer:latest",
        "cpu": 4,
        "memory": "16Gi",
        "gpu": 0,                        
        "gpu_type": null,                
        "machine_type": "c2-standard-4",
        "timeout": 360000,               
        "command": ["python"],
        "args": ["/workspace/inference_runner.py"]
    }
```

*Note: We use `c2-standard-4` here because ffmpeg video processing is heavily CPU-bound.*

## 🚀 Step 5: Triggering in Airflow

Airflow triggers exactly like our local test did in Step 2.

1. Go to Google Cloud console, search `Airflow`, select `Managed Airflow` -> `composer-env1` -> `Open Airflow UI` tab.
2. Locate the `nmfs-optics-pipeline-longrunning-dag`, click **Trigger DAG w/ config**.
3. Set the `model_type` to `video-optimizer`.
4. Set the `input_file` parameter to the GCS URI of your uploaded JSON payload from Step 2 (e.g., `gs://ggn-nmfs-osi-dev-1-data/my-user/inputs/test_payload.json`).
5. Change the output folder if desired, hit **Trigger**, and monitor your job's progress in the logs!

