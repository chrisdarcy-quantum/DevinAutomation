import { useEffect, useState } from 'react';
import { apiClient } from '../api';
import { SessionLog } from '../types';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Loader2 } from 'lucide-react';
import { useToast } from '../hooks/use-toast';
import { ScrollArea } from './ui/scroll-area';

interface LogsViewProps {
  requestId: number;
}

export function LogsView({ requestId }: LogsViewProps) {
  const [logs, setLogs] = useState<SessionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    const loadLogs = async () => {
      try {
        setLoading(true);
        const data = await apiClient.getRemovalLogs(requestId);
        setLogs(data);
      } catch (error) {
        toast({
          title: 'Error',
          description: error instanceof Error ? error.message : 'Failed to load logs',
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    };

    loadLogs();
    const interval = setInterval(loadLogs, 5000);

    return () => clearInterval(interval);
  }, [requestId]);

  const getLogLevelBadge = (level: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive'> = {
      info: 'default',
      warning: 'secondary',
      error: 'destructive',
    };
    return <Badge variant={variants[level] || 'default'} className="text-xs">{level}</Badge>;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Session Logs</CardTitle>
      </CardHeader>
      <CardContent>
        {loading && logs.length === 0 ? (
          <div className="flex justify-center items-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : logs.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-8">No logs available</p>
        ) : (
          <ScrollArea className="h-96">
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="p-3 border border-gray-200 rounded-md hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <span className="text-xs text-gray-500">
                      {new Date(log.timestamp).toLocaleString()}
                    </span>
                    {getLogLevelBadge(log.log_level)}
                  </div>
                  <p className="text-sm text-gray-900">{log.message}</p>
                  {log.metadata && Object.keys(log.metadata).length > 0 && (
                    <div className="mt-2 p-2 bg-gray-50 rounded text-xs">
                      <pre className="text-gray-600 overflow-x-auto">
                        {JSON.stringify(log.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
