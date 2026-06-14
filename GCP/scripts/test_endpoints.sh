#!/usr/bin/env bash
# test_endpoints.sh
#
# Smoke tests for all 4 deployed Cloud Run services.
# Sends curl requests to each endpoint and reports PASS/FAIL.
#
# Run this after deploy_all.sh to confirm all services are healthy.
#
# Usage:
#   chmod +x scripts/test_endpoints.sh
#   ./scripts/test_endpoints.sh
#
# Prerequisites:
#   - curl installed (it is on all modern Linux and macOS systems)
#   - All 4 services deployed and reachable
#   - Set the 4 URL variables below before running

set -euo pipefail

# ---------------------------------------------------------------------------
# CONFIGURATION -- set service URLs after deploying
# ---------------------------------------------------------------------------

SMOLSEARCH_URL="<YOUR_SMOLSEARCH_URL>"
# What to put here: the Cloud Run URL for the smolsearch service.
# Get it with: gcloud run services describe smolsearch --region <REGION> --format "value(status.url)"
# Example: https://smolsearch-abc123xyz-uc.a.run.app

RAGIFY_URL="<YOUR_RAGIFY_URL>"
# What to put here: the Cloud Run URL for the ragify service.
# Get it with: gcloud run services describe ragify --region <REGION> --format "value(status.url)"
# Example: https://ragify-abc123xyz-uc.a.run.app

AGENTFLOW_URL="<YOUR_AGENTFLOW_URL>"
# What to put here: the Cloud Run URL for the agentflow service.
# Get it with: gcloud run services describe agentflow --region <REGION> --format "value(status.url)"
# Example: https://agentflow-abc123xyz-uc.a.run.app

LLMOPS_URL="<YOUR_LLMOPS_URL>"
# What to put here: the Cloud Run URL for the llmops-baseline service.
# Get it with: gcloud run services describe llmops-baseline --region <REGION> --format "value(status.url)"
# Example: https://llmops-baseline-abc123xyz-uc.a.run.app

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Test tracking
# ---------------------------------------------------------------------------

PASS=0
FAIL=0

pass() { echo -e "${GREEN}PASS${NC}  $*"; ((PASS++)); }
fail() { echo -e "${RED}FAIL${NC}  $*"; ((FAIL++)); }
info() { echo -e "${CYAN}----${NC}  $*"; }

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------

if [[ "${SMOLSEARCH_URL}" == "<YOUR_SMOLSEARCH_URL>" ]] || \
   [[ "${RAGIFY_URL}"    == "<YOUR_RAGIFY_URL>"    ]] || \
   [[ "${AGENTFLOW_URL}" == "<YOUR_AGENTFLOW_URL>" ]] || \
   [[ "${LLMOPS_URL}"    == "<YOUR_LLMOPS_URL>"    ]]; then
    echo -e "${YELLOW}[WARN]${NC}  One or more service URLs are still set to placeholder values."
    echo "       Edit the top of this script to set the actual URLs."
    echo "       Get URLs with: gcloud run services describe <NAME> --region <REGION> --format 'value(status.url)'"
    exit 1
fi

# ---------------------------------------------------------------------------
# Helper function: assert HTTP status code equals expected value
# assert_status TEST_NAME URL METHOD DATA EXPECTED_STATUS
# ---------------------------------------------------------------------------

assert_status() {
    local test_name="$1"
    local url="$2"
    local method="$3"         # GET or POST
    local data="$4"           # JSON body for POST requests; empty string for GET
    local expected_status="$5"

    local http_status
    local response_body

    if [[ "${method}" == "GET" ]]; then
        # -s: silent (no progress output)
        # -o /tmp/resp: write response body to a temp file
        # -w "%{http_code}": print the HTTP status code to stdout
        http_status=$(curl -s -o /tmp/test_resp.json \
            -w "%{http_code}" \
            --max-time 90 \
            "${url}")
    else
        # -X POST: use POST method
        # -H: set request header
        # -d: request body
        http_status=$(curl -s -o /tmp/test_resp.json \
            -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "${data}" \
            --max-time 90 \
            "${url}")
    fi

    response_body=$(cat /tmp/test_resp.json 2>/dev/null || echo "(no response body)")

    if [[ "${http_status}" == "${expected_status}" ]]; then
        pass "[HTTP ${http_status}] ${test_name}"
    else
        fail "[HTTP ${http_status}, expected ${expected_status}] ${test_name}"
        echo "         Response body: ${response_body}"
    fi
}

# ---------------------------------------------------------------------------
# Helper function: assert response body contains a JSON key
# assert_contains TEST_NAME URL METHOD DATA KEY
# ---------------------------------------------------------------------------

assert_contains() {
    local test_name="$1"
    local url="$2"
    local method="$3"
    local data="$4"
    local expected_key="$5"

    local http_status
    local response_body

    if [[ "${method}" == "GET" ]]; then
        http_status=$(curl -s -o /tmp/test_resp.json \
            -w "%{http_code}" \
            --max-time 90 \
            "${url}")
    else
        http_status=$(curl -s -o /tmp/test_resp.json \
            -w "%{http_code}" \
            -X POST \
            -H "Content-Type: application/json" \
            -d "${data}" \
            --max-time 90 \
            "${url}")
    fi

    response_body=$(cat /tmp/test_resp.json 2>/dev/null || echo "")

    if [[ "${http_status}" =~ ^2 ]] && echo "${response_body}" | grep -q "\"${expected_key}\""; then
        pass "[HTTP ${http_status}, has '${expected_key}'] ${test_name}"
    else
        fail "[HTTP ${http_status}, missing '${expected_key}'] ${test_name}"
        echo "         Response body: ${response_body}"
    fi
}

