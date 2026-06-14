#!/usr/bin/env bash
# setup_gcp_infra.sh
#
# One-time setup script for GCP infrastructure required to deploy the
# langchain-production-stack services to Cloud Run.
#
# What this script does:
#   1. Sets gcloud to the target project
#   2. Enables the 4 required APIs
#   3. Creates the Artifact Registry Docker repository (idempotent)
#   4. Creates the github-deployer service account (idempotent)
#   5. Grants 3 IAM roles to the service account
#   6. Grants Artifact Registry reader to the Compute Engine default SA
#   7. Exports a service account key to key.json
#   8. Prints next steps
#
# Run this once when setting up a new GCP project.
# Do NOT run it in CI/CD -- it is a one-time setup tool.
#
# Usage:
#   chmod +x scripts/setup_gcp_infra.sh
#   ./scripts/setup_gcp_infra.sh

set -euo pipefail
# set -e : exit immediately if any command returns a non-zero exit code
# set -u : treat unset variables as errors
# set -o pipefail : if any command in a pipe fails, the whole pipe fails
# These three flags together catch the most common shell script bugs.

# ---------------------------------------------------------------------------
# CONFIGURATION -- edit these three values before running
# ---------------------------------------------------------------------------

PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
# What to put here: your GCP project ID, NOT the project display name.
# Find it with: gcloud projects list
# Example: langchain-prod-stack-123456

REGION="<YOUR_REGION>"
# What to put here: the GCP region where you want to deploy.
# Example: us-central1
# Other options: us-east1, europe-west1, asia-east1

SA_NAME="github-deployer"
# The service account name. Change this only if you want a different name.
# The full email will be: ${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com

# ---------------------------------------------------------------------------
# Derived values -- do not edit below this line
# ---------------------------------------------------------------------------

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
REPO_NAME="slm-apps"

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'  # No Color (reset)

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

info "Checking prerequisites..."

# Verify gcloud is installed
if ! command -v gcloud &>/dev/null; then
    error "gcloud CLI is not installed or not on PATH."
    error "Follow instructions in 02_gcloud_sdk.md to install it."
    exit 1
fi

# Verify the user filled in the configuration values
if [[ "${PROJECT_ID}" == "<YOUR_GCP_PROJECT_ID>" ]]; then
    error "You have not set PROJECT_ID. Open this script and set it at the top."
    exit 1
fi

if [[ "${REGION}" == "<YOUR_REGION>" ]]; then
    error "You have not set REGION. Open this script and set it at the top."
    exit 1
fi

info "Configuration:"
info "  Project ID : ${PROJECT_ID}"
info "  Region     : ${REGION}"
info "  SA name    : ${SA_NAME}"
info "  SA email   : ${SA_EMAIL}"
info "  Repo name  : ${REPO_NAME}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Set gcloud project
# ---------------------------------------------------------------------------

info "Step 1: Setting gcloud project to ${PROJECT_ID}..."

gcloud config set project "${PROJECT_ID}"
# This sets the default project for all subsequent gcloud commands.
# Equivalent to always passing --project ${PROJECT_ID} to every command.

info "Active project: $(gcloud config get-value project)"

# ---------------------------------------------------------------------------
# Step 2: Enable required APIs
# ---------------------------------------------------------------------------

info "Step 2: Enabling required APIs (this may take 1-2 minutes)..."

gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com
# Enabling APIs is idempotent -- if already enabled this is a no-op.

info "APIs enabled:"
gcloud services list --enabled \
    --filter="name:run OR name:artifactregistry OR name:iam OR name:cloudresourcemanager" \
    --format="table(name)"

# ---------------------------------------------------------------------------
# Step 3: Create Artifact Registry repository (idempotent)
# ---------------------------------------------------------------------------

info "Step 3: Creating Artifact Registry repository '${REPO_NAME}' in ${REGION}..."

# Check if the repository already exists before creating it.
# gcloud artifacts repositories describe exits 0 if it exists, non-zero if not.
if gcloud artifacts repositories describe "${REPO_NAME}" \
        --location="${REGION}" \
        --project="${PROJECT_ID}" \
        &>/dev/null; then
    warn "Repository '${REPO_NAME}' already exists in ${REGION}. Skipping create."
else
    gcloud artifacts repositories create "${REPO_NAME}" \
        --repository-format=docker \
        --location="${REGION}" \
        --description="LangChain production stack Docker images"
    info "Repository '${REPO_NAME}' created."
fi

