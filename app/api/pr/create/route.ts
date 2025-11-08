import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@/lib/prisma';
import { githubClient } from '@/lib/github/client';

export const runtime = 'nodejs';

const createPRSchema = z.object({
  sessionId: z.string().min(1),
  userId: z.string().min(1),
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const validated = createPRSchema.parse(body);

    const session = await prisma.removalSession.findUnique({
      where: { id: validated.sessionId },
    });

    if (!session) {
      return NextResponse.json(
        { error: 'Session not found' },
        { status: 404 }
      );
    }

    if (session.status !== 'ready') {
      return NextResponse.json(
        { error: `Session status is ${session.status}, expected 'ready'` },
        { status: 400 }
      );
    }

    JSON.parse(session.repos);
    const scanResults = session.scanResults ? JSON.parse(session.scanResults) : [];

    if (scanResults.length === 0) {
      return NextResponse.json(
        { error: 'No scan results available' },
        { status: 400 }
      );
    }

    const prUrls: string[] = [];

    for (const result of scanResults) {
      if (result.totalMatches === 0) continue;

      try {
        const branchName = `${process.env.PR_BRANCH_PREFIX || 'flag-removal/'}${session.flagKey}-${Date.now()}`;
        const baseBranch = process.env.DEFAULT_BRANCH || 'main';

        await githubClient.createBranch(result.repo, branchName, baseBranch);

        const prBody = generatePRBody(session, result);

        const prUrl = await githubClient.createPR(
          result.repo,
          branchName,
          `Remove feature flag: ${session.flagKey}`,
          prBody,
          baseBranch
        );

        prUrls.push(prUrl);

        await prisma.auditLog.create({
          data: {
            userId: validated.userId,
            action: 'create_pr',
            provider: session.provider,
            flagKey: session.flagKey,
            repos: JSON.stringify([result.repo]),
            success: true,
            metadata: JSON.stringify({ prUrl }),
          },
        });
      } catch (error) {
        console.error(`Error creating PR for ${result.repo}:`, error);

        await prisma.auditLog.create({
          data: {
            userId: validated.userId,
            action: 'create_pr',
            provider: session.provider,
            flagKey: session.flagKey,
            repos: JSON.stringify([result.repo]),
            success: false,
            errorMsg: error instanceof Error ? error.message : 'Unknown error',
          },
        });
      }
    }

    await prisma.removalSession.update({
      where: { id: validated.sessionId },
      data: {
        status: 'pr_created',
        prUrl: prUrls.join(','),
      },
    });

    return NextResponse.json({
      prUrls,
      message: `Created ${prUrls.length} PR(s)`,
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        { error: 'Invalid request', details: error.errors },
        { status: 400 }
      );
    }

    console.error('Error creating PR:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to create PR' },
      { status: 500 }
    );
  }
}

interface ScanMatch {
  file: string;
  line: number;
  confidence: string;
  matchType: string;
  snippet: string;
  language: string;
}

interface ScanResult {
  totalMatches: number;
  scannedFiles: number;
  scanDurationMs: number;
  matches: ScanMatch[];
}

interface SessionData {
  flagKey: string;
  provider: string;
  lastEvaluatedAt?: string;
}

function generatePRBody(session: SessionData, scanResult: ScanResult): string {
  const matches = scanResult.matches || [];
  const highConfidence = matches.filter((m: ScanMatch) => m.confidence === 'high').length;
  const mediumConfidence = matches.filter((m: ScanMatch) => m.confidence === 'medium').length;
  const lowConfidence = matches.filter((m: ScanMatch) => m.confidence === 'low').length;

  return `## 🚩 Feature Flag Removal: \`${session.flagKey}\`

**Provider**: ${session.provider}  
**Last Evaluated**: ${session.lastEvaluatedAt || 'Never'}

### 🔍 Scan Results
- **Total matches**: ${scanResult.totalMatches}
- **Files scanned**: ${scanResult.scannedFiles}
- **Scan duration**: ${scanResult.scanDurationMs}ms

### 📊 Confidence Breakdown
- 🟢 High confidence: ${highConfidence}
- 🟡 Medium confidence: ${mediumConfidence}
- 🔴 Low confidence: ${lowConfidence}

### 📝 Matches Found
${matches.slice(0, 10).map((m: ScanMatch) => `
**${m.file}:${m.line}**
- Type: ${m.matchType}
- Confidence: ${m.confidence}
- Language: ${m.language}

\`\`\`
${m.snippet}
\`\`\`
`).join('\n')}

${matches.length > 10 ? `\n_... and ${matches.length - 10} more matches_` : ''}

### ⚠️ Risk Assessment
${highConfidence > 0 ? '✅ High confidence matches found - safe to remove' : ''}
${mediumConfidence > 0 ? '⚠️ Medium confidence matches - review carefully' : ''}
${lowConfidence > 0 ? '🔴 Low confidence matches - manual verification required' : ''}

### 🔄 Rollback Plan
\`\`\`bash
git revert HEAD -m 1
\`\`\`

---
_Generated by [Flag Removal Dashboard](${process.env.NEXTAUTH_URL})_
`;
}
