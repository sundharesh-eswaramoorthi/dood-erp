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

export async function postVoucher(payload: {
  party_id: number;
  account_id: number;
  voucher_type: string;
  amount: string;
  note?: string;
}): Promise<{ doc_no: string | null; account_balance: string; party_net: string }> {
  const { data } = await api.post("/api/v1/accounts/payment-vouchers", payload);
  return data as never;
}

export async function listVouchers(): Promise<Voucher[]> {
  const { data } = await api.get<Voucher[]>("/api/v1/accounts/payment-vouchers");
  return data;
}
