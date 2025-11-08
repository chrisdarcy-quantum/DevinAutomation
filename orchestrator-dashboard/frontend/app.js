/**
 * Feature Flag Removal Dashboard - Vanilla JavaScript
 * Single-file frontend application with hash-based routing and SSE support
 */


const API_BASE_URL = 'http://localhost:8000';


const state = {
  view: 'dashboard',
  requests: [],
  requestDetails: {},
  statusFilter: 'all',
  loading: false,
  eventSource: null
};

function setState(updates) {
  Object.assign(state, updates);
  render();
}


const api = {
  async listRemovals(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = `${API_BASE_URL}/api/removals${queryString ? '?' + queryString : ''}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to load requests');
    return response.json();
  },

  async getRemoval(id) {
    const response = await fetch(`${API_BASE_URL}/api/removals/${id}`);
    if (!response.ok) throw new Error('Failed to load request details');
    return response.json();
  },

  async createRemoval(data) {
    const response = await fetch(`${API_BASE_URL}/api/removals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create request');
    }
    return response.json();
  },

  streamStatus(id, onUpdate) {
    if (state.eventSource) {
      state.eventSource.close();
    }
    
    const eventSource = new EventSource(`${API_BASE_URL}/api/removals/${id}/stream`);
    
    eventSource.addEventListener('status_update', (e) => {
      const data = JSON.parse(e.data);
      onUpdate(data);
    });
    
    eventSource.addEventListener('complete', () => {
      eventSource.close();
      state.eventSource = null;
    });
    
    eventSource.addEventListener('error', () => {
      eventSource.close();
      state.eventSource = null;
    });
    
    state.eventSource = eventSource;
    return eventSource;
  }
};


function formatDate(dateString) {
  return new Date(dateString).toLocaleString();
}

function getStatusBadgeClass(status) {
  const classes = {
    queued: 'badge-secondary',
    in_progress: 'badge-default',
    completed: 'badge-outline',
    failed: 'badge-destructive',
    partial: 'badge-secondary'
  };
  return classes[status] || 'badge-default';
}

