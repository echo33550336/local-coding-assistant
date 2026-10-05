from __future__ import annotations

import difflib
import asyncio
import hashlib
import json
import os
import secrets
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
if os.name == "nt":
    SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "StackLamp"
else:
    SETTINGS_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "stacklamp"
LOCAL_SETTINGS_PATH = SETTINGS_DIR / "settings.json"
PUBLIC_MODE = os.environ.get("APP_MODE", "local").strip().lower() == "public"
SESSION_TOKEN = secrets.token_urlsafe(32)
LOCAL_STATE: dict[str, Path | None] = {"workspace": None}
LOCAL_LOCK = threading.Lock()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
AUTH_READY = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
QUOTA_READY = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT") or
                      (Path(tempfile.gettempdir()) / "zhangdeng-workspaces")).resolve()
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 5000
OMIT_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}
OMIT_NAMES = {".env", ".env.local", ".env.production", ".stacklamp-settings.json", "id_rsa", "id_ed25519", "credentials", "secrets.json"}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".jsonc", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".md", ".mdx", ".txt", ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".xml", ".svg", ".sh", ".bat", ".ps1", ".sql", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".ex", ".exs", ".vue", ".svelte", ".astro", ".graphql", ".gql",
    ".dockerfile", ".makefile", ".gitignore", ".editorconfig",
}

app = FastAPI(title="栈灯 AI 编程助手",
              openapi_url=None if PUBLIC_MODE else "/openapi.json",
              docs_url=None if PUBLIC_MODE else "/docs",
              redoc_url=None if PUBLIC_MODE else "/redoc")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
JANITOR_TASK: asyncio.Task | None = None


@app.middleware("http")
async def protect_public_writes(request: Request, call_next):
    if not PUBLIC_MODE and (request.url.hostname or "").lower() not in {"127.0.0.1", "localhost"}:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Local access only", status_code=403)
    if PUBLIC_MODE and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        host = request.headers.get("host", "").lower()
        try:
            same_origin = bool(origin and host and httpx.URL(origin).netloc.lower() == host)
        except ValueError:
            same_origin = False
        if not same_origin:
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse("Cross-site request rejected", status_code=403)
    return await call_next(request)


def remove_expired_workspaces() -> None:
    if not PUBLIC_MODE:
        return
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    expiry = __import__("time").time() - 24 * 60 * 60
    for entry in WORKSPACE_ROOT.iterdir():
        try:
            if entry.is_dir() and entry.stat().st_mtime < expiry:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            continue


async def workspace_janitor() -> None:
    while True:
        await asyncio.sleep(60 * 60)
        await asyncio.to_thread(remove_expired_workspaces)


@app.on_event("startup")
async def start_workspace_janitor() -> None:
    global JANITOR_TASK
    if PUBLIC_MODE:
        remove_expired_workspaces()
        JANITOR_TASK = asyncio.create_task(workspace_janitor())


@app.on_event("shutdown")
async def stop_workspace_janitor() -> None:
    if JANITOR_TASK:
        JANITOR_TASK.cancel()


class WorkspaceRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    files: list[str] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=300_000)
    expected_hash: str = Field(min_length=64, max_length=64)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)


class VerifyEmail(BaseModel):
    token_hash: str = Field(min_length=16, max_length=500)
    type: str = Field(pattern="^(signup|email)$")


class LocalSettingsRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200)


