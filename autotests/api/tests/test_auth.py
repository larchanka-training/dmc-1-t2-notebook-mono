"""Auth API — OTP request/verify, JWT, refresh, me. TC-API-AUTH-*, сценарии A/R."""

import allure
import pytest

from conftest import login, unique_email


@allure.feature("Аутентификация")
@allure.story("Запрос OTP-кода")
@allure.title("Запрос OTP возвращает 6-значный dev-код")
@pytest.mark.smoke
@pytest.mark.auth
def test_otp_request_returns_six_digit_dev_code(client):
    with allure.step("Запросить OTP для нового email"):
        res = client.post("/auth/otp/request", json={"email": unique_email()})
    with allure.step("Ответ 200, в теле 6-значный код"):
        assert res.status_code == 200
        otp = res.json()["otp"]
        assert otp.isdigit() and len(otp) == 6


@allure.feature("Аутентификация")
@allure.story("Запрос OTP-кода")
@allure.title("Запрос OTP отклоняет некорректный email")
@pytest.mark.regression
@pytest.mark.auth
def test_otp_request_rejects_invalid_email(client):
    with allure.step("Запросить OTP для невалидного email"):
        res = client.post("/auth/otp/request", json={"email": "not-an-email"})
    with allure.step("Ответ 400 или 422"):
        assert res.status_code in (400, 422)


@allure.feature("Аутентификация")
@allure.story("Подтверждение OTP")
@allure.title("Подтверждение OTP выдаёт access/refresh токены")
@pytest.mark.smoke
@pytest.mark.auth
def test_otp_verify_issues_tokens(client):
    body = login(client)
    with allure.step("В ответе есть accessToken, refreshToken и user"):
        assert body["accessToken"]
        assert body["refreshToken"]
        assert body["user"]["email"] == body["email"].lower() or body["user"]["email"] == body["email"]


@allure.feature("Аутентификация")
@allure.story("Подтверждение OTP")
@allure.title("Подтверждение OTP отклоняет неверный код")
@pytest.mark.regression
@pytest.mark.auth
def test_otp_verify_rejects_wrong_code(client):
    email = unique_email()
    with allure.step("Запросить OTP"):
        client.post("/auth/otp/request", json={"email": email})
    with allure.step("Подтвердить заведомо неверным кодом 000000"):
        res = client.post("/auth/otp/verify", json={"email": email, "otp": "000000"})
    with allure.step("Ответ 401 или 422"):
        assert res.status_code in (401, 422)


@allure.feature("Аутентификация")
@allure.story("Текущий пользователь")
@allure.title("GET /auth/me без токена возвращает 401")
@pytest.mark.smoke
@pytest.mark.auth
def test_me_requires_bearer_token(client):
    with allure.step("GET /auth/me без Authorization"):
        res = client.get("/auth/me")
    with allure.step("Ответ 401"):
        assert res.status_code == 401


@allure.feature("Аутентификация")
@allure.story("Текущий пользователь")
@allure.title("GET /auth/me возвращает текущего пользователя")
@pytest.mark.regression
@pytest.mark.auth
def test_me_returns_current_user(authed, session):
    with allure.step("GET /auth/me с Bearer-токеном"):
        res = authed.get("/auth/me")
    with allure.step("Ответ 200, id совпадает с залогиненным пользователем"):
        assert res.status_code == 200
        assert res.json()["id"] == session["user"]["id"]


@allure.feature("Аутентификация")
@allure.story("Обновление токенов")
@allure.title("Refresh ротирует токены (выдаёт новый refresh)")
@pytest.mark.regression
@pytest.mark.auth
def test_refresh_rotates_tokens(client, session):
    with allure.step("POST /auth/refresh с текущим refresh-токеном"):
        res = client.post("/auth/refresh", json={"refreshToken": session["refreshToken"]})
    with allure.step("Ответ 200, выданы новые токены, refresh изменился"):
        assert res.status_code == 200
        rotated = res.json()
        assert rotated["accessToken"] and rotated["refreshToken"]
        assert rotated["refreshToken"] != session["refreshToken"]


@allure.feature("Аутентификация")
@allure.story("Обновление токенов")
@allure.title("Повторное использование старого refresh отклоняется")
@pytest.mark.regression
@pytest.mark.auth
def test_refresh_reuse_is_rejected(client, session):
    old = session["refreshToken"]
    with allure.step("Первый refresh старым токеном — успех"):
        first = client.post("/auth/refresh", json={"refreshToken": old})
        assert first.status_code == 200
    with allure.step("Повторный refresh тем же (уже ротированным) токеном — 401"):
        reuse = client.post("/auth/refresh", json={"refreshToken": old})
        assert reuse.status_code == 401


@allure.feature("Аутентификация")
@allure.story("Выход")
@allure.title("Logout идемпотентен (повторный — тоже 204)")
@pytest.mark.regression
@pytest.mark.auth
def test_logout_is_idempotent(client, session):
    with allure.step("Первый logout — 204"):
        first = client.post("/auth/logout", json={"refreshToken": session["refreshToken"]})
        assert first.status_code == 204
    with allure.step("Повторный logout тем же токеном — снова 204"):
        again = client.post("/auth/logout", json={"refreshToken": session["refreshToken"]})
        assert again.status_code == 204
