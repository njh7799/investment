# 전략 연구

이 디렉터리는 실행 전략으로 승격하기 전의 조사 기준, 실험 결과와 판정을 관리한다. 공통 평가 방법은 [방법론](methodology.md), 개별 실행 결과는 [`batches/`](batches/)에서 확인한다.

| 문서 | 역할 |
| --- | --- |
| [프로그램 요약](program-summary.md) | 공개 모델 연구의 범위와 전체 결론 |
| [평가 방법론](methodology.md) | 기간, 지표, 비교군과 판정 기준 |
| [블라인드 조사 프로토콜](discovery-protocol.md) | 탐색·원전 검증·사전등록·통합의 정보 분리 절차 |
| [승격 기준](promotion-criteria.md) | 독립 전략, VO 대체와 addon의 사전 판정 기준 |
| [`preregistrations/`](preregistrations/) | 결과 확인 전에 고정한 후보와 배치 명세 |
| [자동 조사 기록](automation-log.md) | 일일 조사 결과와 3회 연속 포화 여부 |
| [모델 조사 목록](model-census.md) | 조사한 모델, 원전과 적용 방식 |
| [연구 후보](candidates.md) | 추가 검증 중이며 아직 승격하지 않은 모델 |
| [폐기 전략 기록](rejected-strategies.md) | 채택하지 않은 이유와 재검토 조건 |
| [VO 상승 대응 연구](vo-upside-recovery.md) | VO의 급상승장 대응 변형과 결과 |
| [VO 연도별 수익과 비중 조절의 기회비용](vo-annual-tradeoffs.md) | 연간 수익률, 감축 중 놓친 상승과 100% 비중 중 하락 |
| [VO 경계 완충 연구](batches/12-vo-boundary-buffers.md) | 히스테리시스·확인일수·최소 유지기간의 왕복 감소와 CAGR·MDD 영향 |
| [VO 급반등 재진입 연구](batches/13-vo-rebound-entry.md) | 급반등 신호와 실제 매수가 손절의 반복 휩쏘 위험 |
| [VO 연속 상승 재진입 연구](batches/14-vo-consecutive-up.md) | 연속 상승 확인 속도와 매수가 손절의 수익·위험 절충 |
| [VO V자 반등 참여 제어 연구](batches/15-vo-v-recovery-controls.md) | 빠른 참여와 반복 손절 제한을 분리한 24개 정책 비교 |

정확히 재현되고 사전 정의한 역할별 기준을 통과한 규칙만 [`../strategies/`](../strategies/)로 옮긴다. 공개 전략은 VO와 독립적으로 먼저 평가하고, 기본 VO 변경 여부는 그 다음 통합 단계에서 별도로 판정한다.
