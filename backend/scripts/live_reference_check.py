"""Ask the real AI tutor a set of questions about a repository and count how many files and line ranges it cites that really exist.

Run from the backend folder, with GEMINI_API_KEY in backend/.env:
    python scripts/live_reference_check.py [repo_path]        # default: this backend folder

Writes eval_results/tutor_references.json (every reply, every reference, which ones were not real, and the overall rate).
The questions are about this very repository, so every cited path can be checked against the files on disk.
"""
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.chat_service import ChatError, chat_with_tutor  # noqa: E402
from app.services.eval_checks import check_references, hallucinated_reference_rate  # noqa: E402

QUESTIONS = [
    "How does the assistant make sure it only changes files inside the connected repository?",
    "Where are the quiz questions generated and how are they validated?",
    "How does the tutor chat decide which files to show the model?",
    "What happens when the Gemini API is rate limited?",
    "How is a user's data kept separate from other users?",
    "Where does the dependency graph come from and how are imports found?",
    "What does the assistant do when its edit would create a Python syntax error?",
    "How are changes undone after the assistant edits files?",
    "Which function builds the repository digest and what is in it?",
    "Where are passwords or tokens handled, and how?",
]


def main() -> None:
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND
    results, replies = [], []
    for q in QUESTIONS:
        try:
            out = chat_with_tutor(str(repo), q)
        except ChatError as exc:
            print("tutor unavailable:", exc)
            continue
        check = check_references(repo, out["reply"])
        results.append(check)
        replies.append({"question": q, "reply": out["reply"], **check})
        print(f"{check['valid']}/{check['cited']} references real :: {q[:70]}", flush=True)
        time.sleep(3)
    summary = {"repo": repo.name, "n_replies": len(results), "references_cited": sum(r["cited"] for r in results),
               "references_not_real": sum(len(r["bad"]) for r in results), "hallucinated_reference_rate": hallucinated_reference_rate(results),
               "note": "small set of 10 questions about this repository; indicative only", "replies": replies}
    out_dir = BACKEND / "eval_results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "tutor_references.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print({k: v for k, v in summary.items() if k != "replies"})


if __name__ == "__main__":
    main()
