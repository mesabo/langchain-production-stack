# 04 - Artifact Registry: Docker Image Storage

## What Artifact Registry is

Artifact Registry is GCP's managed service for storing and distributing software artifacts. For our purposes it is a Docker image registry -- a place to push Docker images from our local machine (or from GitHub Actions) and from which Cloud Run pulls images when starting containers.

It is the successor to Google Container Registry (`gcr.io`). Key differences:
- Artifact Registry is regional (you choose which GCP region stores the images)
- It supports multiple artifact formats beyond Docker: npm packages, Python packages, Maven jars
- IAM policies can be set per repository (not just per project)
- The image URI format uses `pkg.dev` instead of `gcr.io`

Think of it like Docker Hub, but private, hosted by Google, and tightly integrated with Cloud Run IAM.

---

## Image URI format

Before creating the repository, understand the image URI format. Every Docker image in Artifact Registry has a URI of this form:

```
REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME:TAG
```

Breaking this down character by character for a concrete example:

```
us-central1-docker.pkg.dev/my-project-123456/slm-apps/smolsearch:abc123def
|___________|              |________________| |______| |_________| |_______|
     |                           |               |          |          |
  GCP region                 project ID       repo name  image name  git SHA tag
  where images               (your project    (we create  (matches    (for traceability;
  are stored                  ID here)        "slm-apps") service     could also be "latest")
                                              this step)  name)
```

- `us-central1` -- the region you chose. Images are physically stored here. Cloud Run services in the same region pull faster.
- `docker.pkg.dev` -- the domain for Artifact Registry Docker repositories. Do not confuse with `gcr.io` (old Container Registry).
- `my-project-123456` -- your GCP project ID.
- `slm-apps` -- the repository name you create in this step. One repository can hold many images.
- `smolsearch` -- the image name. We use one per service.
- `abc123def` -- the tag. Using a git SHA here means every image is uniquely traceable to the exact commit that built it.

Memorize this pattern. You will type it in every `docker build`, `docker push`, and `gcloud run deploy` command.

---

## Create the Artifact Registry repository

We create one repository called `slm-apps` that will hold Docker images for all four services.

```bash
# Create the repository
# --repository-format=docker    : specifies this is a Docker image registry
# --location=<REGION>           : the GCP region where images are stored; use your chosen region
# --description                 : a human-readable label; optional but useful
# Replace <REGION> with your region (e.g., us-central1)
gcloud artifacts repositories create slm-apps \
  --repository-format=docker \
  --location=<REGION> \
  --description="LangChain production stack Docker images"
```

Expected output:

```
Create request issued for: [slm-apps]
Waiting for operation [projects/my-project-123456/locations/us-central1/operations/abc123] to complete...done.
Created repository [slm-apps].
```

If you see `ALREADY_EXISTS`, the repository already exists. That is fine -- skip to the verify step.

---

## Verify the repository was created

```bash
# List all Artifact Registry repositories in the project
gcloud artifacts repositories list
```

Expected output:

```
REPOSITORY  FORMAT  MODE                 DESCRIPTION                                      LOCATION    LABELS  ENCRYPTION  CREATE_TIME          UPDATE_TIME
slm-apps    DOCKER  STANDARD_REPOSITORY  LangChain production stack Docker images         us-central1         Google-managed  2024-01-15T10:45:00  2024-01-15T10:45:00
```

---

## Configure Docker to authenticate to Artifact Registry

Before you can push or pull images, Docker needs credentials to authenticate to Artifact Registry. The `gcloud` tool can configure this automatically.

```bash
# Write credential helpers to ~/.docker/config.json
# Replace <REGION> with your region
gcloud auth configure-docker <REGION>-docker.pkg.dev
```

Example with `us-central1`:

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

What this command does: it adds an entry to `~/.docker/config.json` that tells Docker to call `gcloud auth print-access-token` whenever it needs to authenticate to `<REGION>-docker.pkg.dev`. The token is short-lived (1 hour) and is refreshed automatically.

Expected output:

```
Adding credentials for: us-central1-docker.pkg.dev
After update, the following will be written to your Docker config file
 located at [/home/yourname/.docker/config.json]:
 {
   "credHelpers": {
     "us-central1-docker.pkg.dev": "gcloud"
   }
 }

Do you want to continue (Y/n)?
```

Press Y and Enter.

To verify the Docker config was updated:

```bash
# Show the Docker credential helper configuration
cat ~/.docker/config.json
```

You should see `"us-central1-docker.pkg.dev": "gcloud"` (or your region) in the `credHelpers` section.

---

## List images after pushing

After you push images in file 06, you can list them:

```bash
# List all images in the slm-apps repository
# Replace <REGION> and <PROJECT_ID> with your values
gcloud artifacts docker images list <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps
```

Example output:

```
IMAGE                                                                   DIGEST         TAGS     CREATE_TIME          UPDATE_TIME
us-central1-docker.pkg.dev/my-project-123456/slm-apps/smolsearch       sha256:abc123  abc123de 2024-01-15T11:00:00  2024-01-15T11:00:00
us-central1-docker.pkg.dev/my-project-123456/slm-apps/ragify            sha256:def456  def456gh 2024-01-15T11:05:00  2024-01-15T11:05:00
```

---

## Delete old image tags to control storage cost

Artifact Registry charges for storage (after the 0.5 GB free tier). Each Docker image layer is stored independently; pushing new images does not automatically delete old ones.

To delete a specific tag:

```bash
# Delete a specific image tag
# Replace the values with your region, project, and image details
gcloud artifacts docker tags delete \
  <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/smolsearch:old-tag-name
```

To delete an entire image (all tags and the underlying layers):

```bash
# Delete an image by digest
# First get the digest from the list command above
gcloud artifacts docker images delete \
  <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/smolsearch@sha256:<DIGEST> \
  --delete-tags \
  --quiet
```

The `--delete-tags` flag removes all tags pointing to this digest before deleting. Without it the command fails if any tags reference the image. The `--quiet` flag skips the confirmation prompt.

For a learning project you will rarely need this, but it is good practice to clean up after yourself when running experiments.

---

## Summary

At the end of this step you have:
- An Artifact Registry repository named `slm-apps` in your chosen region
- Docker configured to authenticate to Artifact Registry using your gcloud credentials

The repository is empty at this point. Images will be pushed in file 06.

Note the full image URI pattern for your project:
```
<REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/<IMAGE_NAME>:<TAG>
```

Write this down with your actual values filled in. You will use it constantly.

Next: `05_service_account_iam.md` -- create the service account and grant IAM roles for GitHub Actions.
