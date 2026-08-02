# Investment Market Data

과거 시장 데이터를 일관된 형식으로 관리하고, 이를 이용해 지표 분석과 전략 백테스트를 수행하기 위한 저장소입니다.

Nasdaq 계열과 공개 모델 검증에 필요한 미국 상장 ETF의 일별 조정 OHLC 데이터를 수집하고 매일 자동 갱신합니다. 분석과 백테스트의 공통 규칙은 [AGENTS.md](AGENTS.md), 전략별 규칙과 상태는 [전략 문서](docs/)에서 관리합니다.

## 구성

| 경로 | 내용 |
| --- | --- |
| `assets/` | IXIC·QQQ·TQQQ와 다중자산 ETF의 일별 조정 OHLC |
| `scripts/` | 시장 데이터 수집과 검증 |
| `tests/` | 데이터 생성 로직 테스트 |
| `docs/` | 전략, 연구 방법론과 참고 자료 |
| `.github/workflows/` | 일일 데이터 갱신 자동화 |

## 데이터

`assets/`에는 다음 파일이 있습니다.

| 파일 | Yahoo 심볼 | 내용 |
| --- | --- | --- |
| `IXIC.csv` | `^IXIC` | Nasdaq Composite 지수 |
| `QQQ.csv` | `QQQ` | Invesco QQQ ETF |
| `TQQQ.csv` | `TQQQ` | ProShares UltraPro QQQ 및 상장 전 합성 데이터 |
| `SPY.csv`, `EFA.csv`, `VEU.csv` | 동일 | 미국·미국 외 주식 프록시 |
| `IEF.csv`, `AGG.csv` | 동일 | 미국 중기 국채·종합채권 프록시 |
| `VNQ.csv`, `DBC.csv`, `GLD.csv` | 동일 | 리츠·원자재·금 프록시 |

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

## 백테스트

공개 모델 1차 배치를 재현합니다.

```bash
python scripts/backtest_models.py --batch batch-01 --output results/manual-run
```

개별 전략, 기간, 초기 자산과 수수료를 지정할 수 있습니다.

```bash
python scripts/backtest_models.py \
  --strategy faber_10m \
  --start 2010-02-11 \
  --initial-cash 100000 \
  --fee-rate 0.001 \
  --output results/manual-run
```

연구 보고서의 전체·롤링·스트레스·비용 민감도 결과는 다음 명령으로 재생성합니다.

```bash
python scripts/analyze_model_batch.py --batch batch-01 --output results/research/batch-01
```

다중자산 3차 배치는 다음과 같이 재생성합니다.

```bash
python scripts/analyze_allocation_batch.py --output results/research/batch-03
```

## 토스증권 계좌 조회

자격증명을 `.env`에 설정하고 실행합니다.

```bash
python scripts/toss_api.py
```

설정, 보안 규칙과 응답 해석은 [토스증권 Open API 연동 문서](docs/integrations/toss-api.md)를 확인합니다.

## 자동 갱신

GitHub Actions는 매일 `23:00 UTC`에 일일 갱신을 실행합니다. Nasdaq 휴장일에는 파일을 변경하지 않으며, 검증된 CSV에 실제 차이가 있을 때만 커밋하고 푸시합니다.
