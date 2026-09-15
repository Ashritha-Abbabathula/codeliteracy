import { RepoConnect } from "./pages/RepoConnect";

export function App() {
  return (
    <div className="app">
      <header>
        <h1>CodeLiteracy</h1>
        <p className="tagline">Understand a repo. Make AI-assisted changes. Actually learn.</p>
      </header>
      <main>
        <RepoConnect />
      </main>
    </div>
  );
}
