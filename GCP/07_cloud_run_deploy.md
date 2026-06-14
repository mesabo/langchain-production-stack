# 07 - Deploy to Cloud Run

## What Cloud Run is

Cloud Run is Google's managed serverless container platform. You give it a Docker image and it:

- Starts containers on demand when requests arrive
- Scales the number of containers up as traffic increases
- Scales back down to zero containers when there is no traffic (billing stops)
- Provides an HTTPS endpoint with a Google-managed TLS certificate
- Handles load balancing across multiple container instances

You do not manage virtual machines, Kubernetes nodes, or operating systems. Cloud Run abstracts all of that. You only manage the container image, environment variables, and resource limits.

This is the standard deployment model for FastAPI microservices at companies that do not want to operate Kubernetes themselves.

---

## Deploy SmolSearch

```bash
# Set variables (if not already set from file 06)
PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
REGION="<YOUR_REGION>"
REPO="slm-apps"
GIT_SHA=$(git rev-parse --short HEAD)
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Deploy smolsearch to Cloud Run
gcloud run deploy smolsearch \
  --image ${REGISTRY}/smolsearch:${GIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet
```

### Flag-by-flag explanation

`--image ${REGISTRY}/smolsearch:${GIT_SHA}`
: The Docker image to deploy. Must be a fully qualified Artifact Registry URI. Cloud Run pulls this image when starting containers.

`--region ${REGION}`
: The GCP region where the service runs. Use the same region as your Artifact Registry repository. Cross-region image pulls are slower and add latency to cold starts.

`--platform managed`
: Specifies Cloud Run (fully managed), as opposed to Cloud Run for Anthos (runs on a GKE cluster you manage). Always use `managed` unless you have a specific reason to use Anthos.

`--allow-unauthenticated`
: Makes the service publicly accessible without an authentication token. Anyone with the URL can call it. For a public API this is correct. For internal services used only by other services, omit this flag and use service-to-service authentication instead.

`--memory 2Gi`
: Maximum RAM per container instance. `2Gi` means 2 gibibytes (2 * 1024 * 1024 * 1024 bytes). Sentence transformer models (the `all-MiniLM-L6-v2` model is 90 MB on disk but expands to ~500 MB in memory) plus FAISS index plus Python overhead typically requires 1--1.5 GB. We set 2 GB for headroom.

`--cpu 2`
: Number of vCPUs per container instance. With 1 CPU, computation-heavy operations (embedding generation) block other requests. 2 CPUs allow some parallelism. Cloud Run allocates CPU only during active requests; idle containers get 0 CPU.

`--concurrency 10`
: Maximum number of simultaneous requests a single container instance handles. With `--concurrency 10`, one container can handle 10 concurrent requests before Cloud Run spins up another instance. For CPU-bound inference workloads keep this low (5--20). For pure I/O workloads (proxies, simple APIs) it can be 100+.

`--set-env-vars "HF_HOME=/tmp/.cache/huggingface"`
: Sets an environment variable inside the container. HuggingFace's model download cache defaults to `~/.cache/huggingface`. Cloud Run containers run as a non-root user with a read-only filesystem except for `/tmp`. Setting `HF_HOME=/tmp/.cache/huggingface` puts the cache in `/tmp`, which is writable. Without this, the first request that tries to cache a model file will fail with a permission error.

`--timeout 300`
: Maximum time in seconds for a single request before Cloud Run returns a 504 Gateway Timeout. The default is 60 seconds. For requests that load a model on cold start (which can take 20--30 seconds before the actual inference runs), 60 seconds is too short. Set to 300 seconds (5 minutes) to be safe.

`--quiet`
: Suppresses interactive prompts. Without this flag, `gcloud run deploy` asks you to confirm the service name and region. In scripts and CI, always include `--quiet`.

---

## Cold starts

A cold start happens when Cloud Run starts a new container from scratch because there are no idle containers. With `--concurrency 10` and `--min-instances 0` (the default), Cloud Run scales to zero when there is no traffic. The next request starts a new container.

A cold start on Cloud Run involves:
1. Pulling the Docker image from Artifact Registry (~5--15 seconds for a 1 GB image)
2. Starting the container process
3. Your FastAPI app initializing (loading models into memory, ~10--30 seconds for a 135M sLM)
4. The container signaling it is ready to accept requests (by listening on the PORT)

Total cold start time: typically 30--60 seconds for a service that loads a sentence transformer model.

After the cold start, subsequent requests to the same container are fast (milliseconds). Cloud Run keeps containers alive for several minutes after the last request before scaling to zero.

