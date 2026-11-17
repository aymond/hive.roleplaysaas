# Hivemind SaaS — Serverless Architecture

## System Architecture (`europe-west4`)

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        Browser["Browser (React 19 + Vite SPA)"]
    end

    subgraph Edge["Firebase & GCP Identity"]
        FH["Firebase Hosting (CDN + /api/** Rewrite)"]
        IdP["GCP Identity Platform (OAuth / Email / Admin Claims)"]
    end

    subgraph Compute["Serverless Compute (europe-west4)"]
        CR["Cloud Run v2: hivemind-api (FastAPI, min=0)"]
        Mod["Pre-Flight SFW Trigger-Word Filter"]
        Bill["Stripe Billing & Webhook Handler"]
    end

    subgraph Data["Serverless State, Media & Secrets"]
        FS["Cloud Firestore (Native Mode, europe-west4)"]
        GCS["Cloud Storage (Private Bucket, Signed URLs)"]
        SM["GCP Secret Manager (Stripe & RunPod Keys)"]
    end

    subgraph AI["Configurable GCP-Native SFW AI Backends"]
        LLM_V["Vertex AI Gemini Flash (Managed LLM)"]
        LLM_CR["Cloud Run GPU: vLLM / Ollama (Self-Hosted LLM)"]
        Img_V["Vertex AI Imagen (Managed SFW)"]
        Img_CR["Cloud Run GPU (L4): ComfyUI Juggernaut-XL (Self-Hosted)"]
    end

    Stripe["Stripe Checkout & Portal"]

    Browser -->|"Static SPA & /api/**"| FH
    Browser -->|"Sign In (JWT)"| IdP
    FH -->|"HTTPS + Bearer JWT"| CR
    CR -->|"Verify JWT & Admin Claim"| IdP
    CR --> Mod
    Mod -->|"HTTP 422 if Triggered"| Browser
    CR -->|"Tenant Data & Moderation Policy"| FS
    CR -->|"Private PNG + JSON Metadata"| GCS
    CR -->|"Runtime Secrets"| SM
    CR -->|"llm_provider = vertex_ai"| LLM_V
    CR -->|"llm_provider = openai_compat / ollama"| LLM_CR
    CR -->|"image_provider = vertex_imagen"| Img_V
    CR -->|"image_provider = comfyui"| Img_CR
    Browser -->|"Checkout / Portal"| Stripe
    Stripe -->|"Signed Webhook"| Bill
    Bill --> CR
```

## Key Design Decisions
- **Scale-to-Zero Cost Optimization**: Cloud Run (`min_instance_count = 0`), Firestore Native, Firebase Hosting, and GCP Identity Platform (free up to 50,000 MAU) keep idle infrastructure cost near **\$0/month** on GCP.
- **Pre-Flight Moderation**: All user inputs (chat, scenes, character cards, worlds/lore) are scanned against admin-managed trigger words **before** any LLM or GPU API call is made.
- **Configurable Image Pipeline**: `InferenceConfig.image_provider` supports `vertex_imagen`, `runpod_serverless`, `comfyui`, `mps_diffusers`, and `procedural_art` without changing application code.
