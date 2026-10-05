"""SmartHR backend package.

This file has to exist, and it is not a formality.

Without an `__init__.py`, `app` is an implicit **namespace package**: Python
merges every `app/` directory it finds anywhere on `sys.path` into one package,
and each submodule is resolved from whichever directory comes first. A stray
`app/` folder in the working directory - a leftover copy, an extracted
snapshot, a file saved one level too high - then silently shadows part of this
package, and the server boots with a mixture of old and new modules and no
error at all.

That is exactly what happened here: a stale `app/main.py` sitting in the user's
home directory was being loaded while `app.routers.*` came from this project,
so `uvicorn app.main:app` started a server with 17 routers instead of 19 - no
`/dashboard/*`, no `/ai/*` - and `--reload` never noticed, because the file it
had actually loaded never changed.

With this file present, `app` is a regular package. A regular package wins over
any namespace portion, so the modules under this directory are the only ones
that can ever be imported as `app.*`.
"""
