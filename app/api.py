from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.application.templates import (
    TEMPLATE_DEFINITIONS,
    TemplateValidationError,
    seed_templates,
    validate_template,
)
from app.infrastructure.config import load_dotenv
from app.infrastructure.store import SQLiteStore


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "runtime.db"
WEB_DIST = ROOT / "web" / "dist"
load_dotenv(ROOT / ".env")

app = FastAPI(title="Aex AI 情报管理 API", version="0.1.0", docs_url=None, redoc_url=None)


class DraftUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)
    expected_revision: int = Field(ge=1)


class RevisionCommand(BaseModel):
    expected_revision: int = Field(ge=1)


def _database_path() -> Path:
    value = os.environ.get("RUNTIME_DB_PATH", "").strip()
    return Path(value) if value else DEFAULT_DB


def _open_store() -> SQLiteStore:
    store = SQLiteStore(_database_path())
    seed_templates(store)
    return store


def require_admin(authorization: str | None = Header(default=None)) -> str:
    configured = os.environ.get("ADMIN_API_TOKEN", "").strip()
    if len(configured) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="管理接口尚未配置至少 32 个字符的 ADMIN_API_TOKEN",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理凭据无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "admin"


def _serialize_template(value: dict) -> dict:
    definition = TEMPLATE_DEFINITIONS[str(value["template_id"])]
    return {
        "id": value["template_id"],
        "name": value["name"],
        "description": value["description"],
        "status": "已发布" if value["status"] == "published" else "草稿",
        "updatedAt": value["updated_at"],
        "version": value["published_version"],
        "draftRevision": value["draft_revision"],
        "content": value["draft_content"],
        "allowedVariables": list(definition.allowed_variables),
        "versions": [
            {
                "version": version["version"],
                "content": version["content"],
                "publishedAt": version["published_at"],
                "author": version["created_by"],
            }
            for version in value["versions"]
        ],
    }


def _detail_or_404(store: SQLiteStore, template_id: str) -> dict:
    detail = store.template_detail(template_id)
    if detail is None or template_id not in TEMPLATE_DEFINITIONS:
        raise HTTPException(status_code=404, detail="模板不存在")
    return detail


def _conflict() -> HTTPException:
    return HTTPException(status_code=409, detail="模板已被其他页面修改，请刷新后重试")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data: https:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/admin/session")
def session(_: str = Depends(require_admin)) -> dict:
    return {"authenticated": True}


@app.get("/api/admin/templates")
def list_templates(_: str = Depends(require_admin)) -> list[dict]:
    store = _open_store()
    try:
        return [
            _serialize_template(_detail_or_404(store, str(row["template_id"])))
            for row in store.template_summaries()
        ]
    finally:
        store.close()


@app.get("/api/admin/templates/{template_id}")
def get_template(template_id: str, _: str = Depends(require_admin)) -> dict:
    store = _open_store()
    try:
        return _serialize_template(_detail_or_404(store, template_id))
    finally:
        store.close()


@app.put("/api/admin/templates/{template_id}/draft")
def save_draft(template_id: str, request: DraftUpdate, _: str = Depends(require_admin)) -> dict:
    try:
        content = validate_template(template_id, request.content)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store = _open_store()
    try:
        _detail_or_404(store, template_id)
        result = store.save_template_draft(template_id, content, request.expected_revision)
        if result is None:
            raise _conflict()
        return _serialize_template(result)
    finally:
        store.close()


@app.post("/api/admin/templates/{template_id}/publish")
def publish_template(template_id: str, request: RevisionCommand, admin: str = Depends(require_admin)) -> dict:
    store = _open_store()
    try:
        detail = _detail_or_404(store, template_id)
        try:
            validate_template(template_id, str(detail["draft_content"]))
        except TemplateValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if detail["status"] == "published":
            raise HTTPException(status_code=409, detail="当前草稿与已发布版本一致，无需重复发布")
        result = store.publish_template(template_id, request.expected_revision, admin)
        if result is None:
            raise _conflict()
        return _serialize_template(result)
    finally:
        store.close()


@app.post("/api/admin/templates/{template_id}/versions/{version}/restore")
def restore_version(
    template_id: str,
    version: int,
    request: RevisionCommand,
    _: str = Depends(require_admin),
) -> dict:
    store = _open_store()
    try:
        _detail_or_404(store, template_id)
        result = store.restore_template_version(template_id, version, request.expected_revision)
        if result is None:
            existing = store.connection.execute(
                "SELECT 1 FROM message_template_versions WHERE template_id=? AND version=?",
                (template_id, version),
            ).fetchone()
            if existing is None:
                raise HTTPException(status_code=404, detail="历史版本不存在")
            raise _conflict()
        return _serialize_template(result)
    finally:
        store.close()


if WEB_DIST.exists():
    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        candidate = (WEB_DIST / path).resolve()
        if path and candidate.is_file() and WEB_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
