"""Method navigation and exact, frozen result references; no new strategy calculations."""
import gzip
import json
import pandas as pd

METHODS = {
    'volatility-allocation': dict(
        name='VO · 변동성 배분', status='현재 기본 방법 · addon ON', category='TQQQ · 변동성 대응',
        summary='TQQQ의 장기 성장에 참여하면서 변동성이 커지면 현금을 늘리고, 5/20 상향돌파 때 구간당 한 번 반등에 추가 참여합니다.',
        mechanics='최근 30거래일의 연율화 변동성을 보고 세 단계로 배분합니다. 60% 이하에서는 TQQQ 100%, 60% 초과 90% 이하에서는 50%, 90%를 넘으면 현금으로 전환합니다. ',
        cadence='상태가 바뀔 때만 거래 · 종가 판단, 다음 시가 체결',
        decision='핵심 VO는 비교 기준으로 유지하고, 현재 공격형 운용 프로필에는 5/20 상향돌파·구간당 1회 addon을 활성화합니다.',
        limitation='addon의 초과성과는 소수의 강한 V자 반등에 집중됐고 MDD가 더 깊었습니다. 30일 기본값과 addon 선정 모두 과거 데이터를 사용했으므로 미래 성과의 독립 검증과 구분합니다.',
        batch='batch-01', model='vo', period='full_synthetic',
        peers=['vo','tqqq_hold','qqq_hold'], studies=['batch-01','batch-05','batch-08','batch-13','batch-14','batch-15','vo-upside','vo-sgov','vo-regimes']),
    'ixic-three-percent-rule': dict(
        name='IXIC 3% 규칙', status='독립 전략', category='TQQQ · 급락 대응',
        summary='나스닥의 급락 이력으로 시장 상태를 나누고, TQQQ가 기준 고점에서 얼마나 하락했는지에 따라 대응합니다.',
        mechanics='IXIC가 하루 3% 이상 하락하면 공황, 한 달 안에 네 번 발생하면 대공황으로 봅니다. 정상·공황에서는 TQQQ 하락률을 10개 구간으로 나누어 배분하고, 대공황에서는 현금을 유지합니다.',
        cadence='시장 상태·가격 구간 변경 시 거래 · 다음 시가 체결',
        decision='실행 가능한 독립 규칙으로 보존합니다. 전체 구간에서 VO보다 수익률이 낮고 낙폭이 커 기본 방법을 대체하지 않았습니다.',
        limitation='시장 상태 만료와 고점 확정 등 관리할 조건이 많습니다. 이 저장소의 10구간 규칙과 별도로 검토한 Jordan 공개 규칙은 서로 다른 판본입니다.',
        batch='batch-01', model='three_percent', period='full_synthetic',
        peers=['three_percent','vo','tqqq_hold','qqq_hold'], studies=['batch-01','batch-11']),
    'value-rebalancing': dict(
        name='VR 5.0 · 가치 리밸런싱', status='외부 참고', category='TQQQ · 평가금 밴드',
        summary='TQQQ 평가금의 목표값을 정하고, 그 값에서 크게 벗어나면 현금 Pool과 주식 사이에서 사고팝니다.',
        mechanics='거치식 비교 프로필입니다. 초기 TQQQ 90%·현금 10%, 10거래일마다 목표 평가금 V를 현금 Pool의 1/10만큼 늘립니다(G=10). V의 ±15% 밴드를 벗어나면 V로 되돌리고, 사이클당 매수는 시작 Pool의 50%로 제한합니다.',
        cadence='10거래일 목표값 갱신 · 밴드 이탈 시 다음 시가 체결',
        decision='상승 구간의 높은 수익과 하락 구간의 현금 소진을 함께 살펴보기 위한 참고 방법입니다. 일부 구간의 높은 수익만으로 기본 방법으로 선택하지 않았습니다.',
        limitation='장기 하락으로 Pool이 소진되면 방어력이 약해집니다. 달력 2주 대신 10거래일, 지정가 대신 다음 시가로 비교하므로 원 방법론의 실제 운용 성과와 다릅니다.',
        batch='batch-01', model='vr5', period='full_synthetic',
        peers=['vr5','vo','tqqq_hold','qqq_hold'], studies=['batch-01']),
    'permanent-portfolio': dict(
        name='Permanent Portfolio', status='외부 참고', category='다중자산 · 분산',
        summary='주식·장기국채·금·현금을 나누어 보유하며, 성장보다 손실 폭과 거래를 줄이는 데 무게를 둡니다.',
        mechanics='SPY·TLT·GLD·SHY를 각각 25%로 시작합니다. 어느 자산이 15% 미만 또는 35% 초과가 되면 네 자산을 다시 25%씩 맞춥니다.',
        cadence='15/35 밴드 이탈 시 전체 리밸런싱 · 다음 시가 체결',
        decision='연례 동일비중 방식과의 독립 평가 기준을 통과해 저위험 목적의 참고 방법으로 남겼습니다. 높은 TQQQ 장기 성장을 추구하는 VO와 목적이 다릅니다.',
        limitation='낮은 낙폭과 낮은 수익률을 함께 받아들여야 합니다. ETF는 원전 자산의 대체물이며 원전 수익률을 그대로 재현하지 않습니다.',
        batch='batch-10', model='permanent_band', period='common_full',
        peers=['permanent_band','permanent_annual_equal','permanent_buyhold'], studies=['batch-10']),
}

