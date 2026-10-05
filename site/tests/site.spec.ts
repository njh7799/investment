import {test,expect} from '@playwright/test';

test('analysis index restores search and filters without operational panels',async({page})=>{
  await page.goto('research/');
  await expect(page.locator('h1')).toHaveText('분석 기록');
  expect(await page.locator('.study-row').count()).toBeGreaterThan(0);
  await expect(page.locator('body')).not.toContainText('현재 규칙의 목표 비중');
  await expect(page.locator('[data-chart]')).toHaveCount(0);
  await page.locator('#research-search').fill('458');
  await expect(page.locator('.study-row:visible')).toHaveCount(1);
  await expect(page).toHaveURL(/q=458/);
  await page.reload();await expect(page.locator('#research-search')).toHaveValue('458');
  await page.locator('.study-row:visible .study-title').click();
  await expect(page.locator('h1').first()).toContainText('이동평균');
  await page.goBack();
  await expect(page.locator('#research-search')).toHaveValue('458');
  await page.locator('#research-search').fill('');
  await page.locator('#status-filter').selectOption('실행 실패');
  await expect(page.locator('.study-row:visible')).toHaveCount(1);
  await page.locator('.study-row:visible .study-title').click();
  await expect(page.getByText('백테스트 전 실행 실패',{exact:true})).toBeVisible();
  await expect(page.locator('[data-chart]')).toHaveCount(0);
});

test('backtest periods, drawdown and standalone HTML download',async({page},testInfo)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('backtests/');
  await expect(page).toHaveURL(/strategies\/volatility-allocation\/#performance$/);
  await expect(page.locator('h1')).toHaveText('VO · 변동성 배분');
  await expect(page.locator('body')).not.toContainText('다음 거래일 대응');
  await expect(page.locator('[data-chart]')).toHaveCount(3);
  await expect(page.locator('.chart-canvas')).toHaveCount(3);
  for(let i=0;i<3;i++){
    await page.locator('[data-chart]').nth(i).scrollIntoViewIfNeeded();
    await expect(page.locator('.chart-canvas').nth(i).locator('.main-svg').first()).toBeVisible({timeout:15000});
  }
  const chartSpec=await page.locator('.chart-canvas').first().evaluate((element:any)=>({
    names:element.data.map((trace:any)=>trace.name),
    compactValues:element.data[0].customdata.slice(0,20).map((point:any[])=>point[1]),
    hoverDate:element.layout.xaxis.hoverformat,
  }));
  expect(chartSpec.names).not.toContain('QQQ 단순 보유');
  expect(chartSpec.compactValues.some((value:string)=>/\$[\d.]+[KM]/.test(value))).toBeTruthy();
  expect(chartSpec.hoverDate).toBe('%Y-%m-%d');
  await page.locator('.chart-canvas').first().evaluate((element:any)=>(window as any).Plotly.Fx.hover(element,[{curveNumber:0,pointNumber:0}]));
  const hover=page.locator('.chart-canvas').first().locator('.hoverlayer');
  await expect(hover).toContainText(/\d{4}-\d{2}-\d{2}/);
  await expect(hover).toContainText(/\$[\d.]+[KM]/);
  const metadata=await (await page.request.get('data/backtest-metadata.json')).json();
  const recentPeriod=await (await page.request.get('data/backtest-recent-10y.json')).json();
  await expect(page.locator('.chart-panel h2').nth(0)).toContainText(recentPeriod.curves[0].metrics.start);
  await expect(page.locator('.chart-metrics').nth(0)).toContainText(metadata.market_date);
  await expect(page.locator('.chart-metrics').nth(2)).toContainText('1999-03-10');
  for(const id of ['recent-10y','prior-10y','early-10y']){
    const period=await (await page.request.get(`data/backtest-${id}.json`)).json();
    expect(period.curves.every((curve:any)=>curve.metrics.start_equity===100000)).toBeTruthy();
  }
  await page.locator('.metric-picker').nth(2).selectOption('drawdown');
  await expect(page.locator('.chart-canvas').nth(2)).toContainText('고점 대비 낙폭');
  const download=page.waitForEvent('download');await page.locator('.download-chart').nth(2).click();
  const saved=await download;expect(saved.suggestedFilename()).toBe('investment-chart.html');
  const target=testInfo.outputPath('standalone.html');await saved.saveAs(target);
  const standalone=await page.context().newPage();await standalone.goto('file://'+target);
  await expect(standalone.locator('.main-svg').first()).toBeVisible();await standalone.close();
  expect(errors).toEqual([]);
});

