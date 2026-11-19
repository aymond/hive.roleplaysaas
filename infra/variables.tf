variable "project_id" {
  description = "GCP Project ID for the Hivemind SFW SaaS deployment"
  type        = string
}

variable "region" {
  description = "Primary GCP region (default: europe-west4 Netherlands)"
  type        = string
  default     = "europe-west4"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "hivemind-api"
}

variable "container_image" {
  description = "Container image URI in Artifact Registry (e.g. europe-west4-docker.pkg.dev/PROJECT/hivemind-images/hivemind-api:latest)"
  type        = string
}

variable "allowed_origins" {
  description = "Comma-separated CORS allowed origins for the SaaS frontend"
  type        = string
  default     = "https://hivemind-saas.web.app"
}

variable "llm_provider" {
  description = "Default SFW LLM backend (vertex_ai or openai_compat for self-hosted Cloud Run vLLM)"
  type        = string
  default     = "vertex_ai"
}

variable "image_provider" {
  description = "Default SFW image backend (vertex_imagen or comfyui for self-hosted Cloud Run GPU)"
  type        = string
  default     = "vertex_imagen"
}

variable "enable_cloud_run_comfyui_gpu" {
  description = "Deploy a self-hosted ComfyUI service on Cloud Run with NVIDIA L4 GPU (scales to zero)"
  type        = bool
  default     = false
}

variable "comfyui_gpu_image" {
  description = "Container image URI for self-hosted ComfyUI on Cloud Run GPU"
  type        = string
  default     = ""
}

variable "runpod_endpoint_id" {
  description = "Optional RunPod Serverless endpoint ID when image_provider=runpod_serverless"
  type        = string
  default     = ""
}

variable "media_retention_days" {
  description = "Auto-delete generated media objects in GCS after N days to minimize storage cost"
  type        = number
  default     = 90
}

variable "firebase_web_api_key" {
  description = "Public Firebase / Identity Platform Web API key for frontend OAuth & email login"
  type        = string
  default     = ""
}

variable "firebase_auth_domain" {
  description = "Firebase Auth domain (defaults to <project_id>.firebaseapp.com if empty)"
  type        = string
  default     = ""
}

variable "admin_emails" {
  description = "Comma-separated list of administrator email addresses bootstrapped on first login"
  type        = string
  default     = ""
}

variable "auth_providers" {
  description = "Comma-separated OAuth providers shown on the login screen (google,apple,github,instagram)"
  type        = string
  default     = "google"
}

variable "rate_limit_per_minute" {
  description = "Per-tenant sliding-window rate limit for LLM and image generation endpoints"
  type        = number
  default     = 30
}
