# 06 - Build Docker Images and Push to Artifact Registry

## Prerequisites

Before running any command in this file, confirm:

```bash
# Docker is installed and running
docker --version
# Expected: Docker version 24.x.x or higher

# gcloud is configured with the right project
gcloud config list
# Confirm project and account are correct

# Docker is configured to authenticate to Artifact Registry
cat ~/.docker/config.json
# Should contain "credHelpers": { "<REGION>-docker.pkg.dev": "gcloud" }
# If not, run: gcloud auth configure-docker <REGION>-docker.pkg.dev
```

You need to be at the root of the `langchain-production-stack` repository for the build commands in this file to work. The build context paths (`01_smolsearch/`, etc.) are relative to the repo root.

```bash
# Confirm you are in the repo root
ls
# Should show: 01_smolsearch  02_ragify  03_agentflow  04_llmops_baseline
```

---

## Set your three variables

Set these once at the start of your terminal session. All commands below use them.

```bash
# Your GCP project ID
PROJECT_ID="<YOUR_GCP_PROJECT_ID>"

# The GCP region where Artifact Registry lives
REGION="<YOUR_REGION>"
# Example: us-central1

# The Artifact Registry repository name (created in file 04)
REPO="slm-apps"

# Convenience: the base URI for all images
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

echo "Registry: $REGISTRY"
# Example: us-central1-docker.pkg.dev/my-project-123456/slm-apps
```

---

## Build a single image: SmolSearch

```bash
# Build the smolsearch Docker image
# --platform linux/amd64  : force the image to be built for the x86-64 architecture
# -f                      : path to the Dockerfile (relative to current directory)
# -t                      : name and tag for the resulting image
# last argument           : the build context (directory sent to Docker daemon during build)
docker build \
  --platform linux/amd64 \
  -f 01_smolsearch/deploy/Dockerfile \
  -t ${REGISTRY}/smolsearch:latest \
  01_smolsearch/
```

### Why `--platform linux/amd64`

Cloud Run containers run on x86-64 Linux. If you build on an Apple Silicon Mac (M1/M2/M3) or any ARM machine, Docker by default builds an `arm64` image. When Cloud Run tries to start that container it fails with `exec format error` in the logs.

The `--platform linux/amd64` flag forces the image to be built for x86-64 regardless of your local hardware. Always include this flag when building images that will run on Cloud Run.

### The build context explained

The last argument to `docker build` is the build context: the directory that Docker sends to the build daemon. Every `COPY` instruction in your Dockerfile copies files relative to this directory.

In the command above, `01_smolsearch/` is the build context. If your Dockerfile contains:
```
COPY requirements.txt .
COPY src/ ./src/
```
Docker looks for `requirements.txt` inside `01_smolsearch/`, not in the repo root.

The `-f 01_smolsearch/deploy/Dockerfile` flag points to the Dockerfile itself. The Dockerfile path and the build context can be different (and often are, as here).

---

## Push the image to Artifact Registry

```bash
# Push the image
# Docker reads the image name, sees it starts with <REGION>-docker.pkg.dev,
# and uses the gcloud credential helper configured in ~/.docker/config.json
docker push ${REGISTRY}/smolsearch:latest
```

Expected output:

```
The push refers to repository [us-central1-docker.pkg.dev/my-project-123456/slm-apps/smolsearch]
abc123: Pushed
def456: Pushed
...
latest: digest: sha256:xyz789... size: 1234
```

If you see `unauthorized: Unauthenticated request`, run `gcloud auth configure-docker ${REGION}-docker.pkg.dev` and try again.

---

## Tag images with git SHA for traceability

Using `latest` as a tag makes it impossible to know which code is running in production. Tag with the git commit SHA instead. This lets you:
- Look at the running Cloud Run revision and know exactly which commit it came from
- Roll back by deploying a specific SHA tag
- Correlate a bug report to the exact code that caused it

