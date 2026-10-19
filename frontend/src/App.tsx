import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { Navbar } from "./components/Navbar";
import { RepoConnect } from "./pages/RepoConnect";
import { RepoView } from "./pages/RepoView";
import { Notebook } from "./pages/Notebook";

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div className="app-container">
          <Navbar />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<RepoConnect />} />
              <Route path="/repo/:repoId" element={<RepoView />} />
              <Route path="/notebook" element={<Notebook />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
