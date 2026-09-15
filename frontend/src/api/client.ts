const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail ?? `Request to ${path} failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

// --- Sprint 1: repo connection + dependency graph ---------------------------------

export interface GraphNode {
  id: string;
  label: string;
  kind: "module" | "package";
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface DependencyGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface RepoConnectResponse {
  repo_id: string;
  name: string;
  source: string;
  node_count: number;
  edge_count: number;
  graph: DependencyGraph;
}

export function connectRepo(source: string): Promise<RepoConnectResponse> {
  return request<RepoConnectResponse>("/api/repo/connect", {
    method: "POST",
    body: JSON.stringify({ source }),
  });
}

export function getRepoGraph(repoId: string): Promise<DependencyGraph> {
  return request<DependencyGraph>(`/api/repo/${repoId}/graph`);
}

// --- Sprint 2: plain-language explanations -----------------------------------------

export interface FileExplanation {
  path: string;
  explanation: string;
}

export interface RepoExplanation {
  overview: string;
  files: FileExplanation[];
}

export function explainRepo(repoId: string): Promise<RepoExplanation> {
  return request<RepoExplanation>(`/api/repo/${repoId}/explain`, { method: "POST" });
}
