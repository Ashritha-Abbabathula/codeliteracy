import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, MessageSquare, RefreshCw, Sparkles } from "lucide-react";
import {
  ArchitectureFlowchart as FlowchartData,
  ChatMessageContext,
  errorMessage,
  FileDetailsResponse,
  getFileDetails,
  getRepoFiles,
  getRepoFlowchart,
  getRepoInfo,
  getRepoOnboarding,
  getRepoProgress,
  RepoFile,
  RepoInfo,
  RepoOnboarding,
  RepoProgress,
} from "../api/client";
import { TutorGreeting } from "../components/TutorGreeting";
import { ArchitectureFlowchart } from "../components/ArchitectureFlowchart";
import { CodeInspector } from "../components/CodeInspector";
import { ErrorFixer } from "../components/ErrorFixer";
import { TutorChatDrawer } from "../components/TutorChatDrawer";

type ActiveTab = "onboarding" | "flowchart" | "code_inspector" | "fix_errors";

const TAB_IDS: Record<string, ActiveTab> = { overview: "onboarding", map: "flowchart", code: "code_inspector", change: "fix_errors" };
const TAB_SLUG: Record<ActiveTab, string> = { onboarding: "overview", flowchart: "map", code_inspector: "code", fix_errors: "change" };

interface Loadable<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const idle = <T,>(): Loadable<T> => ({ data: null, loading: false, error: null });

