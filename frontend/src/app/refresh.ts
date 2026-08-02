import type { QueryClient } from "@tanstack/react-query";

/** What to re-read after a document posts.
 *
 * Every screen that moved stock used to name its own list of caches to drop,
 * and every one of them forgot something different — not one invalidated
 * `products`, which is where BOTH the Stock page and the Products page read
 * their quantity, average cost and stock value from. A purchase bill posted,
 * the goods really did arrive, and the screen kept showing the old figure.
 *
 * Keys are matched by prefix, so listing the root here also drops
 * ["products", filters, branchId] and ["stock-current", productId].
 */

const STOCK_KEYS = [
  "products",        // carries stock_qty / avg_cost / stock_value / low_stock
  "stock-current",
  "stock-movements",
  "reorders",        // low-stock thresholds are evaluated against the balance
  "transfers",
  "dashboard",       // stock value + low-stock widgets
];

const LEDGER_KEYS = [
  "parties",         // outstanding receivable/payable on the list
  "party",
  "ledger",
  "open-items",
  "accounts",        // a bank/cash balance moves when a document is settled
  "expenses",
  "vouchers",
  "bill-payments",
  "dashboard",
];

function drop(qc: QueryClient, keys: string[]): void {
  for (const key of new Set(keys)) qc.invalidateQueries({ queryKey: [key] });
}

/** Goods moved: stock, cost and anything computed from them. */
export function invalidateStock(qc: QueryClient): void {
  drop(qc, STOCK_KEYS);
}

/** Money moved: party balances and the accounts it landed in. */
export function invalidateLedgers(qc: QueryClient): void {
  drop(qc, LEDGER_KEYS);
}

/** A posted invoice does both in one transaction, so refresh it as one thing. */
export function invalidateDocument(qc: QueryClient): void {
  drop(qc, [...STOCK_KEYS, ...LEDGER_KEYS]);
}
