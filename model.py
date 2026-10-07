"""
model.py - Video Web-Optimization

Welcome! If you are integrating a new model into the NOAA/NMFS ecosystem, 
THIS IS THE ONLY PYTHON FILE YOU NEED TO EDIT.

The surrounding infrastructure (app.py, inference_runner.py) handles downloading 
files from Google Cloud Storage (GCS), setting up the web server, and uploading 
the final results back to GCS. 

Your goal:
1. Read the input videos from `input_dir`.
2. Inspect the video codec.
3. Remux to h.264 if possible, otherwise transcode.
4. Apply web-optimization flags and save to `output_file_path`.
"""

import os
import subprocess
import json

def get_video_codec(filepath: str) -> str:
    """
    Uses ffprobe to extract the video codec stream.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        filepath
    ]
    
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
        
    info = json.loads(result.stdout)
    
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream.get("codec_name")
            
    raise ValueError("Could not determine video codec. Is this a valid video file?")

def run_inference(input_dir: str, output_file_path: str, config: dict):
    """
    Core inference logic. 
    
    Parameters
    ----------
    input_dir : str
        Local directory where all your input images/videos have ALREADY been downloaded.
    output_file_path : str
        The exact local file path where you MUST save your final results.
    config : dict
        The "config" dictionary passed from the Airflow payload. Contains paths 
        to your downloaded weights, hyperparameters, etc.
    """
    
    print(f"[MODEL] Starting video optimization...")
    
    input_files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
    if not input_files:
        raise FileNotFoundError("[MODEL] No input files found in directory!")
        
    filename = input_files[0]
    filepath = os.path.join(input_dir, filename)
    
    print(f"[MODEL] Analyzing {filename}...")
    video_codec = get_video_codec(filepath)
    print(f"[MODEL] Detected Video Codec: {video_codec}")

    # Build base ffmpeg command
    cmd = [
        "ffmpeg",
        "-y",               # Overwrite output without asking
        "-i", filepath,     # Input file
    ]
    
    # Video stream handling
    if video_codec == "h264":
        print("[MODEL] Action: Remuxing (h.264 detected)")
        cmd.extend(["-c:v", "copy"])
    else:
        print("[MODEL] Action: Transcoding (converting to h.264)")
        cmd.extend([
            "-c:v", "libx264", 
            "-preset", "medium", 
            "-crf", "23",
            "-pix_fmt", "yuv420p" # Ensure web compatibility for colorspace
        ])
        
    # Audio stream and Web Optimization handling
    # -c:a aac safely transcodes audio if present, or is ignored if absent
    # -movflags +faststart optimizes the mp4 for web streaming
    print("[MODEL] Action: Transcoding audio to aac (if present) and applying web optimization")
    cmd.extend([
        "-c:a", "aac", 
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_file_path
    ])
    
    print(f"[MODEL] Executing: {' '.join(cmd)}")
    
    # Execute ffmpeg
    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if process.returncode != 0:
        print(f"[MODEL] ffmpeg error output: {process.stderr}")
        raise RuntimeError(f"ffmpeg processing failed with return code {process.returncode}")
        
    print(f"[MODEL] Optimization complete! Saved to {output_file_path}")