test('result period filter, key columns, sorting and pagination',async({page})=>{
  await page.goto('research/batch-05/');await page.reload();
  await expect(page.locator('.table-period')).toHaveValue('full_current');
  await expect(page.locator('.data-table tbody tr').first()).toContainText('연구 기준일까지 전체');
  await expect(page.locator('.data-table tbody tr')).toHaveCount(25);
  await expect(page.locator('.data-table thead')).not.toContainText('수수료');
  await page.locator('.next').click();await expect(page.locator('.table-count')).toContainText('2 /');
  await page.locator('.table-period').selectOption('full_pre2026');
  await expect(page.locator('.table-count')).toContainText('1 /');
  await expect(page.locator('.data-table tbody tr').first()).toContainText('2025년까지 전체');
  await page.locator('.column-mode').selectOption('all');
  await expect(page.locator('.data-table thead')).toContainText('수수료');
  await page.locator('.table-sort').selectOption('cagr');
  await page.locator('.sort-order').click();
  const returns=await page.locator('.data-table tbody tr').evaluateAll(rows=>{const headers=[...rows[0].closest('table')!.querySelectorAll('thead th')];const column=headers.findIndex(h=>h.getAttribute('title')==='cagr');return rows.map(row=>Number(row.children[column].textContent?.replace('%','')))});
  expect(returns[0]).toBeGreaterThanOrEqual(returns[1]);
  await page.locator('.table-search').fill('no-such-model');
  await expect(page.locator('.table-count')).toContainText('0행');
  await page.locator('.table-search').fill('vo');
  await expect(page.locator('.data-table tbody tr').first()).toBeVisible();
});

test('mobile layout, audit search and legacy route',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('./');
  await page.locator('.sidebar-trigger').click();
  await expect(page.locator('.sidebar-trigger')).toHaveAttribute('aria-expanded','true');
  await expect(page.locator('.site-sidebar')).toBeInViewport();
  await page.locator('.sidebar-overlay').click({position:{x:380,y:400}});
  await expect(page.locator('.sidebar-trigger')).toHaveAttribute('aria-expanded','false');
  for(const route of ['./','backtests/','research/','research/audits/','strategies/ixic-three-percent-rule/','strategies/value-rebalancing/','strategies/permanent-portfolio/','guide/']){
    await page.goto(route);await expect(page.locator('h1').first()).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  }
  await page.goto('research/audits/');await page.locator('#audit-search').fill('no-such-audit');
  await expect(page.locator('#audit-empty')).toBeVisible();
  await page.goto('research/batch-10/');await page.locator('.chart-canvas').scrollIntoViewIfNeeded();
  await expect(page.locator('.chart-canvas .main-svg').first()).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await page.goto('operation/');await expect(page).toHaveURL(/strategies\/volatility-allocation\/#performance$/);
});


