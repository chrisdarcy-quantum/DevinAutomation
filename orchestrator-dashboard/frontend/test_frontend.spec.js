/**
 * Playwright tests for the Feature Flag Removal Dashboard frontend
 * 
 * These tests verify the UI functionality and user interactions.
 */

const { test, expect } = require('@playwright/test');

const BASE_URL = 'http://localhost:8000';

test.describe('Feature Flag Removal Dashboard', () => {
  
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);
  });

  test('should load the dashboard page', async ({ page }) => {
    await expect(page).toHaveTitle(/Feature Flag Removal Dashboard/);
    
    const header = page.locator('h1');
    await expect(header).toContainText('Feature Flag Removal Dashboard');
  });

  test('should display navigation tabs', async ({ page }) => {
    const dashboardTab = page.locator('.tab', { hasText: 'Dashboard' });
    await expect(dashboardTab).toBeVisible();
    
    const createTab = page.locator('.tab', { hasText: 'Create Request' });
    await expect(createTab).toBeVisible();
  });

  test('should navigate to create request form', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    
    await page.waitForSelector('form');
    
    await expect(page.locator('input[name="flag_key"]')).toBeVisible();
    await expect(page.locator('textarea[name="repositories"]')).toBeVisible();
    await expect(page.locator('input[name="feature_flag_provider"]')).toBeVisible();
    await expect(page.locator('input[name="created_by"]')).toBeVisible();
  });

  test('should validate required fields in create form', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.click('button[type="submit"]');
    
    const flagKeyInput = page.locator('input[name="flag_key"]');
    const isInvalid = await flagKeyInput.evaluate(el => !el.validity.valid);
    expect(isInvalid).toBe(true);
  });

  test('should fill and submit create request form', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.fill('input[name="flag_key"]', 'TEST_FEATURE_FLAG');
    await page.fill('textarea[name="repositories"]', 'https://github.com/test/repo1');
    await page.fill('input[name="feature_flag_provider"]', 'LaunchDarkly');
    await page.fill('input[name="created_by"]', 'test@example.com');
    
    await page.click('button[type="submit"]');
    
    await page.waitForTimeout(1000);
    
    const dashboardTab = page.locator('.tab.active', { hasText: 'Dashboard' });
    const successToast = page.locator('.toast-success');
    
    const isDashboard = await dashboardTab.isVisible().catch(() => false);
    const hasToast = await successToast.isVisible().catch(() => false);
    
    expect(isDashboard || hasToast).toBe(true);
  });

  test('should display status filter dropdown', async ({ page }) => {
    const statusFilter = page.locator('select.select');
    await expect(statusFilter).toBeVisible();
    
    const options = await statusFilter.locator('option').count();
    expect(options).toBeGreaterThan(1);
  });

  test('should have refresh button', async ({ page }) => {
    const refreshButton = page.locator('button:has-text("Refresh")');
    await expect(refreshButton).toBeVisible();
    
    await refreshButton.click();
    
    await page.waitForTimeout(500);
  });

  test('should display empty state when no requests', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    const emptyState = page.locator('text=No removal requests found');
    const requestCards = page.locator('.card');
    
    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    const hasCards = await requestCards.count().then(c => c > 0).catch(() => false);
    
    expect(hasEmptyState || hasCards).toBe(true);
  });

  test('should navigate back from create form', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.click('button:has-text("Cancel")');
    
    await page.waitForTimeout(500);
    
    const dashboardTab = page.locator('.tab.active', { hasText: 'Dashboard' });
    await expect(dashboardTab).toBeVisible();
  });

  test('should have proper styling and layout', async ({ page }) => {
    const app = page.locator('#app');
    await expect(app).toBeVisible();
    
    const header = page.locator('header');
    await expect(header).toBeVisible();
    
    const body = page.locator('body');
    const bgClass = await body.getAttribute('class');
    expect(bgClass).toContain('bg-gray-50');
  });

  test('should handle form validation for invalid repository URLs', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.fill('input[name="flag_key"]', 'TEST_FLAG');
    await page.fill('textarea[name="repositories"]', 'not-a-valid-url');
    await page.fill('input[name="created_by"]', 'test@example.com');
    
    await page.click('button[type="submit"]');
    
    await page.waitForTimeout(1000);
    
    const errorToast = page.locator('.toast-error');
    const hasError = await errorToast.isVisible().catch(() => false);
    
    expect(hasError).toBe(true);
  });

  test('should handle multiple repositories in textarea', async ({ page }) => {
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.fill('input[name="flag_key"]', 'MULTI_REPO_FLAG');
    await page.fill('textarea[name="repositories"]', 
      'https://github.com/test/repo1\nhttps://github.com/test/repo2\nhttps://github.com/test/repo3');
    await page.fill('input[name="created_by"]', 'test@example.com');
    
    await page.click('button[type="submit"]');
    
    await page.waitForTimeout(1000);
  });

  test('should display toast container', async ({ page }) => {
    const toastContainer = page.locator('#toast-container');
    await expect(toastContainer).toBeAttached();
  });

  test('should have responsive design elements', async ({ page }) => {
    const content = page.locator('.max-w-7xl');
    await expect(content).toBeVisible();
  });
});

test.describe('Dashboard Interactions', () => {
  
  test('should filter requests by status', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.selectOption('select.select', 'completed');
    
    await page.waitForTimeout(1000);
    
    const selectedValue = await page.locator('select.select').inputValue();
    expect(selectedValue).toBe('completed');
  });

  test('should maintain state when navigating between tabs', async ({ page }) => {
    await page.goto(BASE_URL);
    
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    await page.click('.tab:has-text("Dashboard")');
    
    const dashboardTab = page.locator('.tab.active', { hasText: 'Dashboard' });
    await expect(dashboardTab).toBeVisible();
  });
});

test.describe('Accessibility', () => {
  
  test('should have proper heading hierarchy', async ({ page }) => {
    await page.goto(BASE_URL);
    
    const h1 = page.locator('h1');
    await expect(h1).toBeVisible();
    
    await expect(h1).toContainText('Feature Flag Removal Dashboard');
  });

  test('should have form labels', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    const labels = page.locator('label');
    const labelCount = await labels.count();
    expect(labelCount).toBeGreaterThan(0);
  });

  test('should have required field indicators', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.click('.tab:has-text("Create Request")');
    await page.waitForSelector('form');
    
    const requiredIndicators = page.locator('.text-red-500');
    const count = await requiredIndicators.count();
    expect(count).toBeGreaterThan(0);
  });
});
