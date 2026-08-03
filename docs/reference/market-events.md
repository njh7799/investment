# SPY 기준 주요 시장 하락 사건

차트의 시장 사건은 S&P 500 ETF인 SPY의 조정 종가로 기계적으로 선정한다. SPY는 S&P 500 지수의 프록시이며 배당과 운용비용이 반영되므로 지수 자체와 값이 완전히 같지는 않다.

고점 대비 10~20% 하락을 조정으로 부르는 [시장 관행](https://www.nasdaq.com/articles/what-is-a-market-correction)과 20% 이상을 약세장으로 부르는 [Investor.gov 정의](https://www.investor.gov/introduction-investing/investing-basics/glossary/bear-market)를 분류 기준으로 사용한다. 국면의 시작과 종료에는 보편적으로 강제되는 공식 규칙이 없으므로, 겹치지 않는 결과를 만들기 위해 아래의 저장소 규칙을 적용한다.

## 선정 규칙

- 상승 국면에서는 SPY 조정 종가의 최고값과 발생일을 계속 갱신한다.
- 종가가 국면 고점보다 정확히 10% 이상 하락하면 `조정(correction)`이 시작된다.
- 같은 하락 국면의 낙폭이 정확히 20% 이상이면 `약세장(bear market)`으로 변경한다.
- 조정은 종가가 직전 국면 고점을 완전히 회복하면 종료한다.
- 약세장은 종가가 해당 국면 저점보다 정확히 20% 이상 반등하면 종료하고, 종료일 종가부터 새 상승 국면의 고점을 추적한다.
- 대표일은 국면 고점부터 저점까지 SPY의 전일 종가 대비 수익률이 가장 낮은 거래일이다. 동률이면 먼저 발생한 날을 사용한다.
- 아직 종료되지 않은 국면도 저점과 대표일을 잠정값으로 기록하고 `미종료`로 표시한다.

이 규칙은 과거 차트 주석을 재현하기 위한 사후 분류이며 매매 신호가 아니다. `python scripts/list_market_events.py`로 정량 항목을 다시 계산할 수 있다. 사건명과 배경만 당시 보도 및 공식 자료로 수동 검증한다.

## 공식 서킷브레이커와의 구분

미국의 시장 전체 서킷브레이커는 S&P 500 **지수의 장중 가격**이 전일 종가보다 7%·13%·20% 하락할 때 발동한다. SPY 일봉의 종가나 저가만으로 실제 발동 여부를 판정하지 않으며, 공식 발동 사건을 언급할 때는 [NYSE 공식 자료](https://beta.nyse.com/publicdocs/nyse/NYSE_MWCB_FAQ.pdf)를 별도로 확인한다.

## 사건 목록

정량 값은 `assets/SPY.csv`의 1999년 3월 10일 이후 데이터로 계산했다. `대표일 등락률`과 `최대 낙폭`은 원본 정밀도로 계산하고 아래에는 소수점 둘째 자리까지 표시한다.

| 대표일 | 대표일 등락률 | 고점일 | 저점일 | 최대 낙폭 | 분류 | 사건명 | 주요 배경 | 근거 |
| --- | ---: | --- | --- | ---: | --- | --- | --- | --- |
| 1999.10.13 | -2.59% | 1999.07.16 | 1999.10.15 | -11.70% | 조정 | 금리·인플레이션 우려 | 인플레이션과 추가 금리 인상 우려가 금리 민감주와 기술주 매도를 키웠다. | [CNN](https://money.cnn.com/1999/10/15/markets/marketwrap/) |
| 2000.04.14 | -5.72% | 2000.03.24 | 2001.09.21 | -35.55% | 약세장 | 닷컴 버블 붕괴 | 고평가 기술주의 재평가로 시작된 하락이 경기 둔화와 9·11 충격으로 이어졌다. | [Cleveland Fed](https://www.clevelandfed.org/-/media/project/clevelandfedtenant/clevelandfedsite/publications/economic-commentary/2001/ec-20010115-a-retrospective-on-the-stock-market-in-2000-pdf.pdf) |
| 2002.07.10 | -3.64% | 2002.03.19 | 2002.07.23 | -31.69% | 약세장 | 회계 불신·경기 우려 | 기업 회계 스캔들과 이익 전망 악화가 닷컴 붕괴 이후의 신뢰 회복을 다시 훼손했다. | [Federal Reserve](https://www.federalreserve.gov/boarddocs/speeches/2002/20021015/default.htm) |
| 2002.09.03 | -3.81% | 2002.08.22 | 2002.10.09 | -18.86% | 조정 | 세계 경기회복 우려 | 미국과 해외 증시가 함께 하락하며 경기 및 기업이익 회복에 대한 불안이 확대됐다. | [Washington Post](https://www.washingtonpost.com/archive/business/2002/09/04/stocks-slump-across-the-board/7b725b6d-8d46-410a-a63f-9db3c472d263/) |
| 2008.10.15 | -9.84% | 2007.10.09 | 2008.11.20 | -50.76% | 약세장 | 글로벌 금융위기 | 주택·신용시장의 부실이 금융기관과 실물경제로 확산하면서 광범위한 자산 매도가 발생했다. | [Federal Reserve History](https://www.federalreservehistory.org/essays/great-recession-of-200709) |
| 2009.01.20 | -5.28% | 2009.01.06 | 2009.03.09 | -27.13% | 약세장 | 은행 자본 우려 | 부실자산 손실과 추가 자본조달 우려로 대형 은행주가 급락하며 금융위기 매도가 재개됐다. | [Reuters](https://www.marketscreener.com/news/latest/BofA-and-Citi-shares-sink-as-investors-fear-more-losses-13110499/) |
| 2010.05.20 | -3.78% | 2010.04.23 | 2010.07.02 | -15.70% | 조정 | 유럽 재정위기 | 그리스에서 시작된 유럽 재정위기의 전염과 세계 경기의 재침체 가능성이 부각됐다. | [WBUR/AP](https://www.wbur.org/news/2010/05/20/stock-market) |
| 2011.08.08 | -6.51% | 2011.04.29 | 2011.10.03 | -18.61% | 조정 | 미국 신용등급 강등 | 미국 국가신용등급 강등과 유럽 부채위기, 경기침체 우려가 동시에 위험회피를 촉발했다. | [Reuters](https://m.investing.com/news/stock-market-news/us-stocks-wall-st-plummets-as-fear-jumps-on-historic-downgrade-221364?ampMode=1) |
| 2015.08.24 | -4.21% | 2015.07.20 | 2016.02.11 | -13.02% | 조정 | 중국 경기둔화 충격 | 중국 증시 급락과 위안화 절하가 세계 성장 및 원자재 수요 우려를 확대했다. | [Reuters](https://www.business-standard.com/amp/article/reuters/china-stock-plunge-hits-world-stocks-dollar-u-s-stabilizes-115082401440_1.html) |
| 2018.02.05 | -4.18% | 2018.01.26 | 2018.02.08 | -10.10% | 조정 | 금리·변동성 충격 | 인플레이션과 금리 상승 우려 속에서 변동성 연계 포지션의 청산이 시장 움직임을 증폭했다. | [BIS](https://www.bis.org/publ/qtrpdf/r_qt1803.pdf?pdf=1) |
| 2018.12.04 | -3.24% | 2018.09.20 | 2018.12.24 | -19.35% | 조정 | 무역·긴축 우려 | 미·중 무역 갈등, 경기 둔화와 연준 긴축 경로에 대한 불확실성이 겹쳤다. | [Axios](https://www.axios.com/2018/12/07/stocks-lower-again) |
| 2020.03.16 | -10.94% | 2020.02.19 | 2020.03.23 | -33.72% | 약세장 | 코로나19 충격 | 팬데믹과 경제활동 중단 우려가 유동성 경색과 전 세계 위험자산 매도로 이어졌다. | [NYSE](https://www.nyse.com/article/assessing-nyse-model-performance) |
| 2022.09.13 | -4.35% | 2022.01.03 | 2022.10.12 | -24.50% | 약세장 | 인플레이션·긴축 충격 | 예상보다 높은 물가와 공격적인 연준 긴축 전망이 성장 및 밸류에이션 부담을 확대했다. | [Reuters](https://www.marketscreener.com/news/latest/Stocks-tumble-dollar-rallies-as-soaring-U-S-inflation-implies-an-aggressive-Fed-41765172/) |
| 2025.04.04 | -5.85% | 2025.02.19 | 2025.04.08 | -18.76% | 조정 | 상호관세 충격 | 광범위한 미국 관세 발표가 무역전쟁과 경기침체 우려를 촉발했다. | [Axios](https://www.axios.com/2025/04/07/black-monday-1987-trump-tariffs) |

## 갱신 절차

1. 시장 데이터 갱신 후 `python scripts/list_market_events.py`를 실행한다.
2. 출력과 표의 고점일, 저점일, 분류, 낙폭 및 대표일을 대조한다.
3. 새 국면이나 기존 미종료 국면의 변경이 있을 때만 표를 갱신한다.
4. 사건명은 짧게 작성하고 주요 배경은 해당 시점의 신뢰할 수 있는 보도나 공식 자료로 확인한다.
5. 여러 원인이 겹치면 단일 원인으로 단정하지 않는다.