test('methods connect rules, stored historical specs and research in both directions',async({page})=>{
  await page.goto('./');
  await expect(page.locator('h1')).toContainText('수익률보다 과정까지 보는');
  await expect(page.locator('nav[aria-label="주요 메뉴"] .sidebar-primary')).toHaveCount(3);
  await page.goto('strategies/');
  const methodCount=await page.locator('.method-card').count();
  expect(methodCount).toBeGreaterThan(0);
  await expect(page.locator('.sidebar-subnav[aria-label="투자 방법 목록"] a')).toHaveCount(methodCount);
  await expect(page.locator('.sidebar-subnav[aria-label="투자 방법 목록"] a').nth(1)).toContainText('TQQQ Buy & Hold');
  await expect(page.locator('.methods-list>section').nth(1)).toHaveAttribute('id','tqqq-buy-hold');
  await expect(page.locator('main')).not.toContainText(/\d+차 배치/);
  const boxes=await page.locator('.methods-list>section').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,bottom:r.bottom}}));
  for(let i=1;i<boxes.length;i++){expect(boxes[i].x).toBe(boxes[0].x);expect(boxes[i].width).toBe(boxes[0].width);expect(boxes[i].y).toBeGreaterThanOrEqual(boxes[i-1].bottom)}
  await expect(page.locator('[data-method="erc"]')).toHaveCount(0);
  await expect(page.locator('[data-method="vo-rebound-entry"]')).toHaveCount(0);
  await expect(page.locator('[data-method="vo-consecutive-up"]')).toHaveCount(0);
  await expect(page.locator('[data-method="vo-v-recovery-controls"]')).toHaveCount(0);
  const vo=page.locator('[data-method="volatility-allocation"]');
  const voSource=await (await page.request.get('data/method-volatility-allocation.json')).json();
  const voMetrics=voSource.curves.find((curve:any)=>curve.model==='vo').metrics;
  await expect(vo).toContainText(`${(voMetrics.cagr*100).toFixed(2)}%`);
  await expect(vo).toContainText(`${Number(voMetrics.annual_trades).toFixed(1)}회`);
  await expect(vo).not.toContainText(`${voMetrics.start} — ${voMetrics.end}`);
  await expect(page.locator('.method-list-conditions')).toContainText('전략별 실제 평가 기간');
  await expect(vo).toContainText('최장 고점 미회복 기간');
  await expect(vo).toContainText('연평균 거래');
  await expect(vo.locator('.method-card-link')).toHaveAttribute('href','/investment/strategies/volatility-allocation/');
  const buyHold=page.locator('[data-method="tqqq-buy-hold"]');
  const buyHoldMetrics=voSource.curves.find((curve:any)=>curve.model==='tqqq_hold').metrics;
  await expect(buyHold).toContainText(`${(buyHoldMetrics.cagr*100).toFixed(2)}%`);
  await expect(buyHold).toContainText(`${(buyHoldMetrics.mdd*100).toFixed(2)}%`);
  await expect(buyHold).toContainText(`${buyHoldMetrics.longest_time_underwater_days}일`);
  await expect(buyHold).toContainText(`${Number(buyHoldMetrics.annual_trades).toFixed(1)}회`);
  await expect(page.locator('details.method-details')).toHaveCount(0);
  expect((await vo.boundingBox())!.height).toBeLessThan(230);
  await page.setViewportSize({width:390,height:844});
  await expect(vo.locator('.method-metrics')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await vo.locator('.method-card-link').click();
  await expect(page.locator('.sidebar-parent[data-section-active]')).toContainText('투자 방법');
  await expect(page.locator('.sidebar-subnav a[aria-current]')).toContainText('VO · 변동성 배분');
  await page.goto('strategies/');
  await page.locator('[data-method="tqqq-buy-hold"] .method-card-link').click();
  await expect(page.locator('h1')).toHaveText('TQQQ Buy & Hold');
  await expect(page).toHaveURL(/strategies\/tqqq-buy-hold\/$/);
  await expect(page.locator('.sidebar-parent[data-section-active]')).toContainText('투자 방법');
  await expect(page.locator('.sidebar-subnav a[aria-current]')).toContainText('TQQQ Buy & Hold');
  await page.goto('strategies/volatility-allocation/#기본값-선택-근거');
  await expect(page.locator('.full-rules')).toHaveAttribute('open','');
  await expect(page.locator('.full-rules')).toContainText('기본값 선택 근거');
  await page.locator('.evidence-list a').filter({hasText:'이동평균'}).click();
  await expect(page.locator('.sidebar-parent[data-section-active]')).toContainText('분석 기록');
  await expect(page.locator('.sidebar-subnav a[aria-current]')).toContainText('이동평균과 VO 결합');
  await expect.poll(()=>page.evaluate(()=>window.scrollY)).toBe(0);
  await page.getByRole('link',{name:'VO · 변동성 배분 →',exact:true}).click();
  await expect(page).toHaveURL(/strategies\/volatility-allocation\/$/);
  await page.goto('strategies/permanent-portfolio/');
  await page.locator('.chart-canvas').first().scrollIntoViewIfNeeded();
  await expect(page.locator('.chart-canvas .main-svg').first()).toBeVisible();
  const permanentSource=await (await page.request.get('data/method-permanent-portfolio.json')).json();
  const permanentMetrics=permanentSource.curves.find((curve:any)=>curve.model==='permanent_band').metrics;
  await expect(page.locator('.chart-metrics').first()).toContainText(permanentMetrics.end);
  const download=page.waitForEvent('download');
  await page.getByText('성과 원본 CSV ↓',{exact:true}).click();
  expect((await download).suggestedFilename()).toBe('period-summary.csv');
});

