export interface ScanMatch {
  file: string;
  line: number;
  column: number;
  snippet: string;  // 3 lines context
  matchType: 'sdk_call' | 'string_literal' | 'config' | 'test';
  confidence: 'high' | 'medium' | 'low';
  language: string;
}

export interface ScanResult {
  flagKey: string;
  provider: string;
  repo: string;
  totalMatches: number;
  matches: ScanMatch[];
  scannedFiles: number;
  skippedFiles: number;
  scanDurationMs: number;
}

export interface ProposedEdit {
  file: string;
  originalCode: string;
  proposedCode: string;
  reasoning: string;
  confidence: 'high' | 'medium' | 'low';
}
