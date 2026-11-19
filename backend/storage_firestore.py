from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from typing import Any

from .logger import logger
from .models import (
    CharacterCard,
    ChatSession,
    GalleryAsset,
    InferenceConfig,
    Lorebook,
    ModerationPolicy,
    UserRecord,
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
        self._last_saved_hashes: dict[str, dict[str, str]] = {
            "characters": {},
            "worlds": {},
            "chats": {},
            "workflows": {},
            "gallery": {},
        }
        self._load_or_seed(template_store)

    @staticmethod
    def _model_hash(model: Any) -> str:
        raw = json.dumps(model.model_dump(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _record_loaded_hashes(self, name: str, items: dict[str, Any]) -> None:
        self._last_saved_hashes[name] = {k: self._model_hash(v) for k, v in items.items()}

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
        self._record_loaded_hashes("characters", self.characters)
        for doc in self._user_ref.collection("worlds").stream():
            w = Lorebook.model_validate(doc.to_dict())
            self.worlds[w.id] = w
        self._record_loaded_hashes("worlds", self.worlds)
        for doc in self._user_ref.collection("chats").stream():
            ch = ChatSession.model_validate(doc.to_dict())
            self.chats[ch.id] = ch
        self._record_loaded_hashes("chats", self.chats)
        for doc in self._user_ref.collection("workflows").stream():
            wf = WorkflowGraph.model_validate(doc.to_dict())
            self.workflows[wf.id] = wf
        self._record_loaded_hashes("workflows", self.workflows)
        gallery_items = [
            GalleryAsset.model_validate(doc.to_dict())
            for doc in self._user_ref.collection("gallery").stream()
        ]
        self.gallery = sorted(gallery_items, key=lambda g: g.created_at, reverse=True)
        self._record_loaded_hashes("gallery", {g.id: g for g in self.gallery})

    def _sync_collection(self, name: str, items: dict[str, Any]) -> None:
        col = self._user_ref.collection(name)
        prev_hashes = self._last_saved_hashes.setdefault(name, {})
        next_hashes: dict[str, str] = {}
        for item_id, model in items.items():
            digest = self._model_hash(model)
            next_hashes[item_id] = digest
            if prev_hashes.get(item_id) != digest:
                col.document(item_id).set(model.model_dump())
        for stale_id in set(prev_hashes.keys()) - set(items.keys()):
            col.document(stale_id).delete()
        self._last_saved_hashes[name] = next_hashes

    def save(self) -> None:
        self._sync_collection("characters", self.characters)
        self._sync_collection("worlds", self.worlds)
        self._sync_collection("chats", self.chats)
        self._sync_collection("workflows", self.workflows)
        gallery_map = {g.id: g for g in self.gallery}
        self._sync_collection("gallery", gallery_map)


class FirestoreStorage(StudioStorage):
    """Multi-tenant Firestore storage backend for Cloud Run SaaS deployments."""

    MAX_CACHED_TENANTS = 64

    def __init__(self) -> None:
        from google.cloud import firestore  # type: ignore[import-not-found]

        self._db = firestore.Client(project=os.getenv("GCP_PROJECT_ID") or None)
        self._tenant_cache: OrderedDict[str, FirestoreTenantWorkspace] = OrderedDict()
        super().__init__()
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
        if uid in self._tenant_cache:
            self._tenant_cache.move_to_end(uid)
            return self._tenant_cache[uid]
        ws = FirestoreTenantWorkspace(self._db, uid, self)
        self._tenant_cache[uid] = ws
        while len(self._tenant_cache) > self.MAX_CACHED_TENANTS:
            self._tenant_cache.popitem(last=False)
        return ws

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

    @staticmethod
    def _doc_to_user_record(uid: str, data: dict[str, Any]) -> UserRecord:
        return UserRecord(
            uid=str(data.get("uid") or uid),
            email=str(data.get("email") or ""),
            role="admin" if data.get("role") == "admin" else "user",
            plan=str(data.get("plan") or "free"),
            disabled=bool(data.get("disabled", False)),
            credit_balance=int(data.get("credit_balance", 50)),
            created_at=str(data.get("created_at") or utc_now_iso()),
            last_login_at=str(data.get("last_login_at") or utc_now_iso()),
        )

    def get_user(self, uid: str) -> UserRecord | None:
        snap = self._db.collection("users").document(uid).get()
        if not snap.exists:
            return None
        return self._doc_to_user_record(uid, snap.to_dict() or {})

    def list_users(self) -> list[UserRecord]:
        users = [
            self._doc_to_user_record(doc.id, doc.to_dict() or {})
            for doc in self._db.collection("users").stream()
        ]
        return sorted(users, key=lambda u: u.created_at, reverse=True)

    def upsert_user_on_login(
        self,
        uid: str,
        email: str = "",
        default_role: str = "user",
        default_plan: str = "free",
        force_admin: bool = False,
    ) -> UserRecord:
        now = utc_now_iso()
        user_ref = self._db.collection("users").document(uid)
        snap = user_ref.get()
        if snap.exists:
            data = snap.to_dict() or {}
            updates: dict[str, Any] = {"last_login_at": now}
            if email and data.get("email") != email:
                updates["email"] = email
            if force_admin and data.get("role") != "admin":
                updates["role"] = "admin"
            user_ref.set(updates, merge=True)
            merged = {**data, **updates}
            return self._doc_to_user_record(uid, merged)

        self.for_user(uid)
        resolved_role = "admin" if (force_admin or default_role == "admin") else "user"
        updates = {
            "uid": uid,
            "email": email or f"{uid}@localhost",
            "role": resolved_role,
            "plan": default_plan,
            "disabled": False,
            "last_login_at": now,
        }
        user_ref.set(updates, merge=True)
        return self.get_user(uid) or UserRecord(
            uid=uid,
            email=updates["email"],
            role=resolved_role,  # type: ignore[arg-type]
            plan=default_plan,
            created_at=now,
            last_login_at=now,
        )

    def update_user(
        self,
        uid: str,
        *,
        role: str | None = None,
        plan: str | None = None,
        disabled: bool | None = None,
        credit_balance: int | None = None,
    ) -> UserRecord:
        user_ref = self._db.collection("users").document(uid)
        if not user_ref.get().exists:
            raise KeyError(f"User not found: {uid}")
        updates: dict[str, Any] = {}
        if role in ("user", "admin"):
            updates["role"] = role
        if plan is not None:
            updates["plan"] = plan
        if disabled is not None:
            updates["disabled"] = bool(disabled)
        if credit_balance is not None:
            updates["credit_balance"] = max(0, int(credit_balance))
        if updates:
            user_ref.set(updates, merge=True)
        updated = self.get_user(uid)
        assert updated is not None
        return updated

    def delete_user(self, uid: str) -> bool:
        user_ref = self._db.collection("users").document(uid)
        if not user_ref.get().exists:
            return False
        user_ref.delete()
        self._tenant_cache.pop(uid, None)
        return True
