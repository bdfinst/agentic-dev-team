// PASS: one reusable Card primitive, consumed via composition with children.
// No duplicated render subtree, no prop drilling, consistent prop/event API.

import { createContext, useContext, type ReactNode } from "react";

interface User {
  id: string;
  name: string;
}

const SessionContext = createContext<{ user: User; onSignOut: () => void } | null>(
  null,
);

function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}

export function SessionProvider({
  value,
  children,
}: {
  value: { user: User; onSignOut: () => void };
  children: ReactNode;
}) {
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function Card({
  title,
  media,
  children,
  onSelect,
}: {
  title: string;
  media?: string;
  children?: ReactNode;
  onSelect?: () => void;
}) {
  return (
    <article className="card" onClick={onSelect}>
      {media ? <img className="card__media" src={media} alt={title} /> : null}
      <h3 className="card__title">{title}</h3>
      {children}
    </article>
  );
}

export function UserMenu() {
  const { user, onSignOut } = useSession();
  return (
    <Card title={user.name}>
      <button onClick={onSignOut}>Sign out</button>
    </Card>
  );
}
