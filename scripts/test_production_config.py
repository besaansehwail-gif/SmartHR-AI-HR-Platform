"""Phase 10 - production run profiles: worker, backend, CORS, backend URL.

    venv\\Scripts\\python.exe -m scripts.test_production_config

Model-free and LiveKit-free. The launchers are exercised with LiveKit's
`run_app` and `uvicorn.run` replaced by recorders, and any subprocess that
could reach LiveKit gets an unreachable LIVEKIT_URL, so a bug here cannot
start a real worker. Two throwaway backends on 8053/8054 (no model) prove the
CORS allow-list with real preflight requests.
"""

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

passed = 0
failed: list[str] = []
STRONG = secrets.token_urlsafe(48)
DEAD_LIVEKIT = "ws://127.0.0.1:9"   # nothing listens: a real worker could never register


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


class Config:
    """Replace the env -> .env.local -> .env lookup with a dict, for one block."""

    def __init__(self, **values: str):
        self.values = values

    def __enter__(self):
        from app import serve, settings
        from app.ai.interview import production
        self.targets = [settings, production, serve]
        self.saved = [m.interview_setting for m in self.targets]
        for m in self.targets:
            m.interview_setting = lambda name, *a, **k: self.values.get(name)  # type: ignore[assignment]
        return self

    def __exit__(self, *_):
        for m, fn in zip(self.targets, self.saved):
            m.interview_setting = fn  # type: ignore[assignment]


def refused(fn) -> str | None:
    from app.ai.interview.production import WorkerConfigurationError
    from app.settings import ConfigurationError
    try:
        fn()
    except (ConfigurationError, WorkerConfigurationError) as exc:
        return str(exc)
    return None


