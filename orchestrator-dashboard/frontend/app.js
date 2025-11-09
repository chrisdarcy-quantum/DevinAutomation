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
  flagComparison: null,
  statusFilter: 'all',
  loading: false,
  eventSource: null,
  repositoryPollTimeout: null,
  selectedRepository: null
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

  async getFlagComparison(repositoryId) {
    return fetchJson(`${API_BASE_URL}/api/repositories/${repositoryId}/flag-comparison`);
  },

  async markRemovalMerged(id, mergedBy = null) {
    const params = mergedBy ? `?merged_by=${encodeURIComponent(mergedBy)}` : '';
    return fetchJson(`${API_BASE_URL}/api/removals/${id}/mark-merged${params}`, {
      method: 'POST'
    });
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

function getStatusDisplayTextWithSpinner(status) {
  const text = getStatusDisplayText(status);
  if (status === 'in_progress' || status === 'claimed' || status === 'working') {
    return `<span class="inline-block animate-spin mr-1">⟳</span> ${text}`;
  }
  return text;
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
  if (view !== 'repositories' && state.repositoryPollTimeout) {
    clearTimeout(state.repositoryPollTimeout);
    state.repositoryPollTimeout = null;
  }
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
    
    const hasActiveScans = repositories.some(r => r.current_scan);
    if (hasActiveScans && state.view === 'repositories') {
      if (state.repositoryPollTimeout) {
        clearTimeout(state.repositoryPollTimeout);
      }
      state.repositoryPollTimeout = setTimeout(() => loadRepositories(), 5000);
    } else if (state.repositoryPollTimeout) {
      clearTimeout(state.repositoryPollTimeout);
      state.repositoryPollTimeout = null;
    }
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
  const isScanning = repo.current_scan ? true : false;
  const scanButtonText = isScanning ? '<span class="inline-block animate-spin mr-1">⟳</span> Scanning...' : 'Scan';
  
  let scanStatus = 'Not scanned';
  let scanStatusBadge = '';
  let devinLink = '';
  
  if (repo.current_scan) {
    const statusText = getStatusDisplayText(repo.current_scan.status);
    scanStatus = `Scanning: ${statusText}`;
    scanStatusBadge = `<span class="badge ${getStatusBadgeClass(repo.current_scan.status)} text-xs ml-2">${statusText}</span>`;
    if (repo.current_scan.devin_session_url) {
      devinLink = `<div class="mt-2"><a href="${repo.current_scan.devin_session_url}" target="_blank" class="text-xs text-blue-600 hover:underline">Open Devin Session →</a></div>`;
    }
  } else if (repo.last_scanned_at) {
    if (repo.flag_count === 0) {
      scanStatus = 'Scanned - no flags found';
    } else {
      scanStatus = formatDate(repo.last_scanned_at);
    }
  }
  
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
        <div class="text-sm text-gray-600 mb-2">
          <div>Created: ${formatDate(repo.created_at)}</div>
          <div class="flex items-center">Last scan: ${scanStatus}${scanStatusBadge}</div>
        </div>
        ${devinLink}
        <div class="flex gap-2 mt-4">
          <button 
            class="btn btn-outline btn-sm ${isScanning ? 'opacity-50 cursor-not-allowed' : ''}" 
            onclick="handleScanRepository(${repo.id})"
            ${isScanning ? 'disabled' : ''}
          >
            ${scanButtonText}
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
  const repositoryName = state.selectedRepository ? state.selectedRepository.url : 'All Repositories';
  const scanStatus = state.selectedRepository && state.selectedRepository.last_scanned_at && state.flags.length === 0 
    ? '<p class="text-sm text-gray-500 mt-1">Scanned - no flags found</p>' 
    : '';
  
  const hasLaunchDarkly = state.selectedRepository && state.selectedRepository.provider_detected === 'LaunchDarkly';
  const comparison = state.flagComparison;
  
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <div>
          <h2 class="text-xl font-semibold text-gray-900">Discovered Flags</h2>
          <p class="text-sm text-gray-600 mt-1">Repository: ${repositoryName}</p>
          ${scanStatus}
          ${hasLaunchDarkly ? '<span class="badge badge-default text-xs ml-2">LaunchDarkly Connected</span>' : ''}
        </div>
        <button class="btn btn-outline" onclick="loadFlags()">
          Refresh
        </button>
      </div>

      ${hasLaunchDarkly && comparison ? `
        <div class="card bg-blue-50 border border-blue-200">
          <div class="p-4">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">LaunchDarkly Comparison</h3>
            <div class="grid grid-cols-3 gap-4 text-center">
              <div>
                <div class="text-2xl font-bold text-orange-600">${comparison.summary.flags_in_ld_only}</div>
                <div class="text-xs text-gray-600 mt-1">In LaunchDarkly Only</div>
                <div class="text-xs text-gray-500">(Potential stale flags)</div>
              </div>
              <div>
                <div class="text-2xl font-bold text-purple-600">${comparison.summary.flags_in_code_only}</div>
                <div class="text-xs text-gray-600 mt-1">In Code Only</div>
                <div class="text-xs text-gray-500">(Not in LaunchDarkly)</div>
              </div>
              <div>
                <div class="text-2xl font-bold text-green-600">${comparison.summary.flags_in_both}</div>
                <div class="text-xs text-gray-600 mt-1">In Both</div>
                <div class="text-xs text-gray-500">(Properly managed)</div>
              </div>
            </div>
          </div>
        </div>
      ` : ''}

      ${state.loading ? `
        <div class="flex justify-center items-center py-12">
          <div class="spinner"></div>
        </div>
      ` : state.flags.length === 0 && (!comparison || comparison.summary.total_ld_flags === 0) ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No flags discovered yet</p>
            <p class="text-sm text-gray-400 mt-2">${state.selectedRepository ? 'This repository has no feature flags' : 'Scan repositories to discover flags'}</p>
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
  
  const filteredRequests = state.statusFilter === 'all' 
    ? state.requests 
    : state.requests.filter(r => r.status === state.statusFilter);
  
  const requestsByRepo = {};
  filteredRequests.forEach(request => {
    const repoId = request.repository_id || 'legacy';
    if (!requestsByRepo[repoId]) {
      requestsByRepo[repoId] = [];
    }
    requestsByRepo[repoId].push(request);
  });
  
  return `
    <div class="space-y-6">
      <div class="flex justify-between items-center">
        <h2 class="text-xl font-semibold text-gray-900">Removed Flags</h2>
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
      ` : filteredRequests.length === 0 ? `
        <div class="card">
          <div class="py-12 text-center">
            <p class="text-gray-500">No removal requests found</p>
            <p class="text-sm text-gray-400 mt-2">Remove a flag to see history</p>
          </div>
        </div>
      ` : `
        <div class="grid gap-6">
          ${Object.entries(requestsByRepo).map(([repoId, requests]) => {
            const repo = repoId === 'legacy' ? null : state.repositories.find(r => r.id === parseInt(repoId));
            const repoName = repo ? repo.url : (requests[0].repositories ? requests[0].repositories.join(', ') : 'Unknown');
            
            return `
              <div class="card bg-gray-100">
                <div class="p-4">
                  <h3 class="text-lg font-semibold text-gray-900 mb-4">
                    Repository: ${repoName}
                  </h3>
                  <div class="grid gap-3">
                    ${requests.map(request => `
                      <div class="card bg-white">
                        ${renderRequestCard(request)}
                      </div>
                    `).join('')}
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `}
    </div>
  `;
}

function renderRequestCard(request) {
  const details = state.requestDetails?.[request.id];
  const sessions = details?.sessions || [];
  
  const devinLinks = sessions.map(s => s.devin_session_url).filter(Boolean);
  const prLinks = sessions.map(s => s.pr_url || s.structured_output?.pr_url).filter(Boolean);
  const hasPR = prLinks.length > 0;
  
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
          <div class="flex items-center gap-2">
            <span class="badge ${getStatusBadgeClass(request.status)}">${getStatusDisplayTextWithSpinner(request.status)}</span>
            ${request.merged_at ? (
              request.ld_archived_at ? 
                '<span class="badge badge-default text-xs">Merged ✅</span>' :
                request.ld_archive_error ?
                  '<span class="badge badge-secondary text-xs" title="' + request.ld_archive_error + '">Merged ✅ • LD failed</span>' :
                  '<span class="badge badge-secondary text-xs">Merged ✅</span>'
            ) : (
              (hasPR || request.status === 'completed') ?
                '<button class="btn btn-outline btn-sm" onclick="event.stopPropagation(); handleMarkMerged(' + request.id + ')" id="merge-btn-' + request.id + '" title="Mark as merged and archive in LaunchDarkly">Merged?</button>' :
                ''
            )}
          </div>
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
        ${devinLinks.length > 0 ? `
          <div class="mt-2">
            <span class="text-sm text-gray-500">Devin Sessions:</span>
            ${devinLinks.map(url => `
              <a href="${url}" target="_blank" class="ml-2 text-sm text-blue-600 hover:underline">
                View Session →
              </a>
            `).join('')}
          </div>
        ` : ''}
        ${prLinks.length > 0 ? `
          <div class="mt-2">
            <span class="text-sm text-gray-500">Pull Requests:</span>
            ${prLinks.map(url => `
              <a href="${url}" target="_blank" class="ml-2 text-sm text-blue-600 hover:underline break-all">
                ${url}
              </a>
            `).join('')}
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

          <div class="border-t border-gray-200 pt-4 mt-4">
            <label class="block text-sm font-medium text-gray-700 mb-3">
              LaunchDarkly Integration (optional)
            </label>
            
            <div class="space-y-3">
              <div>
                <label class="block text-xs text-gray-600 mb-1">
                  API Access Token
                </label>
                <input 
                  type="password" 
                  name="launchdarkly_api_token" 
                  class="input" 
                  placeholder="LaunchDarkly API token"
                />
              </div>

              <div>
                <label class="block text-xs text-gray-600 mb-1">
                  Project Key
                </label>
                <input 
                  type="text" 
                  name="launchdarkly_project_key" 
                  class="input" 
                  placeholder="default"
                />
              </div>

              <div>
                <label class="block text-xs text-gray-600 mb-1">
                  Environment Key (optional)
                </label>
                <input 
                  type="text" 
                  name="launchdarkly_environment_key" 
                  class="input" 
                  placeholder="production"
                />
              </div>
            </div>
            <p class="text-xs text-gray-500 mt-2">Connect to LaunchDarkly to compare flags with your codebase</p>
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
    github_token: formData.get('github_token') || null,
    launchdarkly_api_token: formData.get('launchdarkly_api_token') || null,
    launchdarkly_project_key: formData.get('launchdarkly_project_key') || null,
    launchdarkly_environment_key: formData.get('launchdarkly_environment_key') || null
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
    loadRepositories();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

async function handleViewFlags(repositoryId) {
  try {
    const repository = state.repositories.find(r => r.id === repositoryId);
    const flags = await api.listFlags({ repository_id: repositoryId });
    
    let comparison = null;
    if (repository && repository.provider_detected === 'LaunchDarkly') {
      try {
        comparison = await api.getFlagComparison(repositoryId);
      } catch (e) {
        console.error('Failed to load flag comparison:', e);
      }
    }
    
    setState({ flags, view: 'flags', selectedRepository: repository, flagComparison: comparison });
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




async function handleMarkMerged(removalId) {
  const button = document.getElementById(`merge-btn-${removalId}`);
  if (button) {
    button.disabled = true;
    button.innerHTML = '<span class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></span>';
  }
  
  try {
    const result = await api.markRemovalMerged(removalId);
    
    if (result.ld_archived) {
      showToast('Flag marked as merged and archived in LaunchDarkly');
    } else if (result.ld_archive_error) {
      showToast('Flag marked as merged, but LaunchDarkly update failed. You can retry.', 'error');
    } else {
      showToast('Flag marked as merged');
    }
    
    loadRequests();
  } catch (error) {
    showToast(error.message, 'error');
    if (button) {
      button.disabled = false;
      button.innerHTML = 'Merged?';
    }
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
        <div class="tab ${state.view === 'history' ? 'active' : ''}" onclick="navigate('history'); loadRequests();">
          Removed Flags
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
