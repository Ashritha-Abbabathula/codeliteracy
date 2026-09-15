# Software Requirements Specification (SRS)

**CodeLiteracy: An Adaptive Learning System for Sustained Developer Comprehension in
AI-Assisted Software Engineering**

Prepared by: Abbabathula Ashritha | Date: July 18, 2026

## 1. Introduction

### 1.1 Purpose of this Document

This document defines the functional and non-functional requirements of CodeLiteracy, a tool
that helps a developer understand an unfamiliar GitHub repository and then make changes to it
with AI assistance — without letting the AI do the thinking for them. The purpose is to specify
exactly what the system must do so that development can proceed sprint by sprint against a
clear, agreed target.

### 1.2 Scope of this Document

CodeLiteracy covers two connected capabilities. First, repository analysis: cloning a repo and
presenting its structure back to the user as a dependency flowchart or a plain-language
walkthrough, so the user has context before touching any code. Second, AI-assisted development:
when the assistant fixes a bug or adds a feature, it explains the commands it runs and the
reasoning behind key decisions, then quizzes the user on the concept. Wrong answers trigger a
learning-resource suggestion and a retry; correct answers get saved to a personal learning
notebook. Out of scope for the initial version: multi-repository/team collaboration features,
support for languages beyond the initial target stack, and fully autonomous changes made without
any explanation step.

### 1.3 Overview

The rest of this document describes the system's expected behaviour, its interfaces, performance
targets, constraints, and the schedule and budget for building it across the semester.

## 2. General Description

- The system provides a single user role — a developer/learner — working against their own
  connected repository.
- Core objective: reduce the time it takes to understand an unfamiliar codebase, while making
  sure AI-assisted fixes actually build the user's understanding instead of replacing it.
- User characteristic: student developers, junior engineers, or solo developers joining or
  returning to a codebase they don't fully know.
- Key benefit: faster onboarding to a repo, less "blind trust" in AI-generated changes, and a
  growing personal record (the notebook) of concepts actually learned.
- The system is used solo/interactively — one user driving one session at a time, not a
  multi-user real-time collaboration tool.

## 3. Functional Requirements

| ID | Requirement Description |
|---|---|
| FR1 | Users can connect the tool to a specified GitHub repository, either by cloning it locally or linking it directly. |
| FR2 | Once connected, the system parses the repository and builds a dependency graph covering its files and modules. |
| FR3 | That dependency graph is rendered as a visual flowchart the user can inspect before making any changes. |
| FR4 | Alongside the flowchart, the system produces a plain-language explanation of what each file or module does and how the pieces connect. |
| FR5 | A user can ask for a bug fix or a new feature on the connected repository through the assistant. |
| FR6 | The AI assistant carries out the commands and code changes needed to complete that request. |
| FR7 | While doing so, it explains — in plain language, not just code comments — each command it runs and the reasoning behind any non-trivial decision, rather than applying changes silently. |
| FR8 | Once a fix or feature is finished, the system generates a short quiz targeting the concept the user was just exposed to. |
| FR9 | A wrong quiz answer triggers a recommended learning resource covering that concept. |
| FR10 | After reviewing the resource, the user can retake the quiz. |
| FR11 | Concepts the user answers correctly get written into a personal learning notebook tied to their account. |
| FR12 | The notebook remains accessible at any time, so the user can look back over what they've actually learned. |

## 4. Interface Requirements

### 4.1 User Interface

- A chat-style interface for requesting fixes/features and receiving explanations.
- A flowchart/diagram viewer for the repository structure.
- A quiz panel shown after each completed fix or feature.
- A notebook view listing learned concepts, searchable/revisitable by the user.

### 4.2 Software Interface

- GitHub API for repository access, cloning, and commit history.
- Git command-line operations for making and tracking code changes.
- An LLM API for generating explanations, quizzes, and resource recommendations.
- A database (local or cloud) for storing notebook entries and session state.

### 4.3 Hardware Interface

The system requires a standard desktop or laptop with an internet connection; no specialised
hardware is needed.

## 5. Performance Requirements

- Repository analysis (dependency graph + explanation) shall complete within an acceptable wait
  time for typical small-to-medium repositories.
- The AI assistant's step-by-step explanations shall be generated with minimal added delay over
  the underlying code change itself.
- Quiz generation shall occur immediately after a fix/feature is marked complete, with no
  separate manual trigger required.

## 6. Design Constraints

- The project is solo/student-built over one semester, so free and open-source tools are the
  default choice.
- The system must operate within GitHub API rate limits.
- LLM API usage must stay within a limited, student-level budget.
- Initial version targets a single primary programming language/ecosystem before broader support
  is considered.

## 7. Non-Functional Attributes

- **Usability**: explanations and quiz feedback must be understandable to someone without deep
  prior context on the repo.
- **Reliability**: the dependency graph and explanations must stay accurate as the repository
  changes across a session.
- **Security**: repository access must be authenticated, and private code must never be exposed
  beyond the user's own session.
- **Scalability**: the architecture should tolerate repositories of varying size without
  redesign, even if performance on very large repos is a later optimisation.
- **Maintainability**: the four core capabilities — repo analyzer, explaining assistant, quiz
  engine, and notebook — are built as separate modules so each can be improved independently.

## 8. Preliminary Schedule and Budget

| Phase | Duration | Cost Estimate |
|---|---|---|
| Sprint 1 – Repo cloning & dependency graph | Weeks 1–2 | ₹0 (open-source tooling) |
| Sprint 2 – Flowchart + plain-language explanations | Weeks 3–4 | ₹0 |
| Sprint 3 – AI coding assistant integration | Weeks 5–6 | LLM API usage – limited free/student tier |
| Sprint 4 – Quiz engine (first version) | Weeks 7–8 | LLM API usage – limited free/student tier |
| Sprint 5 – Resource recommendation & retry flow | Weeks 9–10 | LLM API usage – limited free/student tier |
| Sprint 6 – Learning notebook | Weeks 11–12 | ₹0 (open-source database) |
| **Total** | One semester (~12 weeks) | Minimal – open-source stack + limited LLM API usage |

## 9. Appendices

### 9.1 Acronyms

- SRS: Software Requirements Specification
- LLM: Large Language Model
- API: Application Programming Interface
- UI: User Interface
- DB: Database

### 9.2 References

- IEEE 830 SRS Standard
- GitHub REST API documentation

## 10. Uses of the SRS Document

- Guides development of each sprint against a fixed, agreed set of requirements.
- Gives a checklist for testing whether the repo analyzer, assistant, quiz engine, and notebook
  behave as specified.
- Serves as a reference document when evaluating or presenting the project.
- Helps plan the sprint schedule and keep scope from drifting mid-semester.

## 11. Conclusion

This SRS defines the requirements for CodeLiteracy — a tool that helps a developer understand a
codebase and make AI-assisted changes to it while staying actively engaged in the learning
process, rather than offloading understanding to the assistant. By specifying the functional
behaviour, interfaces, constraints, and schedule up front, this document gives the sprint-based
Agile plan from Experiment 1 a clear target to build against.
