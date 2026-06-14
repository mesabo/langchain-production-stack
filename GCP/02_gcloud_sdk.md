# 02 - Install and Configure the gcloud CLI

## What gcloud is and why you need it

`gcloud` is the official command-line interface for Google Cloud Platform. It lets you create, configure, and manage GCP resources from your terminal instead of clicking through the web console.

You need it because:
- The web console is fine for one-off tasks but bad for reproducibility
- Shell scripts that use `gcloud` can be committed to git and run by anyone
- GitHub Actions workflows call `gcloud` inside the CI runner
- Most GCP error messages in CI logs reference `gcloud` commands; you need to understand them

`gcloud` is part of the Google Cloud SDK, which also includes `gsutil` (Cloud Storage), `bq` (BigQuery), and other tools. We will only use `gcloud` and the Docker credential helper it provides.

---

## Install on Linux

There are three installation methods on Linux. Use Method A (apt) if you are on Debian or Ubuntu. Use Method C (curl) if you are on any other Linux distribution or want to install without root.

### Method A: apt (Debian / Ubuntu)

This installs gcloud as a system package and receives updates through `apt upgrade`.

```bash
# Step 1: Add Google's package signing key
# curl downloads the key; gpg decodes it from binary; tee writes it to a file
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | sudo gpg --dearmor \
  | sudo tee /usr/share/keyrings/cloud.google.gpg > /dev/null

# Step 2: Add the Cloud SDK package repository
# lsb_release -c -s prints your Ubuntu/Debian codename (e.g., "jammy" for 22.04)
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] \
  https://packages.cloud.google.com/apt cloud-sdk main" \
  | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list

# Step 3: Update package list and install
sudo apt-get update && sudo apt-get install -y google-cloud-cli

# Verify the install
gcloud --version
```

Expected output:

```
Google Cloud SDK 460.0.0
bq 2.1.3
core 2024.01.15
gcloud-crc32c 1.0.0
gsutil 5.27
```

The exact version numbers will differ; that is fine.

### Method B: Snap (Ubuntu with snapd)

```bash
sudo snap install google-cloud-sdk --classic
gcloud --version
```

### Method C: Direct install (curl, any Linux)

This installs gcloud in your home directory without root access.

```bash
# Download the installer
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz

# Extract
tar -xzf google-cloud-cli-linux-x86_64.tar.gz

# Run the install script
# The script adds gcloud to your PATH by modifying .bashrc or .zshrc
./google-cloud-sdk/install.sh

# Restart your shell or source the changes
source ~/.bashrc   # or source ~/.zshrc if you use zsh

# Verify
gcloud --version
```

---

## Install on macOS

```bash
# Using Homebrew (recommended)
brew install --cask google-cloud-sdk

# Add gcloud to PATH — Homebrew will print the exact lines to add to .zshrc
# Typically:
source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"

gcloud --version
```

---

## Install on Windows

Download the installer from:
`https://cloud.google.com/sdk/docs/install#windows`

Run the `.exe` installer. It adds gcloud to your PATH and installs Cloud Shell tools. The installer also offers to install Python if needed.

After installation, use `Google Cloud SDK Shell` or PowerShell to run `gcloud` commands.

---

## Initialize gcloud

`gcloud init` is a setup wizard that authenticates you and sets your default project and region. Run it once after installing.

```bash
gcloud init
```

The wizard walks through these prompts:

**1. "Pick configuration to use"**

On a fresh install there is only one option: `[1] Re-initialize this configuration [default]`. Press 1 and Enter.

**2. "Choose the account you would like to use"**

Select your Google account or choose `[1] Log in with a new account`. A browser window will open asking you to sign in to Google and grant the SDK access. Complete the OAuth flow in the browser. Return to the terminal.

**3. "Pick cloud project to use"**

gcloud will list your projects. Type the number next to your project or enter your project ID directly.

**4. "Do you want to configure a default Compute Region and Zone?"**

