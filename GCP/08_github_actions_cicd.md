# 08 - GitHub Actions CI/CD

## What CI/CD means

Continuous Integration (CI) means automatically running tests every time code is pushed to the repository. Continuous Deployment (CD) means automatically deploying the code to production every time tests pass on the main branch.

Without CI/CD, deploying means: developer pushes code, opens a terminal, runs build commands, runs push commands, runs deploy commands. This is slow, error-prone (typos, wrong branch, forgot to pull latest), and inconsistent across team members.

With CI/CD: developer pushes code to `main`, GitHub automatically runs tests, builds the Docker image, pushes it to Artifact Registry, and deploys it to Cloud Run. The developer sees the result in the GitHub Actions tab. The whole process takes about 3--5 minutes.

In a team setting, CI/CD is not optional. It is the standard practice at every tech company.

---

## The two-job model

Our GitHub Actions workflows use a two-job structure:

```
push to main
     |
     v
  [test job]
  - install deps
  - run pytest
  - if tests fail: workflow stops here; deploy never runs
     |
     | (only if test passes)
     v
  [build-and-deploy job]
  - authenticate to GCP
  - docker build + push
  - gcloud run deploy
```

The `needs: test` directive in the `build-and-deploy` job makes it wait for `test` to succeed. This prevents deploying broken code.

---

## Step 1: Add GitHub repository secrets

GitHub secrets are encrypted variables that are available to GitHub Actions workflows but never printed in logs and never accessible outside the workflow.

Navigate to your repository on GitHub:
`https://github.com/mesabo/langchain-production-stack`

Go to: **Settings** (tab at the top) > **Secrets and variables** > **Actions** > **New repository secret**

Add these three secrets one at a time:

### Secret 1: `GCP_PROJECT_ID`

- Name: `GCP_PROJECT_ID`
- Value: your GCP project ID (e.g., `my-langchain-proj-123456`)

This is the plain text project ID, not a JSON object.

### Secret 2: `GCP_REGION`

- Name: `GCP_REGION`
- Value: your GCP region (e.g., `us-central1`)

### Secret 3: `GCP_SA_KEY`

- Name: `GCP_SA_KEY`
- Value: the full contents of `key.json`

Open `key.json` in a text editor. Select everything from the opening `{` to the closing `}`. Copy the entire JSON object. Paste it as the secret value.

The JSON looks like:

```json
{
  "type": "service_account",
  "project_id": "my-project-123456",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "github-deployer@my-project-123456.iam.gserviceaccount.com",
  "client_id": "123456789012345678901",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  ...
}
```

Paste the entire thing, including the outer `{` and `}`. Do not base64-encode it. The `google-github-actions/auth@v2` action expects raw JSON.

After adding all three secrets, go to Settings > Secrets and variables > Actions and confirm you see:
- `GCP_PROJECT_ID`
- `GCP_REGION`
- `GCP_SA_KEY`

Now delete `key.json` from your local machine:

```bash
rm key.json
```

---

## Step 2: The workflow file (line by line)

Our repository has one workflow file per service. Here is the workflow for SmolSearch, annotated in full. The other three workflows follow the same pattern.

File path: `.github/workflows/deploy-01-smolsearch.yml`