test('method cards, sidebar items and detail pages are a strict one-to-one mapping',async({page})=>{
  test.setTimeout(120000);
  await page.goto('strategies/');
  const cards=await page.locator('[data-method-entry]').evaluateAll(entries=>entries.map(entry=>{
    const link=entry.querySelector<HTMLAnchorElement>('.method-card-link')!;
    return {id:entry.id,title:entry.querySelector('h2')!.textContent!.trim(),href:link.getAttribute('href')!};
  }));
  const sidebar=await page.locator('.sidebar-subnav[aria-label="투자 방법 목록"] a').evaluateAll(links=>links.map(link=>({
    id:link.getAttribute('data-method-id')!,title:link.textContent!.trim(),href:link.getAttribute('href')!,
  })));
  expect(sidebar).toEqual(cards);
  expect(cards.map(item=>item.id)).toEqual([
    'volatility-allocation',
    'tqqq-buy-hold',
    'ixic-three-percent-rule',
    'value-rebalancing',
    'permanent-portfolio',
  ]);
  expect(new Set(cards.map(item=>item.href)).size).toBe(cards.length);
  for(const method of cards){
    expect(method.href).toBe(`/investment/strategies/${method.id}/`);
    await page.goto(method.href,{waitUntil:'domcontentloaded'});
    await expect(page.locator('h1').first()).toHaveText(method.title);
    const active=page.locator('.sidebar-subnav[aria-label="투자 방법 목록"] a[aria-current="page"]');
    await expect(active).toHaveAttribute('data-method-id',method.id);
    await expect(active).toHaveText(method.title);
    expect(await page.evaluate(()=>window.scrollY)).toBe(0);
  }
});

test('open sidebar groups collapse and reopen without changing the content page',async({page})=>{
  await page.goto('strategies/permanent-portfolio/');
  const methodParent=page.locator('[data-sidebar-parent="strategies"]');
  const methodNav=page.locator('[data-sidebar-subnav="strategies"]');
  const methodUrl=page.url();
  await expect(methodParent).toHaveAttribute('aria-expanded','true');
  await expect(methodNav).toHaveAttribute('data-open','true');
  const transition=await methodNav.evaluate(element=>getComputedStyle(element).transitionProperty);
  expect(transition).toContain('grid-template-rows');
  expect(transition).toContain('opacity');
  await methodParent.click();
  await expect(page).toHaveURL(methodUrl);
  await expect(methodParent).toHaveAttribute('aria-expanded','false');
  await expect(methodNav).toHaveAttribute('data-open','false');
  await expect(methodNav).toHaveAttribute('aria-hidden','true');
  await expect(methodNav).toHaveAttribute('inert','');
  await methodParent.click();
  await expect(page).toHaveURL(methodUrl);
  await expect(methodParent).toHaveAttribute('aria-expanded','true');
  await expect(methodNav).toHaveAttribute('data-open','true');
  await expect(methodNav).not.toHaveAttribute('inert','');

  await page.goto('research/batch-01/');
  const researchParent=page.locator('[data-sidebar-parent="research"]');
  const researchNav=page.locator('[data-sidebar-subnav="research"]');
  const researchPath=await page.evaluate(()=>location.pathname);
  const researchHeading=await page.locator('h1').first().textContent();
  await researchParent.click();
  expect(await page.evaluate(()=>location.pathname)).toBe(researchPath);
  await expect(page.locator('h1').first()).toHaveText(researchHeading!);
  await expect(researchParent).toHaveAttribute('aria-expanded','false');
  await expect(researchNav).toHaveAttribute('data-open','false');
});


