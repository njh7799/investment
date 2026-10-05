"""Editorial index. Rules and numerical results remain in their original sources."""
from pathlib import Path
import re

# id, document, results directory, family, status, question, finding, lesson
ROWS = [
('batch-01','batches/01-single-asset-timing.md','research/batch-01','추세·타이밍','미채택','공개된 타이밍 규칙으로 TQQQ의 손실과 회복을 개선할 수 있을까?','일부 모멘텀 모델의 수익은 높았지만 낙폭과 회복기간을 함께 개선하지 못했다.','한 기간의 수익률보다 여러 시작점에서의 낙폭과 회복을 함께 확인해야 한다.'),
('batch-02','batches/02-bll-technical-rules.md','research/batch-02','추세·타이밍','미채택','장기 이동평균의 최근 성과는 다른 기간에도 유지될까?','최근 10년의 강점이 실제 전체·합성·롤링 기간에서 일관되게 이어지지 않았다.','좋았던 기간 하나를 선택하는 것과 견고한 규칙을 찾는 것은 다르다.'),
('batch-03','batches/03-multi-asset-allocation.md','research/batch-03','다중자산','미채택','여러 자산으로 분산하면 성장과 방어를 함께 얻을 수 있을까?','GTAA와 GEM은 손실을 줄였지만 VO 성장 목표를 대체할 만큼 수익을 유지하지 못했다.','낮은 위험을 위한 전략과 높은 장기 성장을 위한 전략은 목적을 나누어 평가한다.'),
('batch-04','batches/04-paa2.md','research/batch-04','다중자산','미채택','시장 전반의 약세에 비례해 방어하면 회복까지 빨라질까?','PAA2의 낮은 낙폭이 수익과 장기 미회복 구간의 개선으로 이어지지는 않았다.','낙폭의 깊이뿐 아니라 이전 고점을 회복하는 데 걸린 시간도 중요하다.'),
('batch-05','batches/05-moving-average-vo.md','research/ma-vo','VO 확장','미채택','이동평균을 VO에 결합하면 더 안정적인 개선이 생길까?','458개 변형에서 관찰한 일부 개선은 인접 파라미터와 다른 구간에서 유지되지 않았다.','가장 높은 값 하나를 사후 선택하지 않고 주변 설정에서도 효과가 유지되는지 본다.'),
('batch-06','batches/06-defensive-allocation.md','research/batch-06','다중자산','미채택','VAA와 DAA의 빠른 방어는 장기 성장에도 도움이 될까?','위기 방어에는 성과가 있었지만 수익·회복·비용 조건에서 VO 대체 기준에 못 미쳤다.','급락 방어 성공만으로 전체 투자 목적을 달성했다고 판단하지 않는다.'),
('batch-07','batches/07-flexible-asset-allocation.md','research/batch-07','다중자산','미채택','수익·변동성·상관을 함께 고려한 FAA는 독립 비교군을 이길까?','위기 방어는 확인됐지만 최근·롤링·비용 게이트를 모두 통과하지 못했다.','먼저 전략 자체의 목적과 비교군으로 평가한 뒤 저장소 내 역할을 판단한다.'),
('batch-08','batches/08-vo-bull-participation.md','research/vo-bull-participation','VO 확장','미채택','상승 참여를 높이는 68개 변형은 반복 가능한 개선일까?','개선이 주로 2020년 한 사건에 집중됐고 닷컴 구간 방어가 약해졌다.','같은 사건이 여러 롤링 창에 들어가도 독립적인 성공 사례 여러 개로 세지 않는다.'),
('batch-09','batches/09-erc-8etf.md','research/batch-09','다중자산','실행 실패','동일 위험기여 포트폴리오를 사전등록 오차 이내로 재현할 수 있을까?','첫 신호에서 위험기여 오차 허용치를 넘겨 성과를 생성하지 않았다.','수치 재현에 실패하면 허용오차를 사후 완화하지 않고 실패 자체를 기록한다.'),
('batch-10','batches/10-permanent-portfolio.md','research/batch-10','다중자산','외부 참고','Permanent Portfolio의 15/35 밴드는 거래를 줄이며 목적을 달성할까?','연례 동일비중 대비 독립 기준을 통과해 저위험 목적의 외부 참고 전략으로 남겼다.','VO를 대체하지 않더라도 다른 투자 목적에서 의미 있는 전략일 수 있다.'),
('batch-11','batches/11-jordan-ixic-three-percent.md','research/batch-11','급락 대응','미채택','나스닥 -3% 규칙과 TQQQ 비중 변형은 원래 목적을 달성할까?','최근·롤링·낙폭과 VO 비교 기준을 통과하지 못했다.','같은 이름의 전략도 판본과 실제 규칙을 분리해서 비교해야 한다.'),
('vo-upside','vo-upside-recovery.md','research/vo-upside-directional','VO 확장','추가 검증 대기','급반등 때 VO 감축을 일찍 해제하면 장기 성과가 개선될까?','회복 확인형은 수익 개선과 함께 낙폭·미회복 기간 악화가 관찰돼 미관측 기간 검증 대상으로 보류했다.','규칙을 만든 계기가 된 사례는 독립 검증 성과로 세지 않는다.'),
('vo-sgov','vo-sgov-cash-sleeve.md','vo-sgov','VO 확장','연구 기록','현금 구간을 SGOV로 바꾸면 비용 후에도 이익일까?','연구 기간의 최종 자산은 증가했지만 추가 거래 비용이 이익의 상당 부분을 소모했다.','현금 수익의 보강과 방어 규칙 자체의 개선을 구분한다.'),
('vo-regimes','vo-regime-returns.md','vo-regimes','구간 분석','연구 기록','VO 변동성 밴드가 유지되는 동안 TQQQ는 어떻게 움직였을까?','밴드별 구간 수익은 기간 길이가 달라 단순 평균만으로 기대수익을 해석할 수 없다.','기초자산 구간 등락률은 실제 체결을 반영한 포트폴리오 수익률이 아니다.'),
]
GENERAL = {'README.md','program-summary.md','methodology.md','discovery-protocol.md','promotion-criteria.md','candidates.md','model-census.md','rejected-strategies.md','automation-log.md','batches/README.md'}
STRATEGIES = {
'volatility-allocation':('VO · 변동성 배분','기본 전략','변동성이 커지면 TQQQ 노출을 줄이고, 상태가 바뀔 때만 거래한다.'),
'ixic-three-percent-rule':('IXIC 3% 규칙','독립 전략','나스닥 급락 상태와 TQQQ 하락 구간을 결합한다.'),
'value-rebalancing':('VR 5.0 · 가치 리밸런싱','외부 참고','평가금이 목표 밴드를 벗어날 때 수량을 조절한다.'),
'permanent-portfolio':('Permanent Portfolio','외부 참고','주식·장기국채·금·현금을 분산하고 15/35 밴드로 점검한다.'),
}

def catalog(root: Path):
    entries=[]
    for id,doc,result,family,status,question,finding,lesson in ROWS:
        path='docs/research/'+doc
        title=re.sub(r'^\d+차 배치:\s*','',(root/path).read_text().splitlines()[0].lstrip('# '))
        entries.append(dict(id=id,title=title,document=path,results='results/'+result,family=family,status=status,question=question,finding=finding,lesson=lesson))
    return entries

def validate_coverage(root: Path):
    expected={r[1] for r in ROWS}|GENERAL
    actual={str(p.relative_to(root/'docs/research')) for p in (root/'docs/research').rglob('*.md') if 'preregistrations' not in p.parts}
    if actual != expected:
        raise ValueError(f'Research catalog mismatch: unregistered={actual-expected}, missing={expected-actual}')
    known={str(root/'results'/r[2]) for r in ROWS}
    actual_results={str(p.parent) for p in (root/'results').rglob('*') if p.suffix in ('.csv','.json')}
    if actual_results-known:
        raise ValueError(f'Unregistered results: {actual_results-known}')
