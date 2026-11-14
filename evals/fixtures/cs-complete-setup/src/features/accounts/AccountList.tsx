import { useAccounts } from "../../hooks/useAccounts";

export function AccountList() {
  const { data } = useAccounts();
  return (
    <ul>
      {data?.map((account) => (
        <li key={account.id}>{account.name}</li>
      ))}
    </ul>
  );
}
