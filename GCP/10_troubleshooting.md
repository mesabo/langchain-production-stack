# 10 - Troubleshooting Common Errors

This file is a reference. Come here when a command fails. Each section names the exact error message you will see, explains what caused it, and gives the exact commands to fix it.

---

## Error 1: `PERMISSION_DENIED` on `gcloud run deploy`

### What you see

```
ERROR: (gcloud.run.deploy) PERMISSION_DENIED: Permission 'run.services.create' denied on resource
'projects/my-project-123456/locations/us-central1/services/smolsearch'
```

or

```
ERROR: (gcloud.run.deploy) PERMISSION_DENIED: The caller does not have permission
```

### What caused it

The identity running the command (your user account, or the GitHub Actions service account) does not have `roles/run.admin` on the project. This is either because:
1. The role was never granted
2. The role was granted to the wrong identity
3. You are running as the wrong gcloud account

### Fix

**If running manually from your terminal:**

```bash
# Confirm which account gcloud is using
gcloud config get-value account

# Grant run.admin to your user account
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="user:your-email@gmail.com" \
  --role="roles/run.admin"
```

**If running in GitHub Actions:**

```bash
# Grant run.admin to the service account
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:github-deployer@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/run.admin"
```

Also confirm `roles/iam.serviceAccountUser` is granted (required at deploy time):

```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:github-deployer@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

After granting the role, wait 1--2 minutes for IAM propagation and retry.

---

## Error 2: `unauthorized` on `docker push`

### What you see

```
Error response from daemon: unauthorized: Unauthenticated request. Returned 401.
```

or

```
denied: Permission 'artifactregistry.repositories.uploadArtifacts' denied
on resource 'projects/my-project-123456/locations/us-central1/
repositories/slm-apps' (or it may not exist)
```

### What caused it

**For the 401:** Docker does not have credentials configured for Artifact Registry. The credential helper was not set up.

**For the 403:** Docker has credentials but the authenticated identity lacks `roles/artifactregistry.writer`.

### Fix for 401 (missing credential helper)

```bash
# Set up the credential helper for your region
gcloud auth configure-docker <REGION>-docker.pkg.dev
# Example: gcloud auth configure-docker us-central1-docker.pkg.dev

# Verify it was written to Docker config
cat ~/.docker/config.json | grep -A2 "credHelpers"
```

If your gcloud auth token is stale:

```bash
gcloud auth login
gcloud auth configure-docker <REGION>-docker.pkg.dev
```

### Fix for 403 (missing Artifact Registry role)

```bash
# Grant the writer role to the identity that is pushing
# For manual pushes (your user account):
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="user:your-email@gmail.com" \
  --role="roles/artifactregistry.writer"

# For GitHub Actions (service account):
gcloud projects add-iam-policy-binding <PROJECT_ID> \
  --member="serviceAccount:github-deployer@<PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

---

## Error 3: `exec format error` in Cloud Run logs

### What you see

In Cloud Run logs (Logs Explorer):

```
exec /app/main.py: exec format error
```

or

```
Cloud Run error: Container failed to start.
Failed to start and then listen on the port defined by the PORT environment variable.
Logs:
standard_init_linux.go:228: exec user process caused: exec format error
```

### What caused it

You built the Docker image for the wrong CPU architecture. Cloud Run runs on `linux/amd64` (x86-64). If you built on an Apple Silicon Mac (M1/M2/M3) without `--platform linux/amd64`, Docker built an `arm64` image. Cloud Run cannot run it.

### Fix

Rebuild the image with the architecture flag and redeploy:

```bash
# Rebuild with the correct platform
docker build \
  --platform linux/amd64 \
  -f <SERVICE>/deploy/Dockerfile \
  -t <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/<IMAGE_NAME>:<TAG> \
  <SERVICE>/

# Push the corrected image
docker push <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/<IMAGE_NAME>:<TAG>

# Redeploy
gcloud run deploy <SERVICE_NAME> \
  --image <REGION>-docker.pkg.dev/<PROJECT_ID>/slm-apps/<IMAGE_NAME>:<TAG> \
  --region <REGION> \
  --platform managed \
  --quiet
```

