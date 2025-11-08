/**
 * Playwright E2E tests for Feature Flag Removal Dashboard
 * Tests the repository-first flow with comprehensive coverage
 */

const { test, expect } = require('@playwright/test');

async function registerApiMocks(page, overrides = {}) {
  const defaults = {
    repositories: [],
    flags: [],
    removals: [],
    scanOutcome: { status: 202, body: { message: 'Scan started', repository_id: 1, devin_session_id: 's123', devin_session_url: 'https://app.devin.ai/sessions/s123' } }
  };
  
  const mocks = { ...defaults, ...overrides };
  
  await page.route('**/api/repositories', route => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.repositories) });
    } else if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData());
      const newRepo = { id: Date.now(), url: body.url, github_token: body.github_token, provider_detected: null, last_scanned_at: null, created_at: new Date().toISOString(), flag_count: 0 };
      route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(newRepo) });
    }
  });
  
  await page.route('**/api/repositories/*', route => {
    const method = route.request().method();
    if (method === 'DELETE') {
      route.fulfill({ status: 204 });
    } else if (method === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.repositories[0] || {}) });
    }
  });
  
  await page.route('**/api/repositories/*/scan', route => {
    route.fulfill({ status: mocks.scanOutcome.status, contentType: 'application/json', body: JSON.stringify(mocks.scanOutcome.body) });
  });
  
  await page.route('**/api/repositories/*/flags', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.flags) });
  });
  
  await page.route('**/api/flags*', route => {
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.flags) });
  });
  
  await page.route('**/api/removals*', route => {
    if (route.request().method() === 'GET') {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mocks.removals) });
    } else if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData());
      const newRemoval = {
        id: Date.now(),
        flag_key: body.flag_key,
        repositories: body.repositories || [],
        repository_id: body.repository_id,
        feature_flag_provider: body.feature_flag_provider,
        preserve_mode: body.preserve_mode,
        status: 'queued',
        created_by: body.created_by,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        error_message: null,
        total_acu_consumed: 0,
        sessions: []
      };
      route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(newRemoval) });
    }
  });
}

test.describe('Tab Navigation', () => {
  test('should navigate between Repositories, Flags, and History tabs', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/');
    
    await expect(page.getByRole('heading', { name: 'Repositories' })).toBeVisible();
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    await expect(page.getByRole('heading', { name: 'Discovered Flags' })).toBeVisible();
    
    await page.getByRole('tab', { name: 'History' }).click();
    await expect(page.getByRole('heading', { name: 'Removal Requests' })).toBeVisible();
    
    await page.getByRole('tab', { name: 'Repositories' }).click();
    await expect(page.getByRole('heading', { name: 'Repositories' })).toBeVisible();
  });
});