export const RepoView: React.FC = () => {
  const { repoId } = useParams<{ repoId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  // The tab and open file live in the URL, so a refresh (or a shared link) lands where you were.
  const activeTab: ActiveTab = TAB_IDS[searchParams.get("tab") ?? ""] ?? "onboarding";
  const filePath = searchParams.get("file");

  const [info, setInfo] = useState<Loadable<RepoInfo>>(idle);
  const [onboarding, setOnboarding] = useState<Loadable<RepoOnboarding>>(idle);
  const [flowchart, setFlowchart] = useState<Loadable<FlowchartData>>(idle);
  const [file, setFile] = useState<Loadable<FileDetailsResponse>>(idle);
  const [files, setFiles] = useState<RepoFile[]>([]);
  const [progress, setProgress] = useState<RepoProgress | null>(null);
  // Tabs are mounted the first time they're opened and then kept (hidden), so switching tabs
  // never throws away a half-finished quiz, an assistant result, or your place in a file.
  const [visited, setVisited] = useState<Set<ActiveTab>>(new Set([activeTab]));

  const [chatOpen, setChatOpen] = useState(false);
  const [chatContext, setChatContext] = useState<ChatMessageContext | null>(null);

  // Ignore responses that arrive after the user has moved on to another repo or file.
  const generation = useRef(0);
  const fileRequest = useRef(0);
  const loadedFile = useRef<string | null>(null);

  const go = useCallback(
    (tab: ActiveTab, nextFile?: string | null) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (tab === "onboarding") next.delete("tab");
          else next.set("tab", TAB_SLUG[tab]);
          if (nextFile === null) next.delete("file");
          else if (nextFile) next.set("file", nextFile);
          return next;
        },
        { replace: false }
      );
    },
    [setSearchParams]
  );

  useEffect(() => {
    setVisited((prev) => (prev.has(activeTab) ? prev : new Set(prev).add(activeTab)));
  }, [activeTab]);

  // A different repository: start from a clean slate.
  useEffect(() => {
    generation.current += 1;
    loadedFile.current = null;
    setInfo(idle);
    setOnboarding(idle);
    setFlowchart(idle);
    setFile(idle);
    setFiles([]);
    setProgress(null);
    setVisited(new Set([activeTab]));
    setChatOpen(false);
    setChatContext(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  const loadInfo = useCallback(() => {
    if (!repoId) return;
    const gen = generation.current;
    getRepoInfo(repoId)
      .then((data) => gen === generation.current && setInfo({ data, loading: false, error: null }))
      .catch((err) => gen === generation.current && setInfo({ data: null, loading: false, error: errorMessage(err, "Couldn't load this repository.") }));
  }, [repoId]);

  const loadOnboarding = useCallback(() => {
    if (!repoId) return;
    const gen = generation.current;
    setOnboarding({ data: null, loading: true, error: null });
    getRepoOnboarding(repoId)
      .then((data) => gen === generation.current && setOnboarding({ data, loading: false, error: null }))
      .catch((err) => gen === generation.current && setOnboarding({ data: null, loading: false, error: errorMessage(err, "Couldn't analyze this repository.") }));
  }, [repoId]);

  const loadFlowchart = useCallback(() => {
    if (!repoId) return;
    const gen = generation.current;
    setFlowchart((prev) => ({ data: prev.data, loading: true, error: null }));
    getRepoFlowchart(repoId)
      .then((data) => gen === generation.current && setFlowchart({ data, loading: false, error: null }))
      .catch((err) => gen === generation.current && setFlowchart({ data: null, loading: false, error: errorMessage(err, "Couldn't build the flowchart.") }));
  }, [repoId]);

  /** Files (with what's been explored/solved) and the overall progress numbers. */
  const refreshProgress = useCallback(() => {
    if (!repoId) return;
    const gen = generation.current;
    getRepoFiles(repoId).then((rows) => gen === generation.current && setFiles(rows)).catch(() => {});
    getRepoProgress(repoId).then((p) => gen === generation.current && setProgress(p)).catch(() => {});
  }, [repoId]);

  const loadFile = useCallback(
    (path: string) => {
      if (!repoId) return;
      const gen = generation.current;
      const req = ++fileRequest.current;
      loadedFile.current = path;
      setFile({ data: null, loading: true, error: null });
      getFileDetails(repoId, path)
        .then((data) => {
          if (gen !== generation.current || req !== fileRequest.current) return;
          setFile({ data, loading: false, error: null });
          refreshProgress();
        })
        .catch((err) => gen === generation.current && req === fileRequest.current && setFile({ data: null, loading: false, error: errorMessage(err, "Couldn't analyze this file.") }));
    },
    [repoId, refreshProgress]
  );

  useEffect(() => {
    loadInfo();
    loadOnboarding();
    refreshProgress();
  }, [loadInfo, loadOnboarding, refreshProgress]);

  // The flowchart is a separate AI call, so build it when it's first wanted.
  useEffect(() => {
    if (activeTab === "flowchart" && !flowchart.data && !flowchart.loading && !flowchart.error) loadFlowchart();
  }, [activeTab, flowchart, loadFlowchart]);

  // Open whatever file the URL names (first visit, refresh, back/forward).
  useEffect(() => {
    if (activeTab === "code_inspector" && filePath && filePath !== loadedFile.current) loadFile(filePath);
    if (!filePath && loadedFile.current) {
      loadedFile.current = null;
      fileRequest.current += 1;
      setFile(idle);
    }
  }, [activeTab, filePath, loadFile]);

  const openFile = useCallback((path: string) => go("code_inspector", path), [go]);

  /** A change was applied or undone: everything derived from the code may be out of date. */
  const handleRepoChanged = useCallback(() => {
    setFlowchart(idle);
    refreshProgress();
    if (loadedFile.current) {
      // Re-read the open file the next time the inspector shows it (its content may have changed).
      const path = loadedFile.current;
      loadedFile.current = null;
      if (activeTab === "code_inspector") loadFile(path);
    }
  }, [activeTab, loadFile, refreshProgress]);

  function handleOpenDiscussion(context: ChatMessageContext) {
    setChatContext({ ...context }); // a fresh object each time, so the drawer introduces it again
    setChatOpen(true);
  }

  function toggleChat() {
    if (!chatOpen) {
      // Opened from the floating button: tell the tutor what's on screen, without starting a
      // new topic if a discussion is already going.
      const openPath = activeTab === "code_inspector" ? file.data?.file_path : undefined;
      if (openPath && chatContext?.file_path !== openPath) setChatContext({ context_type: "general", file_path: openPath });
      else if (!openPath && chatContext && chatContext.context_type !== "quiz_discussion") setChatContext(null);
    }
    setChatOpen((open) => !open);
  }

  const exploredPaths = useMemo(() => new Set(files.filter((f) => f.explored).map((f) => f.path)), [files]);
  const learningPath = onboarding.data?.learning_path ?? [];

  if (info.error) {
    return (
      <div className="flowchart-container center-state">
        <AlertTriangle size={32} color="var(--warning)" style={{ margin: "0 auto 0.75rem" }} />
        <p className="error-text">{info.error}</p>
        <div style={{ display: "flex", gap: "0.6rem", justifyContent: "center", marginTop: "1rem" }}>
          <button onClick={loadInfo} className="btn-primary"><RefreshCw size={15} /><span>Try again</span></button>
          <Link to="/" className="btn-secondary"><ArrowLeft size={15} /><span>All repositories</span></Link>
        </div>
      </div>
    );
  }

  const tabs: { id: ActiveTab; step: string; label: string; hint: string }[] = [
    { id: "onboarding", step: "1", label: "Overview", hint: "What this project is and where to start" },
    { id: "flowchart", step: "2", label: "Architecture map", hint: "How the modules depend on each other" },
    { id: "code_inspector", step: "3", label: "Read the code", hint: "Walkthroughs, line explanations and quizzes" },
    { id: "fix_errors", step: "4", label: "Make a change", hint: "Fix or add something with the AI assistant, and learn from it" },
  ];

  const pct = progress && progress.files_total ? Math.min(100, Math.round((progress.files_explored / progress.files_total) * 100)) : 0;

  return (
    <div>
      <div className="repo-header">
        <div className="repo-meta">
          <Link to="/" className="back-link"><ArrowLeft size={13} /> All repositories</Link>
          <h2>
            <Sparkles size={20} color="var(--accent)" />
            <span>{info.data?.name ?? "Repository workspace"}</span>
          </h2>
          {info.data && <span className="repo-source-sub" title={info.data.source}>{info.data.source}</span>}
        </div>

        <div className="repo-header-right">
          <div className="mode-tabs" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={activeTab === t.id}
                className={`tab-btn ${activeTab === t.id ? "active" : ""}`}
                onClick={() => go(t.id)}
                title={t.hint}
              >
                <span className="tab-step">{t.step}</span>
                {t.label}
              </button>
            ))}
          </div>
          {progress && (
            <div className="progress-strip" title="Your progress in this repository">
              <div className="progress-track" aria-hidden="true"><div style={{ width: `${pct}%` }} /></div>
              <span><strong>{progress.files_explored}</strong> of {progress.files_total} files read</span>
              <span><strong>{progress.questions_solved}</strong> of {progress.questions_total} questions solved</span>
              {progress.changes_made > 0 && <span><strong>{progress.changes_made}</strong> change{progress.changes_made === 1 ? "" : "s"} made</span>}
            </div>
          )}
        </div>
      </div>

      <div hidden={activeTab !== "onboarding"}>
        {visited.has("onboarding") && (
          <TutorGreeting
            onboarding={onboarding.data}
            loading={onboarding.loading}
            error={onboarding.error}
            onRetry={loadOnboarding}
            onViewFlowchart={() => go("flowchart")}
            onOpenFile={openFile}
            exploredPaths={exploredPaths}
          />
        )}
      </div>

      <div hidden={activeTab !== "flowchart"}>
        {visited.has("flowchart") && (
          <ArchitectureFlowchart
            flowchart={flowchart.data}
            loading={flowchart.loading && !flowchart.data}
            error={flowchart.error}
            onRetry={loadFlowchart}
            onInspectFile={openFile}
          />
        )}
      </div>

      <div hidden={activeTab !== "code_inspector"}>
        {visited.has("code_inspector") && repoId && (
          <CodeInspector
            repoId={repoId}
            files={files}
            learningPath={learningPath}
            activePath={filePath}
            fileDetails={file.data}
            loading={file.loading}
            error={file.error}
            onRetry={() => filePath && loadFile(filePath)}
            onOpenFile={openFile}
            onBackToFlowchart={() => go("flowchart")}
            onOpenDiscussion={handleOpenDiscussion}
            onProgress={refreshProgress}
          />
        )}
      </div>

      <div hidden={activeTab !== "fix_errors"}>
        {visited.has("fix_errors") && repoId && (
          <ErrorFixer
            repoId={repoId}
            onOpenDiscussion={handleOpenDiscussion}
            onOpenFile={openFile}
            onRepoChanged={handleRepoChanged}
            onProgress={refreshProgress}
          />
        )}
      </div>

      {!chatOpen && (
        <button onClick={toggleChat} className="btn-primary chat-fab" aria-label="Ask the tutor">
          <MessageSquare size={18} />
          <span>Ask the tutor</span>
        </button>
      )}

      {repoId && (
        <TutorChatDrawer
          repoId={repoId}
          isOpen={chatOpen}
          onClose={() => setChatOpen(false)}
          activeContext={chatContext}
          onOpenFile={openFile}
        />
      )}
    </div>
  );
};
