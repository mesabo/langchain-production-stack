# Deployment Guide — LangChain Production Projects

Four FastAPI services deployable to **GCP Cloud Run** via GitHub Actions CI/CD.

---

## Required GitHub Secrets

Set these in `Settings → Secrets and variables → Actions → Repository secrets`:

| Secret | Example value | Description |
|---|---|---|
| `GCP_PROJECT_ID` | `my-gcp-project` | GCP project ID |
| `GCP_SA_KEY` | `{ ... }` | Service account JSON key (base64 or raw JSON) |
| `GCP_REGION` | `us-central1` | Cloud Run deployment region |

### One-time GCP setup

```bash
# Create Artifact Registry repo for Docker images
gcloud artifacts repositories create slm-apps \
  --repository-format=docker \
  --location=us-central1

# Create service account for deployments
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Export key for GitHub Secret
gcloud iam service-accounts keys create key.json \
  --iam-account=github-deployer@$PROJECT_ID.iam.gserviceaccount.com
# → paste contents of key.json as GCP_SA_KEY
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

```bash
# Smoke test all 11 Course 4 classes
for cls in \
  courses/course4_langchain_ecosystem/chapter1_core/class1_lcel_chains \
  courses/course4_langchain_ecosystem/chapter1_core/class2_memory_conversation \
  courses/course4_langchain_ecosystem/chapter1_core/class3_structured_output \
  courses/course4_langchain_ecosystem/chapter2_vector_rag/class1_vector_stores \
  courses/course4_langchain_ecosystem/chapter2_vector_rag/class2_advanced_rag \
  courses/course4_langchain_ecosystem/chapter2_vector_rag/class3_rag_eval \
  courses/course4_langchain_ecosystem/chapter3_agents/class1_tools_function_calling \
  courses/course4_langchain_ecosystem/chapter3_agents/class2_react_agent \
  courses/course4_langchain_ecosystem/chapter3_agents/class3_langgraph_stateful \
  courses/course4_langchain_ecosystem/chapter4_production/class1_langsmith_tracing \
  courses/course4_langchain_ecosystem/chapter4_production/class2_production_patterns; do
  conda run -n slm-gpu bash $cls/run.sh && echo "PASS: $(basename $cls)" || echo "FAIL: $(basename $cls)"
done

# Unit tests for all 4 production projects
for proj in 01_smolsearch 02_ragify 03_agentflow 04_llmops_baseline; do
  PYTHONPATH="courses/projects/$proj" conda run -n slm-gpu pytest courses/projects/$proj/tests/ -q
done
```

---

## Service endpoints (after deploy)

| Service | Endpoints |
|---|---|
| SmolSearch | `POST /index`, `POST /search`, `POST /answer`, `POST /stream`, `GET /health` |
| RAGify | `POST /index`, `POST /query` (strategy: similarity/mmr/multi_query), `GET /health` |
| AgentFlow | `POST /run`, `GET /health` |
| LLMOps Baseline | `POST /query`, `GET /metrics`, `GET /health` |
