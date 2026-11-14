import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

interface SearchResult {
  readonly id: string;
  readonly title: string;
}

interface SearchContextValue {
  readonly query: string;
  readonly setQuery: (query: string) => void;
  readonly results: readonly SearchResult[];
}

const SearchContext = createContext<SearchContextValue | null>(null);

export function useSearch(): SearchContextValue {
  const value = useContext(SearchContext);
  if (value === null)
    throw new Error("useSearch must be used inside <SearchProvider>");
  return value;
}

function useInterval(callback: () => void, delayMs: number | null): void {
  const savedCallback = useRef(callback);

  useLayoutEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    if (delayMs === null) return undefined;
    const timerId = setInterval(() => savedCallback.current(), delayMs);
    return () => clearInterval(timerId);
  }, [delayMs]);
}

interface SearchProviderProps {
  readonly endpoint: string;
  readonly refreshMs: number | null;
  readonly children: ReactNode;
}

export function SearchProvider({
  endpoint,
  refreshMs,
  children,
}: SearchProviderProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<readonly SearchResult[]>([]);
  const [refreshCount, setRefreshCount] = useState(0);

  const fetchResults = useCallback(
    async (signal: AbortSignal) => {
      const response = await fetch(
        `${endpoint}?q=${encodeURIComponent(query)}`,
        { signal },
      );
      if (!response.ok) return;
      setResults((await response.json()) as SearchResult[]);
    },
    [endpoint, query],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchResults(controller.signal).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        throw error;
    });
    return () => controller.abort();
  }, [fetchResults, refreshCount]);

  useInterval(() => setRefreshCount((count) => count + 1), refreshMs);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setQuery("");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const contextValue = useMemo(
    () => ({ query, setQuery, results }),
    [query, results],
  );

  return (
    <SearchContext.Provider value={contextValue}>
      {children}
    </SearchContext.Provider>
  );
}
