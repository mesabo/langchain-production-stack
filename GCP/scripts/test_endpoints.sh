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
# Service URLs are discovered automatically from gcloud using PROJECT_ID and
# REGION from the .env file at the repo root. No manual URL editing required.
# If gcloud is not installed, set the URLs as environment variables before running:
#
#   SMOLSEARCH_URL=https://smolsearch-xxx-an.a.run.app ./scripts/test_endpoints.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Load configuration from .env
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "[ERROR] .env not found at ${ENV_FILE}"
    echo "        Create it from .env.example and fill in GCP_PROJECT_ID and GCP_REGION."
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

PROJECT_ID="${GCP_PROJECT_ID}"
REGION="${GCP_REGION}"

# ---------------------------------------------------------------------------
# Discover Cloud Run URLs (or accept overrides from environment variables)
# ---------------------------------------------------------------------------

lookup_url() {
    local service_name="$1"
    gcloud run services describe "${service_name}" \
        --project="${PROJECT_ID}" \
        --region="${REGION}" \
        --format="value(status.url)" 2>/dev/null || echo ""
}

# Allow callers to override via env vars (useful in CI when gcloud isn't present)
if [[ -z "${SMOLSEARCH_URL:-}" ]]; then
    SMOLSEARCH_URL=$(lookup_url "smolsearch")
fi
if [[ -z "${RAGIFY_URL:-}" ]]; then
    RAGIFY_URL=$(lookup_url "ragify")
fi
if [[ -z "${AGENTFLOW_URL:-}" ]]; then
    AGENTFLOW_URL=$(lookup_url "agentflow")
fi
if [[ -z "${LLMOPS_URL:-}" ]]; then
    LLMOPS_URL=$(lookup_url "llmops-baseline")
fi

# Fail fast if any URL is still empty
missing=0
for pair in "smolsearch:${SMOLSEARCH_URL}" "ragify:${RAGIFY_URL}" "agentflow:${AGENTFLOW_URL}" "llmops-baseline:${LLMOPS_URL}"; do
    svc="${pair%%:*}"
    url="${pair#*:}"
    if [[ -z "${url}" ]]; then
        echo "[ERROR] Could not resolve URL for '${svc}'."
        echo "        Make sure the service is deployed and gcloud is authenticated."
        echo "        Or set the URL manually: ${svc^^}_URL=https://... ./scripts/test_endpoints.sh"
        missing=1
    fi
done
[[ "${missing}" -eq 0 ]] || exit 1

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "${GREEN}PASS${NC}  $*"; ((PASS++)); }
fail() { echo -e "${RED}FAIL${NC}  $*"; ((FAIL++)); }
info() { echo -e "${CYAN}----${NC}  $*"; }

# ---------------------------------------------------------------------------
# Helper: assert HTTP status code equals expected value
# assert_status TEST_NAME URL METHOD DATA EXPECTED_STATUS
# ---------------------------------------------------------------------------

assert_status() {
    local test_name="$1"
    local url="$2"
    local method="$3"
    local data="$4"
    local expected_status="$5"
    local http_status

    if [[ "${method}" == "GET" ]]; then
        http_status=$(curl -s -o /tmp/test_resp.json -w "%{http_code}" \
            --max-time 90 "${url}")
    else
        http_status=$(curl -s -o /tmp/test_resp.json -w "%{http_code}" \
            -X POST -H "Content-Type: application/json" -d "${data}" \
            --max-time 90 "${url}")
    fi

    if [[ "${http_status}" == "${expected_status}" ]]; then
        pass "[HTTP ${http_status}] ${test_name}"
    else
        fail "[HTTP ${http_status}, expected ${expected_status}] ${test_name}"
        echo "         Response: $(cat /tmp/test_resp.json 2>/dev/null | head -c 200)"
    fi
}

# ---------------------------------------------------------------------------
# Helper: assert response body contains a JSON key
# assert_contains TEST_NAME URL METHOD DATA KEY
# ---------------------------------------------------------------------------

