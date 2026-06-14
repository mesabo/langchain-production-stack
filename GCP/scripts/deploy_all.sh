#!/usr/bin/env bash
# deploy_all.sh
#
# Builds, pushes, and deploys all 4 langchain-production-stack services
# to Cloud Run in sequence.
#
# Prerequisites:
#   - Docker installed and running
#   - gcloud authenticated (gcloud auth login)
#   - Docker configured for Artifact Registry (gcloud auth configure-docker ...)
#   - Artifact Registry repository exists (run setup_gcp_infra.sh first)
#   - Cloud Run and Artifact Registry APIs enabled
#
# Usage:
#   chmod +x scripts/deploy_all.sh
#   ./scripts/deploy_all.sh
#
# Run this from the root of the langchain-production-stack repository.

set -euo pipefail

# ---------------------------------------------------------------------------
# CONFIGURATION -- edit these values before running
# ---------------------------------------------------------------------------

PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
# What to put here: your GCP project ID.
# Find it with: gcloud projects list
# Example: langchain-prod-stack-123456

REGION="<YOUR_REGION>"
# What to put here: the GCP region where services are deployed.
# Must match the region where your Artifact Registry repository lives.
# Example: us-central1

GIT_SHA=$(git rev-parse --short HEAD)
# Uses the current git commit's short SHA as the Docker image tag.
# This ensures every image is uniquely traceable to a specific commit.
# Override with a specific value if you want to deploy a particular commit:
#   GIT_SHA="abc123d"

# ---------------------------------------------------------------------------
# Derived values -- do not edit below this line
# ---------------------------------------------------------------------------

