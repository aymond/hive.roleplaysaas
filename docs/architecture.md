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

    subgraph AI["Configurable SFW AI Backends"]
        LLM["SFW LLM (Vertex Gemini Flash / OpenAI-compat)"]
        ImgV["Vertex AI Imagen (Managed SFW)"]
        ImgR["RunPod Serverless ComfyUI (Juggernaut-XL / RealVisXL)"]
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
    CR -->|"Roleplay & Prompt Synthesis"| LLM
    CR -->|"image_provider = vertex_imagen"| ImgV
    CR -->|"image_provider = runpod_serverless"| ImgR
    Browser -->|"Checkout / Portal"| Stripe
    Stripe -->|"Signed Webhook"| Bill
    Bill --> CR
```

## Key Design Decisions
- **Scale-to-Zero Cost Optimization**: Cloud Run (`min_instance_count = 0`), Firestore Native, Firebase Hosting, and GCP Identity Platform (free up to 50,000 MAU) keep idle infrastructure cost near **\$0/month** on GCP.
- **Pre-Flight Moderation**: All user inputs (chat, scenes, character cards, worlds/lore) are scanned against admin-managed trigger words **before** any LLM or GPU API call is made.
- **Configurable Image Pipeline**: `InferenceConfig.image_provider` supports `vertex_imagen`, `runpod_serverless`, `comfyui`, `mps_diffusers`, and `procedural_art` without changing application code.
