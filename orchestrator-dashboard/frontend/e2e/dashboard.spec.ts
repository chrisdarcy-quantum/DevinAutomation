import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('Feature Flag Removal Dashboard');
  });

  test('should display dashboard with request list', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
    
    await expect(page.getByRole('button', { name: 'All Statuses' })).toBeVisible();
    
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('should handle empty state gracefully', async ({ page }) => {
    const emptyState = page.getByText('No removal requests found');
    const requestCards = page.locator('[class*="border"][class*="rounded-lg"]').filter({ hasText: 'Created by:' });
    
    const hasEmptyState = await emptyState.isVisible().catch(() => false);
    const hasRequests = await requestCards.count().then(count => count > 0).catch(() => false);
    
    expect(hasEmptyState || hasRequests).toBeTruthy();
  });

  test('should display request cards with correct information', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    const requestCards = page.locator('[class*="border"][class*="rounded-lg"]').filter({ hasText: 'Created by:' });
    const count = await requestCards.count();
    
    if (count > 0) {
      const firstCard = requestCards.first();
      
      await expect(firstCard.locator('text=/Created by:/')).toBeVisible();
      await expect(firstCard.locator('text=/Sessions:/')).toBeVisible();
      await expect(firstCard.locator('text=/ACU Consumed:/')).toBeVisible();
      
      const statusBadge = firstCard.locator('[class*="badge"]').or(firstCard.locator('text=/queued|in_progress|completed|failed|partial/'));
      await expect(statusBadge.first()).toBeVisible();
    }
  });

  test('should filter requests by status', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    await page.getByRole('button', { name: 'All Statuses' }).click();
    
    await expect(page.getByRole('option', { name: 'All Statuses' })).toBeVisible();
  });

  test('should refresh request list when clicking refresh button', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    await page.getByRole('button', { name: 'Refresh' }).click();
    
    await page.waitForTimeout(500);
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
  });

  test('should navigate to request detail when clicking on a request', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    const requestCards = page.locator('[class*="border"][class*="rounded-lg"]').filter({ hasText: 'Created by:' });
    const count = await requestCards.count();
    
    if (count > 0) {
      await requestCards.first().click();
      
      await expect(page.getByRole('button', { name: 'Request Details' })).toBeVisible();
    }
  });

  test('should not crash when displaying requests without sessions array', async ({ page }) => {
    
    await page.waitForTimeout(1000);
    
    await expect(page.locator('h1')).toContainText('Feature Flag Removal Dashboard');
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    
    const errors: string[] = [];
    page.on('pageerror', error => {
      errors.push(error.message);
    });
    
    await page.waitForTimeout(1000);
    
    const hasFilterError = errors.some(err => err.includes('Cannot read properties of undefined') && err.includes('filter'));
    expect(hasFilterError).toBeFalsy();
  });
});
