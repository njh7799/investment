"""Method navigation and exact, frozen result references; no new strategy calculations."""
import gzip
import json
import pandas as pd

METHODS = {
    'volatility-allocation': dict(
        name='VO · 변동성 배분', status='현재 기본 방법', category='TQQQ · 변동성 대응',
        summary='TQQQ의 장기 성장에 참여하면서, 변동성이 커지는 구간에서는 현금을 늘리는 방법입니다.',
        mechanics='최근 30거래일의 연율화 변동성을 보고 세 단계로 배분합니다. 60% 이하에서는 TQQQ 100%, 60% 초과 90% 이하에서는 50%, 90%를 넘으면 현금으로 전환합니다. ',
        cadence='상태가 바뀔 때만 거래 · 종가 판단, 다음 시가 체결',
        decision='수익률만 가장 높은 방법은 아니지만, 장기 수익·낙폭·회복·거래 빈도의 균형을 기준으로 현재 기본 방법으로 유지합니다. 이동평균 결합과 상승 참여 확대도 시험했지만 반복 가능한 개선을 확인하지 못했습니다.',
        limitation='급반등을 놓칠 수 있고 손실을 없애지는 못합니다. 실제 TQQQ 전체 구간에서는 단순 보유보다 수익률이 낮았습니다. 30일 기본값 선정에는 과거 데이터를 사용했으므로 미래 성과의 독립 검증과 구분합니다.',
        batch='batch-01', model='vo', period='actual_tqqq',
        peers=['vo','tqqq_hold','qqq_hold'], studies=['batch-01','batch-05','batch-08','vo-upside','vo-sgov','vo-regimes']),
    'ixic-three-percent-rule': dict(
        name='IXIC 3% 규칙', status='독립 전략', category='TQQQ · 급락 대응',
        summary='나스닥의 급락 이력으로 시장 상태를 나누고, TQQQ가 기준 고점에서 얼마나 하락했는지에 따라 대응합니다.',
        mechanics='IXIC가 하루 3% 이상 하락하면 공황, 한 달 안에 네 번 발생하면 대공황으로 봅니다. 정상·공황에서는 TQQQ 하락률을 10개 구간으로 나누어 배분하고, 대공황에서는 현금을 유지합니다.',
        cadence='시장 상태·가격 구간 변경 시 거래 · 다음 시가 체결',
        decision='실행 가능한 독립 규칙으로 보존합니다. 저장된 실제 TQQQ 구간에서 VO보다 수익률이 낮고 낙폭이 커 기본 방법을 대체하지 않았습니다.',
        limitation='시장 상태 만료와 고점 확정 등 관리할 조건이 많습니다. 이 저장소의 10구간 규칙과 별도로 검토한 Jordan 공개 규칙은 서로 다른 판본입니다.',
        batch='batch-01', model='three_percent', period='actual_tqqq',
        peers=['three_percent','vo','tqqq_hold','qqq_hold'], studies=['batch-01','batch-11']),
    'value-rebalancing': dict(
        name='VR 5.0 · 가치 리밸런싱', status='외부 참고', category='TQQQ · 평가금 밴드',
        summary='TQQQ 평가금의 목표값을 정하고, 그 값에서 크게 벗어나면 현금 Pool과 주식 사이에서 사고팝니다.',
        mechanics='거치식 비교 프로필입니다. 초기 TQQQ 90%·현금 10%, 10거래일마다 목표 평가금 V를 현금 Pool의 1/10만큼 늘립니다(G=10). V의 ±15% 밴드를 벗어나면 V로 되돌리고, 사이클당 매수는 시작 Pool의 50%로 제한합니다.',
        cadence='10거래일 목표값 갱신 · 밴드 이탈 시 다음 시가 체결',
        decision='상승 구간의 높은 수익과 하락 구간의 현금 소진을 함께 살펴보기 위한 참고 방법입니다. 실제 구간의 높은 수익만으로 기본 방법으로 선택하지 않았습니다.',
        limitation='장기 하락으로 Pool이 소진되면 방어력이 약해집니다. 달력 2주 대신 10거래일, 지정가 대신 다음 시가로 비교하므로 원 방법론의 실제 운용 성과와 다릅니다.',
        batch='batch-01', model='vr5', period='actual_tqqq',
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
                           metrics=metrics,metric_source=source,chart=file))
    return result