test('compact cards show recent metrics and open the matching detail page',async({page})=>{
  await page.goto('strategies/');
  const card=page.locator('[data-method="volatility-allocation"]');
  await expect(card.locator('.method-preview')).toHaveCount(0);
  await expect(card.locator('.metric-conditions')).toHaveCount(0);
  await expect(page.locator('.method-list-conditions')).toHaveCount(1);
  const voPreview=await (await page.request.get('data/preview-volatility-allocation-recent-10y.json')).json();
  expect(voPreview.curves.map((curve:any)=>[curve.preview_role,curve.display_color])).toEqual([
    ['benchmark','#2979FF'],['target','#E5484D']
  ]);
  const metadata=await (await page.request.get('data/backtest-metadata.json')).json();
  expect(voPreview.curves[0].dates.at(-1)).toBe(metadata.market_date);
  const batch=await (await page.request.get('data/batch-01-tables.json')).json();
  const recent=batch.find((table:any)=>table.name==='period-summary').rows.find((row:any)=>row.period==='recent_10y'&&row.model==='vo');
  await expect(card).toContainText(`(${(recent.cagr*100).toFixed(2)}%)`);
  await expect(page.locator('.method-list-conditions')).toContainText('전체 평가 기간 (최근 10년 이내)');
  await expect(page.locator('.method-list-conditions')).toContainText('매수·매도 각각 0.1%');
  await card.locator('.method-card-link').click();
  await expect(page.locator('.detail-context')).toContainText('투자 방법');
  await expect(page.locator('.detail-kind')).toHaveText('방법 상세');
  await expect(page.locator('[data-stress-chart]')).toHaveCount(1);
  await expect(page.locator('.stress-summary')).toContainText('10% 이상 하락');
  await expect(page.locator('.stress-summary')).toContainText('30일 이상 고점 미회복');
  await expect.poll(()=>page.locator('.stress-chart-dot').count()).toBeGreaterThan(10);
  await expect(page.locator('[data-stress-chart]')).toContainText('긴 기간은 간격만 압축');
  await expect(page.locator('[data-chart]')).toHaveCount(3);
  await page.locator('.chart-metrics').nth(0).scrollIntoViewIfNeeded();
  await expect(page.locator('.chart-metrics').nth(0)).toContainText(metadata.market_date);
  await page.locator('.detail-back').click();
  await expect(page).toHaveURL(/investment\/strategies\/$/);
  await expect(page.locator('.detail-context')).toHaveCount(0);
  await page.goto('research/batch-05/');
  await expect(page.locator('.detail-back')).toHaveText('← 분석 기록 목록');
  await expect(page.locator('h1').first()).toContainText('이동평균과 VO 결합');
  await expect(page.locator('#results')).toBeVisible();
  const otherPreview=await (await page.request.get('data/preview-permanent-portfolio-recent-10y.json')).json();
  expect(otherPreview.curves.map((curve:any)=>[curve.preview_role,curve.display_color])).toEqual([
    ['benchmark','#2979FF'],['default','#E5484D'],['target','#D99A00']
  ]);
  await page.goto('charts/volatility-allocation/');
  await expect(page.locator('.chart-panel h2').first()).toContainText(metadata.market_date);
  await expect(page.locator('.chart-panel h2').last()).toContainText('1999-03-10');
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.detail-context')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await page.goto('./');
  await expect(page.locator('#method-search')).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
});

