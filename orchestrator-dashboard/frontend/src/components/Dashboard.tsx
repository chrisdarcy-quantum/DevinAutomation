import { useEffect, useState } from 'react';
import { apiClient } from '../api';
import { RemovalRequest } from '../types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Loader2, RefreshCw } from 'lucide-react';
import { useToast } from '../hooks/use-toast';

interface DashboardProps {
  onRequestSelected: (id: number) => void;
  refreshTrigger: number;
}

export function Dashboard({ onRequestSelected, refreshTrigger }: DashboardProps) {
  const [requests, setRequests] = useState<RemovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const { toast } = useToast();

  const loadRequests = async () => {
    try {
      setLoading(true);
      const params = statusFilter !== 'all' ? { status: statusFilter } : {};
      const response = await apiClient.listRemovals(params);
      setRequests(response.results);
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to load requests',
        variant: 'destructive',
      });
      setRequests([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRequests();
  }, [statusFilter, refreshTrigger]);

  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      queued: 'secondary',
      in_progress: 'default',
      completed: 'outline',
      failed: 'destructive',
      partial: 'secondary',
    };
    return <Badge variant={variants[status] || 'default'}>{status}</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-4">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-48">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="queued">Queued</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="partial">Partial</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button onClick={loadRequests} variant="outline" size="sm">
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : requests.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-gray-500">No removal requests found</p>
            <p className="text-sm text-gray-400 mt-2">
              Create a new request to get started
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {requests.map((request) => (
            <Card
              key={request.id}
              className="cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => onRequestSelected(request.id)}
            >
              <CardHeader>
                <div className="flex justify-between items-start">
                  <div>
                    <CardTitle className="text-lg">{request.flag_key}</CardTitle>
                    <CardDescription className="mt-1">
                      {request.repositories.length} {request.repositories.length === 1 ? 'repository' : 'repositories'}
                      {request.feature_flag_provider && ` • ${request.feature_flag_provider}`}
                    </CardDescription>
                  </div>
                  {getStatusBadge(request.status)}
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Created by:</span>
                    <span className="ml-2 font-medium">{request.created_by}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Created:</span>
                    <span className="ml-2 font-medium">
                      {new Date(request.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Sessions:</span>
                    <span className="ml-2 font-medium">
                      {request.sessions.filter(s => s.status === 'finished').length} / {request.sessions.length} completed
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">ACU Consumed:</span>
                    <span className="ml-2 font-medium">{request.total_acu_consumed}</span>
                  </div>
                </div>
                {request.error_message && (
                  <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
                    <p className="text-sm text-red-800">{request.error_message}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