test.describe('Repositories Tab', () => {
  test('should display empty state when no repositories', async ({ page }) => {
    await registerApiMocks(page, { repositories: [] });
    await page.goto('/');
    
    await expect(page.getByText('No repositories yet')).toBeVisible();
    await expect(page.getByText('Add your first repository')).toBeVisible();
  });
  
  test('should display repository cards', async ({ page }) => {
    const mockRepos = [
      { id: 1, url: 'https://github.com/test/repo1', provider_detected: 'LaunchDarkly', last_scanned_at: new Date().toISOString(), created_at: new Date().toISOString(), flag_count: 5 },
      { id: 2, url: 'https://github.com/test/repo2', provider_detected: null, last_scanned_at: null, created_at: new Date().toISOString(), flag_count: 0 }
    ];
    
    await registerApiMocks(page, { repositories: mockRepos });
    await page.goto('/');
    
    await expect(page.getByText('https://github.com/test/repo1')).toBeVisible();
    await expect(page.getByText('Provider: LaunchDarkly')).toBeVisible();
    await expect(page.getByText('https://github.com/test/repo2')).toBeVisible();
  });
  
  test('should open add repository modal', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/');
    
    await page.getByRole('button', { name: 'Add Repository' }).click();
    
    await expect(page.getByRole('heading', { name: 'Add Repository' })).toBeVisible();
    await expect(page.getByLabel('Repository URL')).toBeVisible();
    await expect(page.getByLabel('GitHub Token')).toBeVisible();
  });
  
  test('should add repository successfully', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/');
    
    await page.getByRole('button', { name: 'Add Repository' }).click();
    await page.getByLabel('Repository URL').fill('https://github.com/test/new-repo');
    await page.getByLabel('GitHub Token').fill('ghp_test123');
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/repositories') && req.method() === 'POST'),
      page.getByRole('button', { name: 'Add' }).click()
    ]);
    
    const postData = JSON.parse(request.postData());
    expect(postData.url).toBe('https://github.com/test/new-repo');
    expect(postData.github_token).toBe('ghp_test123');
    
    await expect(page.getByText('https://github.com/test/new-repo')).toBeVisible();
  });
  
  test('should show error when adding invalid repository URL', async ({ page }) => {
    await page.route('**/api/repositories', route => {
      if (route.request().method() === 'POST') {
        route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'Invalid repository URL' }) });
      } else {
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      }
    });
    
    await page.goto('/');
    
    await page.getByRole('button', { name: 'Add Repository' }).click();
    await page.getByLabel('Repository URL').fill('invalid-url');
    await page.getByRole('button', { name: 'Add' }).click();
    
    await expect(page.getByText('Invalid repository URL')).toBeVisible();
  });
  
  test('should scan repository successfully', async ({ page }) => {
    const mockRepos = [
      { id: 1, url: 'https://github.com/test/repo1', provider_detected: null, last_scanned_at: null, created_at: new Date().toISOString(), flag_count: 0 }
    ];
    
    await registerApiMocks(page, { repositories: mockRepos });
    await page.goto('/');
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/repositories/1/scan') && req.method() === 'POST'),
      page.getByRole('button', { name: 'Scan' }).first().click()
    ]);
    
    await expect(page.getByText('Scan started')).toBeVisible();
  });
  
  test('should handle scan error when Devin not initialized', async ({ page }) => {
    const mockRepos = [
      { id: 1, url: 'https://github.com/test/repo1', provider_detected: null, last_scanned_at: null, created_at: new Date().toISOString(), flag_count: 0 }
    ];
    
    await registerApiMocks(page, { 
      repositories: mockRepos,
      scanOutcome: { status: 503, body: { detail: 'Devin services not initialized' } }
    });
    await page.goto('/');
    
    await page.getByRole('button', { name: 'Scan' }).first().click();
    
    await expect(page.getByText('Devin services not initialized')).toBeVisible();
  });
  
  test('should navigate to flags view when clicking View Flags', async ({ page }) => {
    const mockRepos = [
      { id: 1, url: 'https://github.com/test/repo1', provider_detected: 'LaunchDarkly', last_scanned_at: new Date().toISOString(), created_at: new Date().toISOString(), flag_count: 3 }
    ];
    
    const mockFlags = [
      { id: 1, repository_id: 1, flag_key: 'feature-a', occurrences: 5, files: ['app.js', 'utils.js'], provider: 'LaunchDarkly', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo1' }
    ];
    
    await registerApiMocks(page, { repositories: mockRepos, flags: mockFlags });
    await page.goto('/');
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/flags?repository_id=1')),
      page.getByRole('button', { name: /View Flags/ }).first().click()
    ]);
    
    await expect(page.getByRole('heading', { name: 'Discovered Flags' })).toBeVisible();
    await expect(page.getByText('feature-a')).toBeVisible();
  });
  
  test('should delete repository', async ({ page }) => {
    const mockRepos = [
      { id: 1, url: 'https://github.com/test/repo1', provider_detected: null, last_scanned_at: null, created_at: new Date().toISOString(), flag_count: 0 }
    ];
    
    await registerApiMocks(page, { repositories: mockRepos });
    await page.goto('/');
    
    await expect(page.getByText('https://github.com/test/repo1')).toBeVisible();
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/repositories/1') && req.method() === 'DELETE'),
      page.getByRole('button', { name: 'Delete' }).first().click()
    ]);
    
    await page.waitForTimeout(500);
    await expect(page.getByText('https://github.com/test/repo1')).not.toBeVisible();
  });
});