test('card conditions and exact source survive navigation',async({page})=>{
 await page.goto('strategies/');
 const vo=page.locator('[data-method="volatility-allocation"]');
 const source=await (await page.request.get('data/method-volatility-allocation.json')).json();
 const metrics=source.curves.find((curve:any)=>curve.model==='vo').metrics;
 const batch=await (await page.request.get('data/batch-01-tables.json')).json();
 const recent=batch.find((table:any)=>table.name==='period-summary').rows.find((row:any)=>row.period==='recent_10y'&&row.model==='vo');
 await expect(vo.locator('.metric-conditions')).toHaveCount(0);
 await expect(page.locator('.method-list-conditions')).toContainText('예외 비용 조건은 상세 페이지');
 await vo.locator('.method-card-link').click();
 await expect(page.locator('.historical-spec .metric-conditions')).toContainText(`${metrics.start} — ${metrics.end}`);
 await expect(page.locator('.historical-spec .metric-conditions')).toContainText('괄호 안은 최근 10년 이내 데이터 기준');
 await expect(page.locator('.historical-spec .method-metrics')).toContainText(`(${(recent.cagr*100).toFixed(2)}%)`);
 await expect(page.locator('.historical-spec .method-metrics')).toContainText(`(${(recent.mdd*100).toFixed(2)}%)`);
 await expect(page.locator('.historical-spec .method-metrics')).toContainText(`(${recent.longest_time_underwater_days}일)`);
 await expect(page.locator('.historical-spec .method-metrics')).toContainText(`(${Number(recent.annual_trades).toFixed(1)}회)`);
 await expect(page.locator('.historical-spec .metric-conditions')).toContainText('각각 0.1%');
 await page.getByRole('link',{name:'성과 원본 CSV ↓',exact:true}).waitFor();
 await page.goto('research/batch-01/?table=period-summary&period=full_synthetic&model=vo#results');
 await expect(page.locator('.table-period')).toHaveValue('full_synthetic');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await expect(page.locator('.data-table')).toContainText(`${(metrics.cagr*100).toFixed(2)}%`);
 await page.reload();await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await page.locator('.table-search').fill('골든');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await expect(page.locator('.data-table')).toContainText('골든크로스');
 await page.locator('.table-search').fill('golden');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await page.locator('.table-search').fill('');
 await page.locator('.table-period').selectOption('recent_10y');
 await page.locator('.chart-canvas').scrollIntoViewIfNeeded();
 await expect(page.locator('.chart-period-warning')).toBeVisible();
 await expect(page.locator('.chart-period-warning')).toContainText('기간이 다릅니다');
 await expect(page.locator('.chart-range')).toContainText('1999-03-10');
 await page.locator('.table-period').selectOption('full_synthetic');
 await expect(page.locator('.chart-period-warning')).toBeHidden();
});

test('home has no search, filter, or collapse controls',async({page})=>{
 await page.goto('./');
 await expect(page.locator('[data-method-entry]')).toHaveCount(0);
 await expect(page.locator('#method-search')).toHaveCount(0);
 await expect(page.locator('.method-filters')).toHaveCount(0);
 await expect(page.locator('#asset-filter')).toHaveCount(0);
 await expect(page.locator('#method-family')).toHaveCount(0);
 await expect(page.locator('#method-status')).toHaveCount(0);
 await expect(page.locator('#method-verdict')).toHaveCount(0);
 await expect(page.locator('#collapse-methods')).toHaveCount(0);
 await expect(page.locator('#method-reset')).toHaveCount(0);
 await page.goto('strategies/');
 expect(await page.locator('[data-method-entry]').count()).toBeGreaterThan(0);
 await expect(page.locator('#method-search')).toHaveCount(0);
});

