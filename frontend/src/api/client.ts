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

export function explainFile(repoId: string, path: string): Promise<FileExplanation> {
  return request<FileExplanation>(`/api/repo/${repoId}/explain/file`, {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

// --- Sprint 3: AI coding assistant --------------------------------------------------

export interface AssistantStep {
  action: string;
  explanation: string;
}

export interface AssistantResponse {
  change_id: string;
  summary: string;
  concept: string;
  steps: AssistantStep[];
  files_changed: string[];
  commit_sha: string | null;
}

export function askAssistant(repoId: string, message: string): Promise<AssistantResponse> {
  return request<AssistantResponse>(`/api/repo/${repoId}/assistant`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

// --- Sprint 4: quiz engine -----------------------------------------------------------

export interface QuizPublic {
  quiz_id: string;
  concept: string;
  question: string;
  options: string[];
}

export interface ResourceRecommendation {
  title: string;
  description: string;
  url: string;
}

export interface QuizAnswerResponse {
  correct: boolean;
  correct_index: number;
  resource: ResourceRecommendation | null;
}

export function generateQuiz(changeId: string): Promise<QuizPublic> {
  return request<QuizPublic>(`/api/changes/${changeId}/quiz`, { method: "POST" });
}

export function submitQuizAnswer(quizId: string, selectedIndex: number): Promise<QuizAnswerResponse> {
  return request<QuizAnswerResponse>(`/api/quiz/${quizId}/answer`, {
    method: "POST",
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
}

// --- Sprint 5: retry after reviewing a resource -------------------------------------

export function retryQuiz(quizId: string): Promise<QuizPublic> {
  return request<QuizPublic>(`/api/quiz/${quizId}/retry`, { method: "POST" });
}

// --- Sprint 6: learning notebook ----------------------------------------------------

export interface NotebookEntry {
  id: string;
  concept: string;
  question: string;
  summary: string;
  repo_name: string;
  created_at: string;
}

export function getNotebook(query?: string): Promise<NotebookEntry[]> {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return request<NotebookEntry[]>(`/api/notebook${suffix}`);
}
