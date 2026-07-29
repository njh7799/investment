# Investment Market Data

과거 시장 데이터를 일관된 형식으로 관리하고, 이를 이용해 지표 분석과 전략 백테스트를 수행하기 위한 저장소입니다.

현재 Nasdaq Composite 지수와 QQQ·TQQQ의 일별 조정 OHLC 데이터를 수집하고 매일 자동 갱신합니다. 분석과 백테스트의 공통 규칙은 [AGENTS.md](AGENTS.md), 전략별 규칙과 상태는 [전략 문서](docs/)에서 관리합니다.

## 구성

| 경로 | 내용 |
| --- | --- |
| `assets/` | IXIC·QQQ·TQQQ 일별 조정 OHLC |
| `scripts/` | 시장 데이터 수집과 검증 |
| `tests/` | 데이터 생성 로직 테스트 |
| `docs/strategies/` | 기본 전략, variants와 addons |
| `.github/workflows/` | 일일 데이터 갱신 자동화 |

## 데이터

`assets/`에는 다음 파일이 있습니다.

| 파일 | Yahoo 심볼 | 내용 |
| --- | --- | --- |
| `IXIC.csv` | `^IXIC` | Nasdaq Composite 지수 |
| `QQQ.csv` | `QQQ` | Invesco QQQ ETF |
| `TQQQ.csv` | `TQQQ` | ProShares UltraPro QQQ 및 상장 전 합성 데이터 |

CSV 스키마는 모두 `Date,Open,High,Low,Close`입니다.

- 날짜는 `YYYY.MM.DD` 형식이며 오름차순으로 정렬되고 중복되지 않습니다.
- 가격은 Yahoo Finance의 액면분할·배당 반영 조정 OHLC입니다.

### TQQQ 상장 전 합성 데이터

TQQQ 상장 전 기간은 QQQ의 일일 움직임을 3배 적용하고 최초 실제 TQQQ 가격을 기준점으로 역산합니다. 상장 이후에는 Yahoo 원본만 사용합니다.

이 합성 구간은 연구 편의를 위한 가상 시계열입니다. 운용보수, 금융비용, 배당세, 추적오차 등 실제 상품의 모든 요소를 재현하지 않으므로 실제 TQQQ 성과로 해석하면 안 됩니다.

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements.txt
```

## 실행

전체 이력을 다시 생성합니다.

```bash
python scripts/update_market_data.py --mode full
```

일일 갱신 모드는 Nasdaq 거래 여부와 장 마감 후 2시간 경과 여부를 확인하고 최신 거래일 데이터를 반영합니다.

```bash
python scripts/update_market_data.py --mode daily
```

테스트를 실행합니다.

```bash
python -m pytest --quiet
```

## 토스증권 계좌 조회

토스증권 Open API의 Client ID와 Client Secret을 이용해 본인의 종합매매 계좌
목록을 조회할 수 있습니다.

- [토스증권 Open API 공식 문서](https://developers.tossinvest.com/docs)
- [공식 OpenAPI 명세](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)

인증은 OAuth 2.0 Client Credentials Grant를 사용합니다. `.env.example`을
`.env`로 복사한 뒤 실제 값을 입력합니다. `.env`는 Git에서 제외됩니다.

```bash
cp .env.example .env
```

```dotenv
TOSS_CLIENT_ID=발급받은_Client_ID
TOSS_CLIENT_SECRET=발급받은_Client_Secret
```

토스증권 WTS의 Open API 설정에서 현재 Mac의 공인 IP를 허용한 뒤 실행합니다.

```bash
python scripts/toss_api.py
```

성공하면 `accountNo`, `accountSeq`, `accountType`이 JSON으로 출력됩니다. 토큰과
자격증명은 출력하거나 파일에 저장하지 않습니다.

`accountSeq`는 보유주식과 매수 가능 금액처럼 사용자 계좌를 지정해야 하는 후속
API의 `X-Tossinvest-Account` 헤더 값입니다. 토스 API의 `cashBuyingPower`는
예수금 자체가 아니라 미수거래를 제외한 통화별 현금 매수 가능 금액입니다.

## 자동 갱신

GitHub Actions는 매일 `23:00 UTC`에 일일 갱신을 실행합니다. Nasdaq 휴장일에는 파일을 변경하지 않으며, 검증된 CSV에 실제 차이가 있을 때만 커밋하고 푸시합니다.
