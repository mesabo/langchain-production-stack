# 01 - GCP Account and Project Setup

## What is Google Cloud Platform

Google Cloud Platform (GCP) is Google's public cloud offering. It provides compute, storage, networking, and managed services that you rent on demand instead of owning physical hardware. Cloud Run (the service we use to host our FastAPI apps) is one of hundreds of GCP products. You pay only for what you use; when services are idle they consume no resources and incur no charges.

---

## Step 1: Create a Google account

If you already have a Gmail or Google Workspace account you can use it for GCP. You do not need a separate account.

If you need a new account:

1. Go to `https://accounts.google.com/signup`
2. Fill in your name, choose a Gmail address, set a password
3. Complete phone verification

A personal Gmail account works fine for learning and personal projects. For company projects your employer may provision a Google Workspace account for you.

---

## Step 2: Go to the GCP Console

Navigate to `https://console.cloud.google.com` in your browser.

Sign in with your Google account. The first time you visit you will see a terms of service page. Accept it.

You will land on the GCP Console home page. This is the web UI where you can manage all GCP resources. We will use both this UI and the `gcloud` command-line tool (covered in the next file).

---

## Step 3: Create a GCP project

Everything in GCP lives inside a project. A project is a container that groups resources (Cloud Run services, Docker images, service accounts, billing, IAM policies) together. You can have many projects; each is independent.

### Project ID vs project name vs project number

These three identifiers are different things and the difference matters:

- **Project name**: A human-readable label you choose (e.g., "My LangChain Apps"). You can change it later. It is NOT used in API calls.
- **Project ID**: A globally unique string (e.g., `my-langchain-apps-123456`). You choose a prefix; GCP may append a random suffix to ensure uniqueness. Once set, it cannot be changed. This is what you use in every `gcloud` command and every image URI.
- **Project number**: A numeric ID that GCP assigns automatically (e.g., `987654321012`). You need this when granting permissions to the Compute Engine default service account (covered in file 05).

### How to create the project

**Option A: Web console**

1. Click the project selector dropdown at the top of the page (it shows "Select a project" if you have none, or the current project name)
2. Click "New Project" in the top-right of the dialog
3. Enter a project name (e.g., `LangChain Production Stack`)
4. GCP will auto-suggest a project ID based on the name. You can edit it. Suggestion: keep it short, lowercase, no spaces (e.g., `langchain-prod-stack`)
5. Under "Location" you can leave it as "No organization" for personal projects
6. Click "Create"
7. Wait about 30 seconds for the project to be created
8. Select the new project from the dropdown

**Option B: gcloud CLI** (after installing gcloud in file 02)

```bash
# Create a project
# Replace <PROJECT_NAME> with a display name and <PROJECT_ID> with your chosen ID
gcloud projects create <PROJECT_ID> --name="<PROJECT_NAME>"
# Example:
# gcloud projects create langchain-prod-stack-123456 --name="LangChain Production Stack"
```

### Find your project ID

After creation, your project ID appears in the console header dropdown next to the project name. You can also run:

```bash
# List all your projects and their IDs
gcloud projects list
```

The output looks like:

```
PROJECT_ID                  NAME                     PROJECT_NUMBER
langchain-prod-stack-123456 LangChain Production Stack 987654321012
```

The value in the `PROJECT_ID` column is what you use everywhere in this guide.

---

## Step 4: Enable billing

GCP requires a billing account linked to your project before you can use most services, including Cloud Run and Artifact Registry. This is true even when you stay within the free tier.

### Why billing is required even for free usage

GCP needs a payment method on file to:
- Enforce usage quotas and prevent abuse
- Charge you if you exceed free-tier limits
- Verify you are a real user

You will not be charged unless you exceed free-tier limits. The free tier for the services we use is generous:
- Cloud Run: 2 million requests per month free, 360,000 GB-seconds of memory free, 180,000 vCPU-seconds free
- Artifact Registry: 0.5 GB of storage per month free

### Create a billing account

1. In the GCP Console, click the navigation menu (the three horizontal lines, top left)
2. Scroll down and click "Billing"
3. Click "Create account"
4. Enter an account name (e.g., "Personal")
5. Select your country
6. Enter your credit card or debit card details
7. Click "Submit and enable billing"

Google will verify your card with a small temporary charge (usually $1) that is immediately refunded.

### Link the billing account to your project

1. In the Billing section, click "My projects"
2. Find your project in the list
3. Click the three dots on the right side of the row
4. Click "Change billing"
5. Select your billing account
6. Click "Set account"

Alternatively with gcloud (after installing it):

```bash
# List your billing accounts to get the BILLING_ACCOUNT_ID
gcloud billing accounts list

# Link billing to the project
# Replace <BILLING_ACCOUNT_ID> with the value from the list (format: XXXXXX-XXXXXX-XXXXXX)
gcloud billing projects link <PROJECT_ID> --billing-account=<BILLING_ACCOUNT_ID>
```

### Set a budget alert at $1

This protects you from surprise charges if you accidentally leave something running.

1. In the Billing section, click "Budgets and alerts"
2. Click "Create budget"
3. Name it "Learning budget"
4. Under "Scope", select your project
5. Set the budget amount to $1
6. Under "Alert thresholds", keep the default 50%, 90%, 100% thresholds
7. Under "Manage notifications", enter your email address
8. Click "Finish"

Now GCP will email you when you have spent $0.50 and again at $0.90 and $1.00 in any calendar month.

---

## Step 5: Confirm everything is set up correctly

```bash
# Describe the project — shows project ID, number, state, and billing status
# Replace <PROJECT_ID> with your actual project ID
gcloud projects describe <PROJECT_ID>
```

Expected output:

```
createTime: '2024-01-15T10:30:00.000Z'
lifecycleState: ACTIVE
name: LangChain Production Stack
parent:
  id: '0'
  type: organization
projectId: langchain-prod-stack-123456
projectNumber: '987654321012'
```

If `lifecycleState` is `ACTIVE`, the project is ready.

```bash
# Check that billing is enabled
gcloud billing projects describe <PROJECT_ID>
```

Expected output includes:

```
billingEnabled: true
billingAccountName: billingAccounts/XXXXXX-XXXXXX-XXXXXX
```

If `billingEnabled` is `false`, go back and link the billing account.

---

## Summary

At the end of this step you have:
- A GCP account
- A project with a known `PROJECT_ID`
- Billing enabled and linked
- A $1 budget alert configured

Write down your `PROJECT_ID` now. You will use it in every subsequent step.

Next: `02_gcloud_sdk.md` — install the gcloud CLI and authenticate.
