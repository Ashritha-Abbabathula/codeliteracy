import React, { useEffect, useRef, useState } from "react";
import { FileCode, RotateCcw, Send, X } from "lucide-react";
import {
  ChatMessageContext,
  clearChatHistory,
  errorMessage,
  getChatHistory,
  MessageItem,
  sendChatMessage,
} from "../api/client";
import { RichText } from "./RichText";

interface TutorChatDrawerProps {
  repoId: string;
  isOpen: boolean;
  onClose: () => void;
  /** What the learner is looking at (a quiz question, a file, some selected lines); sent with every message. */
  activeContext?: ChatMessageContext | null;
  onOpenFile: (path: string) => void;
}

interface Message extends MessageItem {
  sources?: string[];
}

const WELCOME: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "Hi! I'm your code tutor for this repository. I can see its files, so ask me how something works, where something lives, or what to read next. If you have a file open, I'll look at that one first.",
  context_type: "general",
  created_at: "",
};

const QUIZ_CHIPS = ["Why is my choice incorrect?", "Walk me through the relevant code", "Explain it in simpler terms"];
const OPEN_QUIZ_CHIPS = ["Which lines should I look at?", "Explain the concept without the answer"];
const GENERAL_CHIPS = ["What should I read first?", "How do the main parts fit together?", "Where does execution start?"];
const FILE_CHIPS = ["What is this file's job?", "Which part of this file matters most?", "How do other files use this one?"];