**Mitigation options:**
- Set `--min-instances 1` to keep one container always warm (adds cost: ~$5/month for 256MB/0.083 vCPU)
- Reduce the Docker image size (use multi-stage builds, remove dev dependencies)
- Use a smaller model if low latency is critical

---

## Get the service URL

After deploying, Cloud Run assigns a permanent URL:

```bash
# Get the URL of the deployed service
gcloud run services describe smolsearch \
  --region ${REGION} \
  --format "value(status.url)"
```

Expected output:

```
https://smolsearch-abc123xyz-uc.a.run.app
```

The URL is permanent and does not change when you redeploy with a new image. The format is:
`https://<service-name>-<random-suffix>-<region-abbreviation>.a.run.app`

---

## Test the deployed service

```bash
# Save the URL to a variable
SMOLSEARCH_URL=$(gcloud run services describe smolsearch --region ${REGION} --format "value(status.url)")

# Test the health endpoint
curl -s "${SMOLSEARCH_URL}/health"
# Expected: {"status": "ok"}
```

The first request after a cold start will be slow. Subsequent requests are fast.

---

## Update a service

To deploy a new version, run the exact same `gcloud run deploy` command with a new image tag. Cloud Run creates a new revision, gradually shifts traffic to it (100% by default), and keeps the old revision available for rollback.

```bash
# Build and push a new image
NEW_SHA=$(git rev-parse --short HEAD)
docker build --platform linux/amd64 \
  -f 01_smolsearch/deploy/Dockerfile \
  -t ${REGISTRY}/smolsearch:${NEW_SHA} \
  01_smolsearch/
docker push ${REGISTRY}/smolsearch:${NEW_SHA}

# Deploy the new image
gcloud run deploy smolsearch \
  --image ${REGISTRY}/smolsearch:${NEW_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet
```

---

## Roll back to a previous revision

```bash
# List all revisions of a service
gcloud run revisions list --service smolsearch --region ${REGION}

# Send 100% of traffic to a specific revision
# Replace <REVISION_NAME> with the name from the list (e.g., smolsearch-00003-xyz)
gcloud run services update-traffic smolsearch \
  --to-revisions=<REVISION_NAME>=100 \
  --region ${REGION}
```

---

## Delete a service

```bash
# Delete a Cloud Run service (this does not delete the image in Artifact Registry)
gcloud run services delete smolsearch --region ${REGION}
```

---

## Deploy all four services

Deploy each service with memory/CPU/concurrency tuned for its workload.

```bash
# Set variables first
PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
REGION="<YOUR_REGION>"
REPO="slm-apps"
GIT_SHA=$(git rev-parse --short HEAD)
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Service 1: SmolSearch
# 2Gi memory for sentence-transformer model + FAISS index
# concurrency 10: embedding is CPU-bound; cap simultaneous requests
gcloud run deploy smolsearch \
  --image ${REGISTRY}/smolsearch:${GIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet

# Service 2: RAGify
# 2Gi for embedding model + retrieved context in memory
# concurrency 10: RAG pipeline is CPU-bound (retrieval + generation)
gcloud run deploy ragify \
  --image ${REGISTRY}/ragify:${GIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 10 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet

# Service 3: AgentFlow
# 4Gi: agent loop holds more state; tools may load additional models
# concurrency 5: agent with tool routing is more compute-intensive per request
# timeout 300: agent chains can involve multiple LLM calls; needs more time
gcloud run deploy agentflow \
  --image ${REGISTRY}/agentflow:${GIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --concurrency 5 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet

# Service 4: LLMOps Baseline
# 2Gi: inference logging is lightweight; baseline model is smaller
# concurrency 20: this service is primarily I/O (logging, metrics); higher concurrency is safe
gcloud run deploy llmops-baseline \
  --image ${REGISTRY}/llmops-baseline:${GIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --concurrency 20 \
  --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
  --timeout 300 \
  --quiet

echo "All four services deployed."
echo "Getting URLs..."
gcloud run services describe smolsearch    --region ${REGION} --format "value(status.url)"
gcloud run services describe ragify        --region ${REGION} --format "value(status.url)"
gcloud run services describe agentflow     --region ${REGION} --format "value(status.url)"
gcloud run services describe llmops-baseline --region ${REGION} --format "value(status.url)"
```

---

## Summary

At the end of this step you have:
- All four services deployed to Cloud Run
- Each accessible via a permanent HTTPS URL
- Appropriate memory/CPU/concurrency settings for each workload

Write down the four URLs. You will use them in `09_verify_and_monitor.md`.

Next: `08_github_actions_cicd.md` -- automate deploys with GitHub Actions.