def test_cors_rules() -> None:
    print("\n1. CORS allow-list rules")
    from app import settings
    with Config():
        check("development, unset -> ['*'] (unchanged)", settings.cors_origins() == ["*"])
    with Config(SMARTHR_CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:3000"):
        check("development, a list -> that list", settings.cors_origins() == ["http://localhost:3000", "http://127.0.0.1:3000"])
    with Config(SMARTHR_CORS_ORIGINS="*"):
        check("development, '*' -> ['*']", settings.cors_origins() == ["*"])
    prod = {"SMARTHR_ENV": "production"}
    with Config(**prod):
        msg = refused(settings.cors_origins)
        check("production, unset -> refused", msg is not None and "SMARTHR_CORS_ORIGINS" in msg, str(msg))
    with Config(**prod, SMARTHR_CORS_ORIGINS="*"):
        check("production, '*' -> refused", refused(settings.cors_origins) is not None)
    with Config(**prod, SMARTHR_CORS_ORIGINS="https://hr.example.com,*"):
        check("production, a list containing '*' -> refused", refused(settings.cors_origins) is not None)
    with Config(**prod, SMARTHR_CORS_ORIGINS="http://hr.example.com"):
        check("production, plain http to another host -> refused", refused(settings.cors_origins) is not None)
    with Config(**prod, SMARTHR_CORS_ORIGINS="http://localhost:3000"):
        check("production, http://localhost -> allowed (never leaves the machine)",
              settings.cors_origins() == ["http://localhost:3000"])
    with Config(**prod, SMARTHR_CORS_ORIGINS=" https://hr.example.com/ , https://careers.example.com "):
        check("production, https list -> trimmed, trailing slash dropped",
              settings.cors_origins() == ["https://hr.example.com", "https://careers.example.com"])
    for bad in ("hr.example.com", "https://hr.example.com/app", "https://hr.example.com?x=1",
                "ftp://hr.example.com", "https://user@hr.example.com", "https://hr.example.com:99999"):
        with Config(**prod, SMARTHR_CORS_ORIGINS=bad):
            check(f"not an origin -> refused: {bad}", refused(settings.cors_origins) is not None)


def test_backend_url() -> None:
    print("\n2. Worker -> backend URL")
    from app.ai.interview import config
    from app.ai.interview.production import backend_url_problem
    check("development, unset -> fine (default http://127.0.0.1:8000, as before)",
          backend_url_problem(None, production=False) is None)
    check("development, http://127.0.0.1:8000 -> fine", backend_url_problem("http://127.0.0.1:8000", False) is None)
    check("production, unset -> refused (no silent localhost default)",
          "must be set" in (backend_url_problem(None, True) or ""))
    check("production, http to another host -> refused (https required)",
          "https" in (backend_url_problem("http://api.example.com", True) or ""))
    check("production, https -> fine", backend_url_problem("https://api.example.com", True) is None)
    check("production, https with a path prefix -> fine", backend_url_problem("https://example.com/api", True) is None)
    check("production, http://localhost / 127.0.0.1 / [::1] -> fine (loopback)",
          all(backend_url_problem(u, True) is None
              for u in ("http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000")))
    for bad in ("ftp://api.example.com", "https://user:inert@example.com", "https://api.example.com:99999",
                "https://api.example.com/?x=1", "api.example.com"):
        check(f"malformed -> refused: {bad}", backend_url_problem(bad, True) is not None)
    check("...and no refusal repeats a credential in the URL",
          "user:inert" not in (backend_url_problem("https://user:inert@example.com", True) or ""))

    saved = os.environ.get("SMARTHR_INTERVIEW_BACKEND_URL")
    try:
        os.environ["SMARTHR_INTERVIEW_BACKEND_URL"] = "https://api.example.com/"
        check("backend_url() reads SMARTHR_INTERVIEW_BACKEND_URL (trailing slash dropped)",
              config.backend_url() == "https://api.example.com")
        os.environ.pop("SMARTHR_INTERVIEW_BACKEND_URL")
        check("backend_url() unset -> the development default",
              config.backend_url() == config.DEFAULT_BACKEND_URL == "http://127.0.0.1:8000")
    finally:
        if saved is not None:
            os.environ["SMARTHR_INTERVIEW_BACKEND_URL"] = saved


def test_worker_cli() -> None:
    print("\n3. Worker command line in production")
    from app.ai.interview.production import PRODUCTION_ARGS, cli_problem
    check("development: anything goes, e.g. dev --log-level debug (unchanged)",
          cli_problem(["dev", "--log-level", "debug"], production=False) is None)
    check("the production profile is 'start --log-level info'", PRODUCTION_ARGS == ("start", "--log-level", "info"))
    check("...which production accepts", cli_problem(list(PRODUCTION_ARGS), production=True) is None)
    check("production + plain 'start' -> fine (LiveKit's default level is INFO)", cli_problem(["start"], True) is None)
    for cmd in ("dev", "console", "connect", "download-files"):
        check(f"production + '{cmd}' -> refused", cli_problem([cmd], True) is not None)
    check("production + --log-level debug -> refused", cli_problem(["start", "--log-level", "debug"], True) is not None)
    check("production + --log-level=TRACE -> refused", cli_problem(["start", "--log-level=TRACE"], True) is not None)
    check("production + LIVEKIT_LOG_LEVEL=debug -> refused",
          cli_problem(["start"], True, env_log_level="debug") is not None)
    check("production + --log-level warn -> fine", cli_problem(["start", "--log-level", "warn"], True) is None)
    msg = cli_problem(["start", "--api-secret", "inert"], True)
    check("production + --api-secret on the command line -> refused", msg is not None)
    check("...without echoing it", "inert" not in (msg or ""))
    check("production + --api-key=... -> refused", cli_problem(["start", "--api-key=abc"], True) is not None)


def test_worker_profile() -> None:
    print("\n4. The worker's production profile (LiveKit replaced by a recorder)")
    from app.ai.interview import production

    class Voice:
        def __init__(self, missing):
            self.missing = missing

    real_voice = production.voice_settings
    try:
        production.voice_settings = lambda: Voice([])  # type: ignore[assignment]
        with Config(SMARTHR_INTERVIEW_BACKEND_URL="https://api.example.com"):
            check("SMARTHR_ENV not production -> the profile refuses",
                  "SMARTHR_ENV=production" in (refused(production.validate_production) or ""))
        with Config(SMARTHR_ENV="production"):
            check("production, backend URL unset -> refused", refused(production.validate_production) is not None)
        with Config(SMARTHR_ENV="production", SMARTHR_INTERVIEW_BACKEND_URL="http://api.example.com"):
            check("production, http backend URL -> refused", refused(production.validate_production) is not None)
        with Config(SMARTHR_ENV="production", SMARTHR_INTERVIEW_BACKEND_URL="https://api.example.com/"):
            check("production, https backend URL -> valid", production.validate_production() == "https://api.example.com")
        production.voice_settings = lambda: Voice(["LIVEKIT_API_SECRET"])  # type: ignore[assignment]
        with Config(SMARTHR_ENV="production", SMARTHR_INTERVIEW_BACKEND_URL="https://api.example.com"):
            msg = refused(production.validate_production)
            check("production, LiveKit missing -> refused, naming the variable only",
                  msg is not None and "LIVEKIT_API_SECRET" in msg)
    finally:
        production.voice_settings = real_voice  # type: ignore[assignment]

    # main(): validated, then LiveKit's CLI with exactly the production args.
    from livekit.agents import cli as lk_cli
    real_run, seen = lk_cli.run_app, {}
    real_argv = list(sys.argv)
    saved = {k: os.environ.get(k) for k in ("SMARTHR_ENV", "SMARTHR_INTERVIEW_BACKEND_URL", "LIVEKIT_URL")}
    try:
        lk_cli.run_app = lambda server: seen.update(argv=list(sys.argv[1:]), server=server)  # type: ignore[assignment]
        os.environ.update(SMARTHR_ENV="production", SMARTHR_INTERVIEW_BACKEND_URL="https://api.example.com",
                          LIVEKIT_URL=DEAD_LIVEKIT)
        production.main()
        from app.ai.interview.worker import server
        check("main() runs LiveKit's CLI as 'start --log-level info' - never dev, never reload",
              seen.get("argv") == ["start", "--log-level", "info"] and seen.get("server") is server, str(seen))
        import logging

        from app.ai.interview.logging_policy import DropPii
        lk = logging.getLogger("livekit.agents")
        check("...with livekit.agents at INFO and the transcript PII filter installed",
              lk.level == logging.INFO and any(isinstance(f, DropPii) for f in lk.filters))
    finally:
        lk_cli.run_app = real_run  # type: ignore[assignment]
        sys.argv = real_argv
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print("\n5. `worker dev` refused in production (a real process; LiveKit unreachable anyway)")
    r = subprocess.run([sys.executable, "-m", "app.ai.interview.worker", "dev"], cwd=str(ROOT), capture_output=True,
                       text=True, timeout=120,
                       env={**os.environ, "SMARTHR_ENV": "production", "LIVEKIT_URL": DEAD_LIVEKIT,
                            "SMARTHR_INTERVIEW_BACKEND_URL": "https://api.example.com"})
    check("python -m app.ai.interview.worker dev -> exits non-zero before LiveKit starts",
          r.returncode != 0 and "WorkerConfigurationError" in r.stderr and "development command" in r.stderr,
          r.stderr[-300:])
    check("...and printed no credential", all(v not in r.stdout + r.stderr for v in (STRONG,)))


def test_backend_profile() -> None:
    print("\n6. The backend's production profile (uvicorn replaced by a recorder)")
    from app import serve
    with Config():
        opts = serve.uvicorn_options()
        check("reload is False, INFO, 127.0.0.1:8000 by default",
              opts == {"app": "app.main:app", "host": "127.0.0.1", "port": 8000, "reload": False, "log_level": "info"},
              str(opts))
        check("development cannot use the production profile by accident",
              "SMARTHR_ENV=production" in (refused(serve.validate_production) or ""))
    with Config(SMARTHR_BACKEND_PORT="8443", SMARTHR_BACKEND_HOST="0.0.0.0"):
        opts = serve.uvicorn_options()
        check("host and port are configurable; reload stays False",
              opts["port"] == 8443 and opts["host"] == "0.0.0.0" and opts["reload"] is False)
    for bad in ("http", "0", "70000"):
        with Config(SMARTHR_BACKEND_PORT=bad):
            check(f"invalid port refused: {bad}", refused(serve.uvicorn_options) is not None)
    good = dict(SMARTHR_ENV="production", SMARTHR_SECRET_KEY=STRONG,
                SMARTHR_DATABASE_URL="inert-test-database-url", SMARTHR_CORS_ORIGINS="https://hr.example.com")
    with Config(**{k: v for k, v in good.items() if k != "SMARTHR_CORS_ORIGINS"}):
        check("production without a CORS allow-list -> refused before binding",
              "SMARTHR_CORS_ORIGINS" in (refused(serve.validate_production) or ""))
    import uvicorn
    real_run, seen = uvicorn.run, {}
    try:
        uvicorn.run = lambda **kw: seen.update(kw)  # type: ignore[assignment]
        with Config(**good):
            serve.main()
        check("main() calls uvicorn.run with reload=False", seen.get("reload") is False and seen.get("app") == "app.main:app",
              str(seen))
    finally:
        uvicorn.run = real_run  # type: ignore[assignment]
    src = (ROOT / "app/serve.py").read_text(encoding="utf-8")
    check("the backend profile has no way to turn reload on", '"reload": False' in src and "reload=True" not in src)


class Backend:
    def __init__(self, port: int, **env: str):
        self.port, self.env, self.p = port, env, None

    def __enter__(self):
        self.p = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "SMARTHR_LLM_PROVIDER": "none", "LIVEKIT_URL": DEAD_LIVEKIT, **self.env})
        for _ in range(80):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=2)
                return self
            except Exception:
                time.sleep(0.25)
        raise SystemExit("test backend did not start")

    def __exit__(self, *_):
        self.p.terminate()
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()

    def call(self, method: str, path: str, origin: str) -> tuple[int, str | None]:
        headers = {"Origin": origin}
        if method == "OPTIONS":
            headers.update({"Access-Control-Request-Method": "GET",
                            "Access-Control-Request-Headers": "authorization"})
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.headers.get("access-control-allow-origin")
        except urllib.error.HTTPError as err:
            return err.code, err.headers.get("access-control-allow-origin")


