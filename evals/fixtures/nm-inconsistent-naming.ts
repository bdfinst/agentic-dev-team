// FAIL: Same concept named differently, missing boolean prefixes, abbreviations.

interface User {
  id: string;
  name: string;
  email: string;
  active: boolean; // issue: missing is/has prefix for boolean
}

interface AccountInfo {
  accountId: string;
  memberName: string; // issue: same concept as User.name but called memberName
  contactEmail: string;
  enabled: boolean; // issue: missing is/has prefix, also inconsistent with User.active
}

// issue: "mgr" abbreviation instead of "manager"
class UserMgr {
  private accounts: AccountInfo[] = []; // issue: stores AccountInfo but class is about Users

  addMember(member: User): void { // issue: parameter called "member" but type is User
    this.accounts.push({
      accountId: member.id,
      memberName: member.name,
      contactEmail: member.email,
      enabled: member.active,
    });
  }

  getAcct(id: string): AccountInfo | undefined { // issue: "Acct" abbreviation
    return this.accounts.find((a) => a.accountId === id);
  }

  rmUser(id: string): void { // issue: "rm" abbreviation
    this.accounts = this.accounts.filter((a) => a.accountId !== id);
  }
}

// issue: "cfg" abbreviation instead of "config" or "configuration"
interface AppCfg {
  dbHost: string; // issue: "db" abbreviation
  maxRetries: number;
  debugMode: boolean; // acceptable but inconsistent — no is/has
}

function loadCfg(path: string): AppCfg {
  // stub
  return { dbHost: "localhost", maxRetries: 3, debugMode: false };
}

function checkUser(user: User): string {
  // issue: "check" is vague — check what?
  if (user.active) {
    return "active";
  }
  return "inactive";
}