def buy_hold_card(root):
    """Build the explicit TQQQ baseline card from the same frozen study as VO."""
    source='results/research/batch-01/period-summary.csv'
    table=pd.read_csv(root/source)
    rows=table[(table.model=='tqqq_hold') & (table.period=='actual_tqqq')]
    if len(rows)!=1:
        raise ValueError('Ambiguous TQQQ buy-and-hold result')
    return dict(
        id='tqqq-buy-hold',title='TQQQ Buy & Hold',role='비교 기준',status='비교 기준',
        category='TQQQ · 단순 보유',
        summary='TQQQ를 처음 매수한 뒤 시장 상황과 관계없이 계속 보유하는 비교 기준입니다.',
        mechanics='평가 시작일에 TQQQ를 매수하고 이후에는 매도하거나 비중을 조절하지 않습니다.',
        cadence='최초 1회 매수 · 이후 계속 보유',
        decision='VO가 장기 성장과 위험 사이에서 어떤 차이를 만들었는지 판단하기 위한 기준선입니다. 별도의 진입·회피 규칙이 없어 TQQQ 자체의 상승 참여와 손실을 그대로 보여줍니다.',
        limitation='레버리지 ETF에 항상 100% 노출되므로 큰 하락과 긴 회복 기간을 그대로 감수합니다. 높은 장기 수익률만 보고 실제 운용 방법으로 선택한 카드는 아닙니다.',
        batch='batch-01',model='tqqq_hold',period='actual_tqqq',studies=['batch-01'],
        metrics=rows.iloc[0].to_dict(),metric_source=source,
        href='strategies/volatility-allocation/#performance',action_label='VO와 상세 비교 보기 →',
        detail_page=False,
    )