def get_model_settings() -> dict[str, str]:
    saved: dict[str, Any] = {}
    if not PUBLIC_MODE:
        try:
            saved = json.loads(LOCAL_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError, AttributeError):
            saved = {}
    if not isinstance(saved, dict):
        saved = {}
    env_key = os.environ.get("MODEL_API_KEY", os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    api_key = str(saved.get("api_key", saved.get("deepseek_api_key", ""))).strip() or env_key
    source = "local settings" if saved.get("api_key") or saved.get("deepseek_api_key") else ("environment" if env_key else "")
    return {
        "api_key": api_key,
        "api_key_source": source,
        "base_url": str(saved.get("base_url") or os.environ.get("MODEL_BASE_URL", os.environ.get("DEEPSEEK_BASE_URL", ""))).strip(),
        "model": str(saved.get("model") or os.environ.get("MODEL_NAME", os.environ.get("DEEPSEEK_MODEL", ""))).strip(),
    }


def get_model_name() -> str:
    return get_model_settings()["model"]


def require_local_session(request: Request) -> None:
    token = request.headers.get("x-local-session")
    if not token or not secrets.compare_digest(token, SESSION_TOKEN):
        raise HTTPException(status_code=403, detail="本地会话校验失败，请刷新页面")


def current_user(request: Request, response: Response) -> dict[str, Any]:
    if not PUBLIC_MODE:
        require_local_session(request)
        return {"id": "local", "email": "本机用户"}
    if not AUTH_READY:
        raise HTTPException(status_code=503, detail="服务端尚未配置登录服务")
    token = request.cookies.get("zd_access")
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        auth_response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=8,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法验证登录状态")
    if auth_response.status_code != 200:
        refresh_token = request.cookies.get("zd_refresh")
        if not refresh_token:
            raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
        try:
            refreshed = httpx.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
                json={"refresh_token": refresh_token}, timeout=8,
            )
        except httpx.HTTPError:
            raise HTTPException(status_code=503, detail="暂时无法刷新登录状态")
        if refreshed.status_code != 200:
            raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
        data = refreshed.json()
        token = data.get("access_token", "")
        response.set_cookie("zd_access", token, httponly=True, secure=True, samesite="lax",
                            max_age=min(int(data.get("expires_in", 3600)), 3600), path="/")
        response.set_cookie("zd_refresh", data.get("refresh_token", refresh_token), httponly=True,
                            secure=True, samesite="lax", max_age=60 * 60 * 24 * 30, path="/")
        try:
            auth_response = httpx.get(
                f"{SUPABASE_URL}/auth/v1/user",
                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
                timeout=8,
            )
        except httpx.HTTPError:
            raise HTTPException(status_code=503, detail="暂时无法验证登录状态")
        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = auth_response.json()
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="登录状态无效")
    return user


def get_workspace(user_id: str, *, required: bool = True) -> Path | None:
    if user_id == "local":
        path = LOCAL_STATE["workspace"]
    else:
        try:
            stable_id = str(uuid.UUID(user_id))
        except ValueError:
            raise HTTPException(status_code=401, detail="用户身份无效")
        path = WORKSPACE_ROOT / stable_id
        if not path.is_dir():
            path = None
        elif path:
            try:
                os.utime(path, None)
            except OSError:
                pass
    if path is None and required:
        raise HTTPException(status_code=400, detail="请先上传项目 ZIP 文件")
    return path


def safe_file(base: Path, relative: str, *, must_exist: bool = True) -> Path:
    candidate = PurePosixPath(relative)
    if (not relative or candidate.is_absolute() or ".." in candidate.parts
            or any("\\" in part or ":" in part for part in candidate.parts)):
        raise HTTPException(status_code=400, detail="无效的项目内路径")
    target = base.joinpath(*candidate.parts)
    cursor = base
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise HTTPException(status_code=400, detail="暂不支持通过符号链接访问文件")
    try:
        resolved = target.resolve(strict=must_exist)
        resolved.relative_to(base.resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="路径超出项目目录")
    return resolved


def is_allowed_text(path: Path) -> bool:
    low = path.name.lower()
    if (low in OMIT_NAMES or low.startswith(".env")
            or low.endswith((".pem", ".key", ".p12", ".pfx", ".sqlite", ".db"))):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES or low in {
        "dockerfile", "makefile", "justfile", ".gitignore", ".editorconfig"
    }


def list_files(base: Path, *, root: Path | None = None) -> list[str]:
    found: list[str] = []
    for current, dirs, names in os.walk(root or base, followlinks=False):
        dirs[:] = [d for d in dirs if d not in OMIT_DIRS and not (Path(current) / d).is_symlink()]
        for name in names:
            file_path = Path(current) / name
            if file_path.is_symlink() or not is_allowed_text(file_path):
                continue
            try:
                if file_path.stat().st_size <= 300_000:
                    found.append(file_path.relative_to(base).as_posix())
            except OSError:
                continue
    return sorted(found)


