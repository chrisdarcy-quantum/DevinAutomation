import { CreateRemovalRequestPayload, ListRemovalsResponse, RemovalRequest, SessionLog } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class APIClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  async createRemovalRequest(payload: CreateRemovalRequestPayload): Promise<RemovalRequest> {
    const response = await fetch(`${this.baseUrl}/api/removals`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to create removal request');
    }

    return response.json();
  }

  async listRemovals(params?: {
    status?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListRemovalsResponse> {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append('status', params.status);
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    if (params?.offset) queryParams.append('offset', params.offset.toString());

    const url = `${this.baseUrl}/api/removals${queryParams.toString() ? `?${queryParams}` : ''}`;
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error('Failed to fetch removal requests');
    }

    return response.json();
  }

  async getRemovalById(id: number): Promise<RemovalRequest> {
    const response = await fetch(`${this.baseUrl}/api/removals/${id}`);

    if (!response.ok) {
      throw new Error('Failed to fetch removal request');
    }

    return response.json();
  }

  async getRemovalLogs(id: number): Promise<SessionLog[]> {
    const response = await fetch(`${this.baseUrl}/api/removals/${id}/logs`);

    if (!response.ok) {
      throw new Error('Failed to fetch logs');
    }

    return response.json();
  }

  createSSEConnection(id: number): EventSource {
    return new EventSource(`${this.baseUrl}/api/removals/${id}/stream`);
  }
}

export const apiClient = new APIClient();
