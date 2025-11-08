import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export const runtime = 'nodejs';

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const session = await prisma.removalSession.findUnique({
      where: { id: params.id },
      include: {
        user: {
          select: {
            id: true,
            email: true,
            name: true,
          },
        },
      },
    });

    if (!session) {
      return NextResponse.json(
        { error: 'Session not found' },
        { status: 404 }
      );
    }

    const response = {
      ...session,
      repos: JSON.parse(session.repos),
      scanResults: session.scanResults ? JSON.parse(session.scanResults) : null,
      patchPlan: session.patchPlan ? JSON.parse(session.patchPlan) : null,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Error fetching session:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch session' },
      { status: 500 }
    );
  }
}