# Method families are navigation over the existing research, not new backtests.
# A family never receives the best variant's metrics as if it were one strategy.
RESEARCH_METHODS = [
    ('faber-10m','Faber 10개월 이동평균','batch-01','faber_10m','QQQ의 월말 가격과 10개월 평균으로 TQQQ 투자 여부를 결정합니다.','월말 QQQ 종가가 10개월 이동평균보다 높으면 TQQQ를 보유하고, 아니면 현금으로 대기합니다.'),
    ('sma-200','200일 이동평균','batch-01','sma_200','장기 이동평균 위에서는 투자하고 아래에서는 현금으로 대기합니다.','QQQ 종가와 200일 단순이동평균을 매일 비교해 TQQQ 100% 또는 현금으로 전환합니다.'),
    ('golden-cross','골든크로스 · 50/200일','batch-01','golden_cross','단기 평균이 장기 평균을 웃도는 상승 추세에 투자합니다.','QQQ 50일 이동평균이 200일 이동평균보다 높으면 TQQQ를 보유하고, 낮으면 현금으로 전환합니다.'),
    ('absolute-momentum','12개월 절대모멘텀 · 0% 비교','batch-01','absolute_momentum_12m','지난 12개월 수익이 양수일 때만 TQQQ를 보유합니다.','QQQ의 12개월 수익률을 월말에 0%와 비교합니다. 원전의 T-bill 비교와 다중자산 구성을 그대로 재현한 모델은 아닙니다.'),
    ('time-series-momentum','12개월 시계열 모멘텀 · 주식/현금','batch-01','tsmom_12m','과거 수익률의 방향을 이용하는 모멘텀을 TQQQ에 적용했습니다.','QQQ의 12개월 수익 부호를 월말에 확인합니다. 공매도와 변동성 스케일링을 제외한 주식/현금 적용으로, 이 구현에서는 절대모멘텀 0% 비교와 같은 경로입니다.'),
    ('turtle','터틀 · 55/20일 돌파','batch-01','turtle_55_20','장기 고점 돌파에 진입하고 단기 저점 이탈에 청산합니다.','QQQ가 이전 55거래일 최고 종가를 돌파하면 TQQQ에 진입하고, 이전 20거래일 최저 종가를 이탈하면 현금으로 전환합니다.'),
    ('halloween','핼러윈 계절성','batch-01','halloween','연중 특정 계절에만 주식을 보유하는 달력 규칙입니다.','11월부터 4월까지 TQQQ를 보유하고 나머지 기간에는 현금으로 대기합니다. 실제 체결은 달력 신호 이후 거래일 시가입니다.'),
    ('turn-of-month','월말·월초 효과','batch-01','turn_of_month','월이 바뀌는 짧은 구간에만 주식에 노출됩니다.','월의 마지막 거래일과 다음 달 첫 세 거래일을 투자 구간으로 사용합니다. 종가 신호와 다음 시가 체결 조건을 적용한 결과입니다.'),
    ('macd','MACD · 12/26/9','batch-01','macd','두 지수이동평균의 차이가 신호선을 웃돌면 투자합니다.','QQQ의 EMA12−EMA26을 9일 지수평균 신호선과 비교하여 TQQQ와 현금 사이를 전환합니다.'),
    ('rsi2','RSI(2) · 단기 평균회귀','batch-01','rsi2','단기 과매도 때 매수하고 가격이 회복되면 청산합니다.','QQQ RSI(2)가 10 미만이면 진입하고 종가가 5일 이동평균을 넘으면 청산합니다. TQQQ 주식/현금과 다음 시가 체결로 적용했습니다.'),
    ('bll-vma','BLL 이동평균 교차','batch-02','bll_vma_*','짧은 평균과 긴 평균의 교차에 0%·1% 밴드를 적용합니다.','사전에 정한 단기·장기 이동평균 조합 5개와 밴드 2개를 QQQ 신호·TQQQ/현금 운용으로 비교했습니다.'),
    ('bll-trb','BLL 거래범위 돌파','batch-02','bll_trb_*','과거 거래범위를 벗어나는 움직임으로 투자 여부를 정합니다.','QQQ의 50·150·200일 거래범위 돌파 규칙을 TQQQ 주식/현금 운용으로 각각 적용했습니다.'),
    ('gtaa5','GTAA · 5자산 추세 배분','batch-03','gtaa5','여러 자산을 나누어 보유하되 각 자산의 추세가 나쁘면 현금으로 바꿉니다.','SPY·EFA·IEF·VNQ·DBC에 20%씩 슬롯을 두고, 월말에 각 가격이 10개월 평균을 넘는 슬롯만 보유합니다.'),
    ('gem','GEM · 글로벌 주식 모멘텀','batch-03','gem','미국·해외 주식 중 강한 자산을 고르고, 둘 다 약하면 채권으로 이동합니다.','SPY·VEU의 12개월 수익률 중 높은 값이 0%를 넘으면 해당 자산, 아니면 AGG를 보유합니다. T-bill 대신 0%를 사용한 비교입니다.'),
    ('paa2','PAA2 · 방어 자산배분','batch-04','paa2','약세인 자산이 늘어날수록 방어자산 비중을 높입니다.','12개 위험자산 중 모멘텀이 0 이하인 수에 비례해 방어하고 나머지는 양의 모멘텀 상위 6개에 배분합니다. SHY/IEF 상대선택 대안을 사용했습니다.'),
    ('moving-average-vo','이동평균 단독·VO 결합','batch-05','*','이동평균으로 VO의 증액·감축을 확인하거나 투자 비중을 제한합니다.','53개 신호와 458개 변형을 고정했습니다. 단독형 106개와 VO 결합형 352개에서 비중 상한·하한·평균·증감 확인 등을 비교했습니다.'),
    ('vaa','VAA-G4 · 빠른 방어','batch-06','vaa_g4','위험자산 중 하나라도 약해지면 전액 방어자산으로 이동합니다.','SPY·EFA·EEM·AGG의 가중 모멘텀이 모두 양수이면 가장 강한 하나를 보유합니다. 하나라도 0 이하면 SHY·IEF·LQD 중 가장 강한 자산으로 전환합니다.'),
    ('daa','DAA-G12 · 카나리 방어','batch-06','daa_g12','별도의 경고 자산 두 개로 방어 비중을 정합니다.','EEM·AGG 중 모멘텀이 0 이하인 수에 따라 방어비중을 0·50·100%로 정합니다. 남은 비중은 12개 위험자산 중 상위 자산에 배분합니다.'),
    ('faa','FAA · 수익·위험·상관 배분','batch-07','faa_default','수익은 높고 변동성과 상관은 낮은 자산을 함께 고릅니다.','7자산의 최근 4개월 수익·변동성·상관 순위를 1:0.5:0.5로 합산해 상위 3개에 배분합니다. 수익률이 0 이하인 슬롯은 SHY로 바꿉니다.'),
    ('vo-bull','VO · 상승 참여 확대','batch-08','*','추세와 변동성 냉각을 확인해 VO의 감축을 늦추거나 비중을 복원합니다.','위험조정 추세, 단기/장기 변동성 비율, 시장 폭, 여러 기간의 합의와 회복 확인을 이용한 68개 변형을 비교했습니다.'),
    ('erc','ERC · 8자산 동일 위험기여','batch-09',None,'각 자산이 포트폴리오 위험에 같은 정도로 기여하도록 배분합니다.','8개 ETF의 252일 수익률 공분산으로 위험기여율을 각각 1/8로 맞추려 했습니다. 사전에 고정한 수치해법이 첫 신호에서 허용오차를 넘었습니다.'),
    ('jordan-public','조던 -3% · QQQ/TLT 공개형 프록시','batch-11','jordan_public_proxy','나스닥 급락 신호가 나오면 주식에서 장기채로 대피합니다.','정상 상태에서는 QQQ, 공황·대공황에서는 TLT를 보유합니다. 대기기간과 8거래일 연속 상승 종료 조건을 결정론적으로 구현한 프록시입니다.'),
    ('jordan-tqqq','조던 -3% · TQQQ 적용','batch-11','jordan_tqqq_*','공황 때 TQQQ를 얼마나 남길지 고정 비율로 비교합니다.','정상 TQQQ 100%, 공황 1/3, 대공황 0%를 주 모델로 고정했습니다. 공황 0%·2/3는 견고성 비교이며 사후 기본값 선정에 사용하지 않았습니다.'),
    ('vo-upside-method','VO · 급반등 대응','vo-upside','*','상승 방향과 회복을 확인해 변동성 때문에 줄인 노출을 되돌립니다.','수익률·상승일 분산 기여·상승/하락 크기·회복 조건과 비중 하한·한 단계 증액·감축 보류를 조합해 비교했습니다.'),
    ('vo-sgov-method','VO · 현금 대신 SGOV','vo-sgov',None,'VO의 현금 구간을 단기 미국 국채 ETF로 대체합니다.','기존 VO 신호와 리밸런싱 조건을 유지하고 현금 목표분만 SGOV로 바꿉니다. 주문금액별 수수료·절사 조건을 적용해 추가 거래 비용을 반영했습니다.'),
]


