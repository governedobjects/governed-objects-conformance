# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Brafford Labs, LLC
"""In-memory protocol fake with fault injection, for harness self-tests only.

With no faults it behaves as a disclosure-safe, authorization-first Core
implementation. Each fault reproduces one defect the Draft 2.2 target must
detect."""

from __future__ import annotations

import copy
from typing import Any

CEILING = 9223372036854775807
GRANTS = {
    "writer": {"read", "mutate", "transition", "relate", "create"},
    "former-writer": {"read", "mutate", "transition", "relate", "create"},
    "reader": {"read"},
    "writer-no-read": {"mutate", "transition", "relate"},
    "restorer": {"import"},
    "outsider": set(),
    "hist-actor": set(),
}
LIFECYCLE = {("draft", "active"), ("active", "completed")}
FAULTS = {
    "leak_version",
    "token_oracle",
    "reuse_version",
    "missing_version",
    "timestamp_order",
    "dup_add_advances",
    "restore_appends",
}


class FakeClient:
    name = "fake"

    def __init__(self, faults: set[str] | None = None):
        unknown = (faults or set()) - FAULTS
        if unknown:
            raise ValueError(f"unknown faults {unknown}")
        self.faults = faults or set()
        self.capabilities = {
            "protocol": "draft2.2",
            "mutable_objects": True,
            "unconditional_mutation": True,
            "relationship_add": True,
            "relationship_remove": True,
            "replay": False,
            "replay_types": [],
            "semantic_portability_view": True,
            "restart": True,
            "governance_reconfiguration": True,
            "harness_clock": False,
            "restoration": True,
            "restorable_types": ["conformance.record"],
            "create_with_relationships": False,
            "operational_metadata_ops": [],
            "version_token_grammar": "^[1-9][0-9]*$",
            "object_version_ceiling": str(CEILING),
            "declared_refusals": ["OBJECT_VERSION_SPACE_EXHAUSTED"],
            "concurrent_invocation": False,
        }
        self.reset()

    # --- state -------------------------------------------------------------

    def reset(self) -> None:
        self.objects: dict[str, dict[str, Any]] = {}
        self.issued: dict[str, set[int]] = {}
        self.revoked: set[str] = set()
        self.clock = 0

    def _can(self, actor: str, cap: str) -> bool:
        return actor not in self.revoked and cap in GRANTS.get(actor, set())

    def _stamp(self) -> str:
        self.clock += 1
        return f"2026-01-01T00:00:{self.clock:02d}Z"

    def _rep(self, obj: dict[str, Any]) -> tuple:
        return (tuple(sorted(obj["state"].items())), tuple(sorted(obj["rels"])))

    def _allocate(self, oid: str, obj: dict[str, Any]) -> int | None:
        if "reuse_version" in self.faults:
            for entry in obj["history"]:
                if entry.get("_rep") == self._rep(obj):
                    return entry["object_version"]
        nxt = max(self.issued[oid]) + 1
        return None if nxt > CEILING else nxt

    def _accept(self, oid: str, obj: dict[str, Any], effect: str, actor: str, **extra: Any) -> dict[str, Any] | None:
        ver = self._allocate(oid, obj)
        if ver is None:
            return None
        self.issued[oid].add(ver)
        obj["version"] = ver
        entry = {"effect": effect, "object_version": ver, "actor": actor, "accepted_at": self._stamp(), "_rep": self._rep(obj)}
        if "missing_version" in self.faults and effect == "state_updated":
            entry["object_version"] = None
        entry.update(extra)
        obj["history"].append(entry)
        return entry

    def _view(self, oid: str) -> dict[str, Any] | None:
        obj = self.objects.get(oid)
        if obj is None:
            return None
        hist = [{k: v for k, v in e.items() if not k.startswith("_")} for e in obj["history"]]
        if "timestamp_order" in self.faults:
            hist = sorted(hist, key=lambda e: e.get("accepted_at") or "")
        for e in hist:
            e.update(canonical_identity=oid, type_identity=obj["type"], type_version="1")
        return {
            "channel": "observer",
            "canonical_identity": oid,
            "type_identity": obj["type"],
            "type_version": obj["type_version"],
            "object_version": obj["version"],
            "accepted_state": dict(obj["state"]),
            "relationships": [{"source": oid, "type": t, "target": g} for t, g in sorted(obj["rels"])],
            "canonical_history_summary": hist,
        }

    def _result(self, oid: str, outcome: str, actor: str, detail: str = "") -> dict[str, Any]:
        obj = self.objects.get(oid)
        caller: dict[str, Any] = {"outcome": outcome, "detail": detail}
        if obj is not None and (outcome == "ACCEPTED" or self._can(actor, "read")):
            caller["object"] = {"version": obj["version"], "state": dict(obj["state"])}
        elif obj is not None and "leak_version" in self.faults:
            caller["current_version"] = obj["version"]
        return {"ok": True, "outcome": outcome, "unmappable": False, "caller_result": caller, "semantic_view": self._view(oid)}

    # --- protocol ------------------------------------------------------------

    def request(self, req: dict[str, Any]) -> dict[str, Any]:
        op = req["op"]
        handler = getattr(self, f"op_{op}", None)
        if handler is None:
            return {"ok": True, "outcome": "UNMAPPABLE", "unmappable": True, "outcome_detail": f"{op} not supported"}
        return handler(req)

    def op_capabilities(self, req):
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False, "capabilities": self.capabilities}

    def op_reset(self, req):
        self.reset()
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False}

    def op_define_fixture_types(self, req):
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False}

    def op_restart(self, req):
        self.revoked |= set(req.get("revoke") or [])
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False}

    def op_semantic_view(self, req):
        view = self._view(req["object_id"])
        return {"ok": True, "outcome": "ACCEPTED" if view else "SEMANTICALLY_INVALID", "unmappable": False, "semantic_view": view}

    def op_get_history(self, req):
        view = self._view(req["object_id"])
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False,
                "canonical_history": (view or {}).get("canonical_history_summary", []), "semantic_view": view}

    def op_create(self, req):
        oid, actor = req["object_id"], req["actor"]
        if req.get("relationships"):
            return {"ok": True, "outcome": "UNMAPPABLE", "unmappable": True}
        if not self._can(actor, "create"):
            return self._result(oid, "AUTHORIZATION_DENIED", actor)
        init = req.get("initial_state") or {}
        self.objects[oid] = {"type": req["type"], "type_version": "1", "version": 1,
                             "state": {"title": init.get("title", "Untitled"), "status": init.get("status", "draft")},
                             "rels": set(), "history": []}
        self.issued[oid] = {1}
        obj = self.objects[oid]
        obj["history"].append({"effect": "object_created", "object_version": 1, "actor": actor,
                               "accepted_at": self._stamp(), "_rep": self._rep(obj)})
        return self._result(oid, "ACCEPTED", actor)

    def _gate(self, req, cap):
        """Authorization first, then the precondition. The token_oracle fault
        checks the precondition first for every requester."""
        oid, actor = req["object_id"], req["actor"]
        obj = self.objects.get(oid)
        if obj is None:
            return self._result(oid, "SEMANTICALLY_INVALID", actor, "not found")
        ev = req.get("expected_version")
        stale = ev is not None and int(ev) != obj["version"]
        if "token_oracle" in self.faults and stale:
            return self._result(oid, "CONFLICT", actor)
        if not self._can(actor, cap):
            return self._result(oid, "AUTHORIZATION_DENIED", actor)
        if stale:
            return self._result(oid, "CONFLICT", actor)
        return None

    def _commit(self, req, effect, **extra):
        oid, actor = req["object_id"], req["actor"]
        obj = self.objects[oid]
        if self._accept(oid, obj, effect, actor, **extra) is None:
            return self._result(oid, "REFUSED", actor, "OBJECT_VERSION_SPACE_EXHAUSTED")
        return self._result(oid, "ACCEPTED", actor)

    def op_read(self, req):
        oid, actor = req["object_id"], req["actor"]
        if not self._can(actor, "read"):
            return self._result(oid, "AUTHORIZATION_DENIED", actor)
        return self._result(oid, "ACCEPTED", actor)

    def op_mutate(self, req):
        rejected = self._gate(req, "mutate")
        if rejected:
            return rejected
        obj = self.objects[req["object_id"]]
        changes = req.get("changes") or {}
        if set(changes) - {"title"} or not str(changes.get("title", "")).strip():
            return self._result(req["object_id"], "SEMANTICALLY_INVALID", req["actor"])
        before = copy.deepcopy(obj["state"])
        obj["state"]["title"] = changes["title"]
        out = self._commit(req, "state_updated")
        if out["outcome"] != "ACCEPTED":
            obj["state"] = before
        return out

    def op_transition(self, req):
        rejected = self._gate(req, "transition")
        if rejected:
            return rejected
        obj = self.objects[req["object_id"]]
        if (obj["state"]["status"], req["to"]) not in LIFECYCLE:
            return self._result(req["object_id"], "SEMANTICALLY_INVALID", req["actor"])
        before = obj["state"]["status"]
        obj["state"]["status"] = req["to"]
        out = self._commit(req, "lifecycle_transition")
        if out["outcome"] != "ACCEPTED":
            obj["state"]["status"] = before
        return out

    def _relationship(self, req, add: bool):
        rejected = self._gate(req, "relate")
        if rejected:
            return rejected
        obj = self.objects[req["object_id"]]
        if not req["relationship"].get("type") or not req["relationship"].get("target"):
            return self._result(req["object_id"], "SEMANTICALLY_INVALID", req["actor"])
        triple = (req["relationship"]["type"], req["relationship"]["target"])
        present = triple in obj["rels"]
        if add and present and "dup_add_advances" not in self.faults:
            return self._result(req["object_id"], "ACCEPTED", req["actor"])
        if not add and not present:
            return self._result(req["object_id"], "ACCEPTED", req["actor"])
        (obj["rels"].add if add else obj["rels"].discard)(triple)
        effect = "relationship_added" if add else "relationship_removed"
        out = self._commit(req, effect, relationship_type=triple[0], relationship_target=triple[1])
        if out["outcome"] != "ACCEPTED":
            (obj["rels"].discard if add else obj["rels"].add)(triple)
        return out

    def op_add_relationship(self, req):
        return self._relationship(req, True)

    def op_remove_relationship(self, req):
        return self._relationship(req, False)

    def op_restore(self, req):
        actor = req["actor"]
        objs = req.get("objects") or []
        single = objs[0]["canonical_identity"] if len(objs) == 1 else None
        if not self._can(actor, "import"):
            return {"ok": True, "outcome": "AUTHORIZATION_DENIED", "unmappable": False,
                    "caller_result": {"refusal": "not authorized"}, "semantic_view": self._view(single) if single else None}
        effects = {"create": "object_created", "state_change": "state_updated", "lifecycle_transition": "lifecycle_transition",
                   "relationship_add": "relationship_added", "relationship_remove": "relationship_removed"}
        for o in objs:
            if o["type_version"] != "1" or any(e.get("baseline_relationships") for e in o["history"]):
                return {"ok": True, "outcome": "REFUSED", "unmappable": False, "caller_result": {"refusal": "unsupported"},
                        "semantic_view": self._view(single) if single else None}
        for o in objs:
            oid = o["canonical_identity"]
            hist = []
            for e in o["history"]:
                entry = {"effect": effects[e["effect"]], "object_version": int(e["resulting_object_version"]),
                         "actor": e.get("actor"), "accepted_at": e.get("accepted_at")}
                if e.get("relationship"):
                    entry.update(relationship_type=e["relationship"]["type"], relationship_target=e["relationship"]["target"])
                hist.append(entry)
            obj = {"type": o["type_identity"], "type_version": o["type_version"], "version": int(o["current_object_version"]),
                   "state": dict(o["accepted_state"]), "rels": {(r["type"], r["target"]) for r in o["relationships"]},
                   "history": hist}
            self.objects[oid] = obj
            self.issued[oid] = {e["object_version"] for e in hist}
            if "restore_appends" in self.faults:
                self._accept(oid, obj, "restored", actor)
        return {"ok": True, "outcome": "ACCEPTED", "unmappable": False, "caller_result": {"restored": [o["canonical_identity"] for o in objs]},
                "semantic_view": self._view(single) if single else None}
