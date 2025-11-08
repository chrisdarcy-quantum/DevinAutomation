export interface LanguagePattern {
  extensions: string[];
  sdkImports: RegExp[];
  flagCallPatterns: (flagKey: string) => RegExp[];
}

export const LANGUAGE_PATTERNS: Record<string, LanguagePattern> = {
  typescript: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
    sdkImports: [
      /from ['"]launchdarkly-js-client-sdk['"]/,
      /from ['"]launchdarkly-node-server-sdk['"]/,
      /require\(['"]launchdarkly-/,
    ],
    flagCallPatterns: (key) => [
      new RegExp(`\\.variation\\(['"\`]${key}['"\`]`, 'g'),
      new RegExp(`\\.boolVariation\\(['"\`]${key}['"\`]`, 'g'),
      new RegExp(`\\.jsonVariation\\(['"\`]${key}['"\`]`, 'g'),
      new RegExp(`['"\`]${key}['"\`]`, 'g'), // String literal fallback
    ],
  },
  
  python: {
    extensions: ['.py'],
    sdkImports: [
      /import ldclient/,
      /from ldclient/,
    ],
    flagCallPatterns: (key) => [
      new RegExp(`\\.variation\\(['"]${key}['"]`, 'g'),
      new RegExp(`\\.variation_detail\\(['"]${key}['"]`, 'g'),
      new RegExp(`['"]${key}['"]`, 'g'), // String literal fallback
    ],
  },
  
  java: {
    extensions: ['.java'],
    sdkImports: [
      /import com\.launchdarkly\./,
    ],
    flagCallPatterns: (key) => [
      new RegExp(`\\.boolVariation\\("${key}"`, 'g'),
      new RegExp(`\\.stringVariation\\("${key}"`, 'g'),
      new RegExp(`"${key}"`, 'g'), // String literal fallback
    ],
  },
  
  go: {
    extensions: ['.go'],
    sdkImports: [
      /import.*"github\.com\/launchdarkly\//,
    ],
    flagCallPatterns: (key) => [
      new RegExp(`\\.BoolVariation\\("${key}"`, 'g'),
      new RegExp(`\\.StringVariation\\("${key}"`, 'g'),
      new RegExp(`"${key}"`, 'g'), // String literal fallback
    ],
  },
};

export function detectLanguage(filePath: string): string | null {
  for (const [lang, pattern] of Object.entries(LANGUAGE_PATTERNS)) {
    if (pattern.extensions.some(ext => filePath.endsWith(ext))) {
      return lang;
    }
  }
  return null;
}

export function hasSDKImport(content: string, language: string): boolean {
  const pattern = LANGUAGE_PATTERNS[language];
  if (!pattern) return false;
  
  return pattern.sdkImports.some(regex => regex.test(content));
}
