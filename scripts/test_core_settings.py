"""Phase 10 - no hard-coded credentials: the JWT key and the database URL.

    venv\\Scripts\\python.exe -m scripts.test_core_settings

Offline: no server, no LiveKit, no model; the database is only connected to,
never written. Four parts:

* **source** - no string in `app/` is a PostgreSQL URL with credentials or
  the old public signing key; auth.py and database.py take theirs from
  `app.settings`;
* **rules** - `app.settings` with a controlled lookup: missing values refuse,
  development accepts an explicitly configured key, production refuses the
  public development key, a short key and a misspelt `SMARTHR_ENV`; no
  error message carries a value;
* **auth** - a fresh process given `SMARTHR_SECRET_KEY` signs and verifies
  with exactly that key (environment beats .env.local);
* **startup** - `import app.main` in a fresh process exits non-zero in
  production with the development key, and starts with a strong one.
"""

import ast
import hashlib
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: The key that WAS hard-coded in app/routers/auth.py. Public (it was in the
#: source), so it is written here as the value production must refuse.
OLD_DEV_KEY = "smarthr-development-secret-key"

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


def string_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_source() -> None:
    print("\n1. Source: no credentials in app/")
    offenders_url, offenders_key = [], []
    for path in (ROOT / "app").rglob("*.py"):
        for value in string_constants(path):
            if "postgresql" in value and "@" in value:
                offenders_url.append(path.relative_to(ROOT).as_posix())
            if hashlib.sha256(value.encode()).hexdigest() in {hashlib.sha256(OLD_DEV_KEY.encode()).hexdigest()}:
                offenders_key.append(path.relative_to(ROOT).as_posix())
    check("no PostgreSQL URL with credentials is a string in app/", not offenders_url, str(offenders_url))
    check("the old development signing key is not a string anywhere in app/", not offenders_key, str(offenders_key))

    def assigned(path: Path, name: str) -> ast.AST | None:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
                return node.value
        return None

    key = assigned(ROOT / "app/routers/auth.py", "SECRET_KEY")
    check("auth.py: SECRET_KEY = settings.secret_key(), not a literal",
          isinstance(key, ast.Call) and ast.unparse(key) == "settings.secret_key()", ast.unparse(key) if key else "")
    url = assigned(ROOT / "app/database.py", "DATABASE_URL")
    check("database.py: DATABASE_URL = settings.database_url(), not a literal",
          isinstance(url, ast.Call) and ast.unparse(url) == "settings.database_url()", ast.unparse(url) if url else "")


def test_rules() -> None:
    print("\n2. Rules (controlled configuration, no files read)")
    from app import settings

    real = settings.interview_setting
    config: dict[str, str] = {}
    settings.interview_setting = lambda name, *a, **k: config.get(name)  # type: ignore[assignment]
    strong = secrets.token_urlsafe(48)

    def refused(fn) -> str | None:
        try:
            fn()
        except settings.ConfigurationError as exc:
            return str(exc)
        return None

    try:
        config.clear()
        msg = refused(settings.secret_key)
        check("no SMARTHR_SECRET_KEY -> refused (no default key)", msg is not None and "SMARTHR_SECRET_KEY" in (msg or ""))
        msg = refused(settings.database_url)
        check("no SMARTHR_DATABASE_URL -> refused (no default database)",
              msg is not None and "SMARTHR_DATABASE_URL" in (msg or ""))
        check("SMARTHR_ENV unset -> development", settings.environment() == "development")

        config.update({"SMARTHR_SECRET_KEY": strong, "SMARTHR_DATABASE_URL": "inert-test-database-url"})
        check("the key is returned exactly as configured", settings.secret_key() == strong)
        check("the URL is returned exactly as configured",
              settings.database_url() == "inert-test-database-url")

        config["SMARTHR_SECRET_KEY"] = OLD_DEV_KEY
        check("development: an explicitly configured key is accepted (even the old one)",
              settings.secret_key() == OLD_DEV_KEY)
        check("the old key is recognised as public", settings.is_known_insecure(OLD_DEV_KEY))

        config["SMARTHR_ENV"] = "production"
        msg = refused(settings.secret_key)
        check("production + the public development key -> refused", msg is not None, str(msg))
        check("...and the message does not contain the key", msg is not None and OLD_DEV_KEY not in msg)
        config["SMARTHR_SECRET_KEY"] = "short-but-not-public"
        check("production + a key under 32 characters -> refused", refused(settings.secret_key) is not None)
        config["SMARTHR_SECRET_KEY"] = strong
        check("production + a long random key -> accepted", settings.secret_key() == strong)
        config["SMARTHR_ENV"] = "Production"
        check("SMARTHR_ENV is case-insensitive", settings.environment() == "production")
        config["SMARTHR_ENV"] = "prod"
        msg = refused(settings.secret_key)
        check("a misspelt SMARTHR_ENV is refused, never read as development",
              msg is not None and "SMARTHR_ENV" in (msg or ""), str(msg))
        check("no refusal message carries a configured value",
              all(v not in (msg or "") for v in (strong, "pw-test")))
    finally:
        settings.interview_setting = real  # type: ignore[assignment]


def run(code: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), capture_output=True, text=True,
                          env={**os.environ, **env}, timeout=120)


