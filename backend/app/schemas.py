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