test.describe('Flags Tab', () => {
  test('should display empty state when no flags', async ({ page }) => {
    await registerApiMocks(page, { flags: [] });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    
    await expect(page.getByText('No flags discovered yet')).toBeVisible();
  });
  
  test('should display flag cards with details', async ({ page }) => {
    const mockFlags = [
      { id: 1, repository_id: 1, flag_key: 'feature-a', occurrences: 5, files: ['app.js', 'utils.js'], provider: 'LaunchDarkly', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo1' },
      { id: 2, repository_id: 2, flag_key: 'feature-b', occurrences: 3, files: ['index.js'], provider: 'Statsig', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo2' }
    ];
    
    await registerApiMocks(page, { flags: mockFlags });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    
    await expect(page.getByText('feature-a')).toBeVisible();
    await expect(page.getByText('5 occurrences')).toBeVisible();
    await expect(page.getByText('LaunchDarkly')).toBeVisible();
    await expect(page.getByText('feature-b')).toBeVisible();
    await expect(page.getByText('3 occurrences')).toBeVisible();
    await expect(page.getByText('Statsig')).toBeVisible();
  });
  
  test('should open remove flag modal with pre-filled data', async ({ page }) => {
    const mockFlags = [
      { id: 1, repository_id: 1, flag_key: 'feature-a', occurrences: 5, files: ['app.js'], provider: 'LaunchDarkly', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo1' }
    ];
    
    await registerApiMocks(page, { flags: mockFlags });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    await page.getByRole('button', { name: 'Remove Flag' }).first().click();
    
    await expect(page.getByRole('heading', { name: 'Remove Feature Flag' })).toBeVisible();
    await expect(page.getByLabel('Flag Key')).toHaveValue('feature-a');
    await expect(page.getByLabel('Provider')).toHaveValue('LaunchDarkly');
  });
  
  test('should submit flag removal with preserve mode', async ({ page }) => {
    const mockFlags = [
      { id: 1, repository_id: 1, flag_key: 'feature-a', occurrences: 5, files: ['app.js'], provider: 'LaunchDarkly', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo1' }
    ];
    
    await registerApiMocks(page, { flags: mockFlags });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    await page.getByRole('button', { name: 'Remove Flag' }).first().click();
    
    await page.getByLabel('Preserve the "disabled" code path').check();
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/removals') && req.method() === 'POST'),
      page.getByRole('button', { name: 'Remove' }).click()
    ]);
    
    const postData = JSON.parse(request.postData());
    expect(postData.flag_key).toBe('feature-a');
    expect(postData.repository_id).toBe(1);
    expect(postData.feature_flag_provider).toBe('LaunchDarkly');
    expect(postData.preserve_mode).toBe('disabled');
    expect(postData.created_by).toBeTruthy();
  });
  
  test('should submit flag removal with enabled preserve mode', async ({ page }) => {
    const mockFlags = [
      { id: 1, repository_id: 1, flag_key: 'feature-a', occurrences: 5, files: ['app.js'], provider: 'LaunchDarkly', last_seen_at: new Date().toISOString(), repository_url: 'https://github.com/test/repo1' }
    ];
    
    await registerApiMocks(page, { flags: mockFlags });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'Flags' }).click();
    await page.getByRole('button', { name: 'Remove Flag' }).first().click();
    
    const [request] = await Promise.all([
      page.waitForRequest(req => req.url().includes('/api/removals') && req.method() === 'POST'),
      page.getByRole('button', { name: 'Remove' }).click()
    ]);
    
    const postData = JSON.parse(request.postData());
    expect(postData.preserve_mode).toBe('enabled');
  });
});

