"""SkillForge serving layer: FastAPI + GraphQL + REST.

GraphQL (/graphql) is the query layer — library, provenance, traces,
episodes, audit — plus run/lifecycle mutations and a trace-streaming
subscription (server/schema.py). REST carries what GraphQL is the
wrong shape for: /health, zip import/export, and the staged dynamic
-creation gate (draft -> summary -> human approve/deny), where the
human decision is an explicit API call rather than a server default.

Run locally:
    PYTHONPATH=src:. uvicorn server.app:app --port 8000
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from strawberry.fastapi.router import GraphQLRouter

from skillforge import Platform
from skillforge.library import permission_diff
from skillforge.packages import load_package
from skillforge.validate_pkg import validate_package

from .schema import run_type, schema, skill_type

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# Request models live at module level: FastAPI resolves handler
# annotations from module globals, so models defined inside the app
# factory would be misread as query parameters.
class RunRequest(BaseModel):
    task: str
    provider: str = "stub-pro"
    auto_approve: bool = True
    pin_skill: str | None = None


class CreateRequest(BaseModel):
    description: str
    demonstration: dict | None = None


class ApproveRequest(BaseModel):
    approve: bool
    lifecycle: str = "shadow"


def default_platform() -> Platform:
    data_dir = os.environ.get("SKILLFORGE_DATA_DIR",
                              os.path.join(REPO_ROOT, "data"))
    return Platform([os.path.join(REPO_ROOT, "library")], data_dir)


def create_app(platform: Platform | None = None) -> FastAPI:
    plat = platform or default_platform()
    app = FastAPI(title="SkillForge", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])
    app.state.platform = plat
    app.state.runs: dict = {}
    app.state.pending_drafts: dict = {}

    async def context_getter():
        return {"platform": plat, "runs": app.state.runs}

    app.include_router(GraphQLRouter(schema, context_getter=context_getter),
                       prefix="/graphql")

    # ------------------------------------------------------------ REST
    @app.get("/health")
    def health():
        return {"status": "ok", "skills": len(plat.library),
                "library_errors": plat.library.load_errors,
                "providers": ["stub-pro", "stub-basic"],
                "audit_chain_valid": plat.audit.verify_chain()}

    @app.get("/library")
    def library_json():
        return [skill_type(p).__dict__ for p in plat.library.all()]

    @app.post("/runs")
    def trigger_run(req: RunRequest):
        approver = (lambda step, record: True) if req.auto_approve else \
            (lambda step, record: step.action != "publish")
        pins = (req.pin_skill,) if req.pin_skill else ()
        bundle = plat.run_task(req.task, provider=req.provider,
                               approver=approver, pins=pins)
        run_id = uuid.uuid4().hex[:12]
        app.state.runs[run_id] = bundle
        out = run_type(bundle).__dict__
        out["run_id"] = run_id
        out["traces"] = [t.__dict__ for t in run_type(bundle).traces]
        return out

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        bundle = app.state.runs.get(run_id)
        if bundle is None:
            raise HTTPException(404, "unknown run")
        out = run_type(bundle).__dict__
        out["traces"] = [t.__dict__ for t in run_type(bundle).traces]
        return out

    @app.get("/episodes")
    def episodes(limit: int = 50):
        return plat.episodes.all()[-limit:]

    @app.post("/import")
    async def import_package(file: UploadFile = File(...)):
        suffix = ".zip" if (file.filename or "").endswith(".zip") else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as fh:
            fh.write(await file.read())
            path = fh.name
        try:
            if suffix == ".zip":
                result = plat.library.import_package(path)
            else:
                raise HTTPException(400, "upload a .zip of one package folder")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, str(exc))
        return result

    @app.get("/export/{name}")
    def export_package(name: str, portable: bool = False):
        dest = os.path.join(tempfile.mkdtemp(), f"{name}.zip")
        try:
            plat.library.export_package(name, dest, portable=portable)
        except Exception as exc:
            raise HTTPException(404, str(exc))
        return FileResponse(dest, filename=f"{name}.zip",
                            media_type="application/zip")

    # -------------------------------------------- staged creation gate
    @app.post("/skills/draft")
    def draft_skill(req: CreateRequest):
        """Stage 1 of creation: draft + validate + trial. Nothing is
        registered; the response is what a human approves."""
        creator = plat.creator()
        draft_dir = creator.draft_from_description(
            req.description, req.demonstration)
        pkg = load_package(draft_dir)
        report = validate_package(draft_dir)
        if not report.valid:
            return JSONResponse(status_code=422,
                                content={"stage": "validation",
                                         "errors": report.errors})
        trial_platform = plat.ephemeral(
            library_roots=[os.path.dirname(draft_dir)])
        trial = trial_platform.evaluator().run_package(
            trial_platform.library.get(pkg.name))
        draft_id = uuid.uuid4().hex[:12]
        app.state.pending_drafts[draft_id] = {
            "dir": draft_dir, "name": pkg.name, "trial": trial.to_dict()}
        return {"draft_id": draft_id, "skill": pkg.name,
                "permissions": permission_diff(pkg)["summary_lines"],
                "trial": trial.to_dict()}

    @app.post("/skills/{draft_id}/decide")
    def decide_draft(draft_id: str, req: ApproveRequest):
        """Stage 2: the human gate. Approval registers the draft in
        the requested lifecycle state (shadow by default)."""
        pending = app.state.pending_drafts.pop(draft_id, None)
        if pending is None:
            raise HTTPException(404, "unknown or already-decided draft")
        if not req.approve:
            plat.audit.append("creation_denied",
                              {"skill": pending["name"], "actor": "api"})
            return {"registered": False, "skill": pending["name"]}
        import shutil
        from skillforge.library import write_provenance
        dest = os.path.join(plat.library.roots[0], pending["name"])
        if os.path.exists(dest):
            raise HTTPException(409, f"skill {pending['name']} already exists")
        shutil.copytree(pending["dir"], dest)
        write_provenance(dest, {
            "author": "api", "origin": "dynamic-creation",
            "trial": pending["trial"]})
        plat.library.reload()
        if plat.library.get(pending["name"]).lifecycle != req.lifecycle:
            plat.library.set_lifecycle(pending["name"], req.lifecycle,
                                       actor="api")
        plat.audit.append("created", {"skill": pending["name"],
                                      "actor": "api",
                                      "lifecycle": req.lifecycle})
        return {"registered": True, "skill": pending["name"],
                "lifecycle": req.lifecycle}

    return app


app = create_app()