# ---------------------------------------------------------------------------
# Tests start here
# ---------------------------------------------------------------------------

echo ""
echo "========================================================================"
echo "  langchain-production-stack endpoint smoke tests"
echo "========================================================================"
echo ""
echo "Note: The first request to each service may be slow (cold start, up to 60s)."
echo "      Subsequent requests will be fast."
echo ""

# ---------------------------------------------------------------------------
# SmolSearch
# ---------------------------------------------------------------------------

info "SmolSearch: ${SMOLSEARCH_URL}"

assert_status \
    "SmolSearch /health" \
    "${SMOLSEARCH_URL}/health" \
    "GET" "" "200"
# Expected response: {"status": "ok"}

assert_contains \
    "SmolSearch /index (index 3 documents)" \
    "${SMOLSEARCH_URL}/index" \
    "POST" \
    '{"documents": ["LangChain is a framework for building LLM-powered applications.", "FAISS enables fast approximate nearest-neighbor search over dense vectors.", "Sentence transformers encode text into fixed-size embedding vectors."]}' \
    "indexed"
# Expected response: {"indexed": 3}

assert_contains \
    "SmolSearch /search (semantic query)" \
    "${SMOLSEARCH_URL}/search" \
    "POST" \
    '{"query": "What is LangChain?", "k": 2}' \
    "results"
# Expected response: {"results": ["LangChain is a framework...", "..."]}

echo ""

# ---------------------------------------------------------------------------
# RAGify
# ---------------------------------------------------------------------------

info "RAGify: ${RAGIFY_URL}"

assert_status \
    "RAGify /health" \
    "${RAGIFY_URL}/health" \
    "GET" "" "200"

assert_contains \
    "RAGify /index (index 3 documents)" \
    "${RAGIFY_URL}/index" \
    "POST" \
    '{"documents": ["The capital of France is Paris.", "The Eiffel Tower was completed in 1889 and stands 330 meters tall.", "French cuisine includes croissants, baguettes, and coq au vin."]}' \
    "indexed"
# Expected response: {"indexed": 3}

assert_contains \
    "RAGify /query (retrieval-augmented question)" \
    "${RAGIFY_URL}/query" \
    "POST" \
    '{"question": "When was the Eiffel Tower built?"}' \
    "answer"
# Expected response: {"answer": "The Eiffel Tower was completed in 1889...", "sources": [...]}

echo ""

# ---------------------------------------------------------------------------
# AgentFlow
# ---------------------------------------------------------------------------

info "AgentFlow: ${AGENTFLOW_URL}"

assert_status \
    "AgentFlow /health" \
    "${AGENTFLOW_URL}/health" \
    "GET" "" "200"

assert_contains \
    "AgentFlow /run (arithmetic task)" \
    "${AGENTFLOW_URL}/run" \
    "POST" \
    '{"task": "What is 15 plus 27?"}' \
    "result"
# Expected response: {"result": "42", "steps": [...]}

assert_contains \
    "AgentFlow /run (text task)" \
    "${AGENTFLOW_URL}/run" \
    "POST" \
    '{"task": "Summarize the concept of a neural network in one sentence."}' \
    "result"

echo ""

# ---------------------------------------------------------------------------
# LLMOps Baseline
# ---------------------------------------------------------------------------

info "LLMOps Baseline: ${LLMOPS_URL}"

assert_status \
    "LLMOps /health" \
    "${LLMOPS_URL}/health" \
    "GET" "" "200"

assert_contains \
    "LLMOps /query (text generation)" \
    "${LLMOPS_URL}/query" \
    "POST" \
    '{"prompt": "Explain what a transformer model is in one sentence."}' \
    "response"
# Expected response: {"response": "...", "latency_ms": 123}

assert_contains \
    "LLMOps /query (response has latency field)" \
    "${LLMOPS_URL}/query" \
    "POST" \
    '{"prompt": "What is machine learning?"}' \
    "latency_ms"

assert_contains \
    "LLMOps /metrics (metrics tracking)" \
    "${LLMOPS_URL}/metrics" \
    "GET" "" \
    "n_calls"
# Expected response: {"n_calls": 2, "avg_latency_ms": 123, ...}
# n_calls should be at least 2 since we ran two /query requests above

echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS + FAIL))
echo "========================================================================"
echo "  Test results: ${PASS}/${TOTAL} passed"
if [[ ${FAIL} -gt 0 ]]; then
    echo -e "  ${RED}${FAIL} test(s) failed.${NC}"
    echo ""
    echo "  Debugging tips:"
    echo "  - Check Cloud Run logs: https://console.cloud.google.com/logs/query"
    echo "  - Filter: resource.type=cloud_run_revision AND severity>=ERROR"
    echo "  - See 10_troubleshooting.md for common errors and fixes"
    echo "========================================================================"
    exit 1
else
    echo -e "  ${GREEN}All tests passed.${NC}"
    echo "========================================================================"
    exit 0
fi
