# Deployment Guide — LangChain Production Projects

Four FastAPI services deployable to **GCP Cloud Run** via GitHub Actions CI/CD.

For a complete step-by-step guide including novice instructions, see [`GCP/README.md`](GCP/README.md).

---

## Required GitHub Secrets

Set these in `Settings → Secrets and variables → Actions → Repository secrets`:

| Secret | Example value | Description |
|---|---|---|
| `GCP_PROJECT_ID` | `my-gcp-project` | GCP project ID |
| `GCP_SA_KEY` | `{ ... }` | Service account JSON key (raw JSON, not base64) |
| `GCP_REGION` | `us-central1` | Cloud Run deployment region |

### One-time GCP setup

Run `scripts/setup_gcp_infra.sh` for fully automated setup, or perform the steps manually:

```bash
PROJECT_ID="<YOUR_GCP_PROJECT_ID>"
REGION="<YOUR_REGION>"

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com

# Create Artifact Registry repo for Docker images
gcloud artifacts repositories create slm-apps \
  --repository-format=docker \
  --location=${REGION}

# Create service account for deployments
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer"

# Grant 3 required permissions to the deployer SA
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:github-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:github-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:github-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Allow Cloud Run to pull images from Artifact Registry
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"

# Export key — paste its full contents as the GCP_SA_KEY secret, then delete the file
gcloud iam service-accounts keys create key.json \
  --iam-account=github-deployer@${PROJECT_ID}.iam.gserviceaccount.com
# → open key.json, copy everything from { to }, paste as GCP_SA_KEY in GitHub
# → then: rm key.json
```

---

## Workflows

| Workflow file | Triggers on | Deploys |
|---|---|---|
| `ci.yml` | every push + PR | runs unit tests for all 4 projects |
| `deploy-01-smolsearch.yml` | push to main + changes in `01_smolsearch/` | Cloud Run: `smolsearch` |
| `deploy-02-ragify.yml` | push to main + changes in `02_ragify/` | Cloud Run: `ragify` |
| `deploy-03-agentflow.yml` | push to main + changes in `03_agentflow/` | Cloud Run: `agentflow` |
| `deploy-04-llmops-baseline.yml` | push to main + changes in `04_llmops_baseline/` | Cloud Run: `llmops-baseline` |

Each deploy workflow: **test → build Docker image → push to Artifact Registry → gcloud run deploy**.

---

## Local test run before pushing

Run from the root of this repository (`langchain-production-stack/`):

```bash
# Unit tests for all 4 production projects
for proj in 01_smolsearch 02_ragify 03_agentflow 04_llmops_baseline; do
  PYTHONPATH="${proj}" python -m pytest ${proj}/tests/ -q && \
    echo "PASS: ${proj}" || echo "FAIL: ${proj}"
done
```

---

## Manual deploy (without CI/CD)

```bash
# After running setup_gcp_infra.sh and setting PROJECT_ID/REGION in the script:
./scripts/deploy_all.sh
```

After deploying, verify all endpoints:

```bash
# Edit scripts/test_endpoints.sh to set the 4 service URLs, then:
./scripts/test_endpoints.sh
```

---

## Service endpoints (after deploy)

| Service | Endpoints |
|---|---|
| SmolSearch | `POST /index`, `POST /search`, `GET /health` |
| RAGify | `POST /index`, `POST /query` (strategy: similarity/mmr/multi_query), `GET /health` |
| AgentFlow | `POST /run`, `GET /health` |
| LLMOps Baseline | `POST /query`, `GET /metrics`, `GET /health` |
