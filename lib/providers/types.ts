export interface FlagSummary {
  key: string;
  name: string;
  description?: string;
  tags: string[];
  lastEvaluatedAt: string | null;
  archived: boolean;
  createdAt: string;
  
  staleLikely: boolean;  // true if lastEvaluated > 90 days or null
  daysSinceEval: number | null;
}

export interface ProviderConfig {
  apiToken: string;
  projectKey: string;
  envKey: string;
}

export interface FeatureFlagProvider {
  readonly name: string;
  
  listFlags(config: ProviderConfig, search?: string): Promise<FlagSummary[]>;
  getFlag(config: ProviderConfig, flagKey: string): Promise<FlagSummary>;
  archiveFlag(config: ProviderConfig, flagKey: string): Promise<void>;
  deleteFlag?(config: ProviderConfig, flagKey: string): Promise<void>;
}
