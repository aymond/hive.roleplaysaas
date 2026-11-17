from __future__ import annotations

import os
from typing import Any

from .logger import logger
from .models import (
    CharacterCard,
    ChatSession,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    ModerationPolicy,
    WorkflowGraph,
    utc_now_iso,
)
from .storage import StudioStorage, TenantWorkspace


class FirestoreTenantWorkspace(TenantWorkspace):
    """Tenant-scoped Firestore workspace under `users/{uid}/...`."""

    def __init__(self, db: Any, uid: str, template_store: StudioStorage) -> None:
        self._db = db
        self.uid = uid
        self._user_ref = db.collection("users").document(uid)
        self.characters: dict[str, CharacterCard] = {}
        self.worlds: dict[str, Lorebook] = {}
        self.chats: dict[str, ChatSession] = {}
        self.workflows: dict[str, WorkflowGraph] = {}
        self.gallery: list[GalleryAsset] = []
        self._load_or_seed(template_store)

    def _load_or_seed(self, template_store: StudioStorage) -> None:
        user_snap = self._user_ref.get()
        if not user_snap.exists:
            self._user_ref.set(
                {
                    "uid": self.uid,
                    "plan": "free",
                    "credit_balance": int(os.getenv("DEFAULT_FREE_CREDITS", "50")),
                    "stripe_customer_id": "",
                    "created_at": utc_now_iso(),
                    "seeded": True,
                }
            )
            # Seed starter SFW-friendly copies for this tenant only
            self.characters = {k: v.model_copy(deep=True) for k, v in template_store.characters.items()}
            self.worlds = {k: v.model_copy(deep=True) for k, v in template_store.worlds.items()}
            self.workflows = {k: v.model_copy(deep=True) for k, v in template_store.workflows.items()}
            self.save()
            return

        for doc in self._user_ref.collection("characters").stream():
            c = CharacterCard.model_validate(doc.to_dict())
            self.characters[c.id] = c
        for doc in self._user_ref.collection("worlds").stream():
            w = Lorebook.model_validate(doc.to_dict())
            self.worlds[w.id] = w
        for doc in self._user_ref.collection("chats").stream():
            ch = ChatSession.model_validate(doc.to_dict())
            self.chats[ch.id] = ch
        for doc in self._user_ref.collection("workflows").stream():
            wf = WorkflowGraph.model_validate(doc.to_dict())
            self.workflows[wf.id] = wf
        gallery_items = [
            GalleryAsset.model_validate(doc.to_dict())
            for doc in self._user_ref.collection("gallery").stream()
        ]
        self.gallery = sorted(gallery_items, key=lambda g: g.created_at, reverse=True)

    def _sync_collection(self, name: str, items: dict[str, Any]) -> None:
        col = self._user_ref.collection(name)
        existing_ids = {d.id for d in col.stream()}
        for item_id, model in items.items():
            col.document(item_id).set(model.model_dump())
        for stale_id in existing_ids - set(items.keys()):
            col.document(stale_id).delete()

    def save(self) -> None:
        self._sync_collection("characters", self.characters)
        self._sync_collection("worlds", self.worlds)
        self._sync_collection("chats", self.chats)
        self._sync_collection("workflows", self.workflows)
        gallery_map = {g.id: g for g in self.gallery}
        self._sync_collection("gallery", gallery_map)


class FirestoreStorage(StudioStorage):
    """Multi-tenant Firestore storage backend for Cloud Run SaaS deployments."""

    def __init__(self) -> None:
        super().__init__()
        from google.cloud import firestore  # type: ignore[import-not-found]

        self._db = firestore.Client(project=os.getenv("GCP_PROJECT_ID") or None)
        self._tenant_cache: dict[str, FirestoreTenantWorkspace] = {}
        self._load_global_configs()

    def _load_global_configs(self) -> None:
        try:
            sys_doc = self._db.collection("config").document("system").get()
            if sys_doc.exists:
                self.config = InferenceConfig.model_validate(sys_doc.to_dict() or {})
            mod_doc = self._db.collection("config").document("moderation").get()
            if mod_doc.exists:
                self.moderation_policy = ModerationPolicy.model_validate(mod_doc.to_dict() or {})
        except Exception as exc:
            logger.warning("⚠️ FIRESTORE | Failed to load global config: %s", exc)

    def save(self) -> None:
        try:
            self._db.collection("config").document("system").set(self.config.model_dump())
            self._db.collection("config").document("moderation").set(self.moderation_policy.model_dump())
        except Exception as exc:
            logger.warning("⚠️ FIRESTORE | Failed to save global config: %s", exc)

    def for_user(self, uid: str) -> FirestoreTenantWorkspace:
        if uid not in self._tenant_cache:
            self._tenant_cache[uid] = FirestoreTenantWorkspace(self._db, uid, self)
        return self._tenant_cache[uid]

    def get_user_billing(self, uid: str) -> dict[str, Any]:
        snap = self._db.collection("users").document(uid).get()
        if not snap.exists:
            self.for_user(uid)
            snap = self._db.collection("users").document(uid).get()
        return snap.to_dict() or {}

    def adjust_credits(self, uid: str, delta: int, reason: str, event_id: str | None = None) -> int:
        from google.cloud import firestore  # type: ignore[import-not-found]

        user_ref = self._db.collection("users").document(uid)
        if event_id:
            evt_ref = user_ref.collection("ledger").document(event_id)
            if evt_ref.get().exists:
                return int((user_ref.get().to_dict() or {}).get("credit_balance", 0))

        @firestore.transactional
        def _txn(transaction: Any) -> int:
            snap = user_ref.get(transaction=transaction)
            data = snap.to_dict() or {}
            current = int(data.get("credit_balance", 0))
            new_bal = current + delta
            if new_bal < 0:
                raise ValueError(f"Insufficient credits (balance={current}, needed={abs(delta)})")
            transaction.set(user_ref, {"credit_balance": new_bal}, merge=True)
            tx_id = event_id or f"tx_{utc_now_iso()}"
            transaction.set(
                user_ref.collection("ledger").document(tx_id),
                {"delta": delta, "balance_after": new_bal, "reason": reason, "ts": utc_now_iso()},
            )
            return new_bal

        return _txn(self._db.transaction())