# Configure Docker authentication for this registry
info "Configuring Docker credential helper for ${REGION}-docker.pkg.dev..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
info "Docker configured to authenticate to Artifact Registry."

# ---------------------------------------------------------------------------
# Step 4: Create service account (idempotent)
# ---------------------------------------------------------------------------

info "Step 4: Creating service account '${SA_NAME}'..."

# Check if the service account already exists
if gcloud iam service-accounts describe "${SA_EMAIL}" \
        --project="${PROJECT_ID}" \
        &>/dev/null; then
    warn "Service account '${SA_EMAIL}' already exists. Skipping create."
else
    gcloud iam service-accounts create "${SA_NAME}" \
        --display-name="GitHub Actions Deployer" \
        --description="Used by GitHub Actions to push Docker images and deploy to Cloud Run" \
        --project="${PROJECT_ID}"
    info "Service account '${SA_EMAIL}' created."
fi

# ---------------------------------------------------------------------------
# Step 5: Grant IAM roles to the service account
# ---------------------------------------------------------------------------

info "Step 5: Granting IAM roles to ${SA_EMAIL}..."

# Role 1: Push Docker images to Artifact Registry
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/artifactregistry.writer" \
    --quiet
info "  Granted: roles/artifactregistry.writer"

# Role 2: Create and update Cloud Run services
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/run.admin" \
    --quiet
info "  Granted: roles/run.admin"

# Role 3: Allow the SA to act as itself at Cloud Run deploy time
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/iam.serviceAccountUser" \
    --quiet
info "  Granted: roles/iam.serviceAccountUser"

# Verify
info "Current roles for ${SA_EMAIL}:"
gcloud projects get-iam-policy "${PROJECT_ID}" \
    --flatten="bindings[].members" \
    --filter="bindings.members:${SA_NAME}" \
    --format="table(bindings.role)"

# ---------------------------------------------------------------------------
# Step 6: Grant Compute Engine default SA access to Artifact Registry
# ---------------------------------------------------------------------------

info "Step 6: Granting Artifact Registry reader to Compute Engine default SA..."

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# This is the service account Cloud Run uses at runtime to pull Docker images.
# Without this grant, Cloud Run pulls fail with 403 when starting containers.

info "  Compute Engine default SA: ${COMPUTE_SA}"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/artifactregistry.reader" \
    --quiet
info "  Granted: roles/artifactregistry.reader to ${COMPUTE_SA}"

# ---------------------------------------------------------------------------
# Step 7: Export service account key to key.json
# ---------------------------------------------------------------------------

warn "Step 7: Exporting service account key to key.json..."
warn "  key.json is a CREDENTIAL FILE. Treat it like a password."
warn "  Do NOT commit it to git."
warn "  Delete it after pasting its contents into GitHub Secrets."

if [[ -f "key.json" ]]; then
    warn "  key.json already exists. Deleting and recreating..."
    rm key.json
fi

gcloud iam service-accounts keys create key.json \
    --iam-account="${SA_EMAIL}"

info "  key.json created in the current directory: $(pwd)/key.json"

# ---------------------------------------------------------------------------
# Step 8: Print summary and next steps
# ---------------------------------------------------------------------------

echo ""
echo "========================================================================"
echo "  GCP infrastructure setup complete."
echo "========================================================================"
echo ""
echo "Summary:"
echo "  Project ID        : ${PROJECT_ID}"
echo "  Region            : ${REGION}"
echo "  Artifact Registry : ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}"
echo "  Service account   : ${SA_EMAIL}"
echo "  Key file          : $(pwd)/key.json"
echo ""
echo "========================================================================"
echo "  NEXT STEPS"
echo "========================================================================"
echo ""
echo "1. Add GitHub repository secrets:"
echo "   Go to: https://github.com/mesabo/langchain-production-stack"
echo "   Settings > Secrets and variables > Actions > New repository secret"
echo ""
echo "   Secret name        Value"
echo "   GCP_PROJECT_ID     ${PROJECT_ID}"
echo "   GCP_REGION         ${REGION}"
echo "   GCP_SA_KEY         (paste full contents of key.json)"
echo ""
echo "2. Delete key.json after pasting:"
echo "   rm key.json"
echo ""
echo "3. Add key.json to .gitignore NOW (if not already there):"
echo "   echo 'key.json' >> .gitignore"
echo ""
echo "4. To deploy manually, run:"
echo "   ./scripts/deploy_all.sh"
echo ""
echo "5. To deploy via CI/CD, push a change to main in any service directory."
echo ""
echo "========================================================================"
