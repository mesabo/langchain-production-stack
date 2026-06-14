# GCP Deployment Learning Guide

## Purpose

This folder teaches you how to deploy containerized FastAPI services to Google Cloud Platform from scratch. The target audience is a developer with Python and Docker experience but no prior GCP knowledge. By the end of this guide you will be able to:

- Set up a GCP project with billing and IAM
- Build and push Docker images to Artifact Registry
- Deploy and update Cloud Run services
- Automate every deploy through GitHub Actions CI/CD

These are exactly the skills hiring teams at FAANG and mid-size tech companies test in infrastructure and MLOps interview loops.

---

## The project we are deploying

Repository: `langchain-production-stack`

Four FastAPI services, each in its own subdirectory:

| Directory | Service name | What it does |
|---|---|---|
| `01_smolsearch/` | smolsearch | Semantic search with sentence transformers and FAISS |
| `02_ragify/` | ragify | Retrieval-augmented generation pipeline |
| `03_agentflow/` | agentflow | LangChain agent with tool routing |
| `04_llmops_baseline/` | llmops-baseline | Inference logging and latency metrics |

Each service has a `deploy/Dockerfile` that packages it for production.

---

## Three variables you need before starting

Before running any command in this guide, decide on these three values and write them down. Every command in every file uses them.

| Variable | What it is | Example |
|---|---|---|
| `PROJECT_ID` | Your GCP project identifier (not display name) | `my-langchain-proj-123456` |
| `REGION` | GCP region where you deploy services | `us-central1` |
| `SA_EMAIL` | Service account email (created in step 5) | `github-deployer@my-langchain-proj-123456.iam.gserviceaccount.com` |

Wherever this guide shows `<PROJECT_ID>`, replace that with your actual project ID. Same for `<REGION>` and `<SA_EMAIL>`.

---

## Reading order

Work through these files in order. Each file builds on the previous one.

| File | Topic | Estimated time |
|---|---|---|
| `01_account_and_project.md` | Create GCP account, project, billing | 20 minutes |
| `02_gcloud_sdk.md` | Install gcloud CLI, authenticate | 15 minutes |
| `03_enable_apis.md` | Enable required GCP APIs | 5 minutes |
| `04_artifact_registry.md` | Create Docker image registry | 10 minutes |
| `05_service_account_iam.md` | Service account and IAM roles | 15 minutes |
| `06_build_and_push.md` | Build Docker images, push to registry | 20 minutes |
| `07_cloud_run_deploy.md` | Deploy services to Cloud Run | 20 minutes |
| `08_github_actions_cicd.md` | Automate deploys with GitHub Actions | 30 minutes |
| `09_verify_and_monitor.md` | Verify deploys, read logs, test endpoints | 15 minutes |
| `10_troubleshooting.md` | Common errors and exact fixes | Reference |

---

## Two learning tracks

### Track A: Manual deploy (full understanding first)

Read files 01 through 07 in order. At the end you will have all four services running on Cloud Run, deployed by hand. This is the right starting point because you understand every piece before automating it.

Files: `01` → `02` → `03` → `04` → `05` → `06` → `07`

### Track B: CI/CD deploy (after manual deploy works)

After completing Track A, read file 08. This adds GitHub Actions so every push to `main` triggers an automatic test-build-deploy cycle.

Files: `01` → `02` → `03` → `04` → `05` → `08`

---

## Scripts

The `scripts/` directory contains ready-to-run shell scripts for common operations.

| Script | What it does |
|---|---|
| `scripts/setup_gcp_infra.sh` | One-shot: creates registry, service account, grants IAM roles |
| `scripts/deploy_all.sh` | Builds, pushes, and deploys all 4 services |
| `scripts/test_endpoints.sh` | Runs curl smoke tests against all 4 live services |

Run `setup_gcp_infra.sh` once when setting up a new GCP project. Run `deploy_all.sh` to do a full manual redeploy. Run `test_endpoints.sh` after any deploy to confirm services are healthy.

---

## Cost

All four services running at low traffic will cost close to $0 per month. Cloud Run bills per request and scales to zero when idle. The only consistent cost is Artifact Registry storage (cents per GB per month). Set a billing alert at $1 as described in `01_account_and_project.md` so you get an email before anything accumulates.