def expand_selected_files(base: Path, paths: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for relative in dict.fromkeys(paths):
        target = safe_file(base, relative)
        if target.is_dir():
            candidates = list_files(base, root=target)
        elif target.is_file() and is_allowed_text(target) and target.stat().st_size <= 300_000:
            candidates = [target.relative_to(base).as_posix()]
        else:
            continue
        for candidate in candidates:
            if candidate not in seen:
                expanded.append(candidate)
                seen.add(candidate)
    return sorted(expanded)


def replace_workspace(user_id: str, extracted: Path) -> None:
    if user_id == "local":
        with LOCAL_LOCK:
            LOCAL_STATE["workspace"] = extracted
        return
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    target = get_workspace(user_id, required=False)
    final = WORKSPACE_ROOT / str(uuid.UUID(user_id))
    if target is not None:
        target_resolved = target.resolve()
        if target_resolved.parent != WORKSPACE_ROOT:
            raise HTTPException(status_code=500, detail="工作区路径校验失败")
        shutil.rmtree(target_resolved)
    shutil.move(str(extracted), str(final))


def supabase_headers() -> dict[str, str]:
    if not QUOTA_READY:
        raise HTTPException(status_code=503, detail="服务端尚未配置用量数据库")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def read_account(user_id: str) -> dict[str, Any]:
    if user_id == "local":
        return {"plan": "local", "subscription_status": "active", "requests_used": 0,
                "monthly_request_limit": None, "period_end": None}
    headers = supabase_headers()
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"select": "plan,subscription_status,requests_used,monthly_request_limit,period_end",
                    "id": f"eq.{user_id}"},
            headers=headers, timeout=8,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法读取账号用量")
    if response.status_code >= 300:
        raise HTTPException(status_code=503, detail="用量数据库暂时不可用")
    rows = response.json()
    if not rows:
        return {"plan": "free", "subscription_status": "free", "requests_used": 0,
                "monthly_request_limit": 20, "period_end": None}
    return rows[0]


def reserve_request(user_id: str) -> dict[str, Any]:
    if user_id == "local":
        return {"allowed": True, "requests_used": 0, "monthly_request_limit": None,
                "plan": "local", "subscription_status": "active"}
    headers = supabase_headers()
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/rest/v1/rpc/reserve_ai_request",
            headers=headers,
            json={"p_user_id": user_id},
            timeout=8,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法确认 AI 使用额度")
    if response.status_code >= 300:
        raise HTTPException(status_code=503, detail="用量额度服务暂时不可用")
    data = response.json()
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict) or "allowed" not in data:
        raise HTTPException(status_code=503, detail="用量额度服务返回无效结果")
    if not data["allowed"]:
        raise HTTPException(status_code=429, detail="本月 AI 使用额度已用完，请稍后再试或升级套餐")
    return data


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/auth/config")
def auth_config():
    return {"public_mode": PUBLIC_MODE,
            "auth_enabled": (AUTH_READY and QUOTA_READY) if PUBLIC_MODE else False,
            "model": get_model_name()}


@app.post("/api/auth/register")
def register(credentials: Credentials):
    if not PUBLIC_MODE or not AUTH_READY:
        raise HTTPException(status_code=404, detail="注册服务未启用")
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/signup",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": credentials.email, "password": credentials.password},
            timeout=12,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法连接注册服务")
    if response.status_code >= 400:
        message = response.json().get("msg") or response.json().get("message") or "注册失败，请检查邮箱或稍后重试"
        raise HTTPException(status_code=400, detail=message[:300])
    data = response.json()
    if data.get("access_token"):
        return _set_auth_cookie(data)
    return {"ok": True, "confirmation_required": True, "message": "请查看邮箱并完成验证后登录"}


@app.post("/api/auth/login")
def login(credentials: Credentials):
    if not PUBLIC_MODE or not AUTH_READY:
        raise HTTPException(status_code=404, detail="登录服务未启用")
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": credentials.email, "password": credentials.password},
            timeout=12,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法连接登录服务")
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="邮箱或密码不正确，或邮箱尚未验证")
    return _set_auth_cookie(response.json())


