/**
 * Feature Flag Removal Dashboard - Vanilla JavaScript
 * Single-file frontend application with hash-based routing and SSE support
 */


const API_BASE_URL = 'http://localhost:8000';


const state = {
  view: 'repositories',
  requests: [],
  requestDetails: {},
  repositories: [],
  flags: [],
  statusFilter: 'all',
  loading: false,
  eventSource: null
};

function setState(updates) {
  Object.assign(state, updates);
  render();
}


async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    if (options.errorMessage) throw new Error(options.errorMessage);
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Request failed');
  }
  return response.status === 204 ? null : response.json();
}

const api = {
  async listRemovals(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return fetchJson(`${API_BASE_URL}/api/removals${queryString ? '?' + queryString : ''}`);
  },

  async getRemoval(id) {
    return fetchJson(`${API_BASE_URL}/api/removals/${id}`);
  },

  async createRemoval(data) {
    return fetchJson(`${API_BASE_URL}/api/removals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
  },

  async listRepositories() {
    return fetchJson(`${API_BASE_URL}/api/repositories`);
  },

  async createRepository(data) {
    return fetchJson(`${API_BASE_URL}/api/repositories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
  },

  async deleteRepository(id) {
    return fetchJson(`${API_BASE_URL}/api/repositories/${id}`, { method: 'DELETE' });
  },

  async scanRepository(id) {
    return fetchJson(`${API_BASE_URL}/api/repositories/${id}/scan`, { method: 'POST' });
  },

  async listFlags(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    return fetchJson(`${API_BASE_URL}/api/flags${queryString ? '?' + queryString : ''}`);
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
  const hash = window.location.hash.slice(1) || 'repositories';
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

async function loadRepositories() {
  try {
    setState({ loading: true });
    const repositories = await api.listRepositories();
    setState({ repositories, loading: false });
  } catch (error) {
    showToast(error.message, 'error');
    setState({ repositories: [], loading: false });
  }
}

async function loadFlags() {
  try {
    setState({ loading: true });
    const flags = await api.listFlags();
    setState({ flags, loading: false });
  } catch (error) {
    showToast(error.message, 'error');
    setState({ flags: [], loading: false });
  }
}

function renderRepositories() {
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <h2 class="text-xl font-semibold text-gray-900">Repositories</h2>
        <button class="btn btn-primary" onclick="showAddRepositoryModal()">
          Add Repository
        </button>
      </div>

      ${state.loading ? `
        <div class="flex justify-center items-center py-12">
          <div class="spinner"></div>
        </div>
      ` : state.repositories.length === 0 ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No repositories registered</p>
            <p class="text-sm text-gray-400 mt-2">Add a repository to start discovering flags</p>
          </div>
        </div>
      ` : `
        <div class="grid gap-4 md:grid-cols-2">
          ${state.repositories.map(repo => renderRepositoryCard(repo)).join('')}
        </div>
      `}
    </div>
  `;
}

function renderRepositoryCard(repo) {
  return `
    <div class="card">
      <div class="p-6">
        <div class="flex justify-between items-start mb-4">
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-gray-900 break-all">${repo.url}</h3>
            <p class="text-sm text-gray-600 mt-1">
              ${repo.provider_detected ? `Provider: ${repo.provider_detected}` : 'Provider: Not detected'}
              ${repo.flag_count ? ` • ${repo.flag_count} flags` : ''}
            </p>
          </div>
        </div>
        <div class="text-sm text-gray-600 mb-4">
          <div>Created: ${formatDate(repo.created_at)}</div>
          ${repo.last_scanned_at ? `<div>Last scan: ${formatDate(repo.last_scanned_at)}</div>` : '<div>Not scanned yet</div>'}
        </div>
        <div class="flex gap-2">
          <button class="btn btn-outline btn-sm" onclick="handleScanRepository(${repo.id})">
            Scan
          </button>
          <button class="btn btn-outline btn-sm" onclick="handleViewFlags(${repo.id})">
            View Flags
          </button>
          <button class="btn btn-outline btn-sm text-red-600" onclick="handleDeleteRepository(${repo.id})">
            Delete
          </button>
        </div>
      </div>
    </div>
  `;
}

function renderFlags() {
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <h2 class="text-xl font-semibold text-gray-900">Discovered Flags</h2>
        <button class="btn btn-outline" onclick="loadFlags()">
          Refresh
        </button>
      </div>

      ${state.loading ? `
        <div class="flex justify-center items-center py-12">
          <div class="spinner"></div>
        </div>
      ` : state.flags.length === 0 ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No flags discovered yet</p>
            <p class="text-sm text-gray-400 mt-2">Scan repositories to discover flags</p>
          </div>
        </div>
      ` : `
        <div class="card">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Flag Key</th>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Repository</th>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Provider</th>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Occurrences</th>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Seen</th>
                  <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                ${state.flags.map(flag => `
                  <tr>
                    <td class="px-6 py-4 text-sm font-medium text-gray-900">${flag.flag_key}</td>
                    <td class="px-6 py-4 text-sm text-gray-600 break-all">${flag.repository_url || 'N/A'}</td>
                    <td class="px-6 py-4 text-sm text-gray-600">${flag.provider || 'Unknown'}</td>
                    <td class="px-6 py-4 text-sm text-gray-600">${flag.occurrences}</td>
                    <td class="px-6 py-4 text-sm text-gray-600">${formatDate(flag.last_seen_at)}</td>
                    <td class="px-6 py-4 text-sm">
                      <button class="btn btn-outline btn-sm" onclick="handleRemoveFlag(${flag.repository_id}, '${flag.flag_key}', '${flag.provider || ''}')">
                        Remove
                      </button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `}
    </div>
  `;
}

function renderHistory() {
  const filterOptions = ['all', 'queued', 'in_progress', 'completed', 'failed', 'partial'];
  
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <h2 class="text-xl font-semibold text-gray-900">Removal History</h2>
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
          <button class="btn btn-outline" onclick="loadRequests()">
            Refresh
          </button>
        </div>
      </div>

      ${state.loading ? `
        <div class="flex justify-center items-center py-12">
          <div class="spinner"></div>
        </div>
      ` : state.requests.length === 0 ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No removal requests found</p>
            <p class="text-sm text-gray-400 mt-2">Remove a flag to see history</p>
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
                    ${session.pr_url ? `
                      <div class="col-span-2">
                        <span class="text-gray-500">PR:</span>
                        <a href="${session.pr_url}" target="_blank" class="ml-1 text-blue-600 hover:underline break-all">
                          ${session.pr_url}
                        </a>
                      </div>
                    ` : ''}
                  </div>
                  ${session.error_message ? `
                    <div class="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                      ${session.error_message}
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


function showAddRepositoryModal() {
  const modal = document.createElement('div');
  modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
  modal.innerHTML = `
    <div class="card max-w-lg mx-4" onclick="event.stopPropagation()">
      <div class="p-6">
        <h2 class="text-xl font-semibold text-gray-900 mb-6">Add Repository</h2>
        <form onsubmit="handleAddRepository(event)" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Repository URL <span class="text-red-500">*</span>
            </label>
            <input 
              type="text" 
              name="url" 
              class="input" 
              placeholder="https://github.com/example/repo"
              required
            />
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              GitHub Token (optional)
            </label>
            <input 
              type="password" 
              name="github_token" 
              class="input" 
              placeholder="For private repositories"
            />
            <p class="text-xs text-gray-500 mt-1">Only needed for private repositories</p>
          </div>

          <div class="flex gap-3 pt-4">
            <button type="submit" class="btn btn-primary flex-1">
              Add & Scan
            </button>
            <button type="button" class="btn btn-outline" onclick="this.closest('.fixed').remove()">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  `;
  modal.onclick = () => modal.remove();
  document.body.appendChild(modal);
}

async function handleAddRepository(event) {
  event.preventDefault();
  const formData = new FormData(event.target);
  const data = {
    url: formData.get('url'),
    github_token: formData.get('github_token') || null
  };

  try {
    const repo = await api.createRepository(data);
    showToast('Repository added successfully');
    event.target.closest('.fixed').remove();
    
    showToast('Starting flag discovery scan...');
    await api.scanRepository(repo.id);
    
    loadRepositories();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function handleScanRepository(id) {
  try {
    await api.scanRepository(id);
    showToast('Scan started - this may take a few minutes');
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function handleViewFlags(repositoryId) {
  try {
    const flags = await api.listFlags({ repository_id: repositoryId });
    setState({ flags, view: 'flags' });
    window.location.hash = 'flags';
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function handleDeleteRepository(id) {
  if (!confirm('Are you sure you want to delete this repository? All discovered flags will be removed.')) {
    return;
  }

  try {
    await api.deleteRepository(id);
    showToast('Repository deleted');
    loadRepositories();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function handleRemoveFlag(repositoryId, flagKey, provider) {
  const modal = document.createElement('div');
  modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
  modal.innerHTML = `
    <div class="card max-w-lg mx-4" onclick="event.stopPropagation()">
      <div class="p-6">
        <h2 class="text-xl font-semibold text-gray-900 mb-6">Remove Flag</h2>
        <form onsubmit="handleRemoveFlagSubmit(event, ${repositoryId}, '${flagKey}', '${provider}')" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Flag Key
            </label>
            <input 
              type="text" 
              value="${flagKey}" 
              class="input bg-gray-100" 
              readonly
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
              Remove Flag
            </button>
            <button type="button" class="btn btn-outline" onclick="this.closest('.fixed').remove()">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  `;
  modal.onclick = () => modal.remove();
  document.body.appendChild(modal);
}

async function handleRemoveFlagSubmit(event, repositoryId, flagKey, provider) {
  event.preventDefault();
  const formData = new FormData(event.target);
  
  const data = {
    flag_key: flagKey,
    repository_id: repositoryId,
    feature_flag_provider: provider || null,
    preserve_mode: formData.get('preserve_mode') || 'enabled',
    created_by: formData.get('created_by')
  };

  try {
    await api.createRemoval(data);
    showToast('Removal request created successfully');
    event.target.closest('.fixed').remove();
    navigate('history');
    loadRequests();
  } catch (error) {
    showToast(error.message, 'error');
  }
}




function handleFilterChange(event) {
  setState({ statusFilter: event.target.value });
  loadRequests();
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
        <div class="tab ${state.view === 'repositories' ? 'active' : ''}" onclick="navigate('repositories'); loadRepositories();">
          Repositories
        </div>
        <div class="tab ${state.view === 'flags' ? 'active' : ''}" onclick="navigate('flags'); loadFlags();">
          Flags
        </div>
        <div class="tab ${state.view === 'history' ? 'active' : ''}" onclick="navigate('history'); loadRequests();">
          History
        </div>
      </div>
    </div>
  `;

  let content = '';
  if (state.view === 'repositories') {
    content = renderRepositories();
  } else if (state.view === 'flags') {
    content = renderFlags();
  } else if (state.view === 'history') {
    content = renderHistory();
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
  const hash = window.location.hash.slice(1) || 'repositories';
  state.view = hash;
  
  if (hash === 'repositories') {
    loadRepositories();
  } else if (hash === 'flags') {
    loadFlags();
  } else if (hash === 'history') {
    loadRequests();
  }
  
  render();
});

window.addEventListener('beforeunload', () => {
  if (state.eventSource) {
    state.eventSource.close();
  }
});