test('home combines the reading guide and criteria while legacy comparison redirects',async({page})=>{
 await page.setViewportSize({width:1440,height:900});
 await page.goto('./');
 await expect(page.locator('#start')).toContainText('이 사이트 읽는 순서');
 await expect(page.locator('#start')).not.toContainText('하루 수익률 3배');
 await expect(page.locator('#start')).not.toContainText('94.54');
 await expect(page.locator('#criteria')).toContainText('평가 기준 이해하기');
 await expect(page.locator('#criteria .criteria-card')).toHaveCount(4);
 await expect(page.locator('#criteria')).toContainText('연평균 복리수익률');
 await expect(page.locator('#criteria')).toContainText('최대 낙폭');
 await expect(page.locator('#criteria')).toContainText('고점 미회복 기간');
 await expect(page.locator('body')).not.toContainText('같은 조건으로 비교하기');
 await expect(page.locator('[data-page-index]')).toBeVisible();
 await expect(page.locator('[data-page-index-links] a')).toHaveCount(3);
 await expect(page.locator('[data-page-index-links]')).toContainText('평가 기준 이해하기');
 await page.goto('compare/?study=vo-sgov');
 await expect(page).toHaveURL(/investment\/strategies\/$/);
 await expect(page.locator('.methods-list')).toBeVisible();
});

