import { test, expect } from '@playwright/test'

test.describe('Auto-Scholar Smoke Tests', () => {
  test('homepage loads correctly', async ({ page }) => {
    await page.goto('/')
    
    await expect(page.locator('text=Agent Console').or(page.locator('text=智能助手控制台'))).toBeVisible()
    await expect(page.locator('text=Auto-Scholar')).toBeVisible()
    await expect(page.locator('input[placeholder]')).toBeVisible()
  })

  test('example queries are clickable', async ({ page }) => {
    await page.goto('/')
    
    const exampleButtons = page.locator('button').filter({ hasText: /Transformer|Deep learning|Reinforcement|Large language|Federated/i })
    await expect(exampleButtons.first()).toBeVisible()
    
    await exampleButtons.first().click()
    
    const input = page.locator('input[placeholder]')
    await expect(input).not.toHaveValue('')
  })

  test('source selectors are visible and interactive', async ({ page }) => {
    await page.goto('/')
    
    await expect(page.locator('text=Semantic Scholar')).toBeVisible()
    await expect(page.locator('text=arXiv')).toBeVisible()
    await expect(page.locator('text=PubMed')).toBeVisible()
    
    const arxivCheckbox = page.locator('label').filter({ hasText: 'arXiv' }).locator('button[role="checkbox"]')
    await arxivCheckbox.click()
    await expect(arxivCheckbox).toHaveAttribute('data-state', 'checked')
  })

  test('output language selector works', async ({ page }) => {
    await page.goto('/')
    
    const langSelector = page.locator('button').filter({ hasText: /EN|中/ }).first()
    await expect(langSelector).toBeVisible()
    
    await langSelector.click()
    await expect(langSelector).toBeVisible()
  })

  test('UI language switcher works', async ({ page }) => {
    await page.goto('/')
    
    const switcher = page.locator('button').filter({ hasText: /中文|English/ })
    await expect(switcher).toBeVisible()
    
    const initialText = await switcher.textContent()
    await switcher.click()
    
    await page.waitForTimeout(500)
    const newText = await switcher.textContent()
    expect(newText).not.toBe(initialText)
  })

  test('history panel expands', async ({ page }) => {
    await page.goto('/')
    
    const historyButton = page.locator('button').filter({ hasText: /History|历史记录/ })
    await expect(historyButton).toBeVisible()
    
    await historyButton.click()
    
    await expect(
      page.locator('text=No previous sessions').or(page.locator('text=暂无历史记录')).or(page.locator('button').filter({ hasText: /Load|加载/ }))
    ).toBeVisible({ timeout: 5000 })
  })

  test('start button is disabled without query', async ({ page }) => {
    await page.goto('/')
    
    const startButton = page.locator('button').filter({ hasText: /Start|开始/ }).first()
    await expect(startButton).toBeDisabled()
  })

  test('start button enables with query', async ({ page }) => {
    await page.goto('/')
    
    const input = page.locator('input[placeholder]')
    await input.fill('test query')
    
    const startButton = page.locator('button[type="submit"]').filter({ hasText: /Start|开始/ })
    await expect(startButton).toBeEnabled()
  })

  test('workspace shows idle state initially', async ({ page }) => {
    await page.goto('/')
    
    await expect(
      page.locator('text=Enter a research topic').or(page.locator('text=输入研究主题'))
    ).toBeVisible()
  })
})