def test_auth_and_startup() -> None:
    print("\n3. Authentication signs with the configured key")
    key = secrets.token_urlsafe(48)
    probe = (
        "import hashlib, jwt, os\n"
        "from app.routers import auth\n"
        "tok = auth.create_access_token(1, 2)\n"
        "want = os.environ['SMARTHR_SECRET_KEY']\n"
        "print('same', auth.SECRET_KEY == want)\n"
        "print('verifies', jwt.decode(tok, want, algorithms=['HS256'])['sub'] == '1')\n"
        "try:\n"
        "    jwt.decode(tok, 'some-other-key-' + 'x' * 40, algorithms=['HS256']); print('other', True)\n"
        "except jwt.InvalidSignatureError:\n"
        "    print('other', False)\n"
    )
    r = run(probe, SMARTHR_SECRET_KEY=key)
    out = r.stdout.split()
    check("the environment's SMARTHR_SECRET_KEY is the key auth uses (env beats .env.local)",
          r.returncode == 0 and "same" in out and out[out.index("same") + 1] == "True", r.stderr[-300:])
    check("a token it issues verifies with that key", "verifies" in out and out[out.index("verifies") + 1] == "True")
    check("...and not with any other key", "other" in out and out[out.index("other") + 1] == "False")
    check("the key is not printed by the application", key not in r.stdout and key not in r.stderr)

    print("\n4. Startup validation (a fresh `import app.main`, as uvicorn does)")
    r = run("import app.main", SMARTHR_ENV="production", SMARTHR_SECRET_KEY=OLD_DEV_KEY)
    check("production + the development key -> the application does not start",
          r.returncode != 0 and "ConfigurationError" in r.stderr and "SMARTHR_SECRET_KEY" in r.stderr,
          r.stderr[-300:])
    check("...and the refusal does not print the key", OLD_DEV_KEY not in r.stderr and OLD_DEV_KEY not in r.stdout)
    # Production also needs a CORS allow-list since Phase 10 (test_production_config).
    r = run("import app.main; print('started')", SMARTHR_ENV="production", SMARTHR_SECRET_KEY=key,
            SMARTHR_CORS_ORIGINS="https://hr.example.com")
    check("production + a strong key -> starts", r.returncode == 0 and "started" in r.stdout, r.stderr[-300:])
    r = run("import app.main; print('started')")
    check("development with the keys in .env.local -> starts", r.returncode == 0 and "started" in r.stdout,
          r.stderr[-300:])
    r = run("from sqlalchemy import text\nfrom app.database import engine\n"
            "with engine.connect() as c: print('db', c.execute(text('select 1')).scalar())")
    check("the configured database URL connects (read-only SELECT 1)", r.returncode == 0 and "db 1" in r.stdout,
          r.stderr[-300:])
    check("the database URL is not printed", "postgresql" not in r.stdout + r.stderr)


def main() -> int:
    print("SmartHR - core settings: no hard-coded credentials (Phase 10)")
    test_source()
    test_rules()
    test_auth_and_startup()
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
