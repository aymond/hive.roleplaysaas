output "cloud_run_url" {
  description = "HTTPS URL of the deployed Hivemind Cloud Run API"
  value       = google_cloud_run_v2_service.api.uri
}

output "media_bucket_name" {
  description = "Private GCS bucket for generated images and metadata"
  value       = google_storage_bucket.media.name
}

output "artifact_registry_repo" {
  description = "Artifact Registry Docker repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "api_service_account_email" {
  description = "Least-privilege service account attached to Cloud Run"
  value       = google_service_account.api_sa.email
}
