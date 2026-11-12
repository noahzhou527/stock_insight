import { expect, test, type Page } from '@playwright/test'

/** Fail the test on uncaught page errors (render crashes would otherwise only show as a blank block). */
function watchErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

test('every page opens', async ({ page }) => {
  const errors = watchErrors(page)

  await page.goto('/stock/CN/300308.SZ')
  await expect(page.getByRole('heading', { level: 1, name: '中际旭创' })).toBeVisible()
  await expect(page.getByRole('img', { name: /日 K 线图/ })).toBeVisible()
  await expect(page.getByText('技术信号摘要')).toBeVisible()
  for (const tab of ['财务报表', '同业对比', '数据明细']) {
    await page.getByRole('tab', { name: tab }).click()
    await expect(page.getByRole('tabpanel')).not.toBeEmpty()
  }
  await expect(page.getByRole('table', { name: '日线明细' })).toBeVisible()

  await page.goto('/watchlist')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(/当日表现|最近交易日|暂无行情|自选/)

  await page.goto('/market/CN')
  await expect(page.getByRole('heading', { name: '市场概览' })).toBeVisible()
  await expect(page.getByRole('list', { name: '指数' }).getByRole('listitem').first()).toBeVisible()
  await page.getByRole('tab', { name: '美股' }).click()
  await expect(page).toHaveURL(/\/market\/US/)
  await expect(page.getByText('美股涨跌家数')).toBeVisible()

  await page.goto('/rankings')
  await expect(page.getByRole('table', { name: '股票池排行' }).locator('tbody tr').first()).toBeVisible()
  await page.getByRole('radio', { name: 'PE TTM' }).click()
  await expect(page).toHaveURL(/metric=pe_ttm/)

  await page.goto('/news')
  await expect(page.getByRole('list', { name: '新闻列表' }).getByRole('link').first()).toBeVisible()
  await expect(page.getByLabel('新闻来源状态')).toContainText('Yahoo')

  expect(errors).toEqual([])
})

test('search finds a stock by code and opens it', async ({ page }) => {
  const errors = watchErrors(page)
  await page.goto('/market/CN')
  await expect(page.getByRole('heading', { name: '市场概览' })).toBeVisible() // lazy page loaded, hotkey bound
  await page.keyboard.press('Control+k')
  const input = page.getByPlaceholder(/代码或名称/)
  await expect(input).toBeFocused()
  await input.fill('SZ300502')
  await page.getByRole('option', { name: /300502\.SZ/ }).first().click()
  await expect(page).toHaveURL(/\/stock\/CN\/300502\.SZ/)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  expect(errors).toEqual([])
})

test('watchlist: add, remove, undo', async ({ page }) => {
  const errors = watchErrors(page)
  await page.goto('/watchlist')
  const table = page.getByRole('table', { name: '自选行情' })
  const add = page.getByLabel('添加自选代码')

  await add.fill('300308')
  await page.getByRole('button', { name: '加入' }).click()
  await expect(table.getByText('300308.SZ')).toBeVisible()

  await add.fill('SZ300308')
  await page.getByRole('button', { name: '加入' }).click()
  await expect(page.getByRole('alert')).toContainText('已在自选中')

  await add.fill('abc')
  await page.getByRole('button', { name: '加入' }).click()
  await expect(page.getByRole('alert')).toContainText('格式')

  await table.getByRole('button', { name: /移出自选/ }).first().click()
  await expect(table.getByText('300308.SZ')).toHaveCount(0)
  await page.getByRole('button', { name: '撤销' }).click()
  await expect(table.getByText('300308.SZ')).toBeVisible()

  await table.getByRole('button', { name: /移出自选/ }).first().click()
  await expect(page.getByText('自选还是空的')).toBeVisible()
  expect(errors).toEqual([])
})
