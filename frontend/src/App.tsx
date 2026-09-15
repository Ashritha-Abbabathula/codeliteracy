import { BrowserRouter, Route, Routes } from "react-router-dom";

import { RepoConnect } from "./pages/RepoConnect";
import { RepoView } from "./pages/RepoView";

export function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <header>
          <h1>CodeLiteracy</h1>
          <p className="tagline">Understand a repo. Make AI-assisted changes. Actually learn.</p>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<RepoConnect />} />
            <Route path="/repo/:repoId" element={<RepoView />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
