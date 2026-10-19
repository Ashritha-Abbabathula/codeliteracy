import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileCode,
  FilePlus,
  FolderOpen,
  GitCommit,
  Lightbulb,
  ListChecks,
  Pencil,
  RefreshCw,
  Search,
  Sparkles,
  Undo2,
  Wrench,
} from "lucide-react";
import {
  ActivityItem,
  askAssistant,
  AssistantResponse,
  ChatMessageContext,
  errorMessage,
  FileDiff,
  getChangeQuizzes,
  getChanges,
  undoChange,
} from "../api/client";
import { InteractiveQuiz } from "./InteractiveQuiz";
import { InlineText } from "./RichText";

interface ErrorFixerProps {
  repoId: string;
  onOpenDiscussion: (context: ChatMessageContext) => void;
  onOpenFile: (path: string) => void;
  /** The repo's code changed (a change was applied or undone): refresh anything derived from it. */
  onRepoChanged: () => void;
  onProgress: () => void;
}

const SAMPLE_PROMPTS = [
  "Add input validation to a public function that currently trusts its arguments",
  "Add a docstring to the most important function that doesn't have one",
  "Make one error message more helpful to the person who sees it",
];

const ACTIVITY_ICON: Record<ActivityItem["kind"], React.ReactNode> = {
  list: <FolderOpen size={13} />,
  read: <Eye size={13} />,
  search: <Search size={13} />,
  edit: <Pencil size={13} />,
  create: <FilePlus size={13} />,
  error: <AlertTriangle size={13} />,
};

/** What the assistant changed, as a real diff: removed lines in red, added in green, with
 * line numbers and a few lines of surrounding context. */
const DiffView: React.FC<{ diff: FileDiff; onOpenFile: (path: string) => void; reverted: boolean }> = ({ diff, onOpenFile, reverted }) => (
  <div className="diff-container">
    <div className="diff-header">
      <FileCode size={14} style={{ display: "inline", marginRight: "6px", verticalAlign: "-2px" }} />
      {diff.path}
      <span style={{ marginLeft: "0.75rem", color: "#86efac" }}>+{diff.added}</span>
      <span style={{ marginLeft: "0.4rem", color: "#fca5a5" }}>−{diff.removed}</span>
      {diff.is_new_file && <span className="tech-tag" style={{ marginLeft: "0.6rem" }}>new file</span>}
      {!(reverted && diff.is_new_file) && (
        <button className="link-btn" style={{ marginLeft: "auto" }} onClick={() => onOpenFile(diff.path)}>
          Open in the inspector <ChevronRight size={12} />
        </button>
      )}
    </div>
    <div className="diff-scroll">
      {diff.lines.map((line, i) =>
        line.kind === "gap" ? (
          <div key={i} className="diff-row gap">{line.text || "⋯"}</div>
        ) : (
          <div key={i} className={`diff-row ${line.kind}`}>
            <span className="diff-no">{line.old_no ?? ""}</span>
            <span className="diff-no">{line.new_no ?? ""}</span>
            <span className="diff-sign">{line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}</span>
            <span className="diff-text">{line.text || " "}</span>
          </div>
        )
      )}
    </div>
  </div>
);

interface ResultCardProps {
  result: AssistantResponse;
  defaultOpen: boolean;
  onOpenDiscussion: (context: ChatMessageContext) => void;
  onOpenFile: (path: string) => void;
  onRepoChanged: () => void;
  onProgress: () => void;
  onUpdate: (next: AssistantResponse) => void;
}

