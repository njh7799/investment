import pytest

from scripts.toss_api import REQUEST_TIMEOUT, TossApiClient, TossApiError


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}
        self.ok = 200 <= status_code < 400

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return next(self.responses)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return next(self.responses)


def test_get_accounts_authenticates_and_uses_bearer_token():
    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token", "expires_in": 86400}),
            FakeResponse(
                200,
                {
                    "result": [
                        {
                            "accountNo": "12345678901",
                            "accountSeq": 1,
                            "accountType": "BROKERAGE",
                        }
                    ]
                },
            ),
        ]
    )

    accounts = TossApiClient("client", "secret", session=session).get_accounts()

    assert accounts[0]["accountSeq"] == 1
    token_call, account_call = session.calls
    assert token_call[2]["data"] == {
        "grant_type": "client_credentials",
        "client_id": "client",
        "client_secret": "secret",
    }
    assert token_call[2]["timeout"] == REQUEST_TIMEOUT
    assert account_call[2]["headers"] == {"Authorization": "Bearer token"}


def test_empty_account_list_is_valid():
    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token"}),
            FakeResponse(200, {"result": []}),
        ]
    )

    assert TossApiClient("client", "secret", session=session).get_accounts() == []


def test_missing_credentials_are_rejected():
    with pytest.raises(ValueError, match="TOSS_CLIENT_ID"):
        TossApiClient("", "")


def test_api_error_includes_code_and_request_id_without_credentials():
    session = FakeSession(
        [
            FakeResponse(
                403,
                {
                    "error": {
                        "code": "access_denied",
                        "message": "IP address not allowed",
                        "requestId": "request-1",
                    }
                },
            )
        ]
    )

    with pytest.raises(TossApiError) as caught:
        TossApiClient("client", "top-secret", session=session).get_accounts()

    message = str(caught.value)
    assert "access_denied" in message
    assert "request-1" in message
    assert "top-secret" not in message


def test_holdings_uses_account_seq_header_and_symbol_filter():
    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token"}),
            FakeResponse(200, {"result": {"items": []}}),
        ]
    )

    result = TossApiClient("client", "secret", session=session).get_holdings(
        42, symbol="TQQQ"
    )

    assert result == {"items": []}
    call = session.calls[-1]
    assert call[1].endswith("/api/v1/holdings")
    assert call[2]["headers"] == {
        "Authorization": "Bearer token",
        "X-Tossinvest-Account": "42",
    }
    assert call[2]["params"] == {"symbol": "TQQQ"}


def test_buying_power_validates_currency_and_cash_amount():
    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token"}),
            FakeResponse(
                200,
                {"result": {"currency": "USD", "cashBuyingPower": "3500.50"}},
            ),
        ]
    )

    result = TossApiClient("client", "secret", session=session).get_buying_power(
        7, "USD"
    )

    assert result["cashBuyingPower"] == "3500.50"
    assert session.calls[-1][2]["params"] == {"currency": "USD"}


def test_candles_retry_rate_limit_and_validate_page():
    sleeps = []
    session = FakeSession(
        [
            FakeResponse(200, {"access_token": "token"}),
            FakeResponse(
                429,
                {"error": {"code": "rate-limit-exceeded"}},
                headers={"Retry-After": "0.25"},
            ),
            FakeResponse(
                200,
                {
                    "result": {
                        "candles": [
                            {
                                "timestamp": "2026-10-27T13:00:00+09:00",
                                "openPrice": "100",
                                "highPrice": "102",
                                "lowPrice": "99",
                                "closePrice": "101",
                                "volume": "1000",
                                "currency": "USD",
                            }
                        ],
                        "nextBefore": None,
                    }
                },
            ),
        ]
    )

    result = TossApiClient(
        "client", "secret", session=session, sleep=sleeps.append
    ).get_candles("QQQ")

    assert result["candles"][0]["closePrice"] == "101"
    assert sleeps == [0.25]
    assert session.calls[-1][2]["params"]["adjusted"] == "true"
