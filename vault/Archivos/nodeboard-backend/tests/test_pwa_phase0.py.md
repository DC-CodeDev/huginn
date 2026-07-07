import importlib
import json
import shutil
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import anyio
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "public"


@pytest.fixture()
def static_build(tmp_path):
    backup_dir = None
    if STATIC_DIR.exists():
        backup_dir = tmp_path / "static-backup"
        shutil.move(str(STATIC_DIR), str(backup_dir))

    (STATIC_DIR / "assets").mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "icons").mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "index.html").write_text(
        "<!doctype html><html><body><div id='app'>Huginn</div></body></html>",
        encoding="utf-8",
    )
    (STATIC_DIR / "assets" / "app-12345678.js").write_text(
        "console.log('huginn');",
        encoding="utf-8",
    )
    shutil.copy2(PUBLIC_DIR / "manifest.webmanifest", STATIC_DIR / "manifest.webmanifest")
    shutil.copy2(PUBLIC_DIR / "offline.html", STATIC_DIR / "offline.html")
    shutil.copy2(PUBLIC_DIR / "apple-touch-icon.png", STATIC_DIR / "apple-touch-icon.png")
    shutil.copy2(PUBLIC_DIR / "favicon.ico", STATIC_DIR / "favicon.ico")
    for icon in (PUBLIC_DIR / "icons").iterdir():
        shutil.copy2(icon, STATIC_DIR / "icons" / icon.name)
    (STATIC_DIR / "sw.js").write_text(
        "self.addEventListener('fetch', () => {});",
        encoding="utf-8",
    )

    try:
        yield STATIC_DIR
    finally:
        if STATIC_DIR.exists():
            shutil.rmtree(STATIC_DIR)
        if backup_dir is not None and backup_dir.exists():
            shutil.move(str(backup_dir), str(STATIC_DIR))


def _load_main(monkeypatch, tmp_path, *, environment="development", cookie_secure=None):
    monkeypatch.setenv("NODEBOARD_DB", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("ENVIRONMENT", environment)
    if cookie_secure is None:
        monkeypatch.delenv("COOKIE_SECURE", raising=False)
    else:
        monkeypatch.setenv("COOKIE_SECURE", cookie_secure)

    import app.main as main

    main = importlib.reload(main)

    @asynccontextmanager
    async def _noop_lifespan(_):
        yield

    main.app.router.lifespan_context = _noop_lifespan
    return main


@dataclass
class AppResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")


def _mock_google_identity(monkeypatch, main):
    class Identity:
        email = "user@example.com"
        name = "User"
        avatar_url = "https://example.com/avatar.png"

    monkeypatch.setattr(main.auth, "verify_google_token", lambda _: Identity())


def _db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return testing_session()


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} no es un PNG valido")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def _request(main, method, path, *, json_body=None, headers=None, base_url="http://testserver"):
    body = b""
    header_list: list[tuple[bytes, bytes]] = []
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        header_list.append((b"content-type", b"application/json"))
    for key, value in (headers or {}).items():
        header_list.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    async def run() -> AppResponse:
        messages: list[dict] = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scheme = "https" if base_url.startswith("https://") else "http"
        host = base_url.split("://", 1)[1]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", host.encode("latin-1")), *header_list],
            "client": ("testclient", 50000),
            "server": (host, 443 if scheme == "https" else 80),
        }
        await main.app(scope, receive, send)

        start = next(message for message in messages if message["type"] == "http.response.start")
        chunks = [message.get("body", b"") for message in messages if message["type"] == "http.response.body"]
        response_headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in start["headers"]
        }
        return AppResponse(
            status_code=start["status"],
            headers=response_headers,
            body=b"".join(chunks),
        )

    return anyio.run(run)


def _login(main, base_url="http://testserver"):
    return _request(
        main,
        "POST",
        "/api/auth/login",
        json_body={"code": "oauth-code"},
        base_url=base_url,
    )


def test_root_and_spa_routes_return_index(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path)

    root = _request(main, "GET", "/")
    spa = _request(main, "GET", "/boards/123")

    assert root.status_code == 200
    assert "Huginn" in root.text
    assert spa.status_code == 200
    assert spa.text == root.text


def test_api_and_missing_files_do_not_fall_back_to_index(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path)

    api_missing = _request(main, "GET", "/api/ruta-inexistente")
    js_missing = _request(main, "GET", "/archivo-inexistente.js")

    assert api_missing.status_code == 404
    assert "Huginn" not in api_missing.text
    assert js_missing.status_code == 404
    assert _request(main, "GET", "/manifest.webmanifest").status_code == 200
    assert _request(main, "GET", "/sw.js").status_code == 200


def test_existing_asset_is_served(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path)

    response = _request(main, "GET", "/assets/app-12345678.js")

    assert response.status_code == 200
    assert "console.log('huginn');" in response.text
    assert response.headers["content-type"].startswith(("text/javascript", "application/javascript"))


