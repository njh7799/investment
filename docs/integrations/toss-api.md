# 토스증권 Open API 연동

토스증권 연동은 [공식 문서](https://developers.tossinvest.com/docs)와 [공식 OpenAPI 명세](https://openapi.tossinvest.com/openapi-docs/latest/openapi.json)를 기준으로 한다.

## 설정과 실행

`.env.example`을 루트 `.env`로 복사하고 Client ID와 Client Secret을 설정한다. `.env`는 Git에서 제외된다.

```bash
cp .env.example .env
```

```dotenv
TOSS_CLIENT_ID=발급받은_Client_ID
TOSS_CLIENT_SECRET=발급받은_Client_Secret
```

토스증권 WTS의 Open API 설정에서 현재 공인 IP를 허용한 뒤 실행한다.

```bash
python scripts/toss_api.py
```

## API 규칙

- 인증은 OAuth 2.0 Client Credentials Grant를 사용한다.
- 계좌 목록은 `GET /api/v1/accounts`로 조회한다.
- 계좌별 API의 `X-Tossinvest-Account` 헤더에는 `accountNo`가 아닌 계좌 목록 응답의 `accountSeq`를 사용한다.
- 보유주식은 `GET /api/v1/holdings`, 원화·달러 현금 매수 가능 금액은 `GET /api/v1/buying-power`로 조회한다.
- `cashBuyingPower`는 예수금이 아니라 미수거래를 제외한 통화별 현금 매수 가능 금액으로 표현한다.

## 보안

- Client ID와 Client Secret은 루트 `.env`에서만 읽는다.
- 실제 자격증명, access token과 전체 계좌번호를 코드, 문서, 로그, 테스트 fixture나 커밋에 남기지 않는다.
- 실시간 계좌 응답은 사용자가 저장을 요청하지 않으면 파일로 기록하지 않는다.
- 계좌번호는 기본적으로 끝 네 자리만 남기고 마스킹한다.