test('stress distribution, mobile summaries and freshness explain their scope',async({page})=>{
 await page.goto('strategies/volatility-allocation/#performance');
 await expect(page.locator('[data-freshness]')).toContainText('다음 기대 거래일:');
 await expect(page.locator('[data-freshness]')).toContainText('KST');
 const stress=page.locator('.stress-section');
 await expect(stress).toContainText(/10% 이상 하락/);
 await expect(stress).toContainText(/30일 이상 고점 미회복/);
 await expect(stress.locator('[data-stress-chart]')).toHaveCount(1);
 const point=stress.locator('.stress-chart-dot').first();
 await point.hover();
 await expect(stress.locator('.chart-tooltip-content')).toContainText(/\d{4}-\d{2}-\d{2}/);
 const tooltip=stress.locator('.recharts-tooltip-wrapper');
 await expect(tooltip).toHaveCSS('transition-duration','0s');
 await expect(tooltip).toHaveCSS('pointer-events','none');
 await expect(point).toHaveCSS('cursor','pointer');
 const covid=stress.locator('.stress-chart-dot[aria-label*="2020-02-19"]');
 await covid.click();
 await expect(stress.locator('.stress-detail-panel')).toContainText('2020-02-19');
 await expect(stress.locator('.stress-detail-panel')).toContainText('코로나19 충격');
 await expect(stress.locator('.stress-detail-panel')).toContainText('이 기간의 주요 시장 악재');
 const chart=page.locator('[data-chart]').first();await chart.scrollIntoViewIfNeeded();
 await expect(chart.locator('.chart-canvas .main-svg').first()).toBeVisible({timeout:15000});
 await expect(chart.locator('.chart-canvas')).not.toContainText('합성 구간');
 await page.setViewportSize({width:390,height:844});
 await expect(chart.locator('.chart-metrics td[data-label="최대 낙폭"]').first()).toBeVisible();
 expect(await chart.locator('.chart-metrics').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await page.goto('guide/start/');await expect(page).toHaveURL(/investment\/#start$/);
 await expect(page.locator('main')).toContainText('이 사이트 읽는 순서');
 await expect(page.locator('main')).not.toContainText('하루 수익률 3배');
});

test('every analysis shows annual returns and MDD or an explicit source limitation',async({page})=>{
 await page.goto('research/batch-01/');
 await expect(page.locator('#yearly h2')).toHaveText('연도별 수익률과 MDD');
 await expect(page.locator('.yearly-model')).toHaveValue('vo');
 await expect(page.locator('.yearly-row')).toHaveCount(10);
 await expect(page.locator('.yearly-row>strong').first()).toContainText('2026');
 await expect(page.locator('.yearly-row>strong').nth(1)).toHaveText('2025');
 await expect(page.locator('.yearly-start')).toHaveCount(0);
 await expect(page.locator('.yearly-table')).toHaveCount(0);
 const directions=await page.locator('#yearly').evaluate(root=>{
  const position=(selector:string)=>{const bar=root.querySelector(selector)!.getBoundingClientRect(),track=root.querySelector(selector)!.parentElement!.getBoundingClientRect();return {left:bar.left, right:bar.right, center:track.left+track.width/2}};
  return {positive:position('.yearly-measure:first-of-type i.positive'),negative:position('.yearly-measure:first-of-type i.negative'),mdd:position('.yearly-measure:nth-of-type(2) i.drawdown')};
 });
 expect(Math.abs(directions.positive.left-directions.positive.center)).toBeLessThanOrEqual(1);
 expect(Math.abs(directions.negative.right-directions.negative.center)).toBeLessThanOrEqual(1);
 expect(Math.abs(directions.mdd.right-directions.mdd.center)).toBeLessThanOrEqual(1);
 await page.locator('.yearly-range-toggle').click();
 await expect(page.locator('.yearly-row')).toHaveCount(28);
 await expect(page.locator('.yearly-range-toggle')).toContainText('최근 10년만 보기');
 await page.locator('.yearly-model').selectOption('tqqq_hold');
 await expect(page.locator('.yearly-row')).toHaveCount(10);
 await expect(page.locator('.yearly-range-toggle')).toContainText('전체 보기');
 await page.setViewportSize({width:390,height:844});
 expect(await page.locator('#yearly').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await page.goto('research/batch-09/');
 await expect(page.locator('#yearly')).toContainText('일별 포트폴리오 자산 곡선이 저장되어 있지 않아');
 await expect(page.locator('.yearly-row')).toHaveCount(0);
});

test('every strategy detail shows recent annual returns and can expand the full history',async({page})=>{
 const strategies=[
  ['volatility-allocation','vo',28],
  ['ixic-three-percent-rule','three_percent',28],
  ['value-rebalancing','vr5',28],
  ['permanent-portfolio','permanent_band',23],
 ] as const;
 for(const [id,model,years] of strategies){
  await page.goto(`strategies/${id}/#yearly`);
  const yearly=page.locator('#yearly');
  await expect(yearly.locator('h2')).toHaveText('연도별 수익률과 MDD');
  await expect(yearly.locator('.yearly-row')).toHaveCount(10);
  await expect(yearly.locator('.yearly-row>strong').first()).toContainText('2026');
  await expect(yearly.locator('.yearly-row>strong').nth(1)).toHaveText('2025');
  await expect(yearly.locator('.yearly-model')).toHaveCount(1);
  await expect(yearly.locator('.yearly-model').locator('option')).toHaveCount(1);
  await expect(yearly.locator('.yearly-start')).toHaveCount(0);
  await expect(yearly.locator('.yearly-table')).toHaveCount(0);
  await yearly.locator('.yearly-range-toggle').click();
  await expect(yearly.locator('.yearly-row')).toHaveCount(years);
  await expect(yearly.locator('.yearly-range-toggle')).toHaveAttribute('aria-expanded','true');
  const source=await (await page.request.get(`data/method-${id}.json`)).json();
  const metrics=source.curves.find((curve:any)=>curve.model===model).metrics;
  const stress=page.locator('.stress-section');
  await expect(stress.locator('h2')).toHaveText('하락 스트레스 분포');
  await expect(stress.locator('.stress-summary')).toContainText(`${(metrics.mdd*100).toFixed(2)}%`);
  await expect(stress.locator('[data-stress-chart]')).toHaveCount(1);
  const current=stress.locator('[data-episode-id="current"]');
  await expect(current).toHaveCount(1);
  await expect(stress.locator('[data-episode-id^="current-"]')).toHaveCount(0);
  const currentSummary=await stress.locator('.stress-current').textContent();
  const currentDrawdown=currentSummary?.match(/기준일 낙폭 (-?\d+\.\d+%)/)?.[1];
  expect(currentDrawdown).toBeTruthy();
  await expect(current).toHaveAttribute('aria-label',new RegExp(`현재 낙폭 ${currentDrawdown}`));
  await expect(stress.locator('.stress-chart-foot')).toContainText('현재 상태');
 }
});
