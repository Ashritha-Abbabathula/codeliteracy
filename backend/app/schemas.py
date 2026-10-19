from datetime import datetime

from pydantic import BaseModel, Field


# --- Repositories & dependency graph -----------------------------------------------


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


class RepoInfo(BaseModel):
    repo_id: str
    name: str
    source: str
    connected_at: datetime


# --- Plain-language explanations ---------------------------------------------------


class FileExplanation(BaseModel):
    path: str
    explanation: str


class RepoExplanation(BaseModel):
    overview: str
    files: list[FileExplanation]


class ExplainFileRequest(BaseModel):
    path: str


# --- Quizzes -------------------------------------------------------------------------


class ResourceRecommendation(BaseModel):
    title: str
    description: str
    url: str


class QuizAnswerRequest(BaseModel):
    selected_index: int


class QuizAnswerResponse(BaseModel):
    """Feedback on one submitted answer.

    A learner gets two tries. The first wrong one is *not* final: it returns why that option
    is wrong plus a hint, and keeps the correct answer hidden (`correct_index` is None) so
    the second try is still real thinking. Once the question is closed (`final`), everything
    is revealed."""

    correct: bool
    final: bool = True
    selected_index: int | None = None
    correct_index: int | None = None
    explanation: str | None = None
    option_feedback: str | None = None  # why the option the learner picked is right/wrong
    hint: str | None = None
    resource: ResourceRecommendation | None = None
    saved_to_notebook: bool = False
    attempts_left: int = 0


class QuizItem(BaseModel):
    """A question as shown to the learner. The correct answer is deliberately absent: it is
    only revealed by the server after an answer is submitted (and the notebook is only ever
    credited by the server, never by the client claiming it got one right).

    The learner's progress on it travels with it, so a page refresh or a tab switch doesn't
    reset a question they've already worked on."""

    id: str
    concept: str
    question: str
    options: list[str]
    attempts: int = 0
    eliminated: list[int] = Field(default_factory=list)  # options already tried and wrong
    hint: str | None = None  # shown once a first try has been wrong
    review: QuizAnswerResponse | None = None  # set once the question is closed


# --- AI coding assistant ------------------------------------------------------------


class AssistantRequest(BaseModel):
    message: str


class AssistantStep(BaseModel):
    action: str
    explanation: str


class DiffLine(BaseModel):
    kind: str  # "add" | "del" | "ctx" | "gap"
    old_no: int | None = None
    new_no: int | None = None
    text: str = ""


class FileDiff(BaseModel):
    path: str
    is_new_file: bool = False
    added: int = 0
    removed: int = 0
    lines: list[DiffLine] = Field(default_factory=list)


class ActivityItem(BaseModel):
    """One thing the assistant did while working (its visible work log)."""

    kind: str  # "list" | "read" | "search" | "edit" | "create" | "error"
    label: str
    detail: str = ""
    ok: bool = True


class AssistantResponse(BaseModel):
    change_id: str
    request: str = ""
    summary: str
    concept: str
    concept_explanation: str | None = None
    verify: str | None = None
    steps: list[AssistantStep]
    activity: list[ActivityItem] = Field(default_factory=list)
    files_changed: list[str]
    diffs: list[FileDiff] = Field(default_factory=list)
    quizzes: list[QuizItem] = Field(default_factory=list)
    quiz_error: str | None = None
    commit_sha: str | None = None
    reverted: bool = False
    can_undo: bool = False
    created_at: datetime | None = None


class UndoResponse(BaseModel):
    change_id: str
    reverted: bool
    restored: list[str]
    commit_sha: str | None = None


# --- Repo files, line explanations, progress ----------------------------------------


class RepoFile(BaseModel):
    path: str
    lines: int
    kind: str  # "python" | "other"
    explored: bool = False
    questions: int = 0
    solved: int = 0


class ExplainLinesRequest(BaseModel):
    path: str
    start_line: int
    end_line: int


class LineNote(BaseModel):
    start_line: int
    end_line: int
    explanation: str


class GlossaryTerm(BaseModel):
    term: str
    meaning: str


class ExplainLinesResponse(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    summary: str
    notes: list[LineNote] = Field(default_factory=list)
    concepts: list[GlossaryTerm] = Field(default_factory=list)
    cached: bool = False


class RepoProgress(BaseModel):
    files_total: int
    files_explored: int
    questions_total: int
    questions_answered: int
    questions_solved: int
    changes_made: int


# --- Learning notebook --------------------------------------------------------------


class NotebookEntryCreate(BaseModel):
    concept: str
    summary: str
    question: str = ""
    repo_name: str = "Personal note"
    file_path: str | None = None
    code_snippet: str | None = None
    user_notes: str | None = None
    category: str = "note"


class NotebookEntryUpdate(BaseModel):
    user_notes: str


class NotebookEntryPublic(BaseModel):
    id: str
    concept: str
    question: str
    summary: str
    repo_name: str
    file_path: str | None = None
    code_snippet: str | None = None
    user_notes: str | None = None
    category: str = "concept"
    is_favorite: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
