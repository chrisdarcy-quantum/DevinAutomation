import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { prisma } from '@/lib/prisma';
import { codeScanner } from '@/lib/scanner';
import { githubClient } from '@/lib/github/client';
import * as path from 'path';
import * as fs from 'fs';

export const runtime = 'nodejs';

const scanRequestSchema = z.object({
  flagKey: z.string().min(1),
  projectKey: z.string().min(1),
  envKey: z.string().min(1),
  repos: z.array(z.string()).min(1).max(5),
  userId: z.string().min(1),
});

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const validated = scanRequestSchema.parse(body);

    const session = await prisma.removalSession.create({
      data: {
        userId: validated.userId,
        provider: 'launchdarkly',
        flagKey: validated.flagKey,
        projectKey: validated.projectKey,
        envKey: validated.envKey,
        repos: JSON.stringify(validated.repos),
        status: 'scanning',
      },
    });

    scanRepositories(session.id, validated.flagKey, validated.repos, validated.userId)
      .catch(error => {
        console.error('Scan error:', error);
        prisma.removalSession.update({
          where: { id: session.id },
          data: { status: 'failed' },
        }).catch(console.error);
      });

    return NextResponse.json({
      sessionId: session.id,
      status: 'scanning',
      message: 'Scan started',
    }, { status: 202 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        { error: 'Invalid request', details: error.errors },
        { status: 400 }
      );
    }

    console.error('Error starting scan:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to start scan' },
      { status: 500 }
    );
  }
}

async function scanRepositories(
  sessionId: string,
  flagKey: string,
  repos: string[],
  userId: string
) {
  const workDir = path.join('/tmp', `scan-${sessionId}`);
  await fs.promises.mkdir(workDir, { recursive: true });

  const allResults = [];

  try {
    for (const repo of repos) {
      try {
        const repoPath = path.join(workDir, repo);
        
        await githubClient.cloneRepository(repo, repoPath);

        const result = await codeScanner.scanRepository(
          repoPath,
          flagKey,
          'launchdarkly'
        );

        allResults.push(result);

        await prisma.auditLog.create({
          data: {
            userId,
            action: 'scan',
            provider: 'launchdarkly',
            flagKey,
            repos: JSON.stringify([repo]),
            success: true,
            metadata: JSON.stringify({ matches: result.totalMatches }),
          },
        });
      } catch (error) {
        console.error(`Error scanning ${repo}:`, error);
        
        await prisma.auditLog.create({
          data: {
            userId,
            action: 'scan',
            provider: 'launchdarkly',
            flagKey,
            repos: JSON.stringify([repo]),
            success: false,
            errorMsg: error instanceof Error ? error.message : 'Unknown error',
          },
        });
      }
    }

    await prisma.removalSession.update({
      where: { id: sessionId },
      data: {
        scanResults: JSON.stringify(allResults),
        status: allResults.length > 0 ? 'ready' : 'failed',
      },
    });
  } finally {
    try {
      await fs.promises.rm(workDir, { recursive: true, force: true });
    } catch (error) {
      console.error('Cleanup error:', error);
    }
  }
}
