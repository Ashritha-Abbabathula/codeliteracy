const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {}

const TOKEN_KEY = "codeliteracy_token";

function getAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** FastAPI returns `detail` as a string for our own errors, but as a list of {msg, loc} for
 * request-validation (422) errors. Turn either into one readable sentence. */
function describeError(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => (typeof d?.msg === "string" ? d.msg : ""))
      .filter(Boolean)
      .join("; ") || fallback;
  }
  return fallback;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch {
    throw new ApiError(`Can't reach the CodeLiteracy server at ${BASE_URL}. Is the backend running?`);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(describeError(body.detail, `Request to ${path} failed (${response.status})`));
  }
  return response.json() as Promise<T>;
}

export function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

// --- Auth & users -------------------------------------------------------------------

export interface UserPublic {
  id: string;
  username: string;
  email: string;
  is_guest: boolean;
  created_at: string;
}

export interface UserStats {
  repos_count: number;
  notebook_count: number;
  quizzes_passed: number;
}

export interface AuthResponse {
  token: string;
  user: UserPublic;
}

export interface MeResponse {
  user: UserPublic;
  stats: UserStats;
}

export function registerUser(payload: { username: string; email: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/register", { method: "POST", body: JSON.stringify(payload) });
}

export function loginUser(payload: { login_id: string; password: string }): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/login", { method: "POST", body: JSON.stringify(payload) });
}

export function guestLogin(): Promise<AuthResponse> {
  return request<AuthResponse>("/api/auth/guest", { method: "POST" });
}

export function getCurrentUser(): Promise<MeResponse> {
  return request<MeResponse>("/api/auth/me");
}

export function logoutUser(): Promise<{ success: boolean }> {
  return request<{ success: boolean }>("/api/auth/logout", { method: "POST" });
}

// --- Repositories -------------------------------------------------------------------

export interface SampleRepo {
  id: string;
  name: string;
  source: string;
  description: string;
  tech: string;
}

export interface RepoInfo {
  repo_id: string;
  name: string;
  source: string;
  connected_at: string;
}

export function getSampleRepositories(): Promise<SampleRepo[]> {
  return request<SampleRepo[]>("/api/repo/samples");
}

export function getUserRepositories(): Promise<RepoInfo[]> {
  return request<RepoInfo[]>("/api/repo/user/list");
}

export function getRepoInfo(repoId: string): Promise<RepoInfo> {
  return request<RepoInfo>(`/api/repo/${repoId}/info`);
}

export interface RepoConnectResponse {
  repo_id: string;
  name: string;
  source: string;
  node_count: number;
  edge_count: number;
}

export function connectRepo(source: string): Promise<RepoConnectResponse> {
  return request<RepoConnectResponse>("/api/repo/connect", { method: "POST", body: JSON.stringify({ source }) });
}

// --- Onboarding ---------------------------------------------------------------------

export interface TechStackItem {
  name: string;
  category: string;
  purpose: string;
}

export interface FolderGuideItem {
  folder: string;
  title: string;
  purpose: string;
  key_files: string[];
}

export interface LearningStep {
  file_path: string;
  title: string;
  why: string;
}

export interface RepoOnboarding {
  greeting: string;
  main_idea: string;
  tech_stack: TechStackItem[];
  learning_curve: { easy: string[]; hard: string[] };
  folder_guide: FolderGuideItem[];
  /** files to read, in the order that builds understanding (always real paths) */
  learning_path?: LearningStep[];
  transition_message: string;
  /** true when the AI was unavailable and this was built only from facts read off disk */
  degraded?: boolean;
  notice?: string | null;
}

export function getRepoOnboarding(repoId: string): Promise<RepoOnboarding> {
  return request<RepoOnboarding>(`/api/repo/${repoId}/onboarding`);
}

// --- Architecture flowchart ---------------------------------------------------------

export type Tier = "entrypoint" | "router" | "service" | "model" | "external";

export interface FlowchartNode {
  id: string;
  label: string;
  tier: Tier;
  tier_label: string;
  summary: string;
  file_path: string;
  key_functions: string[];
  badge_color: string;
  imports: string[];
  imported_by: string[];
}

export interface FlowchartEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface FlowchartTier {
  id: Tier;
  title: string;
  description: string;
}

