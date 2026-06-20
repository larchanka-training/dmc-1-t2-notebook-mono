"""Health/readiness probes — TC-INFRA-*, сценарий R-00 (smoke-гейт)."""

import allure
import pytest


@allure.feature("Инфраструктура")
@allure.story("Проверки здоровья сервиса")
@allure.title("Liveness-проба отвечает 200/ok")
@pytest.mark.smoke
def test_liveness(client):
    with allure.step("GET /health"):
        res = client.get("/health")
    with allure.step("Статус 200 и status == 'ok'"):
        assert res.status_code == 200
        assert res.json().get("status") == "ok"


@allure.feature("Инфраструктура")
@allure.story("Проверки здоровья сервиса")
@allure.title("Readiness в smoke строго ok (БД поднята)")
@pytest.mark.smoke
def test_readiness_is_ok(client):
    # Smoke — это релизный гейт: БД поднята и миграции применены до прогона,
    # поэтому readiness обязан быть строго «ok». Degraded здесь — реальный блокер.
    with allure.step("GET /health/ready"):
        res = client.get("/health/ready")
    with allure.step("Статус 200 и status == 'ok'"):
        assert res.status_code == 200, res.text
        assert res.json().get("status") == "ok"


@allure.feature("Инфраструктура")
@allure.story("Проверки здоровья сервиса")
@allure.title("Контракт ответа readiness (ok | degraded)")
@pytest.mark.regression
def test_readiness_response_shape(client):
    # Мягкая проверка формы (вынесена из smoke): 200/«ok» если БД доступна,
    # иначе 503/«degraded».
    with allure.step("GET /health/ready"):
        res = client.get("/health/ready")
    with allure.step("Статус из (200, 503), status из ('ok', 'degraded')"):
        assert res.status_code in (200, 503)
        assert res.json().get("status") in ("ok", "degraded")
