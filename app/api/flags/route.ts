import { NextRequest, NextResponse } from 'next/server';
import { launchDarkly } from '@/lib/providers/launchdarkly';
import { z } from 'zod';

export const runtime = 'nodejs';

const querySchema = z.object({
  search: z.string().optional(),
});

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const search = searchParams.get('search') || undefined;

    querySchema.parse({ search });

    const config = {
      apiToken: process.env.LD_API_TOKEN || '',
      projectKey: process.env.LD_PROJECT_KEY || 'default',
      envKey: process.env.LD_ENV_KEY || 'production',
    };

    if (!config.apiToken) {
      return NextResponse.json(
        { error: 'LaunchDarkly API token not configured' },
        { status: 500 }
      );
    }

    const flags = await launchDarkly.listFlags(config, search);

    return NextResponse.json({
      flags,
      total: flags.length,
      provider: 'launchdarkly',
    });
  } catch (error) {
    console.error('Error fetching flags:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch flags' },
      { status: 500 }
    );
  }
}
