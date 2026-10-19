import React, { useState } from "react";
import { ArrowRight, BookCheck, CheckCircle2, ExternalLink, Lightbulb, MessageSquare, RefreshCw, Sparkles, XCircle } from "lucide-react";
import {
  answerQuiz,
  ChatMessageContext,
  errorMessage,
  QuizAnswerResponse,
  QuizItem,
  retryQuiz,
} from "../api/client";
import { useAuth } from "../context/AuthContext";
import { InlineText } from "./RichText";

interface InteractiveQuizProps {
  quizzes: QuizItem[];
  /** The file (or changed file) these questions are about; passed to the tutor for context. */
  filePath: string;
  onOpenDiscussion: (context: ChatMessageContext) => void;
  /** Called after an answer is recorded, so progress shown elsewhere can refresh. */
  onProgress?: () => void;
  title?: string;
}

/** What the learner has done with one question so far. */
interface Progress {
  eliminated: number[];
  hint: string | null;
  /** feedback from a first wrong try (the question is still open) */
  nudge: QuizAnswerResponse | null;
  /** set once the question is closed */
  review: QuizAnswerResponse | null;
}

const fromItem = (q: QuizItem): Progress => ({
  eliminated: q.eliminated ?? [],
  hint: q.hint ?? null,
  nudge: null,
  review: q.review ?? null,
});

const letter = (i: number) => String.fromCharCode(65 + i);

/** Comprehension questions, checked on the server (which also credits the learning notebook,
 * once, for a genuinely correct answer).
 *
 * A learner gets two tries. A first wrong answer is met with *why that option is wrong* and a
 * hint, not the answer, so the second try is still thinking. After a second miss the answer
 * and its explanation are shown with something to read, and they can discuss it with the
 * tutor or ask for a fresh question on the same concept. */
