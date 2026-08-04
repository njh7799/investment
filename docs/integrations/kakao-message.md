# 카카오톡 일일 브리핑

미국 동부시간 기준 평일 오후 6시에 실행되는 `Update market data` 워크플로가 최신 시장 데이터 갱신을 성공적으로 마치면, 독립된 `Daily market and VO briefing` 워크플로가 카카오톡 `나와의 채팅`으로 시장 및 VO 브리핑을 전송한다. 수동 확인은 브리핑 워크플로의 `workflow_dispatch`로 데이터 갱신과 별개로 실행할 수 있다.

## 브리핑 내용

- 최신 거래일 기준 IXIC, QQQ, TQQQ, SPY의 종가와 전일 종가 대비 변동률
- TQQQ 조정 종가의 최근 30거래일 수익률로 계산한 연율화 실현 변동성
- VO 기본 규칙에 따른 현재 TQQQ:현금 목표 비율
- 직전 거래일 신호와 현재 신호가 다를 때 다음 거래일 시가 리밸런싱 안내
- 신호 변경일에는 변경 전후 주식·현금 비율과 다음 거래일 시가 리밸런싱 안내만 표시한다. 계좌 조회와 주문수량 계산은 하지 않는다.

브리핑은 카카오톡 피드의 3:4 표시 비율과 상단 안전 여백을 반영한 800×1067 PNG 카드로 렌더링한다. 상승 행은 붉은색, 하락 행은 파란색으로 표시한다. VO 패널에는 현재 값, 전 거래일 대비 퍼센트포인트 변화와 반원형 계기판을 표시한다. 계기판은 0~120% 범위에서 60%와 90% 경계를 표시하며 바늘이 범위를 넘으면 양 끝에 고정한다. `권장 비중` 영역은 모든 상태에서 첫째 행을 주식, 둘째 행을 현금으로 고정한다. 기본 비중은 회색 막대로 표시하고, 비중이 늘어날 때에만 증가분을 주식은 붉은색, 현금은 파란색으로 구분한다. 비중이 줄어든 구간은 빈 막대로 표시한다. 신호 변경일에만 각 행의 비율을 `직전 → 현재`로 표시하며 행 글꼴, 위치와 막대 크기는 평상시 카드와 동일하게 유지한다.

생성된 PNG는 저장소나 공개 이미지 호스팅에 기록하지 않는다. Actions 러너의 임시 디렉터리에서 생성해 카카오 이미지 서버로 바로 업로드하고, 카카오가 반환한 이미지 URL을 피드 메시지에 사용한다. 카카오 서버의 업로드 이미지는 최대 100일 보관된 뒤 삭제된다.

VO 계산과 경계값은 [`docs/strategies/volatility-allocation/README.md`](../strategies/volatility-allocation/README.md)를 그대로 따른다. 신호는 최신 거래일 종가로 계산하며 주문 안내 시점은 다음 거래일 시가다.

## GitHub Actions Secrets

`.env.example`의 아래 이름을 저장소 Actions secrets에 등록한다.

- `KAKAO_REST_API_KEY`
- `KAKAO_CLIENT_SECRET`
- `KAKAO_REFRESH_TOKEN`
- `GH_SECRETS_TOKEN`

`GH_SECRETS_TOKEN`은 이 저장소에만 접근할 수 있는 fine-grained personal access token으로 만들고, Repository permissions의 `Secrets`를 `Read and write`로 설정한다. 이 토큰은 카카오가 새 리프레시 토큰을 반환했을 때 `KAKAO_REFRESH_TOKEN` secret을 교체하는 용도로만 사용한다.

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
