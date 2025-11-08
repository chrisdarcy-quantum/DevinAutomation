import { useState } from 'react';
import { apiClient } from '../api';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Textarea } from './ui/textarea';
import { Loader2, Plus, X } from 'lucide-react';
import { useToast } from '../hooks/use-toast';

interface CreateRemovalFormProps {
  onSuccess: () => void;
}

export function CreateRemovalForm({ onSuccess }: CreateRemovalFormProps) {
  const [flagKey, setFlagKey] = useState('');
  const [repositories, setRepositories] = useState<string[]>(['']);
  const [provider, setProvider] = useState('');
  const [createdBy, setCreatedBy] = useState('');
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleAddRepository = () => {
    setRepositories([...repositories, '']);
  };

  const handleRemoveRepository = (index: number) => {
    setRepositories(repositories.filter((_, i) => i !== index));
  };

  const handleRepositoryChange = (index: number, value: string) => {
    const newRepos = [...repositories];
    newRepos[index] = value;
    setRepositories(newRepos);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validRepos = repositories.filter(r => r.trim() !== '');
    
    if (!flagKey.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Flag key is required',
        variant: 'destructive',
      });
      return;
    }

    if (validRepos.length === 0) {
      toast({
        title: 'Validation Error',
        description: 'At least one repository is required',
        variant: 'destructive',
      });
      return;
    }

    if (!createdBy.trim()) {
      toast({
        title: 'Validation Error',
        description: 'Created by is required',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      await apiClient.createRemovalRequest({
        flag_key: flagKey.trim(),
        repositories: validRepos,
        feature_flag_provider: provider.trim() || undefined,
        created_by: createdBy.trim(),
      });

      toast({
        title: 'Success',
        description: 'Removal request created successfully',
      });

      setFlagKey('');
      setRepositories(['']);
      setProvider('');
      setCreatedBy('');
      onSuccess();
    } catch (error) {
      toast({
        title: 'Error',
        description: error instanceof Error ? error.message : 'Failed to create request',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Feature Flag Removal Request</CardTitle>
        <CardDescription>
          Submit a request to remove a feature flag from your repositories using Devin AI
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="flagKey">Feature Flag Key *</Label>
            <Input
              id="flagKey"
              placeholder="e.g., ENABLE_NEW_FEATURE"
              value={flagKey}
              onChange={(e) => setFlagKey(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className="space-y-2">
            <Label>Repositories *</Label>
            {repositories.map((repo, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  placeholder="https://github.com/owner/repo"
                  value={repo}
                  onChange={(e) => handleRepositoryChange(index, e.target.value)}
                  disabled={loading}
                />
                {repositories.length > 1 && (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => handleRemoveRepository(index)}
                    disabled={loading}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                )}
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleAddRepository}
              disabled={loading || repositories.length >= 5}
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Repository
            </Button>
            {repositories.length >= 5 && (
              <p className="text-sm text-gray-500">Maximum 5 repositories per request</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="provider">Feature Flag Provider</Label>
            <Input
              id="provider"
              placeholder="e.g., LaunchDarkly, Split, etc. (optional)"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="createdBy">Created By *</Label>
            <Input
              id="createdBy"
              placeholder="your.email@example.com"
              value={createdBy}
              onChange={(e) => setCreatedBy(e.target.value)}
              disabled={loading}
            />
          </div>

          <Button type="submit" disabled={loading} className="w-full">
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Creating Request...
              </>
            ) : (
              'Create Removal Request'
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
