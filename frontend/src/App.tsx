import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import { AssistantChat } from "./pages/AssistantChat";
import { Notebook } from "./pages/Notebook";
import { RepoConnect } from "./pages/RepoConnect";
import { RepoLayout } from "./pages/RepoLayout";
import { RepoView } from "./pages/RepoView";

export function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header>
          <div className="header-row">
            <div>
              <h1>CodeLiteracy</h1>
              <p className="tagline">Understand a repo. Make AI-assisted changes. Actually learn.</p>
            </div>
            <Link to="/notebook" className="notebook-link">
              My notebook
            </Link>
          </div>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<RepoConnect />} />
            <Route path="/notebook" element={<Notebook />} />
            <Route path="/repo/:repoId" element={<RepoLayout />}>
              <Route index element={<RepoView />} />
              <Route path="assistant" element={<AssistantChat />} />
            </Route>
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
