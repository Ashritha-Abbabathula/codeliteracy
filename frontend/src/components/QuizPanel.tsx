import { useEffect, useState } from "react";

import {
  ApiError,
  QuizPublic,
  ResourceRecommendation,
  generateQuiz,
  retryQuiz,
  submitQuizAnswer,
} from "../api/client";

interface QuizPanelProps {
  changeId: string;
}

interface Result {
  correct: boolean;
  correctIndex: number;
  resource: ResourceRecommendation | null;
}

/** FR8: shown right after the assistant finishes a fix/feature, to check the concept
 * actually landed rather than just letting the user watch the change happen.
 * FR9 + FR10: a wrong answer surfaces a resource to review, then lets the user retake
 * with a fresh question on the same concept. */
export function QuizPanel({ changeId }: QuizPanelProps) {
  const [quiz, setQuiz] = useState<QuizPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    generateQuiz(changeId)
      .then(setQuiz)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to generate a quiz."));
  }, [changeId]);

  async function handleSubmit() {
    if (!quiz || selected === null) return;
    setSubmitting(true);
    try {
      const answer = await submitQuizAnswer(quiz.quiz_id, selected);
      setResult({ correct: answer.correct, correctIndex: answer.correct_index, resource: answer.resource });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit your answer.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRetry() {
    if (!quiz) return;
    setRetrying(true);
    try {
      const fresh = await retryQuiz(quiz.quiz_id);
      setQuiz(fresh);
      setSelected(null);
      setResult(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load a retry question.");
    } finally {
      setRetrying(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!quiz) return <p className="hint">Preparing a quick check…</p>;

  return (
    <div className="quiz-panel">
      <h4>Quick check: {quiz.concept}</h4>
      <p>{quiz.question}</p>
      <ul className="quiz-options">
        {quiz.options.map((option, i) => (
          <li key={i}>
            <label
              className={
                result
                  ? i === result.correctIndex
                    ? "correct"
                    : i === selected
                      ? "incorrect"
                      : ""
                  : ""
              }
            >
              <input
                type="radio"
                name={`quiz-${quiz.quiz_id}`}
                checked={selected === i}
                disabled={result !== null}
                onChange={() => setSelected(i)}
              />
              {option}
            </label>
          </li>
        ))}
      </ul>

      {!result && (
        <button onClick={handleSubmit} disabled={selected === null || submitting}>
          {submitting ? "Checking…" : "Submit answer"}
        </button>
      )}

      {result && (
        <>
          <p className={result.correct ? "quiz-feedback correct" : "quiz-feedback incorrect"}>
            {result.correct ? "Correct!" : "Not quite — the highlighted option was right."}
          </p>

          {!result.correct && result.resource && (
            <div className="resource-card">
              <p className="resource-title">{result.resource.title}</p>
              <p>{result.resource.description}</p>
              <a href={result.resource.url} target="_blank" rel="noopener noreferrer">
                Look it up
              </a>
            </div>
          )}

          {!result.correct && (
            <button onClick={handleRetry} disabled={retrying}>
              {retrying ? "Loading…" : "Try again"}
            </button>
          )}
        </>
      )}
    </div>
  );
}
