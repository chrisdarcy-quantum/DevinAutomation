import { describe, it, expect } from 'vitest';
import { detectLanguage, hasSDKImport, LANGUAGE_PATTERNS } from '../lib/scanner/patterns';

describe('Scanner Pattern Matching', () => {
  describe('detectLanguage', () => {
    it('should detect TypeScript files', () => {
      expect(detectLanguage('test.ts')).toBe('typescript');
      expect(detectLanguage('test.tsx')).toBe('typescript');
      expect(detectLanguage('test.js')).toBe('typescript');
      expect(detectLanguage('test.jsx')).toBe('typescript');
    });

    it('should detect Python files', () => {
      expect(detectLanguage('test.py')).toBe('python');
    });

    it('should detect Java files', () => {
      expect(detectLanguage('Test.java')).toBe('java');
    });

    it('should detect Go files', () => {
      expect(detectLanguage('test.go')).toBe('go');
    });

    it('should return null for unknown file types', () => {
      expect(detectLanguage('test.txt')).toBeNull();
      expect(detectLanguage('README.md')).toBeNull();
    });
  });

  describe('hasSDKImport', () => {
    it('should detect LaunchDarkly SDK imports in TypeScript', () => {
      const content = `
        import { LDClient } from 'launchdarkly-js-client-sdk';
        const client = LDClient.initialize('key');
      `;
      expect(hasSDKImport(content, 'typescript')).toBe(true);
    });

    it('should detect LaunchDarkly SDK imports in Python', () => {
      const content = `
        import ldclient
        client = ldclient.get()
      `;
      expect(hasSDKImport(content, 'python')).toBe(true);
    });

    it('should return false when no SDK import is present', () => {
      const content = `
        const someCode = 'test';
      `;
      expect(hasSDKImport(content, 'typescript')).toBe(false);
    });
  });

  describe('LANGUAGE_PATTERNS', () => {
    it('should have patterns for all supported languages', () => {
      expect(LANGUAGE_PATTERNS).toHaveProperty('typescript');
      expect(LANGUAGE_PATTERNS).toHaveProperty('python');
      expect(LANGUAGE_PATTERNS).toHaveProperty('java');
      expect(LANGUAGE_PATTERNS).toHaveProperty('go');
    });

    it('should generate flag call patterns correctly', () => {
      const patterns = LANGUAGE_PATTERNS.typescript.flagCallPatterns('my-flag');
      expect(patterns.length).toBeGreaterThan(0);
      
      const testCode = `.variation('my-flag', false)`;
      expect(patterns.some(p => p.test(testCode))).toBe(true);
    });
  });
});
