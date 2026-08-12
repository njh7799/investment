# 문서 안내

이 디렉터리는 전략 규칙, 연구 기준, 공통 참고 자료와 외부 연동 문서를 관리한다. 시장 데이터와 모든 전략에 공통인 분석·체결 기준은 루트 [AGENTS.md](../AGENTS.md)를 따른다.

## 문서 구성

| 경로 | 역할 |
| --- | --- |
| [`strategies/`](strategies/) | 실행 가능한 전략 규칙, variants와 addons |
| [`research/`](research/) | [프로그램 요약](research/program-summary.md), [블라인드 조사 절차](research/discovery-protocol.md), [평가 방법론](research/methodology.md), [승격 기준](research/promotion-criteria.md), [후보](research/candidates.md), [조사 목록](research/model-census.md)과 [폐기 전략 기록](research/rejected-strategies.md) |
| [`reference/`](reference/) | [시장 데이터 정책](reference/market-data-policy.md), [차트 사양](reference/chart-conventions.md)과 [SPY 기준 주요 시장 하락 사건](reference/market-events.md) |
| [`integrations/`](integrations/) | [토스증권 Open API 연동](integrations/toss-api.md) |

## 문서 규격

- 각 전략 디렉터리의 `README.md`는 추가 파일 없이 실행 가능한 기본 규칙을 정의한다.
- `variants/`는 기본 규칙의 일부를 대체하는 상호 배타적 설정을 관리한다. 한 영역에는 하나의 variant만 적용한다.
- `addons/`는 기본 전략에 선택적으로 덧붙이며 서로 조합할 수 있는 규칙을 관리한다.
- variant와 addon 문서는 기본 README를 반복하지 않고 변경하는 부분만 정의한다.
- 디렉터리가 필요할 때만 생성하며 빈 `variants/`나 `addons/`는 두지 않는다.

## 전략군

| 전략군 | 상태 | 설명 |
| --- | --- | --- |
| [VO(변동성 배분)](strategies/volatility-allocation/) | 기본 전략 | TQQQ 실현 변동성으로 비중을 조절하며 30일 변동성 기준 100%·50%·0% 배분을 기본 설정으로 사용한다. |
| [IXIC 3% 규칙](strategies/ixic-three-percent-rule/) | 독립 전략 | IXIC 급락으로 공황·대공황을 판정하고 TQQQ 하락 구간에 따라 비중을 조절한다. |
| [라오어 VR 5.0](strategies/value-rebalancing/) | 외부 참고 | TQQQ 평가금을 목표 V 밴드 안에서 관리하는 거치식 비교 전략이다. |
| [Permanent Portfolio 15/35](strategies/permanent-portfolio/) | 외부 참고 | 주식·장기 국채·금·현금을 25%씩 보유하고 연례 15/35 밴드 이탈 때만 재조정한다. |

기본 전략은 별도 전략명이 없는 백테스트의 기준 모델이다. 연구 후보는 규칙과 파라미터가 확정되지 않았으므로 결과를 기본 전략으로 해석하지 않는다. 외부 참고 전략은 원저작자의 방법론과 저장소의 재현 가정을 구분해 비교 목적으로만 사용한다.