def test_cache_and_security_headers(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path)

    html = _request(main, "GET", "/studios")
    asset = _request(main, "GET", "/assets/app-12345678.js")
    manifest = _request(main, "GET", "/manifest.webmanifest")
    offline = _request(main, "GET", "/offline.html")
    icon = _request(main, "GET", "/icons/icon-192.png")

    assert html.headers["cache-control"] == "no-cache"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert manifest.headers["cache-control"] == "no-cache"
    assert offline.headers["cache-control"] == "no-cache"
    assert icon.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert main._cache_control_for("/api/health", 200, "application/json") == "no-store"
    assert main._cache_control_for("/api/auth/me", 401, "application/json") == "private, no-store"

    expected_security = main._security_headers_for("http")
    for response in (html, asset, manifest, offline, icon):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert "permissions-policy" in response.headers
        assert "strict-transport-security" not in response.headers
    assert expected_security["X-Content-Type-Options"] == "nosniff"
    assert expected_security["X-Frame-Options"] == "DENY"


def test_manifest_and_pwa_assets_are_served_with_expected_metadata(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path)

    manifest = _request(main, "GET", "/manifest.webmanifest")
    sw = _request(main, "GET", "/sw.js")
    offline = _request(main, "GET", "/offline.html")
    icon_192 = _request(main, "GET", "/icons/icon-192.png")
    icon_512 = _request(main, "GET", "/icons/icon-512.png")
    icon_maskable = _request(main, "GET", "/icons/icon-512-maskable.png")
    apple = _request(main, "GET", "/apple-touch-icon.png")
    favicon = _request(main, "GET", "/favicon.ico")

    manifest_json = json.loads(manifest.text)

    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    assert manifest_json["name"] == "Huginn"
    assert manifest_json["short_name"] == "Huginn"
    assert manifest_json["start_url"] == "/"
    assert manifest_json["scope"] == "/"
    assert manifest_json["display"] == "standalone"
    assert manifest_json["theme_color"] == "#0F1117"
    assert manifest_json["background_color"] == "#0F1117"
    assert manifest_json["lang"] == "es"

    icon_purposes = {
        entry.get("src"): entry.get("purpose", "")
        for entry in manifest_json["icons"]
    }
    assert "/icons/icon-192.png" in icon_purposes
    assert "/icons/icon-512.png" in icon_purposes
    assert icon_purposes["/icons/icon-192-maskable.png"] == "maskable"
    assert icon_purposes["/icons/icon-512-maskable.png"] == "maskable"

    assert sw.status_code == 200
    assert sw.headers["content-type"].startswith("application/javascript")
    assert offline.status_code == 200
    assert offline.headers["content-type"].startswith("text/html")
    assert "Huginn está sin conexión" in offline.text
    assert "Reintentar" in offline.text

    for response in (icon_192, icon_512, icon_maskable, apple, favicon):
        assert response.status_code == 200

    assert icon_192.headers["content-type"].startswith("image/png")
    assert icon_512.headers["content-type"].startswith("image/png")
    assert icon_maskable.headers["content-type"].startswith("image/png")
    assert apple.headers["content-type"].startswith("image/png")
    assert favicon.headers["content-type"].startswith(("image/x-icon", "image/vnd.microsoft.icon"))


def test_icon_dimensions_are_real_and_correct():
    icon_specs = {
        PUBLIC_DIR / "icons" / "icon-192.png": (192, 192),
        PUBLIC_DIR / "icons" / "icon-512.png": (512, 512),
        PUBLIC_DIR / "icons" / "icon-192-maskable.png": (192, 192),
        PUBLIC_DIR / "icons" / "icon-512-maskable.png": (512, 512),
        PUBLIC_DIR / "apple-touch-icon.png": (180, 180),
    }

    for path, expected_size in icon_specs.items():
        assert _png_dimensions(path) == expected_size


def test_hsts_only_in_production_over_https(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path, environment="production")

    prod = _request(main, "GET", "/", base_url="https://testserver")
    local_headers = main._security_headers_for("http")
    secure_headers = main._security_headers_for("https")

    assert prod.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    assert "Strict-Transport-Security" not in local_headers
    assert secure_headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_session_cookie_is_secure_in_production(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path, environment="production")
    _mock_google_identity(monkeypatch, main)
    db = _db_session()

    response = main.Response()
    user = main.login(main.schemas.LoginRequest(code="oauth-code"), response, db)

    cookie = response.headers["set-cookie"].lower()
    assert user.email == "user@example.com"
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    db.close()


def test_session_cookie_can_disable_secure_in_development(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path, environment="development", cookie_secure="false")
    _mock_google_identity(monkeypatch, main)
    db = _db_session()

    response = main.Response()
    user = main.login(main.schemas.LoginRequest(code="oauth-code"), response, db)

    cookie = response.headers["set-cookie"].lower()
    assert user.email == "user@example.com"
    assert "httponly" in cookie
    assert "secure" not in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    db.close()


def test_logout_clears_cookie_with_matching_attributes(monkeypatch, tmp_path, static_build):
    main = _load_main(monkeypatch, tmp_path, environment="production")
    _mock_google_identity(monkeypatch, main)
    db = _db_session()

    login_response = main.Response()
    main.login(main.schemas.LoginRequest(code="oauth-code"), login_response, db)
    session_id = login_response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]

    logout = main.Response()
    main.logout(logout, db, session_id=session_id)

    cookie = logout.headers["set-cookie"].lower()
    assert "max-age=0" in cookie
    assert "path=/" in cookie
    assert "samesite=lax" in cookie
    assert "secure" in cookie
    assert "httponly" in cookie
    db.close()
