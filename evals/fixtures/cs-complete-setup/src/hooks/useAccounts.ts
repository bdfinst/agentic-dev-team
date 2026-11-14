import { useQuery } from "@tanstack/react-query";

export interface Account {
  id: string;
  name: string;
}

function fetchAccounts(): Promise<Account[]> {
  return fetch("/api/accounts")
    .then((response) => response.json())
    .then((body) => body.data);
}

export function useAccounts() {
  return useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
  });
}
