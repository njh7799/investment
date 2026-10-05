# 투자 분석 기록

공개 주소: https://njh7799.github.io/investment/

## 사용 흐름

첫 화면은 투자 방법이다. 모든 화면 너비에서 카드가 한 열로 이어진다. VO만 처음에 펼쳐져 있고, 접으면 상태·이름·요약과 CAGR·MDD 및 평가 기간을 보여준다. 펼치면 나머지 성과·정적 차트·규칙·판단·상세 링크가 이어진다. VO와 IXIC·VR·Permanent Portfolio뿐 아니라 미채택·보류·실행 실패 방법도 같은 목록에 연결한다. 방법 이름에는 연구 실행 순번을 붙이지 않는다. 카드에는 작동 규칙, 차트와 같은 평가 기간의 CAGR·MDD·최장 미회복 기간·거래 빈도, 판단과 한계를 표시한다. 수치는 `reporting/methods.py`의 명시적인 모델·평가 기간 참조로 기존 CSV에서 직접 가져온다. 방법마다 실제 평가 기간을 표시한다. 여러 설정을 비교한 방법군은 최고 수익 설정을 대표로 고르지 않으며, 소규모 설정은 카드 안의 표로, 큰 방법군은 전체 결과 링크로 연결한다.

상단 메뉴는 투자 방법 → 분석 기록 → 평가 기준이다. 방법 상세에서는 규칙 → 성과·차트 → 선택 근거·관련 분석 → 대체·추가 규칙 순으로 읽는다. 연구에서 관련 방법으로 되돌아갈 수 있으며 대체 규칙 문서도 소속 방법의 경로를 표시한다.

`/research/`는 전체 분석 목록이다. 검색·전략군·판정 필터와 기준일 정렬을 제공하고 검색 조건은 URL에 저장된다. 원전 조사·보류·재현 실패 목록은 `/research/audits/`에 있다. 각 분석은 결과·해석 메모, 기간별 결과 표, 차트, 규칙·분석 원문 순으로 읽는다.

최신 VO·TQQQ·QQQ 비교는 `/strategies/volatility-allocation/#performance`에 있다. 기존 `/backtests/`·`/operation/`은 이 위치로, `/strategies/`는 메인으로 이동한다. 현재 목표 비중·매매 신호·시장 현황은 사이트에 표시하거나 데이터로 생성하지 않는다. 일일 카카오 보고서는 기존대로 유지한다.

## 카드 차트와 상세 위치

상세 화면에는 별도의 배경을 가진 현재 위치 표시줄, 상위 목록 링크와 문서 유형이 표시된다. 세부 규칙·차트에서는 소속 방법도 경로에 포함한다.

카드 차트는 기본 최근 10년이며 VO만 최신 데이터로 갱신한다. 다른 단일 모델은 `python -m reporting.preview_restore`로 당시 코드·해시를 복원하고 저장된 `recent_10y`·전체 기간 수치와 대조한 `reporting/archive/previews/`를 사용한다. SGOV는 이용 가능한 10년 미만 전체 구간과 별도 수수료 조건을 따른다. TQQQ는 각 모델의 실제 종료일과 동일 비용으로 계산한다. 다중자산에서는 참고 비교로 표시하고 독립 비교군은 기존 상세에 보존한다. 여러 설정을 갖는 방법군과 실행 실패는 대표 설정의 차트를 임의로 만들지 않는다.

생성 PNG는 16×8인치·180 DPI이며 전체 거래일과 낙폭을 포함한다. 이미지에서 기간 선택·확대·HTML 다운로드가 가능한 대화형 차트로 연결된다. Linux 빌드에는 `fonts-noto-cjk`가 필요하다. 생성 이미지·JSON은 버전 관리하지 않으며 과거 복원 압축 데이터만 보존한다.

## 로컬 실행

저장소 루트에서 Python 3.14 가상환경과 기존 requirements.txt를 설치하고, Node.js 24와 pnpm 11.25.0을 준비한다.

```bash
pnpm --dir site install --frozen-lockfile
python -m reporting.build
pnpm --dir site dev
```

`http://localhost:4321/investment/`에서 확인한다. Markdown 원본은 기존 docs, 수치 원본은 기존 results다. 사이트 생성물과 node_modules는 커밋하지 않는다.

## 검증

```bash
python -m pytest --quiet
python -m reporting.build
pnpm --dir site check
pnpm --dir site build
pnpm --dir site verify
pnpm --dir site exec playwright install chromium
pnpm --dir site exec playwright test
```

## 연구 추가

1. 기존 절차에 따라 문서·사전등록·결과를 기록한다.
2. `reporting/catalog.py`에 질문, 결론, 배운 점과 원본 경로를 등록한다. 기존 보고서나 CSV를 수정해 사이트에 맞추지 않는다.
3. 일별 곡선을 보완할 때 `python -m reporting.restore study-id`를 실행한다. 당시 코드와 데이터만 임시 디렉터리로 복원한다. 입력 해시와 기존 성과가 일치한 곡선만 압축 아카이브에 저장한다. 기존 아카이브가 있으면 재계산하지 않는다.
4. 실패·미재현 연구는 성과를 만들지 않고 상태와 이유를 표시한다. 표·보고서는 원본을 유지한다.
5. 위 검증 후 커밋한다. 등록되지 않은 결과 디렉터리와 연구 문서는 검증 오류가 된다.

대규모 변형 연구의 차트는 문서에서 다룬 가족과 인접 설정을 보여준다. 전체 변형·롤링·위기·비용 결과는 검색·정렬 가능한 표와 CSV로 제공한다. 각 곡선의 평가 구간은 함께 표시한다. 과거 채택 판정은 매일 변경하지 않는다.

## 배포와 일일 작업

`Publish investment reports`가 main push, 수동 실행, `Update market data` 성공에 반응한다. 데이터 봇 커밋은 push 워크플로를 실행하지 않으므로 workflow_run을 별도로 사용한다. 해당 실행 시작 시 main의 최신 커밋을 읽고, 생성 데이터의 커밋과 가격 해시를 기록한다.

`Update market data`와 `Daily market and VO briefing`은 기존 그대로 유지한다. 사이트 작업은 카카오 자격증명을 받지 않으며 메시지를 보내거나 계좌를 조회하지 않는다. 실패한 빌드는 배포되지 않고 이전 정상 사이트가 유지된다. 기본 GitHub Actions 실패 알림과 실행 로그에서 원인을 확인한다. 오류를 수정한 뒤 사이트 워크플로만 다시 실행하면 되며 카카오 발송을 재실행할 필요는 없다.

사이트의 생성 시각과 시장 데이터 기준일은 별개다. XNAS 달력의 다음 거래일 마감 후 2시간부터 이전 데이터는 지연 상태로 표시된다. 브라우저 시계를 이용하므로 기기 시계가 부정확하면 지연 표시도 달라질 수 있다.

Pages 설정은 GitHub Actions 배포이며, site/dist만 공개한다. 롤백은 정상 버전의 사이트 코드를 복구하고 이 워크플로로 재배포한다. 일일 분석은 VO·TQQQ·QQQ만 계산하고 과거 연구를 다시 실행하지 않는다.
