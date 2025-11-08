import { test, expect } from '@playwright/test';

test.describe('Request Detail', () => {
  let requestId: number;

  test.beforeEach(async ({ page }) => {
    const timestamp = Date.now();
    const flagKey = `detail_test_${timestamp}`;
    
    await page.goto('/');
    await page.getByRole('button', { name: 'Create Request' }).click();
    
    await page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE').fill(flagKey);
    await page.getByPlaceholder('https://github.com/owner/repo').fill('https://github.com/test-org/test-repo');
    await page.getByPlaceholder('your.email@example.com').fill('test@example.com');
    
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await page.waitForTimeout(1000);
    
    await page.getByText(flagKey).click();
    
    await expect(page.getByRole('button', { name: 'Request Details' })).toBeVisible();
  });

  test('should display request detail view', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Request Details' })).toHaveAttribute('aria-selected', 'true');
    
    await expect(page.getByText('Overview')).toBeVisible();
    
    await expect(page.getByText('Devin Sessions')).toBeVisible();
    
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
  });

  test('should display request information', async ({ page }) => {
    await expect(page.getByText('Status')).toBeVisible();
    
    await expect(page.getByText('Created')).toBeVisible();
    
    await expect(page.getByText('Last Updated')).toBeVisible();
    
    await expect(page.getByText('Total ACU Consumed')).toBeVisible();
    
    await expect(page.getByText('Progress')).toBeVisible();
  });

  test('should display session information', async ({ page }) => {
    await page.waitForTimeout(1000);
    
    const sessionCard = page.locator('[class*="border"][class*="rounded-lg"]').filter({ hasText: 'Session ID:' });
    
    if (await sessionCard.count() > 0) {
      await expect(sessionCard.first().getByText('Session ID:')).toBeVisible();
      await expect(sessionCard.first().getByText('Created:')).toBeVisible();
    }
  });

  test('should handle sessions array gracefully', async ({ page }) => {
    
    const errors: string[] = [];
    page.on('pageerror', error => {
      errors.push(error.message);
    });
    
    await page.waitForTimeout(2000);
    
    await expect(page.getByText('Overview')).toBeVisible();
    
    const hasError = errors.some(err => err.includes('Cannot read properties of undefined'));
    expect(hasError).toBeFalsy();
  });

  test('should refresh request details', async ({ page }) => {
    await page.getByRole('button', { name: 'Refresh' }).click();
    
    await page.waitForTimeout(1000);
    
    await expect(page.getByText('Overview')).toBeVisible();
  });

  test('should navigate back to dashboard', async ({ page }) => {
    await page.getByRole('button', { name: 'Dashboard' }).click();
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
  });
});
