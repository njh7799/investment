import {test,expect} from '@playwright/test';

test('analysis index restores search and filters without operational panels',async({page})=>{
  await page.goto('research/');
  await expect(page.locator('h1')).toHaveText('분석 기록');
  await expect(page.locator('.study-row')).toHaveCount(15);
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
  const metadata=await (await page.request.get('data/backtest-metadata.json')).json();
  await expect(page.locator('.chart-metrics').nth(0)).toContainText('1999-03-10');
  await expect(page.locator('.chart-metrics').nth(2)).toContainText(metadata.market_date);
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
  await expect(page.locator('.data-table tbody tr').first()).toContainText('합성 포함 · 연구 기준일까지');
  await expect(page.locator('.data-table tbody tr')).toHaveCount(25);
  await expect(page.locator('.data-table thead')).not.toContainText('수수료');
  await page.locator('.next').click();await expect(page.locator('.table-count')).toContainText('2 /');
  await page.locator('.table-period').selectOption('actual_pre2026');
  await expect(page.locator('.table-count')).toContainText('1 /');
  await expect(page.locator('.data-table tbody tr').first()).toContainText('실제 TQQQ · 2025년까지');
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
  await expect(page.locator('h1')).toHaveText('투자 방법');
  await expect(page.locator('nav[aria-label="주요 메뉴"] a')).toHaveCount(3);
  await expect(page.locator('.method-card')).toHaveCount(30);
  await expect(page.locator('.methods-list>section').nth(1)).toHaveAttribute('id','tqqq-buy-hold');
  await expect(page.locator('main')).not.toContainText(/\d+차 배치/);
  const boxes=await page.locator('.methods-list>section').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,bottom:r.bottom}}));
  for(let i=1;i<boxes.length;i++){expect(boxes[i].x).toBe(boxes[0].x);expect(boxes[i].width).toBe(boxes[0].width);expect(boxes[i].y).toBeGreaterThanOrEqual(boxes[i-1].bottom)}
  const failed=page.locator('[data-method="erc"]');
  await failed.locator('.method-toggle').click();
  await expect(failed).toContainText('백테스트 성과를 생성하지 않았습니다');
  await expect(failed.locator('.method-metrics')).toHaveCount(0);
  await failed.locator('.method-toggle').click();
  const vo=page.locator('[data-method="volatility-allocation"]');
  const voSource=await (await page.request.get('data/method-volatility-allocation.json')).json();
  const voMetrics=voSource.curves.find((curve:any)=>curve.model==='vo').metrics;
  await expect(vo).toContainText(`${(voMetrics.cagr*100).toFixed(2)}%`);
  await expect(vo).toContainText(`${Number(voMetrics.annual_trades).toFixed(1)}회`);
  await expect(vo).toContainText(`${voMetrics.start} — ${voMetrics.end}`);
  await expect(vo).toContainText('최장 고점 미회복 기간');
  await expect(vo).toContainText('연평균 거래');
  await expect(vo.locator('.method-details')).toHaveAttribute('open','');
  const buyHold=page.locator('[data-method="tqqq-buy-hold"]');
  const buyHoldMetrics=voSource.curves.find((curve:any)=>curve.model==='tqqq_hold').metrics;
  await expect(buyHold.locator('.method-details')).not.toHaveAttribute('open','');
  await expect(buyHold).toContainText(`${(buyHoldMetrics.cagr*100).toFixed(2)}%`);
  await expect(buyHold).toContainText(`${(buyHoldMetrics.mdd*100).toFixed(2)}%`);
  await expect(buyHold).toContainText(`${buyHoldMetrics.longest_time_underwater_days}일`);
  await expect(buyHold).toContainText(`${Number(buyHoldMetrics.annual_trades).toFixed(1)}회`);
  const ixic=page.locator('[data-method="ixic-three-percent-rule"]');
  await expect(page.locator('.method-details[open]')).toHaveCount(1);
  await expect(ixic.locator('.method-rule')).not.toBeVisible();
  await expect(ixic.locator('.method-metrics')).toBeVisible();
  const collapsedMetrics=await ixic.locator('.method-metrics').boundingBox();
  await expect(ixic.locator('.method-actions')).not.toBeVisible();
  await ixic.locator('.method-details summary').click();
  await expect(ixic.locator('.method-rule')).toBeVisible();
  const expandedMetrics=await ixic.locator('.method-metrics').boundingBox();
  expect(expandedMetrics?.width).toBe(collapsedMetrics?.width);
  expect(expandedMetrics?.height).toBe(collapsedMetrics?.height);
  await expect(vo.locator('.method-rule')).toBeVisible();
  await ixic.locator('.method-details summary').press('Space');
  await expect(ixic.locator('.method-rule')).not.toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await vo.locator('.method-details summary').click();
  await expect(vo.locator('.method-rule')).not.toBeVisible();
  await expect(vo.locator('.method-metrics')).toBeVisible();
  await expect(vo.locator('.method-preview')).not.toBeVisible();
  await expect(vo.locator('.method-actions')).not.toBeVisible();
  await ixic.locator('.method-details summary').click();
  await expect(ixic.locator('.method-rule')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await vo.locator('.method-toggle').click();
  await vo.locator('.method-actions a').first().click();
  await expect(page.locator('nav[aria-label="주요 메뉴"] a[aria-current]')).toHaveText('투자 방법');
  await page.goto('strategies/volatility-allocation/#기본값-선택-근거');
  await expect(page.locator('.full-rules')).toHaveAttribute('open','');
  await expect(page.locator('.full-rules')).toContainText('기본값 선택 근거');
  await page.locator('.evidence-list a').filter({hasText:'이동평균'}).click();
  await expect(page.locator('nav[aria-label="주요 메뉴"] a[aria-current]')).toHaveText('분석 기록');
  await page.locator('.related-methods a').filter({hasText:'VO'}).click();
  await expect(page).toHaveURL(/strategies\/volatility-allocation\/#evidence$/);
  await page.goto('strategies/permanent-portfolio/');
  await page.locator('.chart-canvas').scrollIntoViewIfNeeded();
  await expect(page.locator('.chart-canvas .main-svg').first()).toBeVisible();
  const permanentSource=await (await page.request.get('data/method-permanent-portfolio.json')).json();
  const permanentMetrics=permanentSource.curves.find((curve:any)=>curve.model==='permanent_band').metrics;
  await expect(page.locator('.chart-metrics')).toContainText(permanentMetrics.end);
  const download=page.waitForEvent('download');
  await page.getByText('성과 원본 CSV ↓',{exact:true}).click();
  expect((await download).suggestedFilename()).toBe('period-summary.csv');
});


