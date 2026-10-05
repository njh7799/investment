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
  await expect(page.locator('.chart-canvas .main-svg').first()).toBeVisible();
  await page.locator('.period-picker').selectOption('2025');
  await expect(page.locator('.chart-metrics')).toContainText('2025-12-31');
  await page.locator('.metric-picker').selectOption('drawdown');
  await expect(page.locator('.chart-canvas')).toContainText('고점 대비 낙폭');
  const download=page.waitForEvent('download');await page.locator('.download-chart').click();
  const saved=await download;expect(saved.suggestedFilename()).toBe('investment-chart.html');
  const target=testInfo.outputPath('standalone.html');await saved.saveAs(target);
  const standalone=await page.context().newPage();await standalone.goto('file://'+target);
  await expect(standalone.locator('.main-svg').first()).toBeVisible();await standalone.close();
  expect(errors).toEqual([]);
});

test('result period filter, key columns, sorting and pagination',async({page})=>{
  await page.goto('research/batch-05/');await page.reload();
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


test('methods connect rules, exact historical specs and research in both directions',async({page})=>{
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
  await expect(vo).toContainText('40.70%');
  await expect(vo).toContainText('6.0회');
  await expect(vo).not.toContainText('2010-02-11 — 2026-07-31');
  await expect(vo).toContainText('최장 고점 미회복 기간');
  await expect(vo).toContainText('연평균 거래');
  await expect(vo.locator('.method-details')).toHaveAttribute('open','');
  const buyHold=page.locator('[data-method="tqqq-buy-hold"]');
  await expect(buyHold.locator('.method-details')).not.toHaveAttribute('open','');
  await expect(buyHold).toContainText('42.32%');
  await expect(buyHold).toContainText('-81.66%');
  await expect(buyHold).toContainText('1111일');
  await expect(buyHold).toContainText('0.1회');
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
  await expect(page.locator('.chart-metrics')).toContainText('2026-07-31');
  await expect(page.locator('.chart-metrics')).not.toContainText('2026-08-11');
  const download=page.waitForEvent('download');
  await page.getByText('성과 원본 CSV ↓',{exact:true}).click();
  expect((await download).suggestedFilename()).toBe('period-summary.csv');
});


test('card image opens role-colored comparison periods and clear detail hierarchy',async({page})=>{
  await page.goto('./');
  const card=page.locator('[data-method="volatility-allocation"]');
  await expect(card.locator('.method-preview img')).toBeVisible();
  await expect(card.locator('.method-preview img')).toHaveJSProperty('naturalWidth',2880);
  await expect(card.locator('.method-preview img')).toHaveJSProperty('naturalHeight',1440);
  await expect(card.locator('.metric-period')).toHaveCount(0);
  const voPreview=await (await page.request.get('data/preview-volatility-allocation-actual.json')).json();
  expect(voPreview.curves.map((curve:any)=>[curve.preview_role,curve.display_color])).toEqual([
    ['benchmark','#2979FF'],['target','#E5484D']
  ]);
  await card.locator('.method-preview>a').click();
  await expect(page.locator('.detail-context')).toContainText('투자 방법');
  await expect(page.locator('.detail-trail')).toContainText('VO · 변동성 배분');
  await expect(page.locator('.detail-kind')).toHaveText('차트 상세');
  await expect(page.locator('.period-picker')).toHaveValue('actual');
  await expect(page.locator('.chart-metrics tbody tr')).toHaveCount(2);
  await expect(page.locator('.chart-metrics')).toContainText('2010-02-11');
  await page.locator('.period-picker').selectOption('recent-10y');
  await expect(page.locator('.chart-metrics')).toContainText('2016-10-05');
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
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('.detail-context')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBeTruthy();
});
