// SKILL: semantic-duplication-scan
// EXPECTED: no register entries created — all functions below are trivial
// EXPECTED OUTPUT: "No computation units found to analyze"
//
// A trivial function performs no calculations and does not modify state.
// The skill must exclude all of the following patterns.

interface User {
  id: string;
  name: string;
  role: string;
  price: number;
}

// Getter — reads and returns a field, no computation
function getUserName(user: User): string {
  return user.name;
}

// Pass-through delegator — calls one function with the same args, no transformation
function logUser(user: User): void {
  console.log(user);
}

// Identity function — returns its input unchanged
function identity<T>(value: T): T {
  return value;
}

// Constructor-style initializer — only assigns parameters to fields
class OrderItem {
  id: string;
  quantity: number;
  unitPrice: number;

  constructor(id: string, quantity: number, unitPrice: number) {
    this.id = id;
    this.quantity = quantity;
    this.unitPrice = unitPrice;
  }
}

// Single-expression property accessor
class Pricing {
  private _basePrice: number;

  constructor(price: number) {
    this._basePrice = price;
  }

  get basePrice(): number {
    return this._basePrice;
  }
}
