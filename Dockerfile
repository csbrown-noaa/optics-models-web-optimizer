FROM python:3.10-slim

WORKDIR /workspace

# Install system dependencies (ffmpeg is required for our core logic)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY inference_runner.py .
COPY model.py .

ENV HOME=/workspace

# Setup directories and permissions for the non-root execution required by GCP
RUN chown -R 8080:8080 /workspace && \
    chmod -R 777 /tmp

# Switch to the required non-root user
USER 8080
EXPOSE 8080

# Default command starts the HTTP server
CMD ["python", "app.py"]

