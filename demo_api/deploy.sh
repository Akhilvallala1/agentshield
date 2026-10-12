#!/usr/bin/env bash
# Builds the demo image and deploys it to Cloud Run. Run from the repo root:
#   PROJECT_ID=my-project ./demo_api/deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-agentshield-demo}"
REPO="${REPO:-agentshield}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:$(git rev-parse --short HEAD)"

gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION"

gcloud builds submit --config demo_api/cloudbuild.yaml --substitutions "_IMAGE=${IMAGE}" .

# Scales to zero when idle, so it stays inside Cloud Run's free tier. The portfolio page pings /healthz
# on load, which wakes the instance while the visitor reads; startup CPU boost shortens that wake-up.
# max 2 + concurrency caps the bill if someone floods it.
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" --region "$REGION" --allow-unauthenticated \
  --memory 1Gi --cpu 1 --min-instances 0 --max-instances 2 --concurrency 20 --timeout 15 --cpu-boost \
  --set-env-vars "ALLOWED_ORIGINS=https://akhilvallala1.github.io"

gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)'