assert_contains() {
    local test_name="$1"
    local url="$2"
    local method="$3"
    local data="$4"
    local expected_key="$5"
    local http_status response_body

    if [[ "${method}" == "GET" ]]; then
        http_status=$(curl -s -o /tmp/test_resp.json -w "%{http_code}" \
            --max-time 90 "${url}")
    else
        http_status=$(curl -s -o /tmp/test_resp.json -w "%{http_code}" \
            -X POST -H "Content-Type: application/json" -d "${data}" \
            --max-time 90 "${url}")
    fi

    response_body=$(cat /tmp/test_resp.json 2>/dev/null || echo "")

    if [[ "${http_status}" =~ ^2 ]] && echo "${response_body}" | grep -q "\"${expected_key}\""; then
        pass "[HTTP ${http_status}, has '${expected_key}'] ${test_name}"
    else
        fail "[HTTP ${http_status}, missing '${expected_key}'] ${test_name}"
        echo "         Response: ${response_body:0:200}"
    fi
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

echo ""
echo "========================================================================"
echo "  langchain-production-stack endpoint smoke tests"
echo "  Project: ${PROJECT_ID}  Region: ${REGION}"
echo "========================================================================"
echo "  Note: first request per service may be slow (cold start, up to 60s)."
echo ""

# SmolSearch
info "SmolSearch: ${SMOLSEARCH_URL}"
assert_status   "SmolSearch /health"              "${SMOLSEARCH_URL}/health" "GET" "" "200"
assert_contains "SmolSearch /index (3 docs)"      "${SMOLSEARCH_URL}/index"  "POST" \
    '{"documents":["LangChain builds LLM apps.","FAISS does fast vector search.","Sentence transformers encode text."]}' \
    "indexed"
assert_contains "SmolSearch /search (query)"      "${SMOLSEARCH_URL}/search" "POST" \
    '{"query":"What is LangChain?","k":2}' "results"
echo ""

# RAGify
info "RAGify: ${RAGIFY_URL}"
assert_status   "RAGify /health"                  "${RAGIFY_URL}/health" "GET" "" "200"
assert_contains "RAGify /index (3 docs)"          "${RAGIFY_URL}/index"  "POST" \
    '{"documents":["Paris is the capital of France.","The Eiffel Tower was built in 1889.","French cuisine is world-famous."]}' \
    "indexed"
assert_contains "RAGify /query (RAG question)"    "${RAGIFY_URL}/query"  "POST" \
    '{"query":"When was the Eiffel Tower built?","k":3,"strategy":"similarity"}' "answer"
echo ""

# AgentFlow
info "AgentFlow: ${AGENTFLOW_URL}"
assert_status   "AgentFlow /health"               "${AGENTFLOW_URL}/health" "GET" "" "200"
assert_contains "AgentFlow /run (arithmetic)"     "${AGENTFLOW_URL}/run" "POST" \
    '{"task":"What is 15 plus 27?"}' "result"
assert_contains "AgentFlow /run (text task)"      "${AGENTFLOW_URL}/run" "POST" \
    '{"task":"Summarize what a neural network is in one sentence."}' "result"
echo ""

# LLMOps Baseline
info "LLMOps Baseline: ${LLMOPS_URL}"
assert_status   "LLMOps /health"                  "${LLMOPS_URL}/health" "GET" "" "200"
assert_contains "LLMOps /query (generation)"      "${LLMOPS_URL}/query"  "POST" \
    '{"prompt":"What is a transformer model?"}' "response"
assert_contains "LLMOps /query (latency field)"   "${LLMOPS_URL}/query"  "POST" \
    '{"prompt":"What is machine learning?"}' "latency_ms"
assert_contains "LLMOps /metrics (counters)"      "${LLMOPS_URL}/metrics" "GET" "" "n_calls"
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

TOTAL=$((PASS + FAIL))
echo "========================================================================"
echo "  Results: ${PASS}/${TOTAL} passed"
if [[ ${FAIL} -gt 0 ]]; then
    echo -e "  ${RED}${FAIL} test(s) failed.${NC}"
    echo ""
    echo "  Debug: gcloud logging read 'resource.type=cloud_run_revision' \\"
    echo "         --project=${PROJECT_ID} --limit=50 --freshness=10m"
    echo "  See: GCP/10_troubleshooting.md for common errors and fixes."
    echo "========================================================================"
    exit 1
else
    echo -e "  ${GREEN}All tests passed.${NC}"
    echo "========================================================================"
    exit 0
fi
