#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a new GCP project and deploy Hivemind SFW SaaS (europe-west4)
# Usage:
#   PROJECT_ID=hivemind-saas-prod BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX ./scripts/deploy_gcp.sh

PROJECT_ID="${PROJECT_ID:-hivemind-saas-$(date +%y%m%d)}"
REGION="${REGION:-europe-west4}"
BILLING_ACCOUNT_ID="${BILLING_ACCOUNT_ID:-}"
REPO_NAME="hivemind-images"
SERVICE_NAME="hivemind-api"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Error: gcloud CLI not found. Install with: brew install --cask google-cloud-sdk"
  exit 1
fi

echo "==> 1. Creating GCP project: ${PROJECT_ID}"
if ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud projects create "${PROJECT_ID}" --name="Hivemind SaaS"
fi
gcloud config set project "${PROJECT_ID}"

if [[ -n "${BILLING_ACCOUNT_ID}" ]]; then
  echo "==> 2. Linking billing account ${BILLING_ACCOUNT_ID}"
  gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT_ID}"
else
  echo "WARNING: BILLING_ACCOUNT_ID not set. Link billing in GCP Console before Terraform apply."
fi

echo "==> 3. Enabling Cloud Build & Artifact Registry APIs"
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com

echo "==> 4. Building frontend bundle"
npm --prefix frontend ci
npm --prefix frontend run build

echo "==> 5. Initializing Terraform & provisioning Artifact Registry"
terraform -chdir=infra init
terraform -chdir=infra apply -target=google_project_service.apis -target=google_artifact_registry_repository.images -auto-approve \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="container_image=${IMAGE_URI}"

echo "==> 6. Building & pushing Docker image via Cloud Build: ${IMAGE_URI}"
gcloud builds submit --tag "${IMAGE_URI}" .

echo "==> 7. Applying full Terraform infrastructure (Cloud Run, Firestore, GCS, Identity Platform, Secret Manager)"
TF_ARGS=(
  -var="project_id=${PROJECT_ID}"
  -var="region=${REGION}"
  -var="container_image=${IMAGE_URI}"
)
[[ -n "${ADMIN_EMAILS:-}" ]] && TF_ARGS+=(-var="admin_emails=${ADMIN_EMAILS}")
[[ -n "${FIREBASE_WEB_API_KEY:-}" ]] && TF_ARGS+=(-var="firebase_web_api_key=${FIREBASE_WEB_API_KEY}")
[[ -n "${ALLOWED_ORIGINS:-}" ]] && TF_ARGS+=(-var="allowed_origins=${ALLOWED_ORIGINS}")
[[ -n "${AUTH_PROVIDERS:-}" ]] && TF_ARGS+=(-var="auth_providers=${AUTH_PROVIDERS}")

terraform -chdir=infra apply -auto-approve "${TF_ARGS[@]}"

if command -v firebase >/dev/null 2>&1; then
  echo "==> 8. Deploying frontend to Firebase Hosting"
  firebase deploy --only hosting --project "${PROJECT_ID}"
else
  echo "==> Note: Install firebase-tools and run 'firebase deploy --only hosting --project ${PROJECT_ID}' to publish the Hosting CDN."
fi

echo "==> Deployment infrastructure ready!"
terraform -chdir=infra output
