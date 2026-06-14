#!/usr/bin/env bash
# Deploy SmolSearch to GCP Cloud Run.
# Prerequisites:
#   gcloud auth login
#   gcloud config set project <YOUR_PROJECT_ID>
#   gcloud services enable run.googleapis.com artifactregistry.googleapis.com
#
# Usage: bash deploy/gcp_deploy.sh [PROJECT_ID] [REGION]

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-asia-northeast1}"
SERVICE_NAME="smolsearch"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/smolsearch-repo"
IMAGE="${REGISTRY}/${SERVICE_NAME}:latest"

echo "[deploy] Project: ${PROJECT_ID} | Region: ${REGION}"

# Create Artifact Registry repo if it doesn't exist
gcloud artifacts repositories create smolsearch-repo \
  --repository-format=docker \
  --location="${REGION}" \
  --quiet 2>/dev/null || true

# Build and push image
gcloud builds submit --tag "${IMAGE}" .

# Deploy to Cloud Run (CPU, 2GB RAM)
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10 \
  --concurrency 4 \
  --timeout 60 \
  --allow-unauthenticated \
  --set-env-vars "HF_HOME=/app/.cache/huggingface"

echo "[deploy] Service URL:"
gcloud run services describe "${SERVICE_NAME}" \
  --platform managed \
  --region "${REGION}" \
  --format "value(status.url)"
