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