REPO_NAME="slm-apps"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
step()    { echo -e "${CYAN}[STEP]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

info "Preflight checks..."

if ! command -v docker &>/dev/null; then
    error "Docker is not installed or not on PATH."
    exit 1
fi

if ! command -v gcloud &>/dev/null; then
    error "gcloud CLI is not installed or not on PATH."
    exit 1
fi

if [[ "${PROJECT_ID}" == "<YOUR_GCP_PROJECT_ID>" ]]; then
    error "You have not set PROJECT_ID. Edit the top of this script."
    exit 1
fi

if [[ "${REGION}" == "<YOUR_REGION>" ]]; then
    error "You have not set REGION. Edit the top of this script."
    exit 1
fi

# Confirm we are at the repo root by checking for service directories
for dir in 01_smolsearch 02_ragify 03_agentflow 04_llmops_baseline; do
    if [[ ! -d "${dir}" ]]; then
        error "Directory '${dir}' not found."
        error "Run this script from the root of the langchain-production-stack repository."
        exit 1
    fi
done

info "Configuration:"
info "  Project ID : ${PROJECT_ID}"
info "  Region     : ${REGION}"
info "  Registry   : ${REGISTRY}"
info "  Git SHA    : ${GIT_SHA}"
echo ""

# Set the gcloud project so all gcloud commands target the right project
gcloud config set project "${PROJECT_ID}" --quiet

# ---------------------------------------------------------------------------
# Helper function: build, push, deploy one service
# build_push_deploy SERVICE_DIR IMAGE_NAME SERVICE_NAME MEMORY CPU CONCURRENCY TIMEOUT
# ---------------------------------------------------------------------------

build_push_deploy() {
    local service_dir="$1"    # Directory containing the service (e.g., 01_smolsearch)
    local image_name="$2"     # Image name in Artifact Registry (e.g., smolsearch)
    local service_name="$3"   # Cloud Run service name (e.g., smolsearch)
    local memory="$4"         # Memory limit (e.g., 2Gi)
    local cpu="$5"            # CPU count (e.g., 2)
    local concurrency="$6"    # Max concurrent requests per instance (e.g., 10)
    local timeout="$7"        # Request timeout in seconds (e.g., 300)

    local full_image="${REGISTRY}/${image_name}:${GIT_SHA}"

    echo ""
    step "========================================================"
    step "  ${service_name}"
    step "  Image: ${full_image}"
    step "========================================================"

    # Build
    info "Building Docker image..."
    docker build \
        --platform linux/amd64 \
        -f "${service_dir}/deploy/Dockerfile" \
        -t "${full_image}" \
        "${service_dir}/"
    # --platform linux/amd64 : required for Cloud Run; ensures the image runs on x86-64
    # -f : path to the Dockerfile
    # -t : the full image URI including registry, repo, name, and tag
    # last arg: the build context (files available to COPY instructions in the Dockerfile)

    info "Docker image built: ${full_image}"

    # Push
    info "Pushing image to Artifact Registry..."
    docker push "${full_image}"
    info "Image pushed."

    # Deploy
    info "Deploying to Cloud Run..."
    gcloud run deploy "${service_name}" \
        --image "${full_image}" \
        --region "${REGION}" \
        --platform managed \
        --allow-unauthenticated \
        --memory "${memory}" \
        --cpu "${cpu}" \
        --concurrency "${concurrency}" \
        --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
        --timeout "${timeout}" \
        --quiet
    # --platform managed  : use Cloud Run (fully managed), not Anthos
    # --allow-unauthenticated : make the service publicly accessible
    # --memory            : RAM per container instance
    # --cpu               : vCPUs per container instance
    # --concurrency       : max simultaneous requests per instance
    # --set-env-vars      : HF_HOME must point to /tmp (the only writable dir in Cloud Run)
    # --timeout           : max request duration in seconds
    # --quiet             : suppress interactive confirmation prompts

    local service_url
    service_url=$(gcloud run services describe "${service_name}" \
        --region "${REGION}" \
        --format "value(status.url)")
    info "Deployed: ${service_url}"
    echo "${service_url}"
}

# ---------------------------------------------------------------------------
# Deploy all four services
# ---------------------------------------------------------------------------

# Service 1: SmolSearch
# - 2Gi: sentence-transformer model + FAISS index fits comfortably in 2 GB
# - concurrency 10: embedding generation is CPU-bound; cap at 10 to avoid OOM
SMOLSEARCH_URL=$(build_push_deploy \
    "01_smolsearch" \
    "smolsearch" \
    "smolsearch" \
    "2Gi" "2" "10" "300")

# Service 2: RAGify
# - 2Gi: retriever + generator; similar memory profile to SmolSearch
# - concurrency 10: RAG pipeline is CPU-bound (encode + retrieve + generate)
RAGIFY_URL=$(build_push_deploy \
    "02_ragify" \
    "ragify" \
    "ragify" \
    "2Gi" "2" "10" "300")

# Service 3: AgentFlow
# - 4Gi: agent loop holds larger state; tool outputs accumulate in memory
# - concurrency 5: agent with tool routing is more expensive per request
AGENTFLOW_URL=$(build_push_deploy \
    "03_agentflow" \
    "agentflow" \
    "agentflow" \
    "4Gi" "2" "5" "300")

# Service 4: LLMOps Baseline
# - 2Gi: smaller model + logging overhead; 2 GB is sufficient
# - concurrency 20: logging/metrics service is mostly I/O; higher concurrency is safe
LLMOPS_URL=$(build_push_deploy \
    "04_llmops_baseline" \
    "llmops-baseline" \
    "llmops-baseline" \
    "2Gi" "2" "20" "300")

# ---------------------------------------------------------------------------
# Print final summary
# ---------------------------------------------------------------------------

echo ""
echo "========================================================================"
echo "  All 4 services deployed successfully."
echo "========================================================================"
echo ""
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "SERVICE" "MEMORY" "CPU" "CONCURRENCY" "URL"
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "-------" "------" "---" "-----------" "---"
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "smolsearch"      "2Gi"  "2" "10"  "${SMOLSEARCH_URL}"
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "ragify"          "2Gi"  "2" "10"  "${RAGIFY_URL}"
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "agentflow"       "4Gi"  "2" "5"   "${AGENTFLOW_URL}"
printf "%-20s  %-6s  %-4s  %-11s  %s\n" "llmops-baseline" "2Gi"  "2" "20"  "${LLMOPS_URL}"
echo ""
echo "Git SHA: ${GIT_SHA}"
echo ""
echo "To run smoke tests against these services:"
echo "  Edit scripts/test_endpoints.sh with the URLs above, then:"
echo "  ./scripts/test_endpoints.sh"
echo ""
echo "To view logs:"
echo "  gcloud logging read 'resource.type=cloud_run_revision' --limit 50 --freshness 10m"
echo ""
echo "========================================================================"