Enter `Y`. Then select a region. For most learners `us-central1` is a good default: it has the widest service availability and low latency for North America.

After `gcloud init` completes you will see:

```
Your Google Cloud SDK is configured and ready to use!

* Commands that require authentication will use mesabo18@gmail.com by default
* Commands will reference project `langchain-prod-stack-123456` by default
* Run `gcloud help config` to learn how to change individual settings
```

---

## Authentication: two separate credentials

`gcloud` maintains two distinct credentials. Understanding the difference prevents a common class of bugs.

### `gcloud auth login`

This credential is used when you run `gcloud` commands from the terminal (e.g., `gcloud run deploy`, `gcloud iam service-accounts list`). It is your human identity.

```bash
# Run this when you need to re-authenticate your terminal session
# Opens a browser for the OAuth flow
gcloud auth login
```

### `gcloud auth application-default login`

This credential is used by code running on your machine that calls GCP APIs directly — for example, a Python script that uses the `google-cloud-run` library, or a LangChain application that calls Vertex AI. It is separate from the `gcloud auth login` credential.

```bash
# Run this when your application code (Python, etc.) needs to call GCP APIs locally
# Also opens a browser for OAuth
gcloud auth application-default login
```

**When to use which:**
- Running `gcloud` commands in the terminal: `gcloud auth login`
- Running Python code locally that calls GCP (Vertex AI, Cloud Storage, etc.): `gcloud auth application-default login`
- In GitHub Actions or Cloud Run: neither — use a service account key (file 05)

For this guide, `gcloud auth login` is sufficient. Run `gcloud auth application-default login` only if you write Python code that calls GCP APIs directly.

---

## Configure your defaults

Set the default project and region so you do not have to specify `--project` and `--region` on every command.

```bash
# Set the default project
# Replace <PROJECT_ID> with your actual project ID
gcloud config set project <PROJECT_ID>

# Set the default region
# us-central1 is a good general-purpose choice; change to your preferred region
gcloud config set compute/region <REGION>

# Optionally set a default zone (needed for Compute Engine, not for Cloud Run)
gcloud config set compute/zone <REGION>-a
# Example: us-central1-a
```

---

## Verify your configuration

```bash
# Show all active configuration values
gcloud config list
```

Expected output:

```
[compute]
region = us-central1
zone = us-central1-a
[core]
account = mesabo18@gmail.com
project = langchain-prod-stack-123456

Your active configuration is: [default]
```

Confirm that `account` and `project` match what you expect.

---

## Keep the CLI updated

Google releases new versions of the Cloud SDK frequently. Keep it current:

```bash
# Update all installed components
gcloud components update
```

If you installed via apt, use `sudo apt-get upgrade google-cloud-cli` instead, since apt manages the package.

---

## Multiple gcloud configurations

If you work with multiple GCP projects (e.g., personal and work), you can create named configurations instead of changing the default project back and forth.

```bash
# List all configurations
gcloud config configurations list
```

Output:

```
NAME        IS_ACTIVE  ACCOUNT                  PROJECT                       COMPUTE_DEFAULT_ZONE  COMPUTE_DEFAULT_REGION
default     True       mesabo18@gmail.com        langchain-prod-stack-123456   us-central1-a         us-central1
work        False      me@work.com               my-work-project               us-east1-b            us-east1
```

```bash
# Create a new configuration named "work"
gcloud config configurations create work

# Switch to it
gcloud config configurations activate work

# Switch back to default
gcloud config configurations activate default
```

A common mistake when something "unexpectedly" fails is that the wrong configuration is active. Always run `gcloud config list` at the start of a debugging session to confirm you are targeting the right project.

---

## Summary

At the end of this step you have:
- `gcloud` installed and on your PATH
- Authenticated with your Google account
- Default project and region configured

Run `gcloud config list` to verify before moving to the next step.

Next: `03_enable_apis.md` — enable the GCP APIs required for this project.