```bash
# Get the short git SHA of the current commit
GIT_SHA=$(git rev-parse --short HEAD)
echo "Building with tag: $GIT_SHA"

# Build with the SHA as the tag
docker build \
  --platform linux/amd64 \
  -f 01_smolsearch/deploy/Dockerfile \
  -t ${REGISTRY}/smolsearch:${GIT_SHA} \
  01_smolsearch/

# Push the SHA-tagged image
docker push ${REGISTRY}/smolsearch:${GIT_SHA}
```

In CI (GitHub Actions) we always use `${{ github.sha }}` as the tag. In manual builds, use `$(git rev-parse --short HEAD)`.

---

## Verify the image is in Artifact Registry

```bash
# List all images in the slm-apps repository
gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}
```

You should see `smolsearch` in the list with the tags you pushed.

---

## Build and push all four services

Once you understand the single-service flow, build all four in sequence.

```bash
# Set variables first (if not already set from above)
PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
REGION="<YOUR_REGION>"
REPO="slm-apps"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
GIT_SHA=$(git rev-parse --short HEAD)

# Service 1: SmolSearch
docker build --platform linux/amd64 \
  -f 01_smolsearch/deploy/Dockerfile \
  -t ${REGISTRY}/smolsearch:${GIT_SHA} \
  01_smolsearch/
docker push ${REGISTRY}/smolsearch:${GIT_SHA}
echo "SmolSearch pushed: ${GIT_SHA}"

# Service 2: RAGify
docker build --platform linux/amd64 \
  -f 02_ragify/deploy/Dockerfile \
  -t ${REGISTRY}/ragify:${GIT_SHA} \
  02_ragify/
docker push ${REGISTRY}/ragify:${GIT_SHA}
echo "RAGify pushed: ${GIT_SHA}"

# Service 3: AgentFlow
docker build --platform linux/amd64 \
  -f 03_agentflow/deploy/Dockerfile \
  -t ${REGISTRY}/agentflow:${GIT_SHA} \
  03_agentflow/
docker push ${REGISTRY}/agentflow:${GIT_SHA}
echo "AgentFlow pushed: ${GIT_SHA}"

# Service 4: LLMOps Baseline
docker build --platform linux/amd64 \
  -f 04_llmops_baseline/deploy/Dockerfile \
  -t ${REGISTRY}/llmops-baseline:${GIT_SHA} \
  04_llmops_baseline/
docker push ${REGISTRY}/llmops-baseline:${GIT_SHA}
echo "LLMOps Baseline pushed: ${GIT_SHA}"

echo "All four services pushed with tag: ${GIT_SHA}"
```

Use `scripts/deploy_all.sh` (in the scripts directory) for a more polished version of this with error handling.

---

## Common errors and fixes

### "unauthorized: Unauthenticated request"

```
Error response from daemon: unauthorized: Unauthenticated request. Returned 401.
```

Fix: Docker does not have credentials for Artifact Registry.

```bash
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

If you already ran configure-docker but it still fails, your gcloud auth token may have expired:

```bash
gcloud auth login
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

### "exec format error" on Cloud Run (not a build error, but caught at this stage)

You will see this after deploying if you built without `--platform linux/amd64`:

```
Cloud Run error: Container failed to start.
exec /app/entrypoint.sh: exec format error
```

Fix: Rebuild with the flag:

```bash
docker build --platform linux/amd64 -f ... -t ... .
docker push ...
```

### "no such file or directory" during build

```
COPY failed: file not found in build context or excluded by .dockerignore: stat requirements.txt: file not found
```

Fix: You likely passed the wrong build context. The build context must be the directory containing the files your Dockerfile COPYs. In our setup the context is `01_smolsearch/` (not `.` or `01_smolsearch/deploy/`).

### "denied: Permission 'artifactregistry.repositories.uploadArtifacts' denied"

Fix: Your authenticated user (or service account) does not have `roles/artifactregistry.writer`. See file 05 to grant the role.

---

## Summary

At the end of this step you have:
- All four Docker images built for `linux/amd64`
- All four images pushed to Artifact Registry with git SHA tags
- Verified the images are visible via `gcloud artifacts docker images list`

Next: `07_cloud_run_deploy.md` -- deploy the images to Cloud Run.
