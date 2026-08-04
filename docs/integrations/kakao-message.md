# 카카오톡 일일 브리핑

미국 동부시간 기준 평일 오후 6시에 실행되는 `Update market data` 워크플로가 최신 시장 데이터 갱신을 성공적으로 마치면, 독립된 `Daily market and VO briefing` 워크플로가 카카오톡 `나와의 채팅`으로 시장 및 VO 브리핑을 전송한다. 수동 확인은 브리핑 워크플로의 `workflow_dispatch`로 데이터 갱신과 별개로 실행할 수 있다.

## 브리핑 내용

- 최신 거래일 기준 IXIC, QQQ, TQQQ, SPY의 종가와 전일 종가 대비 변동률
- TQQQ 조정 종가의 최근 30거래일 수익률로 계산한 연율화 실현 변동성
- VO 기본 규칙에 따른 현재 TQQQ:현금 목표 비율
- 직전 거래일 신호와 현재 신호가 다를 때 다음 거래일 시가 리밸런싱 안내
- 신호 변경일에는 토스증권의 TQQQ 보유수량과 USD 현금 매수 가능 금액을 조회해 최신 종가 기준 예상 주문수량 안내

브리핑은 카카오톡 피드의 3:4 표시 비율과 상단 안전 여백을 반영한 800×1067 PNG 카드로 렌더링한다. 상승 행은 붉은색, 하락 행은 파란색으로 표시하고 VO 변동성에는 저변동·중변동·고변동 상태 라벨을 함께 표시한다. `권장 비중` 영역은 모든 상태에서 첫째 행을 주식, 둘째 행을 현금으로 고정한다. 기본 비중은 회색 막대로 표시하고, 비중이 늘어날 때에만 증가분을 주식은 붉은색, 현금은 파란색으로 구분한다. 비중이 줄어든 구간은 빈 막대로 표시한다. 신호 변경일에만 각 행의 비율을 `직전 → 현재`로 표시하며 행 글꼴, 위치와 막대 크기는 평상시 카드와 동일하게 유지한다.

생성된 PNG는 저장소나 공개 이미지 호스팅에 기록하지 않는다. Actions 러너의 임시 디렉터리에서 생성해 카카오 이미지 서버로 바로 업로드하고, 카카오가 반환한 이미지 URL을 피드 메시지에 사용한다. 카카오 서버의 업로드 이미지는 최대 100일 보관된 뒤 삭제된다.

VO 계산과 경계값은 [`docs/strategies/volatility-allocation/README.md`](../strategies/volatility-allocation/README.md)를 그대로 따른다. 신호는 최신 거래일 종가로 계산하며 주문 안내 시점은 다음 거래일 시가다.

## GitHub Actions Secrets

`.env.example`의 아래 이름을 저장소 Actions secrets에 등록한다.

- `KAKAO_REST_API_KEY`
- `KAKAO_CLIENT_SECRET`
- `KAKAO_REFRESH_TOKEN`
- `GH_SECRETS_TOKEN`
- `TOSS_CLIENT_ID`
- `TOSS_CLIENT_SECRET`

종합매매 계좌가 둘 이상이면 사용할 계좌 목록 응답의 `accountSeq`를 `TOSS_ACCOUNT_SEQ`로 추가 등록한다. 전체 계좌번호는 저장하거나 출력하지 않으며 브리핑에는 끝 네 자리만 표시한다.

`GH_SECRETS_TOKEN`은 이 저장소에만 접근할 수 있는 fine-grained personal access token으로 만들고, Repository permissions의 `Secrets`를 `Read and write`로 설정한다. 이 토큰은 카카오가 새 리프레시 토큰을 반환했을 때 `KAKAO_REFRESH_TOKEN` secret을 교체하는 용도로만 사용한다.

토스증권 API는 허용 IP 설정이 필요하다. GitHub-hosted runner의 외부 IP는 고정되지 않으므로, 신호 변경일에 안정적으로 계좌를 조회하려면 고정 공인 IP를 가진 self-hosted runner 또는 고정 egress 환경을 사용하고 해당 IP를 토스증권 Open API 설정에 등록해야 한다. 계좌 조회에 실패해도 시장·VO 브리핑은 발송되며 주문수량을 계산하지 못했다는 경고를 포함한다.

## 로컬 확인

카카오 앱 키 화면에서 REST API 키와 카카오 로그인용 클라이언트 시크릿을 각각 복사한 직후 다음 명령으로 로컬 `.env`에 저장할 수 있다. 값은 터미널에 출력되지 않는다.

```bash
python scripts/set_local_secret.py KAKAO_REST_API_KEY
python scripts/set_local_secret.py KAKAO_CLIENT_SECRET
```

최초 한 번 사용자 동의를 완료하고 리프레시 토큰을 `.env`에 저장한다.

```bash
python scripts/authorize_kakao.py
```

메시지를 전송하지 않고 브리핑 내용만 확인한다.

```bash
python scripts/send_daily_briefing.py --dry-run
```

`.env`에 카카오 자격증명이 설정된 이후 실제 메시지를 전송한다.

```bash
python scripts/send_daily_briefing.py
```