Always include `--platform linux/amd64` in every `docker build` command that targets Cloud Run.

---

## Error 4: Container failed to listen on PORT

### What you see

```
Cloud Run error: Container failed to start. Failed to start and then listen on
the port defined by the PORT environment variable. Logs:
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
```

Despite looking like success, Cloud Run reports the container failed to start. Notice the address: `127.0.0.1:8080`.

### What caused it

The uvicorn server is listening on `127.0.0.1` (localhost only) instead of `0.0.0.0` (all interfaces). Cloud Run's health check connects from outside the container on `0.0.0.0:PORT`. It cannot reach `127.0.0.1`.

### Fix

Change the uvicorn start command in the Dockerfile or application entrypoint from:

```
# Wrong: binds to localhost only
CMD ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8080"]
```

to:

```
# Correct: binds to all interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Also important: Cloud Run injects a `PORT` environment variable at runtime. Best practice is to read it:

```
# Best practice: reads PORT from the environment (Cloud Run sets it to 8080 by default)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
```

After fixing the Dockerfile, rebuild the image, push it, and redeploy.

---

## Error 5: `ALREADY_EXISTS` when creating Artifact Registry repository

### What you see

```
ERROR: (gcloud.artifacts.repositories.create) ALREADY_EXISTS: the repository already exists
```

### What caused it

You (or someone else) already created a repository with the same name in the same region.

### What to do

This is not a real error. The repository exists and is ready to use. Skip the create step and verify it is there:

```bash
gcloud artifacts repositories list
```

If the repository is there, proceed to the next step.

---

## Error 6: `400 Bad Request: billing account not found`

### What you see

```
ERROR: (gcloud.run.deploy) FAILED_PRECONDITION: Billing account for project
'my-project-123456' is not found. Billing must be enabled for activation of
service 'run.googleapis.com' to proceed.
```

### What caused it

Billing is not linked to your project. Even if you have a billing account, you must link it to the specific project.

### Fix

```bash
# List your billing accounts
gcloud billing accounts list

# Link billing to the project
# Replace <BILLING_ACCOUNT_ID> with the ID from the list (format: XXXXXX-XXXXXX-XXXXXX)
gcloud billing projects link <PROJECT_ID> \
  --billing-account=<BILLING_ACCOUNT_ID>

# Verify billing is enabled
gcloud billing projects describe <PROJECT_ID>
# Should show: billingEnabled: true
```

---

## Error 7: Cloud Run timeout -- model takes too long to load on cold start

### What you see

```
Cloud Run error: Container failed to start. Failed to start and then listen on
the port defined by the PORT environment variable.
```

Or your health check curl command returns a `504 Gateway Timeout`.

### What caused it

Your container started successfully but took longer than the Cloud Run startup timeout (300 seconds by default) to start listening on the PORT. This happens when:
- A large model is being loaded during app startup (not on first request)
- The Docker image is very large and pull time exceeds the startup timeout

### Fix options

**Option A: Increase the timeout**

```bash
gcloud run deploy <SERVICE_NAME> \
  --timeout 600 \
  --region <REGION> \
  ...other flags...
```

`--timeout` controls the max per-request time, not the startup time. For startup time, see Option B.

**Option B: Load the model lazily (on first request, not at startup)**

In your FastAPI app, do not load the model at module import time. Use a startup event or load on first request:

```python
# Instead of loading at import:
# model = SentenceTransformer("all-MiniLM-L6-v2")  # this runs at startup

# Load lazily:
model = None

@app.on_event("startup")
async def load_model():
    global model
    model = SentenceTransformer("all-MiniLM-L6-v2")
```

**Option C: Keep one instance warm (no cold starts)**

```bash
gcloud run deploy <SERVICE_NAME> \
  --min-instances 1 \
  ...other flags...
