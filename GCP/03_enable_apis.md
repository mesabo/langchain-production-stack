# 03 - Enable Required GCP APIs

## What "enabling an API" means

GCP is organized around APIs. Each product (Cloud Run, Artifact Registry, IAM, etc.) is exposed as a service with an API. Before you can use any of these services in your project, you must explicitly enable the corresponding API.

Enabling an API does three things:

1. **Activates billing** for that service in your project. GCP will track usage and charge accordingly (or credit against free tier).
2. **Allocates quota** to your project. Quota limits how many requests per second and how much capacity you can use.
3. **Makes the service available** to your project's service accounts and IAM policies. Before an API is enabled, even a user with the right IAM role cannot call it.

Enabling an API takes 1-2 minutes and is idempotent -- if it is already enabled, running the enable command again does nothing.

---

## APIs required for this project

### `run.googleapis.com` -- Cloud Run

Cloud Run is the service that runs our Docker containers. It handles:
- Container scheduling and scaling (including scaling to zero)
- HTTPS endpoint management (GCP provides the domain and TLS certificate)
- Request routing and load balancing

Without this API, `gcloud run deploy` will fail with `PERMISSION_DENIED`.

### `artifactregistry.googleapis.com` -- Artifact Registry

Artifact Registry stores our Docker images. When we build a Docker image locally and push it to GCP, it goes here. Cloud Run then pulls from here when starting a container.

Artifact Registry is the official successor to Container Registry (`gcr.io`). It is faster, supports multiple formats (Docker, npm, Maven, Python), and has per-repository IAM policies.

### `iam.googleapis.com` -- Identity and Access Management

IAM is what controls who (or what service account) can do what in your GCP project. Without IAM enabled, you cannot create service accounts or assign roles, which are required for GitHub Actions to authenticate to GCP.

### `cloudresourcemanager.googleapis.com` -- Cloud Resource Manager

This API is required for IAM policy bindings. Specifically, `gcloud projects add-iam-policy-binding` (used in file 05 to grant roles to the service account) calls the Cloud Resource Manager API internally. Even if you already have IAM enabled, policy bindings will fail if this API is disabled.

### What NOT to enable: `containerregistry.googleapis.com`

Container Registry (`gcr.io`) is the older Docker image storage service. It is deprecated as of 2024. Do not enable it. Use Artifact Registry (`artifactregistry.googleapis.com`) instead. The image URI format is different:

- Old (Container Registry): `gcr.io/<PROJECT_ID>/smolsearch:latest`
- New (Artifact Registry): `<REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/smolsearch:latest`

Mixing these up is a common mistake. Every image URI in this guide uses the Artifact Registry format.

---

## Enable all required APIs

You can enable multiple APIs in a single command by listing them space-separated.

```bash
# Enable all 4 required APIs at once
# This command may take 1-2 minutes to complete
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com
```

Breaking down the command:
- `gcloud services enable` is the subcommand to activate APIs
- Each argument is a service name in the format `<service>.googleapis.com`
- The `\` at the end of each line is a line continuation character; the command is still a single command

Expected output:

```
Operation "operations/acf.p2-987654321012-abc123..." finished successfully.
```

If the command finishes without error, all four APIs are enabled.

---

## Verify the APIs are enabled

```bash
# List enabled services, filtered to show only the ones we care about
gcloud services list \
  --enabled \
  --filter="name:run OR name:artifactregistry OR name:iam OR name:cloudresourcemanager"
```

Expected output:

```
NAME                                TITLE
artifactregistry.googleapis.com     Artifact Registry API
cloudresourcemanager.googleapis.com Cloud Resource Manager API
iam.googleapis.com                  Identity and Access Management (IAM) API
run.googleapis.com                  Cloud Run Admin API
```

All four should appear. If any is missing, re-run the enable command for that specific service.

---

## Check a single API's status

To check whether a specific API is enabled:

```bash
# Check Cloud Run specifically
gcloud services list --enabled --filter="name:run.googleapis.com"
```

If it returns an empty list, the API is not enabled. If it shows `run.googleapis.com`, it is enabled.

---

## Propagation time

After enabling an API, it typically takes 1-2 minutes before it is fully active. If you immediately try to use the API and get a `SERVICE_DISABLED` error, wait 2 minutes and try again.

You will see this most often when you run the enable command and then immediately run `gcloud artifacts repositories create` -- if Artifact Registry hasn't finished propagating, the create command may fail. The fix is to wait and retry.

---

## Summary

At the end of this step you have:
- `run.googleapis.com` enabled
- `artifactregistry.googleapis.com` enabled
- `iam.googleapis.com` enabled
- `cloudresourcemanager.googleapis.com` enabled

Run the verification command above to confirm all four before proceeding.

Next: `04_artifact_registry.md` -- create the Docker image repository.