test('card image opens role-colored comparison periods and clear detail hierarchy',async({page})=>{
  await page.goto('./');
  const card=page.locator('[data-method="volatility-allocation"]');
  await expect(card.locator('.method-preview img')).toHaveCount(1);
  await expect(card.locator('.method-preview img').first()).toBeVisible();
  await expect(card.locator('.method-preview img').first()).toHaveJSProperty('naturalWidth',2880);
  await expect(card.locator('.method-preview img').first()).toHaveJSProperty('naturalHeight',1440);
  await expect(card.locator('.method-preview h3')).toHaveCount(0);
  const alt=await card.locator('.method-preview img').getAttribute('alt');
  expect(alt).toContain('1999-03-10 —');
  await expect(card.locator('.metric-period')).toHaveCount(1);
  const voPreview=await (await page.request.get('data/preview-volatility-allocation-recent-10y.json')).json();
  expect(voPreview.curves.map((curve:any)=>[curve.preview_role,curve.display_color])).toEqual([
    ['benchmark','#2979FF'],['target','#E5484D']
  ]);
  const metadata=await (await page.request.get('data/backtest-metadata.json')).json();
  expect(voPreview.curves[0].dates.at(-1)).toBe(metadata.market_date);
  await card.locator('.method-preview a').first().click();
  await expect(page.locator('.detail-context')).toContainText('투자 방법');
  await expect(page.locator('.detail-trail')).toContainText('VO · 변동성 배분');
  await expect(page.locator('.detail-kind')).toHaveText('차트 상세');
  await expect(page.locator('[data-chart]')).toHaveCount(3);
  await expect(page.locator('.chart-metrics').nth(0)).toContainText('1999-03-10');
  await page.locator('.chart-metrics').nth(2).scrollIntoViewIfNeeded();
  await expect(page.locator('.chart-metrics').nth(2)).toContainText(metadata.market_date);
  await page.locator('.detail-back').click();
  await expect(page).toHaveURL(/investment\/$/);
  await expect(page.locator('.detail-context')).toHaveCount(0);
  await page.goto('strategies/volatility-allocation/');
  await expect(page.locator('.detail-kind')).toHaveText('방법 상세');
  await page.goto('research/batch-05/');
  await expect(page.locator('.detail-back')).toHaveText('← 분석 기록 목록');
  const otherPreview=await (await page.request.get('data/preview-permanent-portfolio-common_full.json')).json();
  expect(otherPreview.curves.map((curve:any)=>[curve.preview_role,curve.display_color])).toEqual([
    ['benchmark','#2979FF'],['default','#E5484D'],['target','#D99A00']
  ]);
  const smaPreview=await (await page.request.get('data/preview-sma-200-recent-10y.json')).json();
  expect(smaPreview.curves[0].dates[0]).toBe(smaPreview.curves[0].metrics.start);
  expect(smaPreview.curves[0].dates.at(-1)).toBe(smaPreview.curves[0].metrics.end);
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.detail-context')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
  await page.goto('./');
  const mobileCard=page.locator('[data-method="volatility-allocation"]');
  const strip=mobileCard.locator('.period-strip-preview');
  expect(await strip.evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBeTruthy();
  await expect(mobileCard.locator('.preview-period-links a')).toHaveCount(3);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
});

test('card conditions and exact source survive navigation and Korean search',async({page})=>{
 await page.goto('./');
 const vo=page.locator('[data-method="volatility-allocation"]');
 const source=await (await page.request.get('data/method-volatility-allocation.json')).json();
 const metrics=source.curves.find((curve:any)=>curve.model==='vo').metrics;
 await expect(vo.locator('.metric-conditions')).toContainText(`${metrics.start} — ${metrics.end}`);
 await expect(vo.locator('.metric-conditions')).toContainText('각각 0.1%');
 await vo.getByRole('link',{name:'수치 원본',exact:true}).click();
 await expect(page.locator('.table-period')).toHaveValue('actual_tqqq');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await expect(page.locator('.data-table')).toContainText(`${(metrics.cagr*100).toFixed(2)}%`);
 await page.reload();await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await page.locator('.table-search').fill('골든');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await expect(page.locator('.data-table')).toContainText('골든크로스');
 await page.locator('.table-search').fill('golden');
 await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
 await page.locator('.table-search').fill('');
 await page.locator('.table-period').selectOption('full_synthetic');
 await page.locator('.chart-canvas').scrollIntoViewIfNeeded();
 await expect(page.locator('.chart-period-warning')).toBeVisible();
 await expect(page.locator('.chart-period-warning')).toContainText('기간이 다릅니다');
 await expect(page.locator('.chart-range')).toContainText('2010-02-11');
 await page.locator('.table-period').selectOption('actual_tqqq');
 await expect(page.locator('.chart-period-warning')).toBeHidden();
});

test('home filters persist, reset, and retain conditions on collapsed cards',async({page})=>{
 await page.goto('./');
 await page.locator('#method-search').fill('골든');
 await expect(page.locator('[data-method-entry]:visible')).toHaveCount(1);
 await page.reload();await expect(page.locator('#method-search')).toHaveValue('골든');
 await expect(page.locator('[data-method-entry]:visible .metric-conditions')).toContainText('실제 TQQQ');
 await page.locator('#method-reset').click();
 await page.locator('#asset-filter').selectOption('other');
 await expect(page.locator('[data-method-entry]:visible')).not.toHaveCount(0);
 await expect(page.locator('[data-method-entry]:visible')).not.toContainText(['VO · 변동성 배분']);
 await page.locator('#method-search').fill('없는방법');await expect(page.locator('#method-empty')).toBeVisible();
 await page.locator('#method-reset').click();await expect(page.locator('[data-method-entry]:visible')).toHaveCount(30);
 await page.locator('#collapse-methods').click();await expect(page.locator('.method-details[open]')).toHaveCount(0);
});

test('same-condition comparison uses SGOV baseline, deduplicates, and restores choices',async({page})=>{
 await page.goto('compare/?study=vo-sgov');
 await expect(page.locator('#compare-results article')).toHaveCount(2);
 const source=await (await page.request.get('data/vo-sgov-tables.json')).json();
 const rows=source.find((table:any)=>table.name==='summary').rows;
 const cash=rows.find((row:any)=>row.scenario==='VO cash');
 const sgov=rows.find((row:any)=>row.scenario==='VO SGOV');
 await expect(page.locator('#compare-conditions')).toContainText(`${cash.start} — ${cash.end}`);
 await expect(page.locator('#compare-results')).toContainText(`${(cash.cagr*100).toFixed(2)}%`);
 await expect(page.locator('#compare-results')).toContainText(`${(sgov.cagr*100).toFixed(2)}%`);
 const difference=(sgov.cagr-cash.cagr)*100;
 await expect(page.locator('#compare-results')).toContainText(`${difference>=0?'+':''}${difference.toFixed(2)}%p`);
 await expect(page.locator('#compare-conditions')).toContainText('$10 이하 주문 무료');
 await page.locator('.compare-model').nth(2).selectOption('VO SGOV');
 await expect(page.locator('#compare-results article')).toHaveCount(2);
 await page.reload();await expect(page.locator('#compare-results article')).toHaveCount(2);
 await page.locator('#compare-study').selectOption('batch-01');
 await expect(page.locator('#compare-conditions')).toContainText('합성 포함 전체');
 await expect(page.locator('#compare-results article')).toHaveCount(3);
 const batchSource=await (await page.request.get('data/batch-01-tables.json')).json();
 const batchRows=batchSource.find((table:any)=>table.name==='period-summary').rows;
 const syntheticVo=batchRows.find((row:any)=>row.period==='full_synthetic'&&row.model==='vo');
 await expect(page.locator('#compare-results')).toContainText(`${(syntheticVo.cagr*100).toFixed(2)}%`);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
});

test('synthetic shading, mobile summaries and freshness explain their scope',async({page})=>{
 await page.goto('strategies/volatility-allocation/#performance');
 await expect(page.locator('[data-freshness]')).toContainText('다음 기대 거래일:');
 await expect(page.locator('[data-freshness]')).toContainText('KST');
 const chart=page.locator('[data-chart]').first();await chart.scrollIntoViewIfNeeded();
 await expect(chart.locator('.chart-canvas')).toContainText('TQQQ 합성 구간');
 await page.setViewportSize({width:390,height:844});
 await expect(chart.locator('.chart-metrics td[data-label="최대 낙폭"]').first()).toBeVisible();
 expect(await chart.locator('.chart-metrics').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await page.goto('guide/start/');await expect(page.locator('h1')).toContainText('처음 읽는 투자 분석');
 await expect(page.locator('main')).toContainText('하루 수익률 3배');
 await expect(page.locator('main')).toContainText('약 94.54');
});

test('every analysis shows annual returns and MDD or an explicit source limitation',async({page})=>{
 await page.goto('research/batch-01/');
 await expect(page.locator('#yearly h2')).toHaveText('연도별 수익률과 MDD');
 await expect(page.locator('.yearly-model')).toHaveValue('vo');
 await expect(page.locator('.yearly-row')).toHaveCount(10);
 await expect(page.locator('.yearly-table thead')).toContainText('연중 MDD');
 await page.locator('.yearly-start').selectOption('2010');
 await expect(page.locator('.yearly-row')).toHaveCount(17);
 await page.locator('.yearly-model').selectOption('tqqq_hold');
 await expect(page.locator('.yearly-table caption')).toContainText('TQQQ 단순 보유');
 await page.setViewportSize({width:390,height:844});
 expect(await page.locator('#yearly').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBeTruthy();
 await page.goto('research/batch-09/');
 await expect(page.locator('#yearly')).toContainText('일별 포트폴리오 자산 곡선이 저장되어 있지 않아');
 await expect(page.locator('.yearly-row')).toHaveCount(0);
});