export const InteractiveQuiz: React.FC<InteractiveQuizProps> = ({ quizzes, filePath, onOpenDiscussion, onProgress, title }) => {
  const { user, refreshUser } = useAuth();
  const [items, setItems] = useState<QuizItem[]>(quizzes);
  const [progress, setProgress] = useState<Record<string, Progress>>(() =>
    Object.fromEntries(quizzes.map((q) => [q.id, fromItem(q)]))
  );
  const [pending, setPending] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  if (!items.length) return null;

  function discussionContext(quiz: QuizItem, selected: number, result: QuizAnswerResponse): ChatMessageContext {
    return {
      context_type: "quiz_discussion",
      file_path: filePath,
      question: quiz.question,
      user_answer: quiz.options[selected],
      // Only once the question is closed: before that the tutor mustn't be handed the answer.
      correct_answer: result.final && result.correct_index !== null ? quiz.options[result.correct_index] : undefined,
      explanation: (result.final ? result.explanation : result.option_feedback) ?? undefined,
    };
  }

  async function handleSelect(quiz: QuizItem, optionIndex: number) {
    const state = progress[quiz.id] ?? fromItem(quiz);
    if (state.review || pending || state.eliminated.includes(optionIndex)) return;
    setPending(quiz.id);
    setErrors((prev) => ({ ...prev, [quiz.id]: "" }));
    try {
      const result = await answerQuiz(quiz.id, optionIndex);
      setProgress((prev) => ({
        ...prev,
        [quiz.id]: result.final
          ? { ...state, nudge: null, review: result }
          : { eliminated: [...state.eliminated, optionIndex], hint: result.hint ?? null, nudge: result, review: null },
      }));
      if (result.saved_to_notebook && user) void refreshUser();
      onProgress?.();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [quiz.id]: errorMessage(err, "Couldn't check that answer. Please try again.") }));
    } finally {
      setPending(null);
    }
  }

  async function handleRetry(quiz: QuizItem) {
    setRetrying(quiz.id);
    setErrors((prev) => ({ ...prev, [quiz.id]: "" }));
    try {
      const fresh = await retryQuiz(quiz.id);
      setItems((prev) => prev.map((q) => (q.id === quiz.id ? fresh : q)));
      setProgress((prev) => {
        const { [quiz.id]: _dropped, ...rest } = prev;
        return { ...rest, [fresh.id]: fromItem(fresh) };
      });
      onProgress?.();
    } catch (err) {
      setErrors((prev) => ({ ...prev, [quiz.id]: errorMessage(err, "Couldn't load a new question. Please try again.") }));
    } finally {
      setRetrying(null);
    }
  }

  const closedCount = items.filter((q) => progress[q.id]?.review).length;
  const correctCount = items.filter((q) => progress[q.id]?.review?.correct).length;

  return (
    <div className="quiz-section-container">
      <div className="quiz-heading-row">
        <div>
          <h3 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Sparkles size={20} color="var(--accent)" />
            <span>{title ?? "Check your understanding"} ({items.length} questions)</span>
          </h3>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            About <code className="inline-code">{filePath}</code>. You get two tries per question: a first miss earns a hint, not the answer.{" "}
            {user
              ? "Correct answers are saved to your Learning Notebook."
              : "Sign in (or use the guest demo) to keep correct answers in your own Learning Notebook."}
          </p>
        </div>
        {closedCount > 0 && (
          <div className="score-pill">
            Score: <strong>{correctCount} / {items.length}</strong>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        {items.map((quiz, qIdx) => {
          const state = progress[quiz.id] ?? fromItem(quiz);
          const review = state.review;
          const isCorrect = review?.correct;
          const selected = review?.selected_index ?? null;
          const busy = pending === quiz.id;

          return (
            <div key={quiz.id} className="quiz-card">
              <div className="quiz-card-top">
                <span className="tech-tag" style={{ background: "rgba(99, 102, 241, 0.2)", color: "#c7d2fe" }}>
                  Question {qIdx + 1} of {items.length} · {quiz.concept}
                </span>
                {review ? (
                  <span style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem", color: isCorrect ? "#34d399" : "#f87171" }}>
                    {isCorrect ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                    {isCorrect ? "Correct" : "Answer revealed"}
                  </span>
                ) : state.eliminated.length > 0 ? (
                  <span style={{ fontSize: "0.8rem", color: "var(--warning)" }}>One try left</span>
                ) : null}
              </div>

              <h4><InlineText text={quiz.question} /></h4>

              <div className="quiz-options-list" role="radiogroup" aria-label={quiz.question}>
                {quiz.options.map((opt, optIdx) => {
                  const eliminated = state.eliminated.includes(optIdx);
                  let status = "";
                  if (review) {
                    if (optIdx === review.correct_index) status = "correct";
                    else if (optIdx === selected || eliminated) status = "incorrect";
                  } else if (eliminated) status = "incorrect eliminated";
                  return (
                    <button
                      key={optIdx}
                      className={`quiz-option-btn ${status}`}
                      onClick={() => handleSelect(quiz, optIdx)}
                      disabled={!!review || pending !== null || eliminated}
                      role="radio"
                      aria-checked={selected === optIdx}
                    >
                      <span className="option-letter">{letter(optIdx)}.</span>
                      <span><InlineText text={opt} /></span>
                    </button>
                  );
                })}
              </div>

              {busy && <p className="hint-text">Checking your answer…</p>}
              {errors[quiz.id] && <div className="quiz-feedback-box incorrect" style={{ marginTop: "0.75rem" }}>{errors[quiz.id]}</div>}

              {/* First miss: teach, don't tell. */}
              {!review && state.eliminated.length > 0 && (
                <div className="quiz-feedback-box hint">
                  <p style={{ fontWeight: 600, marginBottom: "0.3rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <Lightbulb size={16} />
                    Not that one. Have another go.
                  </p>
                  {state.nudge?.option_feedback && (
                    <p style={{ fontSize: "0.86rem" }}>
                      <strong>Why {letter(state.eliminated[state.eliminated.length - 1])} isn&apos;t it:</strong> <InlineText text={state.nudge.option_feedback} />
                    </p>
                  )}
                  {state.hint && (
                    <p style={{ fontSize: "0.86rem", marginTop: "0.3rem" }}>
                      <strong>Hint:</strong> <InlineText text={state.hint} />
                    </p>
                  )}
                  {!state.hint && !state.nudge?.option_feedback && (
                    <p style={{ fontSize: "0.86rem" }}>Re-read the code this question is about, then pick again.</p>
                  )}
                  <button
                    onClick={() =>
                      onOpenDiscussion(
                        discussionContext(quiz, state.eliminated[state.eliminated.length - 1], state.nudge ?? { correct: false, final: false, selected_index: null, correct_index: null, resource: null, saved_to_notebook: false, attempts_left: 1 })
                      )
                    }
                    className="link-btn"
                    style={{ marginTop: "0.5rem" }}
                  >
                    <MessageSquare size={13} /> Stuck? Ask the tutor (it won&apos;t give the answer away)
                  </button>
                </div>
              )}

              {review && (
                <div>
                  <div className={`quiz-feedback-box ${isCorrect ? "correct" : "incorrect"}`}>
                    <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                      {isCorrect
                        ? state.eliminated.length > 0 ? "Got it on the second try." : "Spot on!"
                        : review.correct_index !== null
                          ? `The answer is ${letter(review.correct_index)}.`
                          : "Not quite."}
                    </p>
                    {!isCorrect && review.option_feedback && (
                      <p style={{ fontSize: "0.85rem", marginBottom: "0.35rem" }}>
                        <strong>Your choice{selected !== null ? ` (${letter(selected)})` : ""}:</strong> <InlineText text={review.option_feedback} />
                      </p>
                    )}
                    {review.explanation && <p style={{ fontSize: "0.85rem", opacity: 0.95 }}><InlineText text={review.explanation} /></p>}
                    {review.saved_to_notebook && (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.5rem", fontSize: "0.78rem", color: "#6ee7b7" }}>
                        <BookCheck size={14} />
                        <span>Saved to your Learning Notebook</span>
                      </div>
                    )}
                  </div>

                  {!isCorrect && (
                    <>
                      {review.resource && (
                        <div className="resource-card">
                          <strong>{review.resource.title}</strong>
                          <p>{review.resource.description}</p>
                          <a href={review.resource.url} target="_blank" rel="noopener noreferrer">
                            Look it up <ExternalLink size={12} style={{ display: "inline", verticalAlign: "-1px" }} />
                          </a>
                        </div>
                      )}
                      <div className="discuss-cta" style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                        <button
                          onClick={() => onOpenDiscussion(discussionContext(quiz, selected ?? 0, review))}
                          className="btn-primary"
                          style={{ fontSize: "0.84rem", padding: "0.45rem 0.9rem" }}
                        >
                          <MessageSquare size={15} />
                          <span>Discuss with the AI tutor</span>
                          <ArrowRight size={14} />
                        </button>
                        <button
                          onClick={() => handleRetry(quiz)}
                          className="btn-secondary"
                          style={{ fontSize: "0.84rem", padding: "0.45rem 0.9rem" }}
                          disabled={retrying === quiz.id}
                        >
                          <RefreshCw size={14} />
                          <span>{retrying === quiz.id ? "Writing a new question…" : "Try a fresh question on this concept"}</span>
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
