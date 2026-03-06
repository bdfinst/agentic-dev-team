// PASS: Immutable state management — spread copies, Object.freeze, const everywhere

interface AppState {
  readonly user: Readonly<{ name: string; email: string; role: string }>;
  readonly preferences: Readonly<{ theme: string; locale: string; notifications: boolean }>;
  readonly items: readonly string[];
}

const initialState: AppState = Object.freeze({
  user: Object.freeze({ name: "", email: "", role: "viewer" }),
  preferences: Object.freeze({ theme: "light", locale: "en-US", notifications: true }),
  items: Object.freeze([]),
});

const updateUser = (
  state: AppState,
  updates: Partial<AppState["user"]>,
): AppState => ({
  ...state,
  user: { ...state.user, ...updates },
});

const updatePreferences = (
  state: AppState,
  updates: Partial<AppState["preferences"]>,
): AppState => ({
  ...state,
  preferences: { ...state.preferences, ...updates },
});

const addItem = (state: AppState, item: string): AppState => ({
  ...state,
  items: [...state.items, item],
});

const removeItem = (state: AppState, index: number): AppState => ({
  ...state,
  items: [
    ...state.items.slice(0, index),
    ...state.items.slice(index + 1),
  ],
});

const replaceItem = (state: AppState, index: number, value: string): AppState => ({
  ...state,
  items: state.items.map((existing, i) => (i === index ? value : existing)),
});

const resetState = (): AppState => ({ ...initialState });

const deriveDisplayName = (state: AppState): string => {
  const { name, role } = state.user;
  return name ? `${name} (${role})` : "Anonymous";
};

const serializeState = (state: AppState): string =>
  JSON.stringify(state, null, 2);

export {
  initialState,
  updateUser,
  updatePreferences,
  addItem,
  removeItem,
  replaceItem,
  resetState,
  deriveDisplayName,
  serializeState,
};
