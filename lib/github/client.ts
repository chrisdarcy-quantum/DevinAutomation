import { Octokit } from '@octokit/rest';
import { createAppAuth } from '@octokit/auth-app';
import simpleGit, { SimpleGit } from 'simple-git';
import * as fs from 'fs';
import * as path from 'path';

export interface CreatePROptions {
  repo: string;
  branchName: string;
  title: string;
  body: string;
  files: { path: string; content: string }[];
  baseBranch?: string;
}

export class GitHubClient {
  private octokit: Octokit;
  private org: string;

  constructor() {
    const useApp = !!process.env.GITHUB_APP_ID;
    
    this.octokit = new Octokit({
      authStrategy: useApp ? createAppAuth : undefined,
      auth: useApp ? {
        appId: process.env.GITHUB_APP_ID!,
        privateKey: process.env.GITHUB_APP_PRIVATE_KEY!,
        installationId: process.env.GITHUB_APP_INSTALLATION_ID!,
      } : process.env.GITHUB_TOKEN,
    });

    this.org = process.env.GITHUB_ORG || '';
  }

  async createBranch(repo: string, branchName: string, baseBranch: string = 'main') {
    const { data: baseRef } = await this.octokit.git.getRef({
      owner: this.org,
      repo,
      ref: `heads/${baseBranch}`,
    });

    await this.octokit.git.createRef({
      owner: this.org,
      repo,
      ref: `refs/heads/${branchName}`,
      sha: baseRef.object.sha,
    });

    return baseRef.object.sha;
  }

  async commitFiles(
    repo: string,
    branchName: string,
    files: { path: string; content: string }[],
    message: string
  ) {
    const { data: ref } = await this.octokit.git.getRef({
      owner: this.org,
      repo,
      ref: `heads/${branchName}`,
    });

    const currentCommitSha = ref.object.sha;

    const { data: commit } = await this.octokit.git.getCommit({
      owner: this.org,
      repo,
      commit_sha: currentCommitSha,
    });

    const blobs = await Promise.all(
      files.map(async (file) => {
        const { data: blob } = await this.octokit.git.createBlob({
          owner: this.org,
          repo,
          content: Buffer.from(file.content).toString('base64'),
          encoding: 'base64',
        });
        return { path: file.path, sha: blob.sha, mode: '100644' as const, type: 'blob' as const };
      })
    );

    const { data: newTree } = await this.octokit.git.createTree({
      owner: this.org,
      repo,
      base_tree: commit.tree.sha,
      tree: blobs,
    });

    const { data: newCommit } = await this.octokit.git.createCommit({
      owner: this.org,
      repo,
      message,
      tree: newTree.sha,
      parents: [currentCommitSha],
    });

    await this.octokit.git.updateRef({
      owner: this.org,
      repo,
      ref: `heads/${branchName}`,
      sha: newCommit.sha,
    });

    return newCommit.sha;
  }

  async createPR(repo: string, branch: string, title: string, body: string, baseBranch: string = 'main') {
    const { data } = await this.octokit.pulls.create({
      owner: this.org,
      repo,
      title,
      body,
      head: branch,
      base: baseBranch,
    });

    return data.html_url;
  }

  async getFileContent(repo: string, filePath: string, ref: string = 'main'): Promise<string> {
    try {
      const { data } = await this.octokit.repos.getContent({
        owner: this.org,
        repo,
        path: filePath,
        ref,
      });

      if ('content' in data) {
        return Buffer.from(data.content, 'base64').toString('utf-8');
      }
      throw new Error('File content not available');
    } catch (error) {
      throw new Error(`Failed to get file content: ${error}`);
    }
  }

  async listRepositories(): Promise<string[]> {
    const allowlist = process.env.REPO_ALLOWLIST?.split(',').map(r => r.trim()) || [];
    
    if (allowlist.length > 0) {
      return allowlist;
    }

    const { data } = await this.octokit.repos.listForOrg({
      org: this.org,
      per_page: 100,
    });

    return data.map(repo => repo.name);
  }

  async cloneRepository(repo: string, targetDir: string): Promise<SimpleGit> {
    const repoUrl = `https://github.com/${this.org}/${repo}.git`;
    
    await fs.promises.mkdir(path.dirname(targetDir), { recursive: true });

    const git = simpleGit();
    await git.clone(repoUrl, targetDir);

    return simpleGit(targetDir);
  }
}

export const githubClient = new GitHubClient();