const ResultCard: React.FC<ResultCardProps> = ({ result, defaultOpen, onOpenDiscussion, onOpenFile, onRepoChanged, onProgress, onUpdate }) => {
  const [open, setOpen] = useState(defaultOpen);
  const [quizzes, setQuizzes] = useState(result.quizzes);
  const [quizError, setQuizError] = useState(result.quiz_error);
  const [loadingQuiz, setLoadingQuiz] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [undoError, setUndoError] = useState<string | null>(null);
  const [showLog, setShowLog] = useState(false);

  async function retryQuizzes() {
    setLoadingQuiz(true);
    try {
      setQuizzes(await getChangeQuizzes(result.change_id));
      setQuizError(null);
    } catch (err) {
      setQuizError(errorMessage(err, "Couldn't generate the quiz."));
    } finally {
      setLoadingQuiz(false);
    }
  }

  async function handleUndo() {
    if (!window.confirm("Undo this change? The files will be put back exactly as they were before it.")) return;
    setUndoing(true);
    setUndoError(null);
    try {
      await undoChange(result.change_id);
      onUpdate({ ...result, reverted: true, can_undo: false });
      onRepoChanged();
    } catch (err) {
      setUndoError(errorMessage(err, "Couldn't undo that change."));
    } finally {
      setUndoing(false);
    }
  }

  const when = result.created_at ? new Date(result.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : null;

  return (
    <div className={`change-card ${result.reverted ? "reverted" : ""}`}>
      <button className="change-card-head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        <span className="change-title">
          <span className="change-request">“{result.request}”</span>
          <span className="change-meta">
            {result.reverted ? "Undone" : "Applied"} · {result.concept}
            {when && ` · ${when}`}
          </span>
        </span>
        {result.reverted ? (
          <span className="file-micro-chip">undone</span>
        ) : result.commit_sha ? (
          <span className="file-micro-chip" style={{ background: "rgba(99, 102, 241, 0.2)", color: "#c7d2fe" }}>
            <GitCommit size={12} style={{ display: "inline", marginRight: "4px" }} />
            {result.commit_sha.slice(0, 7)}
          </span>
        ) : (
          <span className="file-micro-chip" title="This folder isn't a git repository, so the change was saved to disk but not committed.">
            saved, not committed
          </span>
        )}
      </button>

      {open && (
        <div className="change-card-body">
          <div className="onboarding-box" style={{ borderColor: result.reverted ? "var(--border)" : "var(--accent)" }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
              <h4 style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <CheckCircle2 size={18} color={result.reverted ? "var(--text-muted)" : "#34d399"} />
                {result.reverted ? "This change was undone" : "What changed"}
              </h4>
              {result.can_undo && (
                <button onClick={handleUndo} disabled={undoing} className="btn-secondary small" title="Put the files back as they were before this change">
                  <Undo2 size={13} />
                  <span>{undoing ? "Undoing…" : "Undo this change"}</span>
                </button>
              )}
            </div>
            <p style={{ fontSize: "0.95rem", margin: "0.5rem 0" }}><InlineText text={result.summary} /></p>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Files: {result.files_changed.join(", ")}</div>
            {undoError && <div className="quiz-feedback-box incorrect" style={{ marginTop: "0.6rem" }}>{undoError}</div>}

            {result.activity.length > 0 && (
              <div style={{ marginTop: "0.75rem" }}>
                <button className="link-btn" onClick={() => setShowLog((s) => !s)} aria-expanded={showLog}>
                  <ListChecks size={13} />
                  {showLog ? "Hide" : "Show"} how the assistant got there ({result.activity.length} steps)
                </button>
                {showLog && (
                  <ol className="activity-log">
                    {result.activity.map((a, i) => (
                      <li key={i} className={a.ok ? "" : "failed"}>
                        <span className="activity-icon">{ACTIVITY_ICON[a.kind] ?? <Eye size={13} />}</span>
                        <span>{a.label}</span>
                        {a.detail && <span className="activity-detail">{a.detail}</span>}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
          </div>

          {(result.concept_explanation || result.concept) && (
            <div className="onboarding-box concept-box">
              <h4 style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Lightbulb size={17} color="#fbbf24" />
                The idea behind it: {result.concept}
              </h4>
              {result.concept_explanation && <p style={{ fontSize: "0.9rem", marginTop: "0.4rem" }}><InlineText text={result.concept_explanation} /></p>}
            </div>
          )}

          <div className="onboarding-box">
            <h4 style={{ color: "#93c5fd" }}>Step by step: what, and why</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.75rem" }}>
              {result.steps.map((step, idx) => (
                <div key={idx} className="step-card">
                  <p style={{ fontSize: "0.88rem" }}><strong>What:</strong> <InlineText text={step.action} /></p>
                  <p style={{ fontSize: "0.84rem", color: "var(--text-secondary)", marginTop: "0.3rem" }}><strong>Why:</strong> <InlineText text={step.explanation} /></p>
                </div>
              ))}
            </div>
            {result.verify && (
              <p className="verify-line">
                <strong>Check it yourself:</strong> <InlineText text={result.verify} />
              </p>
            )}
          </div>

          {result.diffs.length > 0 && (
            <div>
              <h4 className="rail-heading" style={{ marginBottom: "0.25rem" }}>The exact lines that changed</h4>
              {result.diffs.map((d) => <DiffView key={d.path} diff={d} onOpenFile={onOpenFile} reverted={result.reverted} />)}
            </div>
          )}

          {quizzes.length > 0 ? (
            <InteractiveQuiz
              quizzes={quizzes}
              filePath={result.files_changed[0] ?? "the changed files"}
              onOpenDiscussion={onOpenDiscussion}
              onProgress={onProgress}
              title="Did the change make sense?"
            />
          ) : (
            <div className="notice-banner">
              <AlertTriangle size={16} />
              <span>{quizError ?? "No quiz was generated for this change."}</span>
              <button onClick={retryQuizzes} disabled={loadingQuiz} className="btn-secondary" style={{ marginLeft: "auto", fontSize: "0.78rem", padding: "0.25rem 0.6rem" }}>
                <RefreshCw size={13} /> {loadingQuiz ? "Generating…" : "Generate quiz"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const WORKING_STAGES = [
  "Looking around the repository…",
  "Reading the relevant files…",
  "Making the change…",
  "Writing up what it did and why…",
  "Preparing your questions…",
];

export const ErrorFixer: React.FC<ErrorFixerProps> = ({ repoId, onOpenDiscussion, onOpenFile, onRepoChanged, onProgress }) => {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<AssistantResponse[]>([]);
  const [latestId, setLatestId] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Earlier changes to this repo (so a refresh, or coming back later, loses nothing).
  useEffect(() => {
    let cancelled = false;
    setResults([]);
    setLatestId(null);
    getChanges(repoId)
      .then((rows) => !cancelled && setResults(rows))
      .catch((err) => !cancelled && setHistoryError(errorMessage(err, "Couldn't load earlier changes.")));
    return () => {
      cancelled = true;
    };
  }, [repoId]);

  // The request is one long call; walk through what it is typically doing so the wait reads
  // as progress rather than a frozen screen. (Indicative only - the real log arrives with the result.)
  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const timer = setInterval(() => setStage((s) => Math.min(s + 1, WORKING_STAGES.length - 1)), 6000);
    return () => clearInterval(timer);
  }, [loading]);

  async function handleFix(selected?: string) {
    const query = (selected ?? prompt).trim();
    if (!query || loading) return;

    setLoading(true);
    setError(null);
    try {
      const result = await askAssistant(repoId, query);
      setResults((prev) => [result, ...prev]);
      setLatestId(result.change_id);
      setPrompt("");
      onRepoChanged();
    } catch (err) {
      setError(errorMessage(err, "The change couldn't be completed. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flowchart-container">
      <div style={{ marginBottom: "1.5rem" }}>
        <h3 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Wrench size={22} color="var(--accent)" />
          <span>Make a change with the assistant</span>
        </h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.25rem" }}>
          Describe a bug to fix or a feature to add. The assistant reads the repo, makes the change, shows you exactly which
          lines changed, explains <strong>what</strong> and <strong>why</strong>, then quizzes you so you learn from it.
          Every change is committed to the repository&apos;s git history and can be undone here.
        </p>
      </div>

      <div className="connect-card" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
        <form onSubmit={(e) => { e.preventDefault(); void handleFix(); }} className="input-group" style={{ marginTop: 0 }}>
          <input
            type="text"
            className="input-text"
            placeholder="e.g. In app/services/store.py, reject an empty item name with a clear error"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={loading}
            maxLength={2000}
            aria-label="Describe the change"
          />
          <button type="submit" className="btn-primary" disabled={loading || !prompt.trim()}>
            <Sparkles size={16} />
            <span>{loading ? "Working…" : "Make the change"}</span>
          </button>
        </form>
        <p className="hint-text" style={{ marginTop: "0.5rem" }}>
          The more specific you are (which file or function, and what should happen), the better the result.
        </p>

        <div style={{ marginTop: "0.75rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.4rem" }}>Or try one of these:</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {SAMPLE_PROMPTS.map((p) => (
              <button key={p} className="btn-secondary pill" onClick={() => handleFix(p)} disabled={loading}>
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="quiz-feedback-box incorrect" style={{ marginBottom: "1.5rem" }}>{error}</div>}

      {loading && (
        <div className="working-panel">
          <Wrench size={30} color="var(--accent)" style={{ animation: "spin 2s linear infinite" }} />
          <div>
            <h4>The assistant is working on the codebase</h4>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.88rem", marginTop: "0.25rem" }}>{WORKING_STAGES[stage]}</p>
            <p className="hint-text">This usually takes 20–60 seconds. You can use the other tabs meanwhile; your result will be here.</p>
          </div>
        </div>
      )}

      {historyError && <p className="hint-text">{historyError}</p>}

      {results.length > 0 && (
        <h4 className="rail-heading" style={{ marginBottom: "0.75rem" }}>
          {results.length === 1 ? "1 change" : `${results.length} changes`} in this repository
        </h4>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {results.map((r, i) => (
          <ResultCard
            key={r.change_id}
            result={r}
            defaultOpen={r.change_id === latestId || (latestId === null && i === 0 && !r.reverted)}
            onOpenDiscussion={onOpenDiscussion}
            onOpenFile={onOpenFile}
            onRepoChanged={onRepoChanged}
            onProgress={onProgress}
            onUpdate={(next) => setResults((prev) => prev.map((x) => (x.change_id === next.change_id ? next : x)))}
          />
        ))}
      </div>
    </div>
  );
};
