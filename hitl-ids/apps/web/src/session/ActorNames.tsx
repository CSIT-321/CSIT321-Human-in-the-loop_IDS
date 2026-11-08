import { createContext, useContext, type ReactNode } from "react";
import { api, unwrap } from "../api/client";
import { useApi } from "../api/useApi";

/** id -> display name, read once per session. An SOC audit line must name the person, not "Actor #N". */
const ActorNames = createContext<ReadonlyMap<number, string>>(new Map());

export function ActorNamesProvider({ children }: { children: ReactNode }) {
  const actors = useApi(signal => unwrap(api.GET("/api/auth/actors", { signal })), []);
  // Names are a display aid only: a failed or malformed reply must never break a triage screen.
  const items = actors.status === "success" && Array.isArray(actors.data?.items) ? actors.data.items : [];
  const names = new Map<number, string>(items.map(a => [a.id, a.displayName]));
  return <ActorNames.Provider value={names}>{children}</ActorNames.Provider>;
}

/** The person's name; falls back to "User #N" only if the directory has not loaded or the id is unknown. */
export function useActorName(): (id: number | null | undefined) => string {
  const names = useContext(ActorNames);
  return id => id == null ? "Unknown" : names.get(id) ?? `User #${id}`;
}