def method_data(root, strategies, write_chart):
    result=[]
    for id, spec in METHODS.items():
        source=f'results/research/{spec["batch"]}/period-summary.csv'
        table=pd.read_csv(root/source)
        rows=table[(table.model==spec['model']) & (table.period==spec['period'])]
        if len(rows)!=1:
            raise ValueError(f'Ambiguous method result: {id}')
        metrics=rows.iloc[0].to_dict()
        recent=table[(table.model==spec['model']) & (table.period=='recent_10y')]
        recent_metrics=recent.iloc[0].to_dict() if len(recent)==1 else None
        archive=json.loads(gzip.decompress((root/f'reporting/archive/{spec["batch"]}.json.gz').read_bytes()))
        curves=[c for name in spec['peers'] for c in archive['curves'] if c['model']==name]
        if len(curves)!=len(spec['peers']):
            raise ValueError(f'Missing method curves: {id}')
        for curve in curves:
            if (curve['dates'][0],curve['dates'][-1])!=(metrics['start'],metrics['end']):
                raise ValueError(f'Method comparison period mismatch: {id}')
        file=f'data/method-{id}.json'
        write_chart(file,curves)
        result.append(dict(id=id,title=spec['name'],role=strategies[id][1],description=spec['summary'],**spec,
                           metrics=metrics,recent_metrics=recent_metrics,metric_source=source,chart=file))
    return result


def buy_hold_card(root):
    """Build the explicit TQQQ baseline card from the same frozen study as VO."""
    source='results/research/batch-01/period-summary.csv'
    table=pd.read_csv(root/source)
    rows=table[(table.model=='tqqq_hold') & (table.period=='full_synthetic')]
    if len(rows)!=1:
        raise ValueError('Ambiguous TQQQ buy-and-hold result')
    recent=table[(table.model=='tqqq_hold') & (table.period=='recent_10y')]
    return dict(
        id='tqqq-buy-hold',title='TQQQ Buy & Hold',role='비교 기준',status='비교 기준',
        category='TQQQ · 단순 보유',
        summary='TQQQ를 처음 매수한 뒤 시장 상황과 관계없이 계속 보유하는 비교 기준입니다.',
        mechanics='평가 시작일에 TQQQ를 매수하고 이후에는 매도하거나 비중을 조절하지 않습니다.',
        cadence='최초 1회 매수 · 이후 계속 보유',
        decision='VO가 장기 성장과 위험 사이에서 어떤 차이를 만들었는지 판단하기 위한 기준선입니다. 별도의 진입·회피 규칙이 없어 TQQQ 자체의 상승 참여와 손실을 그대로 보여줍니다.',
        limitation='레버리지 ETF에 항상 100% 노출되므로 큰 하락과 긴 회복 기간을 그대로 감수합니다. 높은 장기 수익률만 보고 실제 운용 방법으로 선택한 카드는 아닙니다.',
        batch='batch-01',model='tqqq_hold',period='full_synthetic',studies=['batch-01'],
        metrics=rows.iloc[0].to_dict(),recent_metrics=recent.iloc[0].to_dict() if len(recent)==1 else None,metric_source=source,
        href='strategies/tqqq-buy-hold/',detail_page=True,
    )
