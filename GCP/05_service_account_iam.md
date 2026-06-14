# 05 - Service Accounts and IAM Roles

## What a service account is

In GCP, identities come in two types:

- **User accounts**: human identities tied to a Google account (e.g., `mesabo18@gmail.com`). Authenticated through a browser.
- **Service accounts**: machine identities for non-human actors (e.g., `github-deployer@my-project.iam.gserviceaccount.com`). Authenticated through a JSON key file or Workload Identity.

GitHub Actions workflows run inside GitHub's compute infrastructure. They are not humans and cannot open a browser. To call GCP APIs (push Docker images, deploy to Cloud Run), the workflow needs a machine identity -- a service account -- and a credential for that identity -- a JSON key file that we store as a GitHub secret.

A service account is identified by its email address, which always ends in `.iam.gserviceaccount.com`.

---

## The principle of least privilege

Always grant a service account the minimum set of permissions it needs. If GitHub Actions only needs to push images and deploy services, do not give it project owner or editor. Reasons:

1. If the service account key is stolen, the attacker can only do what the SA is permitted to do
2. Auditing is easier when each SA has a narrow purpose
3. It is the standard practice in any security-conscious organization and will be asked about in interviews

For our deployer service account we need exactly three roles.

---

## Step 1: Set your variables

Before running any command in this file, set these variables in your terminal. The commands below use them.

```bash
# This project's values — already set up in .env at the repo root
PROJECT_ID="langchain-dev-stack"
PROJECT_NUMBER="911301655327"

# The service account name (the part before @)
SA_NAME="github-deployer"

# The full email of the service account (constructed from the above)
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Confirm the values look right
echo "Project: $PROJECT_ID"
echo "SA email: $SA_EMAIL"
```

---

## Step 2: Create the service account

```bash
# Create the service account
# --display-name   : a human-readable label shown in the console
# --description    : a note explaining what this SA is used for
gcloud iam service-accounts create ${SA_NAME} \
  --display-name="GitHub Actions Deployer" \
  --description="Used by GitHub Actions to push Docker images and deploy to Cloud Run"
```

Expected output:

```
Created service account [github-deployer].
```

If you see `ALREADY_EXISTS`, the service account already exists. That is fine -- proceed to the next step.

---

## Step 3: Grant the three required roles

Each role grants a specific set of permissions. We grant them one at a time so each line is easy to audit.

### Role 1: `roles/artifactregistry.writer` -- Push Docker images

This role allows the service account to push (upload) Docker images to Artifact Registry. Without it, `docker push` in GitHub Actions fails with `PERMISSION_DENIED`.

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"
```

### Role 2: `roles/run.admin` -- Create and update Cloud Run services

This role allows the service account to create new Cloud Run services, update existing ones, and manage traffic splits. It is the permission required for `gcloud run deploy`.

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.admin"
```

### Role 3: `roles/iam.serviceAccountUser` -- Act as a service account

When `gcloud run deploy` creates a new Cloud Run revision, it needs to associate a runtime service account with that revision. The deploy operation requires the deploying identity (our `github-deployer` SA) to have permission to "act as" or "impersonate" the service account used by Cloud Run at runtime.

Without this role, `gcloud run deploy` fails with a message like: "The caller does not have permission to act as the service account."

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser"
```

---

## Step 4: Grant Cloud Run permission to pull images from Artifact Registry

When Cloud Run starts a container, it pulls the Docker image from Artifact Registry. The pull happens using the Compute Engine default service account, not the `github-deployer` SA. You must grant this account read access to Artifact Registry.

```bash
# Project number is already known: 911301655327
# To look it up yourself: gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)"
PROJECT_NUMBER="911301655327"

echo "Project number: $PROJECT_NUMBER"
# The Compute Engine default SA email is always <project-number>-compute@developer.gserviceaccount.com
# Example: 987654321012-compute@developer.gserviceaccount.com

# Grant Artifact Registry reader access to the Compute Engine default SA
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

Without this step, Cloud Run starts the container but fails to pull the image with a `403 Forbidden` error in the Cloud Run logs.

---

## Step 5: Export the service account key to a JSON file

GitHub Actions needs a credential to authenticate as `github-deployer`. We export a JSON key file and paste its contents into a GitHub secret.

```bash
# Export the key
# The output file is named key.json; do NOT rename it to something more descriptive
# because you will be instructed to delete it immediately after use
gcloud iam service-accounts keys create key.json \
  --iam-account=${SA_EMAIL}
```

Expected output:

```
created key [abc123...] of type [json] for [github-deployer@my-project.iam.gserviceaccount.com] as [key.json]
```

The file `key.json` now exists in your current directory.

### SECURITY WARNING

`key.json` contains the private key for `github-deployer`. Anyone with this file can call GCP APIs as that service account and:
- Push malicious Docker images to your Artifact Registry
- Deploy arbitrary containers to your Cloud Run services

Handle this file like a password:

1. **Never commit it to git.** Add it to `.gitignore` immediately:
   ```bash
   echo "key.json" >> .gitignore
   ```
2. **Copy its contents now** (open it, select all, copy). You will paste it into GitHub Secrets in file 08.
3. **Delete it after pasting into GitHub Secrets:**
   ```bash
   rm key.json
   ```
4. If you accidentally commit it, rotate the key immediately:
   ```bash
   # List all keys for the SA
   gcloud iam service-accounts keys list --iam-account=${SA_EMAIL}
   # Delete the compromised key (use the key ID from the list)
   gcloud iam service-accounts keys delete <KEY_ID> --iam-account=${SA_EMAIL}
   # Create a new one
   gcloud iam service-accounts keys create key.json --iam-account=${SA_EMAIL}
   ```

---

## Step 6: Verify the service account and its roles

```bash
# List all service accounts in the project
gcloud iam service-accounts list
```

You should see `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com` in the output.

```bash
# Show all IAM policy bindings for the project, filtered to bindings that mention github-deployer
# --flatten="bindings[].members"  : expands the nested bindings structure so each member is its own row
# --filter                        : keeps only rows where the member contains our SA name
gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:github-deployer" \
  --format="table(bindings.role)"
```

Expected output:

```
ROLE
roles/artifactregistry.writer
roles/iam.serviceAccountUser
roles/run.admin
```

All three roles should appear. If any is missing, re-run the corresponding `add-iam-policy-binding` command from Step 3.

---

## Summary

At the end of this step you have:
- Service account `github-deployer@<PROJECT_ID>.iam.gserviceaccount.com` created
- Three roles granted: `artifactregistry.writer`, `run.admin`, `iam.serviceAccountUser`
- Compute Engine default SA granted `artifactregistry.reader` so Cloud Run can pull images
- `key.json` exported (copy its contents and then delete the file)

Next: `06_build_and_push.md` -- build Docker images and push them to Artifact Registry.
