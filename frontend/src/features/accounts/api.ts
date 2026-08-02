import { api } from "../../lib/api";

export interface Account {
  id: number;
  name: string;
  account_type: string;
  current_balance: string;
}

export interface Voucher {
  id: number;
  doc_no: string | null;
  voucher_type: string;
  party_id: number;
  account_id: number;
  amount: string;
  voucher_date?: string;
}

export async function listAccounts(): Promise<Account[]> {
  const { data } = await api.get<Account[]>("/api/v1/accounts/bank-accounts");
  return data;
}

export async function createAccount(payload: {
  name: string;
  account_type: string;
  opening_balance: string;
}): Promise<Account> {
  const { data } = await api.post<Account>("/api/v1/accounts/bank-accounts", payload);
  return data;
}

export interface VoucherResult {
  doc_no: string | null;
  account_balance: string;
  party_net: string;
  unallocated: string;
  allocations: { doc_type: string; doc_id: number; amount: string }[];
}

export async function postVoucher(payload: {
  party_id: number;
  voucher_type: string;
  note?: string;
  /** single-tender form — or send `payments` instead */
  account_id?: number;
  amount?: string;
  payment_type_id?: number;
  /** v2 §3 split payment: the server derives amount and the header account */
  payments?: {
    account_id: number;
    payment_type_id?: number;
    amount: string;
    reference?: string;
  }[];
  /** omit to settle the oldest bills first; [] to leave it on account */
  allocations?: { against_entry_id: number; amount: string }[];
}): Promise<VoucherResult> {
  const { data } = await api.post("/api/v1/accounts/payment-vouchers", payload);
  return data as VoucherResult;
}

export async function listVouchers(): Promise<Voucher[]> {
  const { data } = await api.get<Voucher[]>("/api/v1/accounts/payment-vouchers");
  return data;
}

export interface ExpenseCategory {
  id: number;
  name: string;
}

export interface Expense {
  id: number;
  doc_no: string | null;
  amount: string;
  account_id: number;
  category_id: number | null;
  category?: string | null;
  note?: string | null;
}

export async function listExpenseCategories(): Promise<ExpenseCategory[]> {
  const { data } = await api.get<ExpenseCategory[]>("/api/v1/accounts/expense-categories");
  return data;
}

export async function postExpense(payload: {
  account_id: number;
  amount: string;
  category_id?: number | null;
  note?: string;
}): Promise<{ doc_no: string | null; account_balance: string }> {
  const { data } = await api.post("/api/v1/accounts/expenses", payload);
  return data as never;
}

export async function listExpenses(): Promise<Expense[]> {
  const { data } = await api.get<Expense[]>("/api/v1/accounts/expenses");
  return data;
}

// ---- payment types (v2 §3 "add payment type") ----
export interface PaymentType {
  id: number;
  name: string;
  kind: string;
  default_account_id: number | null;
  is_active: boolean;
  sort_order: number;
}

export async function listPaymentTypes(includeInactive = false): Promise<PaymentType[]> {
  const { data } = await api.get<PaymentType[]>("/api/v1/accounts/payment-types", {
    params: { include_inactive: includeInactive },
  });
  return data;
}

export async function createPaymentType(payload: {
  name: string;
  kind?: string;
}): Promise<PaymentType> {
  const { data } = await api.post<PaymentType>("/api/v1/accounts/payment-types", payload);
  return data;
}

export async function updatePaymentType(
  id: number,
  payload: Partial<PaymentType>,
): Promise<PaymentType> {
  const { data } = await api.put<PaymentType>(`/api/v1/accounts/payment-types/${id}`, payload);
  return data;
}

// ---- bill-wise settlement (v2 §3 payment history) ----
export interface OpenItem {
  entry_id: number;
  source_doc_type: string;
  source_doc_id: number;
  effective_date: string;
  amount: string;
  settled: string;
  outstanding: string;
}

export async function listOpenItems(partyId: number, side = "debit"): Promise<OpenItem[]> {
  const { data } = await api.get<OpenItem[]>(
    `/api/v1/accounts/parties/${partyId}/open-items`,
    { params: { side } },
  );
  return data;
}

export interface DocPayment {
  amount: string;
  source_doc_type: string;
  source_doc_id: number;
  effective_date: string;
  doc_no: string | null;
  voucher_type: string | null;
  payment_type: string | null;
}

export interface PaymentHistory {
  invoice_total: string;
  settled: string;
  outstanding: string;
  payments: DocPayment[];
}

/** v2 §3 "Payment link": the invoice's own settlement history. */
export async function billPayments(
  kind: "sales" | "purchase",
  billId: number,
): Promise<PaymentHistory> {
  const { data } = await api.get<PaymentHistory>(`/api/v1/${kind}/bills/${billId}/payments`);
  return data;
}
