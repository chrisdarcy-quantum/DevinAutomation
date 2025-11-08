import { test, expect } from '@playwright/test';

test.describe('Create Removal Request', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toContainText('Feature Flag Removal Dashboard');
    
    await page.getByRole('button', { name: 'Create Request' }).click();
    await expect(page.getByRole('button', { name: 'Create Request' })).toHaveAttribute('aria-selected', 'true');
  });

  test('should display create request form', async ({ page }) => {
    await expect(page.getByText('Create Feature Flag Removal Request')).toBeVisible();
    
    await expect(page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE')).toBeVisible();
    await expect(page.getByPlaceholder('https://github.com/owner/repo')).toBeVisible();
    await expect(page.getByPlaceholder('e.g., LaunchDarkly, Split, etc. (optional)')).toBeVisible();
    await expect(page.getByPlaceholder('your.email@example.com')).toBeVisible();
    
    await expect(page.getByRole('button', { name: 'Create Removal Request' })).toBeVisible();
    
    await expect(page.getByRole('button', { name: 'Add Repository' })).toBeVisible();
  });

  test('should validate required fields', async ({ page }) => {
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await expect(page.getByRole('button', { name: 'Create Request' })).toHaveAttribute('aria-selected', 'true');
  });

  test('should successfully create a removal request', async ({ page }) => {
    const timestamp = Date.now();
    const flagKey = `test_flag_${timestamp}`;
    
    await page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE').fill(flagKey);
    await page.getByPlaceholder('https://github.com/owner/repo').fill('https://github.com/test-org/test-repo');
    await page.getByPlaceholder('e.g., LaunchDarkly, Split, etc. (optional)').fill('LaunchDarkly');
    await page.getByPlaceholder('your.email@example.com').fill('test@example.com');
    
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
    
    await page.waitForTimeout(1000);
    
    await expect(page.getByText(flagKey)).toBeVisible();
    
    await expect(page.locator('h1')).toContainText('Feature Flag Removal Dashboard');
  });

  test('should handle multiple repositories', async ({ page }) => {
    const timestamp = Date.now();
    const flagKey = `multi_repo_${timestamp}`;
    
    await page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE').fill(flagKey);
    await page.getByPlaceholder('https://github.com/owner/repo').fill('https://github.com/test-org/repo1');
    
    await page.getByRole('button', { name: 'Add Repository' }).click();
    
    const repoInputs = page.getByPlaceholder('https://github.com/owner/repo');
    await repoInputs.nth(1).fill('https://github.com/test-org/repo2');
    
    await page.getByPlaceholder('your.email@example.com').fill('test@example.com');
    
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
    
    await page.waitForTimeout(1000);
    
    const requestCard = page.locator(`text=${flagKey}`).locator('..').locator('..').locator('..');
    await expect(requestCard.getByText('2 repositories')).toBeVisible();
  });

  test('should handle optional provider field', async ({ page }) => {
    const timestamp = Date.now();
    const flagKey = `no_provider_${timestamp}`;
    
    await page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE').fill(flagKey);
    await page.getByPlaceholder('https://github.com/owner/repo').fill('https://github.com/test-org/test-repo');
    await page.getByPlaceholder('your.email@example.com').fill('test@example.com');
    
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'true');
    
    await page.waitForTimeout(1000);
    
    await expect(page.getByText(flagKey)).toBeVisible();
  });

  test('should not crash after successful submission', async ({ page }) => {
    const timestamp = Date.now();
    const flagKey = `crash_test_${timestamp}`;
    
    const errors: string[] = [];
    page.on('pageerror', error => {
      errors.push(error.message);
    });
    
    await page.getByPlaceholder('e.g., ENABLE_NEW_FEATURE').fill(flagKey);
    await page.getByPlaceholder('https://github.com/owner/repo').fill('https://github.com/test-org/test-repo');
    await page.getByPlaceholder('your.email@example.com').fill('test@example.com');
    
    await page.getByRole('button', { name: 'Create Removal Request' }).click();
    
    await page.waitForTimeout(2000);
    
    await expect(page.locator('h1')).toContainText('Feature Flag Removal Dashboard');
    
    await expect(page.getByRole('button', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Refresh' })).toBeVisible();
    
    const hasFilterError = errors.some(err => 
      err.includes('Cannot read properties of undefined') && err.includes('filter')
    );
    expect(hasFilterError).toBeFalsy();
    
    await expect(page.getByText(flagKey)).toBeVisible();
  });
});