export interface ArchitectureFlowchart {
  nodes: FlowchartNode[];
  edges: FlowchartEdge[];
  tiers: FlowchartTier[];
  degraded?: boolean;
  notice?: string | null;
  total_modules?: number;
  shown_modules?: number;
}

export function getRepoFlowchart(repoId: string): Promise<ArchitectureFlowchart> {
  return request<ArchitectureFlowchart>(`/api/repo/${repoId}/flowchart`);
}

// --- Quizzes (answers are checked on the server) ------------------------------------

export interface ResourceRecommendation {
  title: string;
  description: string;
  url: string;
}

/** Feedback on one submitted answer. A learner gets two tries: after a first wrong one
 * (`final: false`) the correct answer stays hidden and they get a hint instead. */
export interface QuizAnswerResponse {
  correct: boolean;
  final: boolean;
  selected_index: number | null;
  correct_index: number | null;
  explanation?: string | null;
  /** why the option they picked is right/wrong */
  option_feedback?: string | null;
  hint?: string | null;
  resource: ResourceRecommendation | null;
  saved_to_notebook: boolean;
  attempts_left: number;
}

export interface QuizItem {
  id: string;
  concept: string;
  question: string;
  options: string[];
  attempts: number;
  /** options already tried and wrong (while the question is still open) */
  eliminated: number[];
  hint: string | null;
  /** set once the question is closed: what happened, with the answer revealed */
  review: QuizAnswerResponse | null;
}

export function answerQuiz(quizId: string, selectedIndex: number): Promise<QuizAnswerResponse> {
  return request<QuizAnswerResponse>(`/api/quiz/${quizId}/answer`, {
    method: "POST",
    body: JSON.stringify({ selected_index: selectedIndex }),
  });
}

export function retryQuiz(quizId: string): Promise<QuizItem> {
  return request<QuizItem>(`/api/quiz/${quizId}/retry`, { method: "POST" });
}

export function getChangeQuizzes(changeId: string): Promise<QuizItem[]> {
  return request<QuizItem[]>(`/api/changes/${changeId}/quizzes`, { method: "POST" });
}

// --- Code inspector -----------------------------------------------------------------

export interface LineSection {
  start_line: number;
  end_line: number;
  title: string;
  explanation: string;
  importance: "core" | "setup" | "handler" | "utility";
  /** part of a long file the AI walkthrough didn't reach: real structure, explained on request */
  needs_explanation?: boolean;
}

export interface GlossaryTerm {
  term: string;
  meaning: string;
}

export interface FileDetailsResponse {
  file_path: string;
  total_lines: number;
  content: string;
  overview: string;
  key_concepts?: GlossaryTerm[];
  line_sections: LineSection[];
  quizzes: QuizItem[];
  degraded: boolean;
  notice: string | null;
  truncated: boolean;
  /** this file's real neighbours in the dependency graph */
  imports?: string[];
  imported_by?: string[];
}

export interface RepoFile {
  path: string;
  lines: number;
  kind: "python" | "other";
  explored: boolean;
  questions: number;
  solved: number;
}

export function getRepoFiles(repoId: string): Promise<RepoFile[]> {
  return request<RepoFile[]>(`/api/repo/${repoId}/files`);
}

export interface RepoProgress {
  files_total: number;
  files_explored: number;
  questions_total: number;
  questions_answered: number;
  questions_solved: number;
  changes_made: number;
}

export function getRepoProgress(repoId: string): Promise<RepoProgress> {
  return request<RepoProgress>(`/api/repo/${repoId}/progress`);
}

export interface LineNote {
  start_line: number;
  end_line: number;
  explanation: string;
}

export interface LinesExplanation {
  file_path: string;
  start_line: number;
  end_line: number;
  summary: string;
  notes: LineNote[];
  concepts: GlossaryTerm[];
  cached: boolean;
}

export const MAX_EXPLAIN_LINES = 80;

export function explainLines(repoId: string, path: string, startLine: number, endLine: number): Promise<LinesExplanation> {
  return request<LinesExplanation>(`/api/repo/${repoId}/explain-lines`, {
    method: "POST",
    body: JSON.stringify({ path, start_line: startLine, end_line: endLine }),
  });
}

