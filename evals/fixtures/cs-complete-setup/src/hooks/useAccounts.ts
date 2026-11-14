import { useQuery } from "@tanstack/react-query";

export interface Account {
  id: string;
  name: string;
}

export function useAccounts() {
  return useQuery<Account[]>({
    queryKey: ["accounts"],
    queryFn: async () => {
      const response = await fetch("/api/accounts");
      const body = await response.json();
      return body.data;
    },
  });
}