def test_cors_live() -> None:
    print("\n7. CORS on a real server")
    with Backend(8053, SMARTHR_ENV="production", SMARTHR_SECRET_KEY=STRONG,
                 SMARTHR_CORS_ORIGINS="https://hr.example.com") as b:
        status, allow = b.call("OPTIONS", "/auth/me", "https://hr.example.com")
        check("production: preflight from the allowed origin -> allowed, echoed back",
              status == 200 and allow == "https://hr.example.com", f"{status} {allow}")
        status, allow = b.call("OPTIONS", "/auth/me", "https://evil.example.com")
        check("production: preflight from another origin -> refused, no allow header",
              status == 400 and allow is None, f"{status} {allow}")
        _, allow = b.call("GET", "/", "https://evil.example.com")
        check("production: a response to another origin carries no allow header (browser blocks it)", allow is None)
        _, allow = b.call("GET", "/", "https://hr.example.com")
        check("production: a response to the allowed origin carries it", allow == "https://hr.example.com")
    with Backend(8054) as b:
        _, allow = b.call("GET", "/", "http://localhost:3000")
        check("development (no SMARTHR_CORS_ORIGINS): any origin, '*' - unchanged", allow == "*", str(allow))
        status, allow = b.call("OPTIONS", "/auth/me", "https://anything.example")
        check("development: preflight from any origin -> allowed", status == 200 and allow == "*", f"{status} {allow}")

    print("\n8. Startup refuses unsafe production configuration")
    def start(**env):
        return subprocess.run([sys.executable, "-c", "import app.main; print('started')"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=120, env={**os.environ, **env})
    r = start(SMARTHR_ENV="production", SMARTHR_SECRET_KEY=STRONG)
    check("production, no CORS allow-list -> the application does not start",
          r.returncode != 0 and "SMARTHR_CORS_ORIGINS" in r.stderr, r.stderr[-200:])
    r = start(SMARTHR_ENV="production", SMARTHR_SECRET_KEY=STRONG, SMARTHR_CORS_ORIGINS="*")
    check("production, CORS '*' -> does not start", r.returncode != 0 and "SMARTHR_CORS_ORIGINS" in r.stderr)
    r = start(SMARTHR_ENV="production", SMARTHR_SECRET_KEY=STRONG, SMARTHR_CORS_ORIGINS="https://hr.example.com")
    check("production, safe configuration -> starts", r.returncode == 0 and "started" in r.stdout, r.stderr[-200:])
    r = start()
    check("development, as configured today -> starts", r.returncode == 0 and "started" in r.stdout, r.stderr[-200:])
    check("no output printed the signing key", STRONG not in r.stdout + r.stderr)


def main() -> int:
    print("SmartHR - production configuration (Phase 10)")
    test_cors_rules()
    test_backend_url()
    test_worker_cli()
    test_worker_profile()
    test_backend_profile()
    test_cors_live()
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
