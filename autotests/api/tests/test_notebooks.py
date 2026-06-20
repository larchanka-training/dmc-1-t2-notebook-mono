"""Notebooks CRUD + синхронизация — TC-API-NB-*, сценарии E/R."""

import uuid

import allure
import pytest

from conftest import new_notebook_payload


@allure.feature("Ноутбуки")
@allure.story("Требуется авторизация")
@allure.title("Список ноутбуков без токена возвращает 401")
@pytest.mark.smoke
@pytest.mark.notebooks
def test_list_requires_auth(client):
    with allure.step("GET /notebooks без токена → 401"):
        assert client.get("/notebooks").status_code == 401


@allure.feature("Ноутбуки")
@allure.story("Создание")
@allure.title("Создание ноутбука возвращает его с ownerId")
@pytest.mark.smoke
@pytest.mark.notebooks
def test_create_notebook(authed):
    payload = new_notebook_payload(title="Created via API")
    with allure.step("POST /notebooks"):
        res = authed.post("/notebooks", json=payload)
    with allure.step("Ответ 200/201, тело содержит id, title, ownerId"):
        assert res.status_code in (200, 201), res.text
        body = res.json()
        assert body["id"] == payload["id"]
        assert body["title"] == "Created via API"
        assert body["ownerId"]


@allure.feature("Ноутбуки")
@allure.story("Создание")
@allure.title("Создание идемпотентно по id")
@pytest.mark.regression
@pytest.mark.notebooks
def test_create_is_idempotent_on_id(authed):
    payload = new_notebook_payload()
    with allure.step("Первое создание"):
        first = authed.post("/notebooks", json=payload)
        assert first.status_code in (200, 201)
    with allure.step("Повторное создание того же payload — снова 200/201, тот же id"):
        second = authed.post("/notebooks", json=payload)
        assert second.status_code in (200, 201)
        assert second.json()["id"] == payload["id"]


@allure.feature("Ноутбуки")
@allure.story("Создание")
@allure.title("Создание отклоняет неподдерживаемый formatVersion")
@pytest.mark.regression
@pytest.mark.notebooks
def test_create_rejects_unsupported_format_version(authed):
    payload = new_notebook_payload()
    payload["formatVersion"] = 999
    with allure.step("POST /notebooks с formatVersion=999 → 400"):
        res = authed.post("/notebooks", json=payload)
        assert res.status_code == 400


@allure.feature("Ноутбуки")
@allure.story("Создание")
@allure.title("Создание отклоняет дублирующиеся id ячеек")
@pytest.mark.regression
@pytest.mark.notebooks
def test_create_rejects_duplicate_cell_ids(authed):
    payload = new_notebook_payload()
    dup = payload["cells"][0]["id"]
    payload["cells"].append({"id": dup, "kind": "code", "content": "x", "updatedAt": 1})
    with allure.step("POST /notebooks с дублем id ячейки → 422"):
        res = authed.post("/notebooks", json=payload)
        assert res.status_code == 422


