locals {
  required_apis = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "identitytoolkit.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "firebasehosting.googleapis.com",
  ])
}

resource "google_project_service" "apis" {
  for_each           = local.required_apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# 1. Artifact Registry for Cloud Run container images
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "hivemind-images"
  description   = "Docker images for Hivemind SFW SaaS"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# 2. Dedicated least-privilege Service Account for Cloud Run
resource "google_service_account" "api_sa" {
  account_id   = "hivemind-api-sa"
  display_name = "Hivemind SaaS Cloud Run API"
}

resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

# 3. Private Cloud Storage bucket for generated PNGs & JSON metadata
resource "google_storage_bucket" "media" {
  name                        = "${var.project_id}-hivemind-media"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = var.media_retention_days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "media_rw" {
  bucket = google_storage_bucket.media.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_sa.email}"
}

# 4. Cloud Firestore (Native Mode) for multi-tenant state, credits & moderation policy
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.apis]
}

# 5. GCP Identity Platform configuration
resource "google_identity_platform_config" "auth" {
  provider                   = google-beta
  project                    = var.project_id
  autodelete_anonymous_users = true

  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
  }

  depends_on = [google_project_service.apis]
}

# 6. Secret Manager placeholders for Stripe & RunPod API keys
resource "google_secret_manager_secret" "stripe_secret_key" {
  secret_id = "hivemind-stripe-secret-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "stripe_webhook_secret" {
  secret_id = "hivemind-stripe-webhook-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "runpod_api_key" {
  secret_id = "hivemind-runpod-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "stripe_secret_key_init" {
  secret      = google_secret_manager_secret.stripe_secret_key.id
  secret_data = " "
  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_version" "stripe_webhook_secret_init" {
  secret      = google_secret_manager_secret.stripe_webhook_secret.id
  secret_data = " "
  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_version" "runpod_api_key_init" {
  secret      = google_secret_manager_secret.runpod_api_key.id
  secret_data = " "
  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each = {
    stripe_key     = google_secret_manager_secret.stripe_secret_key.secret_id
    stripe_webhook = google_secret_manager_secret.stripe_webhook_secret.secret_id
    runpod_key     = google_secret_manager_secret.runpod_api_key.secret_id
  }
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_sa.email}"
}

# 7. Optional self-hosted ComfyUI on Cloud Run GPU (NVIDIA L4, scale-to-zero)
resource "google_cloud_run_v2_service" "comfyui_gpu" {
  count    = var.enable_cloud_run_comfyui_gpu ? 1 : 0
  name     = "${var.service_name}-comfyui-gpu"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.api_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    node_selector {
      accelerator = "nvidia-l4"
    }

    containers {
      image = var.comfyui_gpu_image

      resources {
        limits = {
          cpu              = "4"
          memory           = "16Gi"
          "nvidia.com/gpu" = "1"
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# 8. Scale-to-zero Cloud Run v2 API Service
resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 20
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "SAAS_AUTH_ENABLED"
        value = "true"
      }
      env {
        name  = "FIREBASE_WEB_API_KEY"
        value = var.firebase_web_api_key
      }
      env {
        name  = "FIREBASE_AUTH_DOMAIN"
        value = var.firebase_auth_domain != "" ? var.firebase_auth_domain : "${var.project_id}.firebaseapp.com"
      }
      env {
        name  = "ADMIN_EMAILS"
        value = var.admin_emails
      }
      env {
        name  = "AUTH_PROVIDERS"
        value = var.auth_providers
      }
      env {
        name  = "RATE_LIMIT_PER_MINUTE"
        value = tostring(var.rate_limit_per_minute)
      }
      env {
        name  = "IMPRINT_NAME"
        value = var.imprint_name
      }
      env {
        name  = "IMPRINT_ADDRESS"
        value = var.imprint_address
      }
      env {
        name  = "IMPRINT_EMAIL"
        value = var.imprint_email
      }
      env {
        name  = "IMPRINT_PHONE"
        value = var.imprint_phone
      }
      env {
        name  = "PRIVACY_EMAIL"
        value = var.privacy_email
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "GCS_MEDIA_BUCKET"
        value = google_storage_bucket.media.name
      }
      env {
        name  = "ALLOWED_ORIGINS"
        value = var.allowed_origins
      }
      env {
        name  = "LLM_PROVIDER"
        value = var.llm_provider
      }
      env {
        name  = "IMAGE_PROVIDER"
        value = var.image_provider
      }
      env {
        name  = "COMFYUI_BASE_URL"
        value = var.enable_cloud_run_comfyui_gpu ? google_cloud_run_v2_service.comfyui_gpu[0].uri : "http://127.0.0.1:8188"
      }
      env {
        name  = "RUNPOD_ENDPOINT_ID"
        value = var.runpod_endpoint_id
      }

      env {
        name = "STRIPE_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.stripe_secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "STRIPE_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.stripe_webhook_secret.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "RUNPOD_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.runpod_api_key.secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_firestore_database.default,
    google_secret_manager_secret_iam_member.secret_access,
    google_secret_manager_secret_version.stripe_secret_key_init,
    google_secret_manager_secret_version.stripe_webhook_secret_init,
    google_secret_manager_secret_version.runpod_api_key_init,
  ]
}

# Public HTTPS access to Cloud Run (application enforces GCP Identity Platform JWTs)
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
