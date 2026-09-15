import { NavLink, Outlet, useParams } from "react-router-dom";

/** Shared tab nav for everything scoped to one connected repo (structure, assistant;
 * the notebook in Sprint 6 is account-wide, not per-repo, so it lives outside this). */
export function RepoLayout() {
  const { repoId } = useParams<{ repoId: string }>();

  return (
    <div>
      <nav>
        <NavLink to={`/repo/${repoId}`} end className={({ isActive }) => (isActive ? "active" : "")}>
          Structure
        </NavLink>
        <NavLink to={`/repo/${repoId}/assistant`} className={({ isActive }) => (isActive ? "active" : "")}>
          Assistant
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
