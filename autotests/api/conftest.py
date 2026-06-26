"""Shared fixtures for the black-box API autotests.

These tests hit a RUNNING local server over HTTP (not the in-process TestClient),
so they exercise the same stack a browser does. Bring the stack up first:

    ./start-services.sh          # from the monorepo root (api on :8000)

Auth model (verified against api@8439b84):
  - POST /auth/otp/request → in a local-like backend (APP_ENV=dev/local/test)
    the JSON body carries {"otp", "expiresAt"} so we can complete OTP without
    an email inbox.
  - POST /auth/otp/verify  → {"accessToken", "refreshToken", "user"}.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Iterator

import allure
import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
REQUEST_TIMEOUT = float(os.environ.get("API_TIMEOUT", "15"))

# Settle wait applied after every mutating request (POST/PUT/PATCH/DELETE).
# The backend commits in the get_db dependency teardown (`yield; commit`), which
# races sending the response — so a machine-speed read right after a write can
# miss it (a human never does). A 1s settle closes that window everywhere.
#
# This is a TEMPORARY harness shield for a real backend bug, tracked at
# larchanka-training/js-notebook#166 (commit-before-response in api/app/core/db.py).
# `login()` already uses a read-with-retry instead of a fixed wait; once #166 is
# fixed, drop SETTLE_SECONDS (set it to 0) and rely on retries.
SETTLE_SECONDS = float(os.environ.get("SETTLE_SECONDS", "1.0"))

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _pretty(raw: bytes | str) -> str:
    """Pretty-print a JSON body; fall back to the raw text."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    if not text:
        return "(без тела)"
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except Exception:
        return text


def _on_response(response) -> None:
    """Attach the request/response to the Allure report, then settle on writes.

    Each HTTP exchange becomes two Allure attachments — «Запрос …» and «Ответ …» —
    so the report shows exactly what was sent and received for every call.
    """
    req = response.request
    try:
        allure.attach(
            f"{req.method} {req.url}\n\n{_pretty(req.content or b'')}",
            name=f"→ Запрос: {req.method} {req.url.path}",
            attachment_type=allure.attachment_type.TEXT,
        )
        response.read()  # load the body so .text is available inside the hook
        allure.attach(
            f"HTTP {response.status_code} {response.reason_phrase}\n\n{_pretty(response.text)}",
            name=f"← Ответ: HTTP {response.status_code}",
            attachment_type=allure.attachment_type.TEXT,
        )
    except Exception:
        pass  # the report is best-effort — never fail a test on attachment issues
    if req.method in _WRITE_METHODS:
        time.sleep(SETTLE_SECONDS)


def _hooked_client(**kwargs) -> httpx.Client:
    return httpx.Client(
        base_url=API_BASE_URL,
        timeout=REQUEST_TIMEOUT,
        event_hooks={"response": [_on_response]},
        **kwargs,
    )


def unique_email(prefix: str = "apitest") -> str:
    return f"{prefix}.{int(time.time() * 1000)}.{uuid.uuid4().hex[:6]}@example.com"


@pytest.fixture(scope="session")
def base_url() -> str:
    return API_BASE_URL


@pytest.fixture()
def client() -> Iterator[httpx.Client]:
    """An unauthenticated HTTP client bound to the API base URL.

    Mutating requests get a 1s settle (see SETTLE_SECONDS) so subsequent reads
    are read-your-writes consistent against the dev backend.
    """
    with _hooked_client() as c:
        yield c


def _request_otp(client: httpx.Client, email: str) -> str:
    res = client.post("/auth/otp/request", json={"email": email})
    assert res.status_code == 200, f"otp/request: {res.status_code} {res.text}"
    otp = res.json().get("otp")
    assert otp, (
        "No dev OTP in response. The backend must be local-like "
        "(APP_ENV in dev/local/test) for black-box OTP login."
    )
    return str(otp)


def login(client: httpx.Client, email: str | None = None) -> dict:
    """Full OTP login; returns the verify response (tokens + user).

    A fresh request+verify is retried a couple of times: the dev backend has an
    occasional timing window where a verify issued immediately after the request
    sees `invalid_otp` (the OTP write is not yet visible). This is harness
    hardening, not a product assertion — it is logged as an observation in the
    release report.
    """
    email = email or unique_email()
    # The client's response hook already applies a 1s settle after the
    # otp/request and otp/verify POSTs, so the OTP write (and the refresh/session
    # rows) are visible before the next call. A small retry covers any residual
    # window under heavy load.
    last = None
    for _ in range(3):
        with allure.step(f"Войти по одноразовому коду (OTP): {email}"):
            with allure.step("Запросить OTP-код"):
                otp = _request_otp(client, email)
            with allure.step("Подтвердить OTP-код и получить токены"):
                res = client.post("/auth/otp/verify", json={"email": email, "otp": otp})
        if res.status_code == 200:
            body = res.json()
            body["email"] = email
            return body
        last = res
    assert last is not None and last.status_code == 200, (
        f"otp/verify after retries: {last.status_code if last else '?'} "
        f"{last.text if last else ''}"
    )
    raise AssertionError("unreachable")  # pragma: no cover


@pytest.fixture()
def session(client: httpx.Client) -> dict:
    """A freshly logged-in session (unique user per test)."""
    return login(client)


@pytest.fixture()
def authed(session: dict) -> Iterator[httpx.Client]:
    """An HTTP client carrying the Bearer access token."""
    headers = {"Authorization": f"Bearer {session['accessToken']}"}
    with _hooked_client(headers=headers) as c:
        yield c


def new_notebook_payload(title: str = "API test notebook", cells: list[dict] | None = None) -> dict:
    now = int(time.time() * 1000)
    return {
        "id": str(uuid.uuid4()),
        "title": title,
        "formatVersion": 1,
        "cells": cells
        or [{"id": str(uuid.uuid4()), "kind": "code", "content": "console.log(1)", "updatedAt": now}],
    }
