import os
import sys
import json
import time
import subprocess
import urllib.request
from urllib.error import URLError, HTTPError
from google.cloud import storage

HOST = "http://localhost:8080"
HEALTH_ENDPOINT = f"{HOST}/isalive"
PREDICT_ENDPOINT = f"{HOST}/predict"

MAX_STARTUP_WAIT_SECONDS = 120
# 360000 seconds = 100 hours. Extreme timeout duration to accommodate 
# multi-hour, highly intensive computer vision pipelines running against long videos.
MAX_PREDICTION_WAIT_SECONDS = 360000 

def download_json_from_gcs(gcs_uri: str) -> dict:
    """
    Downloads a JSON payload file from GCS and returns it as a dictionary.
    
    Parameters
    ----------
    gcs_uri : str
        The full gs:// URI of the JSON file to download.
        
    Returns
    -------
    dict
        The parsed JSON dictionary.
        
    Raises
    ------
    ValueError
        If the URI does not start with gs://
    FileNotFoundError
        If the file cannot be located in the specified bucket.
    """
    print(f"[RUNNER] Fetching payload from {gcs_uri}...", flush=True)
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Input file URI must start with gs://. Got: {gcs_uri}")
    
    client = storage.Client()
    path_parts = gcs_uri.replace("gs://", "").split("/")
    bucket_name = path_parts[0]
    blob_path = "/".join(path_parts[1:])
    
    blob = client.bucket(bucket_name).blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError(f"Input file not found in GCS: {gcs_uri}")
    
    return json.loads(blob.download_as_text())

def wait_for_server():
    """
    Polls the /isalive endpoint until the Flask server is ready.
    
    Raises
    ------
    TimeoutError
        If the server fails to report health within MAX_STARTUP_WAIT_SECONDS.
    """
    print("[RUNNER] Waiting for API server to start...", flush=True)
    start_time = time.time()
    while time.time() - start_time < MAX_STARTUP_WAIT_SECONDS:
        try:
            response = urllib.request.urlopen(HEALTH_ENDPOINT)
            if response.getcode() == 200:
                print(f"[RUNNER] Server is healthy! (Took {int(time.time() - start_time)}s)", flush=True)
                return
        except (URLError, ConnectionResetError):
            pass
        time.sleep(2)
    raise TimeoutError(f"Server did not become healthy within {MAX_STARTUP_WAIT_SECONDS} seconds.")

def execute_prediction(payload: dict):
    """
    Sends the JSON payload to the local /predict endpoint to trigger inference.
    
    Parameters
    ----------
    payload : dict
        The Vertex AI-style prediction payload containing input configurations.
    """
    print(f"[RUNNER] Sending payload to /predict endpoint. Timeout set to {MAX_PREDICTION_WAIT_SECONDS}s...", flush=True)
    req = urllib.request.Request(
        PREDICT_ENDPOINT,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        response = urllib.request.urlopen(req, timeout=MAX_PREDICTION_WAIT_SECONDS)
        response_body = response.read().decode('utf-8')
        if response.getcode() == 200:
            print("[RUNNER] Prediction completed successfully.", flush=True)
        else:
            print(f"[RUNNER] Warning: Server returned status {response.getcode()}", flush=True)
    except Exception as e:
        print(f"[RUNNER] Failed to execute prediction: {str(e)}", flush=True)
        sys.exit(1)

def main():
    print("==================================================", flush=True)
    print("  Starting Cloud Batch Inference Wrapper          ", flush=True)
    print("==================================================", flush=True)
    
    input_file = os.environ.get("INPUT_FILE")
    if not input_file:
        print("[RUNNER] Error: INPUT_FILE environment variable is not set.", flush=True)
        sys.exit(1)
        
    print("[RUNNER] Spawning app.py as a background process...", flush=True)
    server_process = subprocess.Popen([sys.executable, "app.py"])
    
    try:
        wait_for_server()
        payload = download_json_from_gcs(input_file)
        
        # --- DYNAMIC PARAMETER INJECTION ---
        # Inject the Airflow environment variables into the payload 
        # so app.py knows where to upload the converted videos.
        if "parameters" not in payload:
            payload["parameters"] = {}
        payload["parameters"]["OUTPUT_BUCKET"] = os.environ.get("OUTPUT_BUCKET", "")
        payload["parameters"]["OUTPUT_FOLDER"] = os.environ.get("OUTPUT_FOLDER", "")
        
        execute_prediction(payload)
    finally:
        print("[RUNNER] Shutting down background server...", flush=True)
        server_process.terminate()
        try:
            server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_process.kill()
            
    print("[RUNNER] Job complete. Exiting.", flush=True)

if __name__ == "__main__":
    main()