```

This keeps one container always running, eliminating cold starts. It costs approximately $5--$10/month per service depending on memory/CPU settings.

---

## Error 8: `ModuleNotFoundError` in Cloud Run logs

### What you see

In Cloud Logging:

```
ModuleNotFoundError: No module named 'sentence_transformers'
```

or

```
ImportError: cannot import name 'FAISS' from 'langchain.vectorstores'
```

### What caused it

The package is not listed in `requirements.txt` (or `setup.py`, `pyproject.toml`). It may be installed in your local conda environment but not in the Docker image.

### Fix

Add the missing package to your service's `requirements.txt`:

```
# 01_smolsearch/requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
sentence-transformers>=2.2.2
faiss-cpu>=1.7.4
# add the missing package here
```

Then rebuild the image and redeploy:

```bash
docker build --platform linux/amd64 \
  -f 01_smolsearch/deploy/Dockerfile \
  -t <FULL_IMAGE_URI>:<TAG> \
  01_smolsearch/
docker push <FULL_IMAGE_URI>:<TAG>
gcloud run deploy smolsearch --image <FULL_IMAGE_URI>:<TAG> --region <REGION> --platform managed --quiet
```

---

## Error 9: GitHub Actions fails at "Authenticate to GCP"

### What you see

In the GitHub Actions log, the step "Authenticate to Google Cloud" fails with:

```
Error: google-github-actions/auth failed with: the GitHub Action
"google-github-actions/auth" encountered an error:
Could not open JSON file: SyntaxError: Unexpected token
```

or

```
Error: google-github-actions/auth failed with: the GitHub Action
"google-github-actions/auth" encountered an error:
The key must be a service account key in JSON format.
```

### What caused it

The `GCP_SA_KEY` secret does not contain the correct JSON. Common mistakes:

1. The JSON was base64-encoded before pasting (some older tutorials say to do this; `google-github-actions/auth@v2` expects raw JSON, not base64)
2. Extra whitespace or newlines were added when pasting
3. Only part of the JSON was pasted (missing the opening `{` or closing `}`)

### Fix

1. Go to your GCP console and create a new service account key:
   ```bash
   gcloud iam service-accounts keys create key.json \
     --iam-account=github-deployer@<PROJECT_ID>.iam.gserviceaccount.com
   ```

2. Open `key.json` in a text editor. Copy the entire contents -- from `{` to `}`.

3. Go to GitHub: Settings > Secrets and variables > Actions > find `GCP_SA_KEY` > Update secret.

4. Paste the raw JSON. Do NOT base64-encode it.

5. Delete `key.json` from your local machine.

To confirm the JSON is valid before pasting, run:

```bash
python3 -c "import json; json.load(open('key.json')); print('valid JSON')"
```

---

## Error 10: `gcloud: command not found` in GitHub Actions

### What you see

```
Run gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
/home/runner/work/_temp/abc123.sh: line 2: gcloud: command not found
Error: Process completed with exit code 127.
```

### What caused it

The workflow is calling `gcloud` before the `google-github-actions/setup-gcloud@v2` step, or that step is missing from the workflow entirely.

### Fix

Make sure the workflow has both steps in this order:

```yaml
steps:
  - name: Authenticate to Google Cloud
    uses: google-github-actions/auth@v2
    with:
      credentials_json: ${{ secrets.GCP_SA_KEY }}
  # auth alone is NOT sufficient — it authenticates but does not install gcloud on PATH

  - name: Set up gcloud CLI
    uses: google-github-actions/setup-gcloud@v2
  # This step installs gcloud on the runner and adds it to PATH

  - name: Configure Docker auth
    run: gcloud auth configure-docker ${{ secrets.GCP_REGION }}-docker.pkg.dev --quiet
  # gcloud is now available because setup-gcloud ran above
```

`google-github-actions/auth@v2` sets up credentials but does not install the CLI. `google-github-actions/setup-gcloud@v2` installs the CLI. Both are required.

---

## General debugging checklist

When something fails and none of the above applies:

1. `gcloud config list` -- confirm you are targeting the right project and account
2. `gcloud services list --enabled --filter="name:run OR name:artifactregistry"` -- confirm APIs are enabled
3. Check Cloud Run logs in Logs Explorer with `severity>=ERROR`
4. Run `gcloud run services describe <SERVICE> --region <REGION>` -- look at the last revision's status
5. Check that the image tag in the deploy command exactly matches the tag you pushed to Artifact Registry
6. Confirm the Artifact Registry repository is in the same region as your Cloud Run service