export function getFileDetails(repoId: string, path: string): Promise<FileDetailsResponse> {
  return request<FileDetailsResponse>(`/api/repo/${repoId}/file-details`, {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

// --- Tutor chat ---------------------------------------------------------------------

export interface ChatMessageContext {
  context_type?: "quiz_discussion" | "file_explainer" | "general";
  file_path?: string;
  question?: string;
  user_answer?: string;
  correct_answer?: string;
  explanation?: string;
  /** e.g. "lines 12-30: Request validation" - what the learner is looking at in the file */
  selection?: string;
  /** the exact lines selected, so the tutor is shown that part of the file */
  start_line?: number;
  end_line?: number;
}

export interface ChatResponse {
  reply: string;
  suggested_followups: string[];
  /** files the tutor was shown when answering */
  sources: string[];
}

export interface MessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  context_type: string | null;
  created_at: string;
}

export function sendChatMessage(repoId: string, message: string, context?: ChatMessageContext): Promise<ChatResponse> {
  return request<ChatResponse>(`/api/repo/${repoId}/chat`, {
    method: "POST",
    body: JSON.stringify({ message, context }),
  });
}

export function clearChatHistory(repoId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/api/repo/${repoId}/chat/history`, { method: "DELETE" });
}

export function getChatHistory(repoId: string): Promise<MessageItem[]> {
  return request<MessageItem[]>(`/api/repo/${repoId}/chat/history`);
}

// --- Assistant (error fixing) -------------------------------------------------------

export interface AssistantStep {
  action: string;
  explanation: string;
}

export interface DiffLine {
  kind: "add" | "del" | "ctx" | "gap";
  old_no: number | null;
  new_no: number | null;
  text: string;
}

export interface FileDiff {
  path: string;
  is_new_file: boolean;
  added: number;
  removed: number;
  lines: DiffLine[];
}

export interface ActivityItem {
  kind: "list" | "read" | "search" | "edit" | "create" | "error";
  label: string;
  detail: string;
  ok: boolean;
}

export interface AssistantResponse {
  change_id: string;
  request: string;
  summary: string;
  concept: string;
  concept_explanation: string | null;
  verify: string | null;
  steps: AssistantStep[];
  /** what the assistant looked at and did, in order */
  activity: ActivityItem[];
  files_changed: string[];
  diffs: FileDiff[];
  quizzes: QuizItem[];
  quiz_error: string | null;
  commit_sha: string | null;
  reverted: boolean;
  can_undo: boolean;
  created_at: string | null;
}

export function getChanges(repoId: string): Promise<AssistantResponse[]> {
  return request<AssistantResponse[]>(`/api/repo/${repoId}/changes`);
}

export function undoChange(changeId: string): Promise<{ change_id: string; reverted: boolean; restored: string[]; commit_sha: string | null }> {
  return request(`/api/changes/${changeId}/undo`, { method: "POST" });
}

export function askAssistant(repoId: string, message: string): Promise<AssistantResponse> {
  return request<AssistantResponse>(`/api/repo/${repoId}/assistant`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

// --- Notebook -----------------------------------------------------------------------

export interface NotebookEntry {
  id: string;
  concept: string;
  question: string;
  summary: string;
  repo_name: string;
  file_path?: string | null;
  code_snippet?: string | null;
  user_notes?: string | null;
  category: string;
  is_favorite: boolean;
  created_at: string;
}

export function getNotebook(params: { q?: string; category?: string; favorites?: boolean } = {}): Promise<NotebookEntry[]> {
  const search = new URLSearchParams();
  if (params.q) search.append("q", params.q);
  if (params.category) search.append("category", params.category);
  if (params.favorites) search.append("favorites", "true");
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return request<NotebookEntry[]>(`/api/notebook${suffix}`);
}

export function createNote(payload: { concept: string; summary: string; repo_name?: string }): Promise<NotebookEntry> {
  return request<NotebookEntry>("/api/notebook", {
    method: "POST",
    body: JSON.stringify({ ...payload, category: "note" }),
  });
}

export function updateNotebookNotes(entryId: string, userNotes: string): Promise<NotebookEntry> {
  return request<NotebookEntry>(`/api/notebook/${entryId}`, {
    method: "PUT",
    body: JSON.stringify({ user_notes: userNotes }),
  });
}

export function toggleNotebookFavorite(entryId: string): Promise<NotebookEntry> {
  return request<NotebookEntry>(`/api/notebook/${entryId}/favorite`, { method: "POST" });
}

export function deleteNotebookEntry(entryId: string): Promise<{ success: boolean }> {
  return request<{ success: boolean }>(`/api/notebook/${entryId}`, { method: "DELETE" });
}
