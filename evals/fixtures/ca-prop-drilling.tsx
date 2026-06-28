// WARN: `currentUser` and `onSignOut` are drilled through three intermediate
// components that do not use them, only to reach the deeply nested menu.
// Should be lifted to a context/provider or composed via children.

interface User {
  id: string;
  name: string;
}

interface PassThrough {
  currentUser: User;
  onSignOut: () => void;
}

export function App({ currentUser, onSignOut }: PassThrough) {
  return <Shell currentUser={currentUser} onSignOut={onSignOut} />;
}

function Shell({ currentUser, onSignOut }: PassThrough) {
  return (
    <div className="shell">
      <Header currentUser={currentUser} onSignOut={onSignOut} />
    </div>
  );
}

function Header({ currentUser, onSignOut }: PassThrough) {
  return (
    <header className="header">
      <Toolbar currentUser={currentUser} onSignOut={onSignOut} />
    </header>
  );
}

function Toolbar({ currentUser, onSignOut }: PassThrough) {
  return (
    <nav className="toolbar">
      <UserMenu currentUser={currentUser} onSignOut={onSignOut} />
    </nav>
  );
}

function UserMenu({ currentUser, onSignOut }: PassThrough) {
  return (
    <div className="user-menu">
      <span>{currentUser.name}</span>
      <button onClick={onSignOut}>Sign out</button>
    </div>
  );
}