def research_method_data(root, studies):
    import fnmatch
    by_id={s['id']:s for s in studies}
    cards=[]
    for id,title,study_id,pattern,summary,mechanics in RESEARCH_METHODS:
        study=by_id[study_id]
        rows=[]; source=None
        if pattern:
            source=study['results']+'/period-summary.csv'
            table=pd.read_csv(root/source)
            period=next(p for p in ('actual_tqqq','actual_tqqq_full','actual_current','common_full') if p in set(table.period))
            selected=table[(table.period==period)&table.model.map(lambda name:fnmatch.fnmatchcase(name,pattern))]
            selected=selected[~selected.model.isin(['vo','tqqq_hold','qqq_hold','three_percent','vr5'])]
            if selected.empty: raise ValueError(f'Missing method results: {id}')
            rows=selected.to_dict('records')
        if study_id=='vo-sgov':
            source=study['results']+'/summary.csv'
            rows=pd.read_csv(root/source).query('scenario == "VO SGOV"').to_dict('records')
        cards.append(dict(id=id,title=title,status=study['status'],category=study['family'],summary=summary,
            mechanics=mechanics,cadence='신호·체결·비용의 세부 조건은 연결된 원문 기준',
            decision=study['finding'],limitation=study['lesson'],studies=[study_id],batch=study_id,
            metrics=rows[0] if len(rows)==1 else None,result_rows=rows,metric_source=source,
            href=f'research/{study_id}/',is_family=len(rows)>1))
    return cards