```yaml
name: Deploy SmolSearch

# Triggers: when to run this workflow
on:
  push:
    branches:
      - main            # Only run on pushes to main, not feature branches
    paths:
      - "01_smolsearch/**"   # Only run when files inside 01_smolsearch/ change
      - ".github/workflows/deploy-01-smolsearch.yml"  # Also run if the workflow itself changes

# Permissions: what the GITHUB_TOKEN can do in this workflow
# id-token: write is required for OIDC / Workload Identity Federation
# contents: read allows the checkout action to read the repo
permissions:
  id-token: write
  contents: read

jobs:

  # Job 1: Run tests before building or deploying anything
  test:
    runs-on: ubuntu-latest   # Use GitHub's hosted Ubuntu runner
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        # Downloads the repository code into the runner's workspace

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
        # Installs Python 3.11 on the runner

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install -r 01_smolsearch/requirements.txt
          pip install pytest httpx
        # Installs the service dependencies plus pytest and httpx (for FastAPI test client)

      - name: Run tests
        run: |
          cd 01_smolsearch
          pytest tests/ -v
        # Runs all tests in 01_smolsearch/tests/
        # If any test fails, this step fails and the job fails
        # Because build-and-deploy has "needs: test", the deploy job is cancelled

  # Job 2: Build Docker image and deploy to Cloud Run
  # Only runs if the test job succeeds
  build-and-deploy:
    runs-on: ubuntu-latest
    needs: test          # This line means: wait for "test" to finish and succeed

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
        # This action reads the JSON from the secret, authenticates as the service account,
        # and writes a temporary credential file to the runner's filesystem.
        # All subsequent gcloud and docker commands run as github-deployer@<project>.iam.gserviceaccount.com

      - name: Set up gcloud CLI
        uses: google-github-actions/setup-gcloud@v2
        # Installs the gcloud CLI on the runner.
        # The auth step above already set the credentials; this step just adds gcloud to PATH.

      - name: Configure Docker to authenticate to Artifact Registry
        run: gcloud auth configure-docker ${{ secrets.GCP_REGION }}-docker.pkg.dev --quiet
        # Writes the gcloud credential helper to the runner's ~/.docker/config.json
        # Required so that "docker push" in the next step can authenticate

      - name: Build Docker image
        run: |
          docker build \
            --platform linux/amd64 \
            -f 01_smolsearch/deploy/Dockerfile \
            -t ${{ secrets.GCP_REGION }}-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/slm-apps/smolsearch:${{ github.sha }} \
            01_smolsearch/
        # ${{ github.sha }} is the full 40-character git commit SHA
        # Using the full SHA (not short) avoids the tiny probability of collision
        # --platform linux/amd64 is essential; GitHub Actions runners are x86-64 but let's be explicit

      - name: Push Docker image
        run: |
          docker push \
            ${{ secrets.GCP_REGION }}-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/slm-apps/smolsearch:${{ github.sha }}

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy smolsearch \
            --image ${{ secrets.GCP_REGION }}-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/slm-apps/smolsearch:${{ github.sha }} \
            --region ${{ secrets.GCP_REGION }} \
            --platform managed \
            --allow-unauthenticated \
            --memory 2Gi \
            --cpu 2 \
            --concurrency 10 \
            --set-env-vars "HF_HOME=/tmp/.cache/huggingface" \
            --timeout 300 \
            --quiet
        # Same flags as the manual deploy in file 07
        # The image tag matches exactly what was pushed in the previous step
```

---

## How secrets are substituted

`${{ secrets.GCP_PROJECT_ID }}` is GitHub's expression syntax for reading a secret. At runtime, GitHub replaces this expression with the secret value. The actual value is never printed in the workflow logs -- GitHub masks it with `***`.

This is why storing credentials in secrets (not hardcoded in the YAML) is mandatory. Hardcoding a project ID is not itself dangerous, but it is bad practice and you would never hardcode a service account key.

---

## Step 3: Trigger the workflow

```bash
# Make a small change to a smolsearch file and push to main
echo "# deployment test" >> 01_smolsearch/README.md
git add 01_smolsearch/README.md
git commit -m "test ci deploy trigger"
git push origin main
```

The `paths` filter in the workflow means this only triggers `deploy-01-smolsearch.yml`. It does not trigger the workflows for the other three services.

---

## Step 4: Monitor the workflow

1. Go to `https://github.com/mesabo/langchain-production-stack`
2. Click the **Actions** tab
3. You will see "Deploy SmolSearch" running (yellow dot = in progress, green check = success, red X = failed)
4. Click the workflow run to see the two jobs: `test` and `build-and-deploy`
5. Click a job to see its steps
6. Click any step to see its log output

The entire workflow takes about 3--5 minutes. The `build` step is the slowest because Docker builds a 1--2 GB image on the runner.

---

## Re-run a failed workflow

If a workflow fails, you can re-run it from the GitHub UI without pushing new code:

1. Click the failed workflow run in the Actions tab
2. Click "Re-run all jobs" in the top right
3. Confirm

This is useful when a failure was due to a transient issue (network timeout during Docker push, GCP API briefly unavailable).

---

## `needs: test` prevents broken deploys

If `pytest` finds a failing test in the `test` job, the `build-and-deploy` job never starts. The workflow fails with a clear indication of which test failed. The broken code is never deployed to Cloud Run.

This is the core value of the two-job model. Without it, a deploy could push broken code to production every time.

---

## The `paths` filter explained

```yaml
paths:
  - "01_smolsearch/**"
  - ".github/workflows/deploy-01-smolsearch.yml"
```

`"01_smolsearch/**"` means: any file under the `01_smolsearch/` directory, at any depth. So `01_smolsearch/src/main.py`, `01_smolsearch/requirements.txt`, and `01_smolsearch/deploy/Dockerfile` all match.

Without this filter, every push to `main` (including changes to `02_ragify/`) would trigger all four deploy workflows. With it, only changes to the relevant service trigger its workflow. This is faster, cheaper (GitHub Actions minutes have limits on free tier), and easier to read in the Actions tab.

---

## Summary

At the end of this step you have:
- Three GitHub repository secrets configured: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_SA_KEY`
- GitHub Actions workflow deploying on every push to `main` that changes a service directory
- `key.json` deleted from your local machine

Next: `09_verify_and_monitor.md` -- verify the deployed services and read their logs.
