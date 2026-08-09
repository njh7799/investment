# 실행 전략

이 디렉터리는 추가 설정 없이 실행할 수 있는 기본 전략과 그 대체·선택 규칙을 관리한다. 아직 검증 중인 아이디어는 [`../research/`](../research/)에 두며 이곳에 바로 추가하지 않는다. 신규 공개 전략과 VO 대체·addon은 [사전 정의된 승격 기준](../research/promotion-criteria.md)을 통과한 뒤 추가한다.

| 전략 | 상태 |
| --- | --- |
| [VO](volatility-allocation/) | 저장소 기본 전략 |
| [IXIC 3% 규칙](ixic-three-percent-rule/) | 독립 전략 |
| [라오어 VR 5.0](value-rebalancing/) | 외부 참고 전략 |

각 전략의 `README.md`가 기본 규칙 전체를 정의한다. `variants/`는 기본값을 대체하는 상호 배타적 설정, `addons/`는 기본 규칙 위에 선택적으로 조합하는 설정이다.