@app.post("/api/auth/verify")
def verify_email(request: VerifyEmail):
    if not PUBLIC_MODE or not AUTH_READY:
        raise HTTPException(status_code=404, detail="邮箱验证未启用")
    try:
        response = httpx.post(
            f"{SUPABASE_URL}/auth/v1/verify",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"token_hash": request.token_hash, "type": request.type},
            timeout=12,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="暂时无法验证邮箱")
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="邮箱验证链接已失效，请重新注册或登录")
    return _set_auth_cookie(response.json())


def _set_auth_cookie(data: dict[str, Any]) -> dict[str, Any]:
    token = data.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="登录服务没有返回有效会话")
    # Cookies are Secure in public mode; the production site must use HTTPS.
    from fastapi.responses import JSONResponse
    result = JSONResponse({"ok": True, "expires_in": data.get("expires_in", 3600)})
    result.set_cookie("zd_access", token, httponly=True, secure=True, samesite="lax",
                      max_age=min(int(data.get("expires_in", 3600)), 3600), path="/")
    if data.get("refresh_token"):
        result.set_cookie("zd_refresh", data["refresh_token"], httponly=True, secure=True,
                          samesite="lax", max_age=60 * 60 * 24 * 30, path="/")
    return result


@app.post("/api/auth/logout")
def logout(request: Request):
    from fastapi.responses import JSONResponse
    token = request.cookies.get("zd_access")
    if token and AUTH_READY:
        try:
            httpx.post(f"{SUPABASE_URL}/auth/v1/logout",
                       headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
                       timeout=5)
        except httpx.HTTPError:
            pass
    result = JSONResponse({"ok": True})
    result.delete_cookie("zd_access", path="/")
    result.delete_cookie("zd_refresh", path="/")
    return result


@app.get("/api/me")
def me(user: dict[str, Any] = Depends(current_user)):
    account = read_account(user["id"])
    base = get_workspace(user["id"], required=False)
    return {"id": user["id"], "email": user.get("email", ""), "account": account,
            "workspace": base.name if base else None,
            "files": list_files(base) if base else []}


@app.get("/api/session")
def get_session():
    if PUBLIC_MODE:
        return {"public_mode": True,
                "model": get_model_name()}
    return {"token": SESSION_TOKEN, "public_mode": False,
            "model": get_model_name()}


@app.get("/api/settings")
def get_local_settings(user: dict[str, Any] = Depends(current_user)):
    if PUBLIC_MODE:
        raise HTTPException(status_code=404, detail="本机密钥设置仅在本地模式下可用")
    settings = get_model_settings()
    return {"api_key_configured": bool(settings["api_key"]), "api_key_source": settings["api_key_source"],
            "base_url": settings["base_url"], "model": settings["model"]}


@app.post("/api/settings")
def save_local_settings(request: LocalSettingsRequest,
                        user: dict[str, Any] = Depends(current_user)):
    if PUBLIC_MODE:
        raise HTTPException(status_code=404, detail="本机密钥设置仅在本地模式下可用")
    api_key = request.api_key.strip()
    if len(api_key) < 8:
        raise HTTPException(status_code=400, detail="请填写有效的个人 API 密钥")
    base_url = request.base_url.strip().rstrip("/")
    model = request.model.strip()
    if not base_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=400, detail="接口地址需以 http:// 或 https:// 开头")
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = LOCAL_SETTINGS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps({"api_key": api_key, "base_url": base_url, "model": model}), encoding="utf-8")
    try:
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(temp_path, LOCAL_SETTINGS_PATH)
    os.environ["MODEL_API_KEY"] = api_key
    os.environ["MODEL_BASE_URL"] = base_url
    os.environ["MODEL_NAME"] = model
    return {"api_key_configured": True, "api_key_source": "local settings",
            "base_url": base_url, "model": model}


