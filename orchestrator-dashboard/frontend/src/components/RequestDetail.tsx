import { useEffect, useState } from 'react';
import { apiClient } from '../api';
import { RemovalRequest } from '../types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Loader2, ExternalLink, RefreshCw } from 'lucide-react';
import { useToast } from '../hooks/use-toast';
import { LogsView } from './LogsView';
import { Progress } from './ui/progress';

interface RequestDetailProps {
  requestId: number;
}

export function RequestDetail({ requestId }: RequestDetailProps) {
  const [request, setRequest] = useState<RemovalRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  const loadRequest = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getRemovalById(requestId);
      setRequest(data);
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to load request',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRequest();

    const eventSource = apiClient.createSSEConnection(requestId);

    eventSource.addEventListener('status_update', (event) => {
      const data = JSON.parse(event.data);
      setRequest(prev => prev ? { ...prev, ...data } : null);
    });

    eventSource.addEventListener('error', () => {
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [requestId]);

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      pending: 'secondary',
      claimed: 'secondary',
      working: 'default',
      blocked: 'secondary',
      finished: 'outline',
      expired: 'destructive',
      failed: 'destructive',
    };
    return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
  };

  const calculateProgress = () => {
    if (!request) return 0;
    const completed = request.sessions.filter(s => 
      s.status === 'finished' || s.status === 'failed' || s.status === 'expired'
    ).length;
    return (completed / request.sessions.length) * 100;
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!request) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-gray-500">Request not found</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">{request.flag_key}</h2>
          <p className="text-sm text-gray-600 mt-1">
            Request ID: {request.id} • Created by {request.created_by}
          </p>
        </div>
        <Button onClick={loadRequest} variant="outline" size="sm">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Overview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-sm text-gray-500">Status</span>
              <div className="mt-1">{getStatusBadge(request.status)}</div>
            </div>
            <div>
              <span className="text-sm text-gray-500">Feature Flag Provider</span>
              <p className="mt-1 font-medium">{request.feature_flag_provider || 'Not specified'}</p>
            </div>
            <div>
              <span className="text-sm text-gray-500">Created</span>
              <p className="mt-1 font-medium">{new Date(request.created_at).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-sm text-gray-500">Last Updated</span>
              <p className="mt-1 font-medium">{new Date(request.updated_at).toLocaleString()}</p>
            </div>
            <div>
              <span className="text-sm text-gray-500">Total ACU Consumed</span>
              <p className="mt-1 font-medium">{request.total_acu_consumed}</p>
            </div>
            <div>
              <span className="text-sm text-gray-500">Progress</span>
              <div className="mt-2">
                <Progress value={calculateProgress()} className="h-2" />
                <p className="text-xs text-gray-500 mt-1">
                  {request.sessions.filter(s => s.status === 'finished').length} / {request.sessions.length} completed
                </p>
              </div>
            </div>
          </div>

          {request.error_message && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm font-medium text-red-800">Error</p>
              <p className="text-sm text-red-700 mt-1">{request.error_message}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Devin Sessions</CardTitle>
          <CardDescription>
            One session per repository
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {request.sessions.map((session) => (
              <div
                key={session.id}
                className="p-4 border border-gray-200 rounded-lg hover:shadow-sm transition-shadow"
              >
                <div className="flex justify-between items-start mb-3">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">{session.repository_url}</p>
                    <p className="text-sm text-gray-500 mt-1">
                      Session ID: {session.devin_session_id || 'Pending'}
                    </p>
                  </div>
                  {getStatusBadge(session.status)}
                </div>

                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span className="text-gray-500">Created:</span>
                    <span className="ml-2">{new Date(session.created_at).toLocaleString()}</span>
                  </div>
                  {session.started_at && (
                    <div>
                      <span className="text-gray-500">Started:</span>
                      <span className="ml-2">{new Date(session.started_at).toLocaleString()}</span>
                    </div>
                  )}
                  {session.completed_at && (
                    <div>
                      <span className="text-gray-500">Completed:</span>
                      <span className="ml-2">{new Date(session.completed_at).toLocaleString()}</span>
                    </div>
                  )}
                  <div>
                    <span className="text-gray-500">ACU Consumed:</span>
                    <span className="ml-2">{session.acu_consumed}</span>
                  </div>
                </div>

                {session.devin_session_url && (
                  <div className="mt-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => window.open(session.devin_session_url!, '_blank')}
                    >
                      <ExternalLink className="w-4 h-4 mr-2" />
                      View Devin Session
                    </Button>
                  </div>
                )}

                {session.pr_url && (
                  <div className="mt-3">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => window.open(session.pr_url!, '_blank')}
                    >
                      <ExternalLink className="w-4 h-4 mr-2" />
                      View Pull Request
                    </Button>
                  </div>
                )}

                {session.error_message && (
                  <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-md">
                    <p className="text-sm text-red-800">{session.error_message}</p>
                  </div>
                )}

                {session.structured_output && (
                  <div className="mt-3 p-3 bg-gray-50 border border-gray-200 rounded-md">
                    <p className="text-xs font-medium text-gray-700 mb-2">Structured Output:</p>
                    <pre className="text-xs text-gray-600 overflow-x-auto">
                      {JSON.stringify(session.structured_output, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <LogsView requestId={requestId} />
    </div>
  );
}