export const TutorChatDrawer: React.FC<TutorChatDrawerProps> = ({ repoId, isOpen, onClose, activeContext, onOpenFile }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [followups, setFollowups] = useState<string[]>([]);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const introducedContext = useRef<ChatMessageContext | null>(null);

  // A different repository is a different conversation.
  useEffect(() => {
    setMessages([]);
    setLoadedFor(null);
    setFollowups([]);
    setError(null);
    introducedContext.current = null;
  }, [repoId]);

  // Load history once per repo, the first time the drawer opens.
  useEffect(() => {
    if (!isOpen || loadedFor === repoId) return;
    let cancelled = false;
    getChatHistory(repoId)
      .then((history) => {
        if (cancelled) return;
        setMessages(history.length ? history : [WELCOME]);
        setFollowups(history.length ? [] : GENERAL_CHIPS);
      })
      .catch(() => {
        if (!cancelled) setMessages([WELCOME]);
      })
      .finally(() => {
        if (!cancelled) setLoadedFor(repoId);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, repoId, loadedFor]);

  // Lead into a quiz/selection discussion - but only after history has loaded, or it would be overwritten.
  useEffect(() => {
    if (!isOpen || loadedFor !== repoId || !activeContext || introducedContext.current === activeContext) return;
    introducedContext.current = activeContext;
    const intro = (content: string, context_type: string) =>
      setMessages((prev) => [
        ...prev,
        { id: `context-${Date.now()}`, role: "assistant", content, context_type, created_at: new Date().toISOString() },
      ]);

    if (activeContext.context_type === "quiz_discussion" && activeContext.question) {
      const open = !activeContext.correct_answer;
      const parts = [
        `Let's talk about this question: **${activeContext.question}**`,
        activeContext.user_answer && `You chose: "${activeContext.user_answer}"`,
        activeContext.correct_answer && `The correct answer is: "${activeContext.correct_answer}"`,
        open
          ? "You still have a try left, so I won't tell you the answer. Ask me about the code or the idea and I'll help you work it out."
          : "What would you like clarified?",
      ].filter(Boolean);
      intro(parts.join("\n\n"), "quiz_discussion");
      setFollowups(open ? OPEN_QUIZ_CHIPS : QUIZ_CHIPS);
    } else if (activeContext.context_type === "file_explainer" && activeContext.selection) {
      intro(`We're looking at \`${activeContext.file_path ?? "this file"}\`, ${activeContext.selection}. What would you like to know about it?`, "file_explainer");
      setFollowups(["Explain this in simpler terms", "Why is it written this way?", "Show me a small example of it running"]);
    } else if (activeContext.file_path) {
      setFollowups(FILE_CHIPS);
    }
  }, [isOpen, loadedFor, repoId, activeContext]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  async function handleSend(text?: string) {
    const message = (text ?? input).trim();
    if (!message || loading) return;

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: message, context_type: activeContext?.context_type ?? "general", created_at: new Date().toISOString() },
    ]);
    setInput("");
    setError(null);
    setFollowups([]);
    setLoading(true);

    try {
      const res = await sendChatMessage(repoId, message, activeContext ?? undefined);
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`, role: "assistant", content: res.reply, sources: res.sources,
          context_type: activeContext?.context_type ?? "general", created_at: new Date().toISOString(),
        },
      ]);
      setFollowups(res.suggested_followups);
    } catch (err) {
      // Give the learner their message back so they can simply resend it.
      setMessages((prev) => prev.slice(0, -1));
      setInput(message);
      setError(errorMessage(err, "The tutor couldn't reply. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  async function handleClear() {
    if (!window.confirm("Start a new conversation? The current one will be cleared.")) return;
    try {
      await clearChatHistory(repoId);
      introducedContext.current = activeContext ?? null;
      setMessages([WELCOME]);
      setFollowups(activeContext?.file_path ? FILE_CHIPS : GENERAL_CHIPS);
      setError(null);
    } catch (err) {
      setError(errorMessage(err, "Couldn't clear the conversation."));
    }
  }

  const lookingAt = activeContext?.file_path
    ? `${activeContext.file_path}${activeContext.start_line ? ` · lines ${activeContext.start_line}–${activeContext.end_line}` : ""}`
    : null;

  return (
    <div className="chat-drawer" role="dialog" aria-label="AI tutor chat">
      <div className="chat-drawer-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div className="logo-badge" style={{ width: "24px", height: "24px", fontSize: "0.8rem" }}>🤖</div>
          <strong style={{ fontSize: "0.92rem" }}>Code tutor</strong>
        </div>
        <div style={{ display: "flex", gap: "0.35rem" }}>
          <button onClick={handleClear} className="btn-secondary icon-btn" title="Start a new conversation" aria-label="Start a new conversation">
            <RotateCcw size={14} />
          </button>
          <button onClick={onClose} className="btn-secondary icon-btn" title="Close chat (Esc)" aria-label="Close chat">
            <X size={16} />
          </button>
        </div>
      </div>

      {lookingAt && (
        <div className="chat-context-bar" title="The tutor is shown this file with every message">
          <FileCode size={13} />
          <span className="ellipsis">Looking at {lookingAt}</span>
        </div>
      )}

      <div className="chat-drawer-body">
        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble ${m.role}`}>
            {m.role === "assistant" ? <RichText text={m.content} /> : <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>}
            {m.sources && m.sources.length > 0 && (
              <div className="chat-sources">
                <span>Based on</span>
                {m.sources.map((s) => (
                  <button key={s} className="file-micro-chip as-button" onClick={() => onOpenFile(s)} title={`Open ${s} in the inspector`}>
                    {s.slice(s.lastIndexOf("/") + 1)}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="chat-bubble assistant" style={{ fontStyle: "italic", opacity: 0.8 }}>
            Reading the code and thinking…
          </div>
        )}

        {error && <div className="quiz-feedback-box incorrect">{error}</div>}

        {followups.length > 0 && !loading && (
          <div>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
              You could ask:
            </span>
            <div className="followup-chips">
              {followups.map((chip, idx) => (
                <button key={idx} className="followup-chip" onClick={() => handleSend(chip)}>
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="chat-drawer-footer">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSend();
          }}
          style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}
        >
          <textarea
            ref={inputRef}
            className="input-text chat-input"
            rows={Math.min(4, Math.max(1, input.split("\n").length))}
            placeholder="Ask about this code…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void handleSend();
              }
            }}
            disabled={loading}
            maxLength={4000}
            aria-label="Message the tutor"
          />
          <button type="submit" className="btn-primary" style={{ padding: "0.55rem 0.75rem" }} disabled={loading || !input.trim()} title="Send">
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  );
};