@app.post("/api/pick-folder")
def pick_folder(user: dict[str, Any] = Depends(current_user)):
    if PUBLIC_MODE:
        raise HTTPException(status_code=404, detail="公网版请上传项目 ZIP 文件")
    import tkinter as tk
    from tkinter import filedialog
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title="选择要交给本地编程助手处理的项目文件夹")
        root.destroy()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"无法打开文件夹选择器：{exc}")
    if not chosen:
        return {"cancelled": True}
    path = Path(chosen).resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="所选路径不是文件夹")
    LOCAL_STATE["workspace"] = path
    return {"path": path.name, "files": list_files(path)}


@app.post("/api/workspace/upload")
async def upload_workspace(file: UploadFile, user: dict[str, Any] = Depends(current_user)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 项目压缩包")
    archive_path: Path | None = None
    extract_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="zd-upload-", suffix=".zip", delete=False) as stream:
            archive_path = Path(stream.name)
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="压缩包不能超过 25 MB")
                stream.write(chunk)
        extract_path = Path(tempfile.mkdtemp(prefix="zd-project-"))
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_FILES:
                raise HTTPException(status_code=413, detail="项目文件数量超过 5000 个")
            total_size = sum(item.file_size for item in members)
            if total_size > MAX_UNPACKED_BYTES:
                raise HTTPException(status_code=413, detail="解压后的项目不能超过 100 MB")
            for item in members:
                name = item.filename.replace("\\", "/")
                relative = PurePosixPath(name)
                if (not name or relative.is_absolute() or ".." in relative.parts
                        or any(":" in part for part in relative.parts)):
                    raise HTTPException(status_code=400, detail="压缩包中包含不安全的文件路径")
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    continue
                parts = relative.parts
                if any(part in OMIT_DIRS or part.lower().startswith(".env") for part in parts):
                    continue
                if item.is_dir():
                    continue
                target = extract_path.joinpath(*parts)
                resolved = target.resolve()
                try:
                    resolved.relative_to(extract_path.resolve())
                except ValueError:
                    raise HTTPException(status_code=400, detail="压缩包文件超出了项目目录")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        # Many ZIP tools add one enclosing project directory; unwrap it for a cleaner workspace.
        children = list(extract_path.iterdir())
        if len(children) == 1 and children[0].is_dir():
            nested = children[0]
            for child in list(nested.iterdir()):
                child.replace(extract_path / child.name)
            nested.rmdir()
        replace_workspace(user["id"], extract_path)
        extract_path = None
        base = get_workspace(user["id"])
        return {"path": Path(file.filename).stem, "files": list_files(base)}
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="无法读取 ZIP 压缩包")
    finally:
        await file.close()
        if archive_path:
            archive_path.unlink(missing_ok=True)
        if extract_path and extract_path.exists():
            shutil.rmtree(extract_path, ignore_errors=True)


@app.post("/api/workspace")
def set_workspace(request: WorkspaceRequest, user: dict[str, Any] = Depends(current_user)):
    if PUBLIC_MODE:
        raise HTTPException(status_code=404, detail="公网版请上传项目 ZIP 文件")
    path = Path(request.path).expanduser().resolve()
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="文件夹不存在")
    LOCAL_STATE["workspace"] = path
    return {"path": path.name, "files": list_files(path)}


@app.get("/api/files")
def files(user: dict[str, Any] = Depends(current_user)):
    base = get_workspace(user["id"], required=False)
    return {"path": base.name if base else None, "files": list_files(base) if base else []}


@app.get("/api/file")
def read_file(path: str, user: dict[str, Any] = Depends(current_user)):
    base = get_workspace(user["id"])
    target = safe_file(base, path)
    if not is_allowed_text(target) or target.stat().st_size > 300_000:
        raise HTTPException(status_code=400, detail="文件类型不支持或文件过大")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是 UTF-8 文本")
    return {"path": path, "content": content, "hash": hashlib.sha256(content.encode()).hexdigest()}


