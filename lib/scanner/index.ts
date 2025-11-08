import * as fs from 'fs';
import * as path from 'path';
import { ScanMatch, ScanResult } from './types';
import { LANGUAGE_PATTERNS, detectLanguage, hasSDKImport } from './patterns';

const IGNORE_DIRS = ['node_modules', '.git', 'dist', 'build', '.next', 'coverage', 'out'];
const MAX_FILE_SIZE = 1024 * 1024; // 1MB

export class CodeScanner {
  async scanRepository(
    repoPath: string,
    flagKey: string,
    provider: string
  ): Promise<ScanResult> {
    const startTime = Date.now();
    const matches: ScanMatch[] = [];
    let scannedFiles = 0;
    let skippedFiles = 0;

    const scanDir = async (dirPath: string) => {
      const entries = await fs.promises.readdir(dirPath, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry.name);

        if (entry.isDirectory()) {
          if (!IGNORE_DIRS.includes(entry.name)) {
            await scanDir(fullPath);
          }
          continue;
        }

        if (entry.isFile()) {
          const language = detectLanguage(entry.name);
          if (!language) {
            skippedFiles++;
            continue;
          }

          try {
            const stats = await fs.promises.stat(fullPath);
            if (stats.size > MAX_FILE_SIZE) {
              skippedFiles++;
              continue;
            }

            const content = await fs.promises.readFile(fullPath, 'utf-8');
            const fileMatches = this.scanFile(
              fullPath,
              content,
              flagKey,
              language,
              repoPath
            );
            matches.push(...fileMatches);
            scannedFiles++;
          } catch {
            skippedFiles++;
          }
        }
      }
    };

    await scanDir(repoPath);

    return {
      flagKey,
      provider,
      repo: path.basename(repoPath),
      totalMatches: matches.length,
      matches,
      scannedFiles,
      skippedFiles,
      scanDurationMs: Date.now() - startTime,
    };
  }

  private scanFile(
    filePath: string,
    content: string,
    flagKey: string,
    language: string,
    repoPath: string
  ): ScanMatch[] {
    const matches: ScanMatch[] = [];
    const lines = content.split('\n');
    const pattern = LANGUAGE_PATTERNS[language];
    const hasSDK = hasSDKImport(content, language);

    if (!pattern) return matches;

    const flagPatterns = pattern.flagCallPatterns(flagKey);

    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      const line = lines[lineIndex];

      for (const regex of flagPatterns) {
        regex.lastIndex = 0;
        const match = regex.exec(line);

        if (match) {
          const matchType = this.determineMatchType(line, hasSDK);
          const confidence = this.determineConfidence(matchType, hasSDK, filePath);

          matches.push({
            file: path.relative(repoPath, filePath),
            line: lineIndex + 1,
            column: match.index,
            snippet: this.getSnippet(lines, lineIndex),
            matchType,
            confidence,
            language,
          });

          break; // Only record one match per line
        }
      }
    }

    return matches;
  }

  private determineMatchType(
    line: string,
    _hasSDK: boolean
  ): 'sdk_call' | 'string_literal' | 'config' | 'test' {
    if (line.includes('.variation') || line.includes('Variation')) {
      return 'sdk_call';
    }
    if (line.includes('config') || line.includes('Config') || line.includes('FLAG')) {
      return 'config';
    }
    if (line.includes('test') || line.includes('Test') || line.includes('spec')) {
      return 'test';
    }
    return 'string_literal';
  }

  private determineConfidence(
    matchType: string,
    hasSDK: boolean,
    filePath: string
  ): 'high' | 'medium' | 'low' {
    const isTest = filePath.includes('test') || filePath.includes('spec') || filePath.includes('__tests__');

    if (matchType === 'sdk_call' && hasSDK && !isTest) {
      return 'high';
    }
    if (matchType === 'sdk_call' || (matchType === 'string_literal' && hasSDK)) {
      return 'medium';
    }
    return 'low';
  }

  private getSnippet(lines: string[], lineIndex: number): string {
    const start = Math.max(0, lineIndex - 1);
    const end = Math.min(lines.length, lineIndex + 2);
    return lines.slice(start, end).join('\n');
  }
}

export const codeScanner = new CodeScanner();
