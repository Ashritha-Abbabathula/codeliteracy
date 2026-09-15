from pydantic import BaseModel


# --- Sprint 1: repo connection + dependency graph ---------------------------------


class RepoConnectRequest(BaseModel):
    source: str  # a GitHub URL (https://github.com/owner/repo[.git]) or a local folder path


class GraphNode(BaseModel):
    id: str  # module path relative to the repo root, e.g. "app/services/foo.py"
    label: str
    kind: str  # "module" | "package"


class GraphEdge(BaseModel):
    source: str
    target: str


class DependencyGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RepoConnectResponse(BaseModel):
    repo_id: str
    name: str
    source: str
    node_count: int
    edge_count: int
    graph: DependencyGraph


# --- Sprint 2: plain-language explanations -----------------------------------------


class FileExplanation(BaseModel):
    path: str
    explanation: str


class RepoExplanation(BaseModel):
    overview: str
    files: list[FileExplanation]


# --- Sprint 3: AI coding assistant --------------------------------------------------


class AssistantRequest(BaseModel):
    message: str


class AssistantStep(BaseModel):
    action: str
    explanation: str


class AssistantResponse(BaseModel):
    change_id: str
    summary: str
    concept: str
    steps: list[AssistantStep]
    files_changed: list[str]
    commit_sha: str | None


# --- Sprint 4: quiz engine -----------------------------------------------------------


class QuizPublic(BaseModel):
    """No correct_index here - the client shouldn't see the answer before submitting."""

    quiz_id: str
    concept: str
    question: str
    options: list[str]


class QuizAnswerRequest(BaseModel):
    selected_index: int


class QuizAnswerResponse(BaseModel):
    correct: bool
    correct_index: int
