export interface RemovalRequest {
  id: number;
  flag_key: string;
  repositories: string[];
  feature_flag_provider: string | null;
  status: 'queued' | 'in_progress' | 'completed' | 'failed' | 'partial';
  created_by: string;
  created_at: string;
  updated_at: string;
  error_message: string | null;
  total_acu_consumed: number;
  sessions: DevinSession[];
}

export interface DevinSession {
  id: number;
  removal_request_id: number;
  repository_url: string;
  devin_session_id: string | null;
  devin_session_url: string | null;
  status: 'pending' | 'claimed' | 'working' | 'blocked' | 'finished' | 'expired' | 'failed';
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  pr_url: string | null;
  acu_consumed: number;
  structured_output: Record<string, any> | null;
}

export interface SessionLog {
  id: number;
  session_id: number;
  timestamp: string;
  log_level: 'info' | 'warning' | 'error';
  message: string;
  metadata: Record<string, any> | null;
}

export interface CreateRemovalRequestPayload {
  flag_key: string;
  repositories: string[];
  feature_flag_provider?: string;
  created_by: string;
}

export interface ListRemovalsResponse {
  results: RemovalRequest[];
  total: number;
  limit: number;
  offset: number;
}
