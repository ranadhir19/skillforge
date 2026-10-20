"""Append-only, hash-chained audit log for lifecycle events.

The pattern is the agent-sentinel evidence chain from governed-agents:
every entry carries the hash of the previous entry, so a gap or a
quiet rewrite of history is detectable by anyone holding the file.
Skill creation, approval, promotion, import and deprecation are all
lifecycle events and all land here — provenance for a skill is its
provenance.json *plus* this chain.
"""

from __future__ import annotations

import hashlib
import json
import os
import time


class AuditLog:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    def _entries(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def append(self, event: str, payload: dict) -> dict:
        entries = self._entries()
        prev = entries[-1]["hash"] if entries else "GENESIS"
        entry = {"seq": len(entries) + 1, "ts": time.time(),
                 "event": event, "payload": payload, "prev": prev}
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True).encode()).hexdigest()[:16]
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def entries(self) -> list[dict]:
        return self._entries()

    def verify_chain(self) -> bool:
        entries = self._entries()
        prev = "GENESIS"
        for e in entries:
            if e["prev"] != prev:
                return False
            body = {k: e[k] for k in ("seq", "ts", "event", "payload", "prev")}
            expect = hashlib.sha256(
                json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
            if e["hash"] != expect:
                return False
            prev = e["hash"]
        return True
