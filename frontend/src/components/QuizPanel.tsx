import { useEffect, useState } from "react";

import { ApiError, QuizPublic, generateQuiz, submitQuizAnswer } from "../api/client";

interface QuizPanelProps {
  changeId: string;
}

/** FR8: shown right after the assistant finishes a fix/feature, to check the concept
 * actually landed rather than just letting the user watch the change happen. */
export function QuizPanel({ changeId }: QuizPanelProps) {
  const [quiz, setQuiz] = useState<QuizPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [result, setResult] = useState<{ correct: boolean; correctIndex: number } | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
      setResult({ correct: answer.correct, correctIndex: answer.correct_index });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to submit your answer.");
    } finally {
      setSubmitting(false);
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
        <p className={result.correct ? "quiz-feedback correct" : "quiz-feedback incorrect"}>
          {result.correct ? "Correct!" : "Not quite — the highlighted option was right."}
        </p>
      )}
    </div>
  );
}
