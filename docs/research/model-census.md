# 공개 투자 모델 조사 목록

조사일은 2026년 8월 3일이다. 1차 배치는 결과를 확인하기 전에 아래 모델과 파라미터로 고정했다. QQQ 또는 달력으로 신호를 계산하고 TQQQ·현금만 운용했다.

| 모델 | 계열 | 기본 규칙 | 출처·해석 | 처리 |
| --- | --- | --- | --- | --- |
| Faber 10개월 SMA | 추세 | 월말 종가 > 10개월 SMA | [Faber 원문](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf) | 백테스트 |
| 200일 SMA | 추세 | 종가 > 200일 SMA | Faber 규칙의 일별 근사 | 백테스트 |
| Golden Cross | 추세 | 50일 SMA > 200일 SMA | Brock·Lakonishok·LeBaron(1992) 이동평균 규칙 | 백테스트 |
| 12개월 절대모멘텀 | 모멘텀 | 월말 12개월 수익률 > 0 | Antonacci, 현금수익률 0 가정 | 백테스트 |
| 12개월 TSMOM | 모멘텀 | 12개월 수익률의 부호 | [Moskowitz·Ooi·Pedersen](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf) | long/cash 적용, 절대모멘텀과 중복 |
| Turtle System 2 | 돌파 | 55일 고가 진입·20일 저가 청산 | [Turtle 규칙](https://www.turtletrader.com/rules/) | 단일 자산 long/cash로 적용 |
| Halloween | 계절성 | 11–4월 투자 | [Bouman·Jacobsen](https://www.aeaweb.org/articles?id=10.1257%2F000282802762024683) | 백테스트 |
| Turn of the Month | 계절성 | 월 말일·월 첫 3거래일 | Lakonishok·Smidt(1988) | 백테스트 |
| MACD | 추세 | EMA 12–26·신호 9 | Gerald Appel 표준 설정 | 백테스트 |
| Connors RSI(2) | 평균회귀 | RSI(2)<10 진입·종가>5일 SMA 청산 | Connors·Alvarez | 백테스트 |
| IXIC 3% 규칙 | 시장 상태 | IXIC 급락·TQQQ ZigZag 구간 | [저장소 규칙](../strategies/ixic-three-percent-rule/) | 전용 상태 엔진·공통 체결 규칙 |
| VR 5.0 거치식 | 가치 리밸런싱 | 10거래일·G=10·±15% | [저장소 비교 프로필](../strategies/value-rebalancing/) | 종가 밴드 신호·다음 시가 체결 |
| CPPI | 포트폴리오 보험 | 쿠션×배수 | Black·Perold | 재현 불가: 원전이 배수·플로어를 단일 기본값으로 고정하지 않음 |
| Bollinger Bands | 돌파·평균회귀 | 20일·2σ 밴드 | John Bollinger | 재현 불가: 밴드 자체는 매매 규칙이 아님 |

TSMOM 원전의 공매도와 변동성 스케일링, Turtle의 복수 선물·ATR 포지션 사이징은 1차 제약과 달라 제외했다. 결과는 원전 재현이 아니라 TQQQ long/cash 적용으로 해석한다.

## 2차 배치: BLL 기술적 규칙 사전 정의 집합

[Brock·Lakonishok·LeBaron(1992)](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x)이 논문에서 대중적인 규칙으로 미리 선택한 집합을 그대로 등록했다. VMA는 `(1,50)`, `(1,150)`, `(5,150)`, `(1,200)`, `(2,200)`을 각각 밴드 0%와 1%로 실행한다. TRB는 직전 50·150·200일 최고·최저 종가 돌파를 사용한다.

- VMA 매수: 단기 SMA가 장기 SMA의 `1 + band`보다 큼
- VMA 매도: 단기 SMA가 장기 SMA의 `1 - band`보다 작음
- 밴드 안에서는 새로운 신호가 없으므로 직전 보유 상태 유지
- TRB 매수·매도: 현재 종가가 현재일을 제외한 직전 N일 최고·최저 종가를 돌파
- 원전의 매도/공매도 상태는 현금으로 바꾸고 QQQ 신호로 TQQQ를 운용

따라서 이 배치는 원전의 수익률 검정 자체를 재현하는 것이 아니라, 원전에 사전 정의된 신호를 저장소의 long/cash 체결 규칙에 이식한 비교다. 기존 `sma_200`은 VMA `(1,200,0%)`와 같아 2차 결과에서 중복 여부를 확인하되 별도 모델로 다시 세지 않는다.