function getStatusDisplayText(status) {
  return status === 'blocked' ? 'waiting for user input' : status;
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <div class="font-semibold">${type === 'error' ? 'Error' : 'Success'}</div>
    <div class="text-sm text-gray-600 mt-1">${message}</div>
  `;
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.remove();
  }, 5000);
}


function navigate(view, data = {}) {
  window.location.hash = view;
  setState({ view, ...data });
}

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.slice(1) || 'dashboard';
  if (hash !== state.view) {
    setState({ view: hash });
  }
});


async function loadRequests() {
  try {
    setState({ loading: true });
    const params = state.statusFilter !== 'all' ? { status: state.statusFilter } : {};
    const response = await api.listRemovals(params);
    setState({ requests: response.results, loading: false });
    
    for (const request of response.results) {
      try {
        const details = await api.getRemoval(request.id);
        state.requestDetails[request.id] = details;
        render();
      } catch (err) {
        console.error(`Failed to load details for request ${request.id}:`, err);
      }
    }
  } catch (error) {
    showToast(error.message, 'error');
    setState({ requests: [], loading: false });
  }
}

function renderDashboard() {
  const filterOptions = ['all', 'queued', 'in_progress', 'completed', 'failed', 'partial'];
  
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-4">
          <select 
            class="select w-48" 
            onchange="handleFilterChange(event)"
            value="${state.statusFilter}"
          >
            ${filterOptions.map(opt => `
              <option value="${opt}" ${state.statusFilter === opt ? 'selected' : ''}>
                ${opt === 'all' ? 'All Statuses' : opt.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </option>
            `).join('')}
          </select>
        </div>
        <button class="btn btn-outline" onclick="loadRequests()">
          <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      ${state.loading ? `
        <div class="flex justify-center items-center py-12">
          <div class="spinner"></div>
        </div>
      ` : state.requests.length === 0 ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No removal requests found</p>
            <p class="text-sm text-gray-400 mt-2">Create a new request to get started</p>
          </div>
        </div>
      ` : `
        <div class="grid gap-4">
          ${state.requests.map(request => renderRequestCard(request)).join('')}
        </div>
      `}
    </div>
  `;
}

function renderRequestCard(request) {
  const details = state.requestDetails?.[request.id];
  const sessions = details?.sessions || [];
  
  return `
    <div class="card">
      <div class="p-6">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h3 class="text-lg font-semibold text-gray-900">${request.flag_key}</h3>
            <p class="text-sm text-gray-600 mt-1">
              ${Array.isArray(request.repositories) ? request.repositories.length : 0} 
              ${(Array.isArray(request.repositories) ? request.repositories.length : 0) === 1 ? 'repository' : 'repositories'}
              ${request.feature_flag_provider ? ` • ${request.feature_flag_provider}` : ''}
              ${request.preserve_mode ? ` • Preserve: ${request.preserve_mode}` : ''}
            </p>
          </div>
          <span class="badge ${getStatusBadgeClass(request.status)}">${getStatusDisplayText(request.status)}</span>
        </div>
        <div class="grid grid-cols-2 gap-4 text-sm mb-4">
          <div>
            <span class="text-gray-500">Created by:</span>
            <span class="ml-2 font-medium">${request.created_by}</span>
          </div>
          <div>
            <span class="text-gray-500">Created:</span>
            <span class="ml-2 font-medium">${formatDate(request.created_at)}</span>
          </div>
          <div>
            <span class="text-gray-500">Sessions:</span>
            <span class="ml-2 font-medium">
              ${request.completed_sessions ?? 0} / ${request.session_count ?? 0} completed
            </span>
          </div>
          <div>
            <span class="text-gray-500">ACU (est.):</span>
            <span class="ml-2 font-medium">${details?.total_acu_consumed || request.total_acu_consumed || 0}</span>
          </div>
        </div>
        ${request.error_message ? `
          <div class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
            <p class="text-sm text-red-800">${request.error_message}</p>
          </div>
        ` : ''}
        ${sessions.length > 0 ? `
          <div class="mt-4 pt-4 border-t border-gray-200">
            <h4 class="text-sm font-semibold text-gray-700 mb-3">Sessions</h4>
            <div class="space-y-3">
              ${sessions.map(session => `
                <div class="border border-gray-200 rounded-lg p-3 bg-gray-50">
                  <div class="flex justify-between items-start mb-2">
                    <div class="flex-1">
                      <p class="text-sm font-medium text-gray-900">${session.repository}</p>
                      ${session.devin_session_url ? `
                        <a href="${session.devin_session_url}" target="_blank" class="text-xs text-blue-600 hover:underline">
                          View Devin Session →
                        </a>
                      ` : ''}
                    </div>
                    <span class="badge ${getStatusBadgeClass(session.status)} text-xs">${getStatusDisplayText(session.status)}</span>
                  </div>
                  <div class="grid grid-cols-2 gap-2 text-xs">
                    ${session.started_at ? `
                      <div>
                        <span class="text-gray-500">Started:</span>
                        <span class="ml-1">${formatDate(session.started_at)}</span>
                      </div>
                    ` : ''}
                    ${session.completed_at ? `
                      <div>
                        <span class="text-gray-500">Completed:</span>
                        <span class="ml-1">${formatDate(session.completed_at)}</span>
                      </div>
                    ` : ''}
                    ${session.acu_consumed ? `
                      <div>
                        <span class="text-gray-500">ACU:</span>
                        <span class="ml-1">${session.acu_consumed}</span>
                      </div>
                    ` : ''}
                    ${session.pr_url || session.structured_output?.pr_url ? `
                      <div class="col-span-2">
                        <span class="text-gray-500">PR:</span>
                        <a href="${session.pr_url || session.structured_output?.pr_url}" target="_blank" class="ml-1 text-blue-600 hover:underline break-all">
                          ${session.pr_url || session.structured_output?.pr_url}
                        </a>
                      </div>
                    ` : session.structured_output?.pr_url === null && session.structured_output?.warnings?.length > 0 ? `
                      <div class="col-span-2 text-orange-600">
                        <span class="text-gray-500">PR:</span>
                        <span class="ml-1">No PR created (see warnings below)</span>
                      </div>
                    ` : ''}
                  </div>
                  ${session.error_message ? `
                    <div class="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                      ${session.error_message}
                    </div>
                  ` : ''}
                  ${session.structured_output ? `
                    <div class="mt-2 pt-2 border-t border-gray-300">
                      ${session.structured_output.warnings?.length > 0 ? `
                        <div class="mb-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs">
                          <div class="font-semibold text-yellow-800 mb-1">⚠️ Warnings:</div>
                          <ul class="list-disc list-inside text-yellow-800 space-y-1">
                            ${session.structured_output.warnings.map(w => `<li>${w}</li>`).join('')}
                          </ul>
                        </div>
                      ` : ''}
                      ${session.structured_output.references_found_initially !== undefined || session.structured_output.references_removed !== undefined || session.structured_output.references_remaining !== undefined ? `
                        <div class="grid grid-cols-3 gap-2 text-xs mb-2">
                          ${session.structured_output.references_found_initially !== undefined ? `
                            <div>
                              <span class="text-gray-500">Found:</span>
                              <span class="ml-1">${session.structured_output.references_found_initially}</span>
                            </div>
                          ` : ''}
                          ${session.structured_output.references_removed !== undefined ? `
                            <div>
                              <span class="text-gray-500">Removed:</span>
                              <span class="ml-1">${session.structured_output.references_removed}</span>
                            </div>
                          ` : ''}
                          ${session.structured_output.references_remaining !== undefined ? `
                            <div class="${session.structured_output.references_remaining > 0 ? 'text-orange-600 font-semibold' : ''}">
                              <span class="text-gray-500">Remaining:</span>
                              <span class="ml-1">${session.structured_output.references_remaining}</span>
                            </div>
                          ` : ''}
                        </div>
                      ` : ''}
                      ${session.structured_output.test_command_run || session.structured_output.test_results ? `
                        <div class="text-xs mb-2">
                          ${session.structured_output.test_command_run ? `
                            <div>
                              <span class="text-gray-500">Test command:</span>
                              <code class="ml-1 bg-gray-100 px-1 rounded">${session.structured_output.test_command_run}</code>
                            </div>
                          ` : ''}
                          ${session.structured_output.test_results ? `
                            <div>
                              <span class="text-gray-500">Test results:</span>
                              <span class="ml-1">${session.structured_output.test_results}</span>
                            </div>
                          ` : ''}
                        </div>
                      ` : ''}
                    </div>
                  ` : ''}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}


function renderCreateForm() {
  return `
    <div class="card max-w-2xl mx-auto">
      <div class="p-6">
        <h2 class="text-xl font-semibold text-gray-900 mb-6">Create Removal Request</h2>
        <form onsubmit="handleCreateSubmit(event)" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Flag Key <span class="text-red-500">*</span>
            </label>
            <input 
              type="text" 
              name="flag_key" 
              class="input" 
              placeholder="ENABLE_NEW_FEATURE"
              required
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Repositories <span class="text-red-500">*</span>
            </label>
            <textarea 
              name="repositories" 
              class="input" 
              rows="3"
              placeholder="https://github.com/example/repo1&#10;https://github.com/example/repo2"
              required
            ></textarea>
            <p class="text-xs text-gray-500 mt-1">One repository URL per line (max 5)</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Feature Flag Provider
            </label>
            <input 
              type="text" 
              name="feature_flag_provider" 
              class="input" 
              placeholder="LaunchDarkly, Unleash, etc."
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Code Path to Preserve <span class="text-red-500">*</span>
            </label>
            <div class="flex gap-6">
              <label class="flex items-center cursor-pointer">
                <input 
                  type="radio" 
                  name="preserve_mode" 
                  value="enabled" 
                  checked
                  class="mr-2"
                />
                <span class="text-sm text-gray-700">Preserve "enabled" code path</span>
              </label>
              <label class="flex items-center cursor-pointer">
                <input 
                  type="radio" 
                  name="preserve_mode" 
                  value="disabled"
                  class="mr-2"
                />
                <span class="text-sm text-gray-700">Preserve "disabled" code path</span>
              </label>
            </div>
            <p class="text-xs text-gray-500 mt-1">Choose which code path to keep when removing the flag</p>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Created By <span class="text-red-500">*</span>
            </label>
            <input 
              type="email" 
              name="created_by" 
              class="input" 
              placeholder="your.email@example.com"
              required
            />
          </div>

          <div class="flex gap-3 pt-4">
            <button type="submit" class="btn btn-primary flex-1">
              Create Request
            </button>
            <button type="button" class="btn btn-outline" onclick="navigate('dashboard')">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  `;
}




function handleFilterChange(event) {
  setState({ statusFilter: event.target.value });
  loadRequests();
}


async function handleCreateSubmit(event) {
  event.preventDefault();
  
  const formData = new FormData(event.target);
  const repositories = formData.get('repositories')
    .split('\n')
    .map(r => r.trim())
    .filter(r => r.length > 0);

  if (repositories.length === 0) {
    showToast('Please enter at least one repository', 'error');
    return;
  }

  if (repositories.length > 5) {
    showToast('Maximum 5 repositories per request', 'error');
    return;
  }

  const data = {
    flag_key: formData.get('flag_key'),
    repositories: repositories,
    feature_flag_provider: formData.get('feature_flag_provider') || null,
    preserve_mode: formData.get('preserve_mode') || 'enabled',
    created_by: formData.get('created_by')
  };

  try {
    await api.createRemoval(data);
    showToast('Removal request created successfully');
    navigate('dashboard');
    loadRequests();
  } catch (error) {
    showToast(error.message, 'error');
  }
}


function render() {
  const app = document.getElementById('app');
  
  const header = `
    <header class="bg-white border-b border-gray-200 shadow-sm">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <h1 class="text-2xl font-bold text-gray-900">
          Feature Flag Removal Dashboard
        </h1>
        <p class="text-sm text-gray-600 mt-1">
          Orchestrate Devin AI to remove stale feature flags from your codebase
        </p>
      </div>
    </header>
  `;

  const tabs = `
    <div class="border-b border-gray-200 mb-6">
      <div class="flex gap-4">
        <div class="tab ${state.view === 'dashboard' ? 'active' : ''}" onclick="navigate('dashboard'); loadRequests();">
          Dashboard
        </div>
        <div class="tab ${state.view === 'create' ? 'active' : ''}" onclick="navigate('create')">
          Create Request
        </div>
      </div>
    </div>
  `;

  let content = '';
  if (state.view === 'dashboard') {
    content = renderDashboard();
  } else if (state.view === 'create') {
    content = renderCreateForm();
  }

  app.innerHTML = `
    ${header}
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      ${tabs}
      ${content}
    </main>
  `;
}


document.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash.slice(1) || 'dashboard';
  state.view = hash;
  
  if (hash === 'dashboard') {
    loadRequests();
  }
  
  render();
});

window.addEventListener('beforeunload', () => {
  if (state.eventSource) {
    state.eventSource.close();
  }
});
