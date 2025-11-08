import { FeatureFlagProvider, FlagSummary, ProviderConfig } from './types';

const LD_API_BASE = 'https://app.launchdarkly.com/api/v2';

export class LaunchDarklyProvider implements FeatureFlagProvider {
  readonly name = 'launchdarkly';

  async listFlags(config: ProviderConfig, search?: string): Promise<FlagSummary[]> {
    const url = `${LD_API_BASE}/flags/${config.projectKey}?env=${config.envKey}`;
    
    const response = await fetch(url, {
      headers: {
        'Authorization': config.apiToken,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`LD API error: ${response.statusText}`);
    }

    const data = await response.json() as { items: Record<string, unknown>[] };
    
    const flags = data.items.map((flag: Record<string, unknown>) => this.transformFlag(flag, config.envKey));
    
    if (search) {
      const searchLower = search.toLowerCase();
      return flags.filter((flag: FlagSummary) => 
        flag.key.toLowerCase().includes(searchLower) ||
        flag.name.toLowerCase().includes(searchLower) ||
        flag.description?.toLowerCase().includes(searchLower)
      );
    }
    
    return flags;
  }

  async getFlag(config: ProviderConfig, flagKey: string): Promise<FlagSummary> {
    const url = `${LD_API_BASE}/flags/${config.projectKey}/${flagKey}?env=${config.envKey}`;
    
    const response = await fetch(url, {
      headers: {
        'Authorization': config.apiToken,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`LD API error: ${response.statusText}`);
    }

    const flag = await response.json();
    return this.transformFlag(flag, config.envKey);
  }

  private transformFlag(ldFlag: Record<string, unknown>, envKey: string): FlagSummary {
    const envData = ldFlag.environments?.[envKey];
    const lastEval = envData?.lastRequested;
    const daysSince = lastEval ? this.daysSince(lastEval) : null;
    
    return {
      key: ldFlag.key,
      name: ldFlag.name,
      description: ldFlag.description,
      tags: ldFlag.tags || [],
      lastEvaluatedAt: lastEval || null,
      archived: ldFlag.archived || false,
      createdAt: ldFlag.creationDate,
      staleLikely: !lastEval || (daysSince !== null && daysSince > 90),
      daysSinceEval: daysSince,
    };
  }

  private daysSince(timestamp: string): number {
    const diff = Date.now() - new Date(timestamp).getTime();
    return Math.floor(diff / (1000 * 60 * 60 * 24));
  }

  async archiveFlag(config: ProviderConfig, flagKey: string): Promise<void> {
    const url = `${LD_API_BASE}/flags/${config.projectKey}/${flagKey}`;
    
    const response = await fetch(url, {
      method: 'PATCH',
      headers: {
        'Authorization': config.apiToken,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        patch: [{ op: 'replace', path: '/archived', value: true }],
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to archive flag: ${response.statusText}`);
    }
  }
}

export const launchDarkly = new LaunchDarklyProvider();
