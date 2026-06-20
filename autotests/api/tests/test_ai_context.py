"""AI-контекст (под-ресурс ноутбука) — TC-API-*, сценарии L/R."""

import allure
import pytest

from conftest import new_notebook_payload


@allure.feature("AI-контекст")
@allure.story("Чтение по умолчанию")
@allure.title("Контекст по умолчанию пустой")
@pytest.mark.regression
@pytest.mark.ai_context
def test_get_context_defaults_empty(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("GET ai-context → 200, context пустой"):
        res = authed.get(f"/notebooks/{payload['id']}/ai-context")
        assert res.status_code == 200
        body = res.json()
        assert body["notebookId"] == payload["id"]
        assert body["context"] == []


@allure.feature("AI-контекст")
@allure.story("Сохранение")
@allure.title("Контекст сохраняется и читается обратно")
@pytest.mark.regression
@pytest.mark.ai_context
def test_store_and_read_back_context(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("PUT ai-context → 200, updatedAt заполнен"):
        store = authed.put(
            f"/notebooks/{payload['id']}/ai-context",
            json={"context": [{"kind": "code", "source": "console.log(1)"}], "historyCount": 1},
        )
        assert store.status_code == 200
        assert store.json()["updatedAt"] is not None


@allure.feature("AI-контекст")
@allure.story("Сохранение")
@allure.title("Слишком большой контекст отклоняется (422)")
@pytest.mark.regression
@pytest.mark.ai_context
def test_store_rejects_oversized_context(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("PUT ai-context с телом сверх лимита (8 KiB) → 422"):
        huge = "a" * 20000  # well over the 8 KiB prompt budget
        res = authed.put(
            f"/notebooks/{payload['id']}/ai-context",
            json={"context": [{"kind": "code", "source": huge}]},
        )
        assert res.status_code == 422


@allure.feature("AI-контекст")
@allure.story("Авторизация")
@allure.title("AI-контекст требует авторизацию (401)")
@pytest.mark.regression
@pytest.mark.ai_context
def test_context_requires_auth(client):
    import uuid

    with allure.step("GET ai-context без токена → 401"):
        assert client.get(f"/notebooks/{uuid.uuid4()}/ai-context").status_code == 401