test.describe('History Tab', () => {
  test('should display empty state when no removal requests', async ({ page }) => {
    await registerApiMocks(page, { removals: [] });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'History' }).click();
    
    await expect(page.getByText('No removal requests yet')).toBeVisible();
  });
  
  test('should display removal request cards with status badges', async ({ page }) => {
    const mockRemovals = [
      { id: 1, flag_key: 'feature-a', repositories: ['https://github.com/test/repo1'], status: 'queued', created_by: 'test@example.com', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), sessions: [] },
      { id: 2, flag_key: 'feature-b', repositories: ['https://github.com/test/repo2'], status: 'in_progress', created_by: 'test@example.com', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), sessions: [] },
      { id: 3, flag_key: 'feature-c', repositories: ['https://github.com/test/repo3'], status: 'completed', created_by: 'test@example.com', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), sessions: [] },
      { id: 4, flag_key: 'feature-d', repositories: ['https://github.com/test/repo4'], status: 'failed', created_by: 'test@example.com', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), sessions: [] }
    ];
    
    await registerApiMocks(page, { removals: mockRemovals });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'History' }).click();
    
    await expect(page.getByText('feature-a')).toBeVisible();
    await expect(page.getByText('feature-b')).toBeVisible();
    await expect(page.getByText('feature-c')).toBeVisible();
    await expect(page.getByText('feature-d')).toBeVisible();
  });
  
  test('should display "waiting for user input" for blocked status', async ({ page }) => {
    const mockRemovals = [
      { id: 1, flag_key: 'feature-blocked', repositories: ['https://github.com/test/repo1'], status: 'blocked', created_by: 'test@example.com', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), sessions: [] }
    ];
    
    await registerApiMocks(page, { removals: mockRemovals });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'History' }).click();
    
    await expect(page.getByText('waiting for user input')).toBeVisible();
  });
  
  test('should display session details inline', async ({ page }) => {
    const mockRemovals = [
      {
        id: 1,
        flag_key: 'feature-a',
        repositories: ['https://github.com/test/repo1'],
        status: 'completed',
        created_by: 'test@example.com',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        sessions: [
          {
            id: 1,
            repository: 'https://github.com/test/repo1',
            devin_session_id: 's123',
            devin_session_url: 'https://app.devin.ai/sessions/s123',
            status: 'completed',
            pr_url: 'https://github.com/test/repo1/pull/1',
            structured_output: {
              references_found_initially: 10,
              references_removed: 8,
              references_remaining: 2,
              test_results: 'PASSED',
              test_command_run: 'npm test',
              code_path_preserved: 'enabled',
              warnings: ['Could not remove 2 references safely']
            },
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            error_message: null,
            acu_consumed: 450
          }
        ]
      }
    ];
    
    await registerApiMocks(page, { removals: mockRemovals });
    await page.goto('/');
    
    await page.getByRole('tab', { name: 'History' }).click();
    
    await expect(page.getByText('References: 10 found, 8 removed, 2 remaining')).toBeVisible();
    await expect(page.getByText('Test: PASSED')).toBeVisible();
    await expect(page.getByText('Could not remove 2 references safely')).toBeVisible();
    await expect(page.getByRole('link', { name: /github.com\/test\/repo1\/pull\/1/ })).toBeVisible();
  });
});

test.describe('Accessibility', () => {
  test('should have proper ARIA labels and roles', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/');
    
    await expect(page.getByRole('tab', { name: 'Repositories' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Flags' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'History' })).toBeVisible();
    
    await expect(page.getByRole('button', { name: 'Add Repository' })).toBeVisible();
  });
  
  test('should be keyboard navigable', async ({ page }) => {
    await registerApiMocks(page);
    await page.goto('/');
    
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    
    await page.keyboard.press('Enter');
  });
});