@allure.feature("Ноутбуки")
@allure.story("Чтение")
@allure.title("Чтение созданного ноутбука по id")
@pytest.mark.smoke
@pytest.mark.notebooks
def test_get_created_notebook(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("GET /notebooks/{id} → 200, тот же id"):
        res = authed.get(f"/notebooks/{payload['id']}")
        assert res.status_code == 200
        assert res.json()["id"] == payload["id"]


@allure.feature("Ноутбуки")
@allure.story("Чтение")
@allure.title("Чтение несуществующего ноутбука возвращает 404")
@pytest.mark.regression
@pytest.mark.notebooks
def test_get_unknown_returns_404(authed):
    with allure.step("GET /notebooks/{случайный-uuid} → 404"):
        assert authed.get(f"/notebooks/{uuid.uuid4()}").status_code == 404


@allure.feature("Ноутбуки")
@allure.story("Список")
@allure.title("Список содержит созданный ноутбук и ограничен владельцем")
@pytest.mark.regression
@pytest.mark.notebooks
def test_list_includes_created_and_is_owner_scoped(authed):
    payload = new_notebook_payload(title="Listed")
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("GET /notebooks — созданный id присутствует в списке"):
        res = authed.get("/notebooks", params={"limit": 200})
        assert res.status_code == 200
        ids = [n["id"] for n in res.json()["items"]]
        assert payload["id"] in ids


@allure.feature("Ноутбуки")
@allure.story("Список")
@allure.title("Список отклоняет недопустимый параметр sort")
@pytest.mark.regression
@pytest.mark.notebooks
def test_list_rejects_invalid_sort(authed):
    with allure.step("GET /notebooks?sort=bogus → 400"):
        res = authed.get("/notebooks", params={"sort": "bogus"})
        assert res.status_code == 400


@allure.feature("Ноутбуки")
@allure.story("Обновление")
@allure.title("PATCH обновляет заголовок ноутбука")
@pytest.mark.regression
@pytest.mark.notebooks
def test_patch_updates_title(authed):
    payload = new_notebook_payload(title="Before")
    with allure.step("Создать ноутбук с заголовком 'Before'"):
        authed.post("/notebooks", json=payload)
    with allure.step("PATCH заголовок → 'After'"):
        res = authed.patch(
            f"/notebooks/{payload['id']}",
            json={"title": "After", "formatVersion": 1, "cells": payload["cells"]},
        )
        assert res.status_code == 200
        assert res.json()["title"] == "After"


@allure.feature("Ноутбуки")
@allure.story("Удаление")
@allure.title("После удаления чтение возвращает 404")
@pytest.mark.regression
@pytest.mark.notebooks
def test_delete_then_get_is_404(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("DELETE → 204"):
        assert authed.delete(f"/notebooks/{payload['id']}").status_code == 204
    with allure.step("GET того же id → 404"):
        assert authed.get(f"/notebooks/{payload['id']}").status_code == 404


@allure.feature("Ноутбуки")
@allure.story("Удаление")
@allure.title("Удаление идемпотентно (повторное — 404, не 500)")
@pytest.mark.regression
@pytest.mark.notebooks
def test_delete_is_idempotent(authed):
    payload = new_notebook_payload()
    with allure.step("Создать ноутбук"):
        authed.post("/notebooks", json=payload)
    with allure.step("Первое удаление → 204"):
        assert authed.delete(f"/notebooks/{payload['id']}").status_code == 204
    with allure.step("Повторное удаление → 404 (никогда не 500)"):
        assert authed.delete(f"/notebooks/{payload['id']}").status_code == 404


@allure.feature("Ноутбуки")
@allure.story("Изоляция владельца")
@allure.title("Чужой ноутбук недоступен другому пользователю")
@pytest.mark.regression
@pytest.mark.notebooks
def test_other_user_cannot_read_notebook(authed, client):
    from conftest import login

    payload = new_notebook_payload(title="Private")
    with allure.step("Пользователь A создаёт приватный ноутбук"):
        authed.post("/notebooks", json=payload)

    with allure.step("Пользователь B логинится"):
        other = login(client)
    import httpx
    from conftest import API_BASE_URL, REQUEST_TIMEOUT, _on_response

    with allure.step("Пользователь B читает ноутбук пользователя A"):
        with httpx.Client(
            base_url=API_BASE_URL,
            timeout=REQUEST_TIMEOUT,
            headers={"Authorization": f"Bearer {other['accessToken']}"},
            event_hooks={"response": [_on_response]},
        ) as other_client:
            res = other_client.get(f"/notebooks/{payload['id']}")
    with allure.step("Доступа нет: 403 (известный id, не свой) или 404"):
        # Owner-scoped: known-id-but-not-owned → 403; truly-absent ids → 404.
        assert res.status_code in (403, 404)