@app.post("/api/chat")
def chat(request: ChatRequest, user: dict[str, Any] = Depends(current_user)):
    model_settings = get_model_settings()
    api_key = model_settings["api_key"]
    if not api_key:
        raise HTTPException(status_code=503, detail="请先在设置中填写你的个人 API 密钥")
    if not model_settings["base_url"] or not model_settings["model"]:
        raise HTTPException(status_code=503, detail="请先填写 API 接口地址和模型名称")
    base = get_workspace(user["id"])
    included: list[dict[str, str]] = []
    for relative in expand_selected_files(base, request.files):
        target = safe_file(base, relative)
        if not is_allowed_text(target) or target.stat().st_size > 120_000:
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        included.append({"path": relative, "content": content})
        if sum(len(item["content"].encode("utf-8")) for item in included) > 500_000:
            included.pop()
            break
    quota = reserve_request(user["id"])
    model = model_settings["model"]
    effort = os.environ.get("MODEL_REASONING_EFFORT", os.environ.get("DEEPSEEK_REASONING_EFFORT", "low"))
    instructions = (
        "你是栈灯，一名熟悉中国大陆软件开发场景的中文 AI 编程搭档。默认使用简体中文，表达直接、清楚、务实，像和同事做代码评审；保留常见英文技术术语。"
        "先理解用户要解决的问题，再结合已提供的文件给出可执行的方案。信息不足且会影响实现时再提问；不要空泛寒暄、夸张承诺或重复用户的话。"
        "必须只输出一个 JSON 对象，结构为 {\"message\":\"简体中文说明\",\"edits\":[{\"path\":\"项目相对路径\",\"content\":\"修改后的完整文件内容\"}]}. "
        "说明改了什么，以及需要用户留意的配置或边界。无需修改时 edits 为空。不要添加 Markdown 代码围栏。只修改用户提供的文件；不执行命令，不捏造文件内容。"
    )
    payload = {"request": request.message, "files": included}

    def sse(event: dict[str, Any]) -> str:
        return "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"

    def generate():
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=model_settings["base_url"],
            )
            stream = client.responses.create(
                model=model,
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
                stream=True,
                max_output_tokens=4000,
                text={"format": {"type": "json_object"}},
                reasoning={"effort": effort},
            )
            pieces: list[str] = []
            for event in stream:
                if event.type == "response.output_text.delta":
                    pieces.append(event.delta)
                    yield sse({"type": "delta", "text": event.delta})
            parsed = json.loads("".join(pieces).strip())
            if not isinstance(parsed, dict) or not isinstance(parsed.get("edits", []), list):
                raise ValueError("响应结构不正确")
            edits = []
            permitted_paths = {item["path"] for item in included}
            for edit in parsed.get("edits", []):
                relative = str(edit["path"])
                target = safe_file(base, relative)
                if relative not in permitted_paths or not is_allowed_text(target):
                    continue
                old = target.read_text(encoding="utf-8")
                new = str(edit["content"])
                if len(new.encode("utf-8")) > 300_000:
                    continue
                edits.append({
                    "path": relative, "before": old, "content": new,
                    "hash": hashlib.sha256(old.encode()).hexdigest(),
                    "diff": "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                           fromfile=relative, tofile=relative)),
                })
            message = str(parsed.get("message", "已生成建议。"))
            message += f"\n\n本月已使用 {quota.get('requests_used', '—')} 次 AI 请求。"
            yield sse({"type": "result", "message": message, "edits": edits,
                       "quota": quota})
        except Exception:
            # Do not return provider internals, credentials, or raw upstream errors to visitors.
            yield sse({"type": "error", "message": "模型请求暂时失败，请稍后重试。"})

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/apply")
def apply_edit(request: ApplyRequest, user: dict[str, Any] = Depends(current_user)):
    base = get_workspace(user["id"])
    target = safe_file(base, request.path)
    if not is_allowed_text(target):
        raise HTTPException(status_code=400, detail="文件类型不支持")
    current = target.read_text(encoding="utf-8")
    current_hash = hashlib.sha256(current.encode()).hexdigest()
    if not secrets.compare_digest(current_hash, request.expected_hash):
        raise HTTPException(status_code=409, detail="文件已变化，请重新读取后再应用")
    target.write_text(request.content, encoding="utf-8", newline="")
    return {"ok": True, "hash": hashlib.sha256(request.content.encode()).hexdigest()}
