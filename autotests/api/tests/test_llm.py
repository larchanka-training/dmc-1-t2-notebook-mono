"""LLM-эндпоинт генерации — только КОНТРАКТ/ВАЛИДАЦИЯ.

Реальная генерация требует кредов Amazon Bedrock (guard + generator), что вне
локального scope. Эти тесты проверяют детерминированный контракт авторизации и
валидации ввода. Успешная генерация (если Bedrock настроен) тоже принимается.

TC-API-LLM-*, сценарии L-05/L-06 (валидация), L-NF (лимиты).
"""

import allure
import pytest

# Бэкенд-дедлайн генерации — 30s (llm_request_timeout_seconds). Даём HTTP-клиенту
# запас сверх него, чтобы медленный провайдер не вызвал ReadTimeout httpx
# (таймаут клиента по умолчанию — 15s) и тест падал по делу, а не по таймауту.
LLM_TIMEOUT_SECONDS = 40.0


@allure.feature("LLM")
@allure.story("Авторизация")
@allure.title("Генерация без токена возвращает 401")
@pytest.mark.smoke
@pytest.mark.llm
def test_generate_requires_auth(client):
    with allure.step("POST /llm/generate без токена → 401"):
        res = client.post("/llm/generate", json={"prompt": "sum two numbers"})
        assert res.status_code == 401


@allure.feature("LLM")
@allure.story("Валидация")
@allure.title("Пустой prompt отклоняется (422)")
@pytest.mark.regression
@pytest.mark.llm
def test_generate_rejects_empty_prompt(authed):
    with allure.step("POST /llm/generate с пустым prompt → 422"):
        res = authed.post("/llm/generate", json={"prompt": ""})
        assert res.status_code == 422


@allure.feature("LLM")
@allure.story("Валидация")
@allure.title("Слишком длинный prompt отклоняется (422)")
@pytest.mark.regression
@pytest.mark.llm
def test_generate_rejects_oversized_prompt(authed):
    with allure.step("POST /llm/generate с prompt 9000 символов (лимит 8000) → 422"):
        res = authed.post("/llm/generate", json={"prompt": "x" * 9000})
        assert res.status_code == 422


@allure.feature("LLM")
@allure.story("Валидация")
@allure.title("Режим edit требует непустой baseCode (422)")
@pytest.mark.regression
@pytest.mark.llm
def test_edit_mode_requires_base_code(authed):
    with allure.step("POST /llm/generate mode=edit без baseCode → 422"):
        res = authed.post("/llm/generate", json={"prompt": "rename x to y", "mode": "edit"})
        assert res.status_code == 422


@allure.feature("LLM")
@allure.story("Провайдер")
@allure.title("Корректный prompt: успех или обработанная ошибка провайдера (без 500)")
@pytest.mark.regression
@pytest.mark.llm
def test_generate_valid_prompt_contract(authed):
    """Корректный запрос: либо успех (Bedrock настроен), либо ОБРАБОТАННЫЙ статус
    провайдера/лимита/таймаута — никогда не 4xx-валидация и никогда голый 500.
    500 = эндпоинт сам упал (traceback/невалидный конфиг) — это дефект, его ловим,
    а не нормализуем. Без кредов Bedrock локальный бэкенд отдаёт 502
    `llm_provider_error`.
    """
    with allure.step("POST /llm/generate с корректным prompt (таймаут 40s)"):
        res = authed.post(
            "/llm/generate",
            json={"prompt": "write a function that returns 42", "language": "javascript"},
            timeout=LLM_TIMEOUT_SECONDS,
        )
    with allure.step("Статус из (200, 429, 502, 503, 504) — не 4xx-валидация и не 500"):
        assert res.status_code in (200, 429, 502, 503, 504), res.text
    if res.status_code == 200:
        with allure.step("Успех: тело содержит content и tier"):
            body = res.json()
            assert body["content"]
            assert body["tier"]
    else:
        with allure.step("Обработанная ошибка несёт envelope с error.code"):
            assert res.json()["error"]["code"]
