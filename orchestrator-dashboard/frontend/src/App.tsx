import { useState } from 'react';
import { Dashboard } from './components/Dashboard';
import { CreateRemovalForm } from './components/CreateRemovalForm';
import { RequestDetail } from './components/RequestDetail';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './components/ui/tabs';
import { Toaster } from './components/ui/toaster';

function App() {
  const [selectedRequestId, setSelectedRequestId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleRequestCreated = () => {
    setActiveTab('dashboard');
    setRefreshTrigger(prev => prev + 1);
  };

  const handleRequestSelected = (id: number) => {
    setSelectedRequestId(id);
    setActiveTab('detail');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <h1 className="text-2xl font-bold text-gray-900">
            Feature Flag Removal Dashboard
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            Orchestrate Devin AI to remove stale feature flags from your codebase
          </p>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-6">
            <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
            <TabsTrigger value="create">Create Request</TabsTrigger>
            {selectedRequestId && (
              <TabsTrigger value="detail">Request Details</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="dashboard">
            <Dashboard
              onRequestSelected={handleRequestSelected}
              refreshTrigger={refreshTrigger}
            />
          </TabsContent>

          <TabsContent value="create">
            <CreateRemovalForm onSuccess={handleRequestCreated} />
          </TabsContent>

          {selectedRequestId && (
            <TabsContent value="detail">
              <RequestDetail requestId={selectedRequestId} />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <Toaster />
    </div>
  );
}

export default App;
