import { api } from "../../lib/api";

export interface SaleOrder {
  id: number;
  doc_no: string | null;
  status: string;
  customer_id: number;
  order_date?: string;
  grand_total?: string;
  /** set when the customer is over their credit limit — the order still posted */
  credit_warning?: string | null;
}

/** A document line, as every sales endpoint takes it. */
export interface SaleLineIn {
  product_id: number;
  godown_id: number;
  entered_qty: string;
  entered_unit_id: number;
  rate: string;
  gst_rate?: string;
  discount_pct?: string;
}

export async function createOrder(payload: {
  customer_id: number;
  branch_id?: number;
  lines: SaleLineIn[];
} & Record<string, unknown>): Promise<SaleOrder> {
  const { data } = await api.post<SaleOrder>("/api/v1/sales/orders", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function listOrders(branchId?: number): Promise<SaleOrder[]> {
  const { data } = await api.get<SaleOrder[]>("/api/v1/sales/orders", {
    params: branchId ? { branch_id: branchId } : undefined,
  });
  return data;
}

export interface SaleOrderLine {
  line_no: number;
  product_id: number;
  godown_id: number;
  entered_qty: string;
  entered_unit_id: number;
  base_qty: string;
  rate: string;
}

export async function getOrder(id: number): Promise<SaleOrder & { lines: SaleOrderLine[] }> {
  const { data } = await api.get<SaleOrder & { lines: SaleOrderLine[] }>(`/api/v1/sales/orders/${id}`);
  return data;
}

export async function cancelOrder(id: number): Promise<SaleOrder> {
  const { data } = await api.post<SaleOrder>(`/api/v1/sales/orders/${id}/cancel`);
  return data;
}

export async function deliverOrder(id: number): Promise<{ doc_no: string | null; status: string }> {
  const { data } = await api.post<{ doc_no: string | null; status: string }>(
    `/api/v1/sales/orders/${id}/deliver`,
  );
  return data;
}

export interface SalesBill {
  id: number;
  doc_no: string | null;
  status: string;
  customer_id: number;
  sale_order_id: number | null;
  grand_total: string;
  paid_amount?: string;
  balance_amount?: string;
  bill_date?: string;
}

export interface BilledOut {
  id: number;
  doc_no: string | null;
  credit_warning?: string | null;
  grand_total: string;
  cogs_total: string;
  taxable_total: string;
  tax_total: string;
  paid_amount: string;
  balance_amount: string;
  round_off: string;
  discount_amount: string;
}

/** `money` carries the v2 §4 block (discounts, charges, paid) — the order
 *  supplies the lines, so only the header needs filling in here. */
export async function billOrder(
  id: number,
  money: Record<string, unknown> = {},
): Promise<BilledOut> {
  const { data } = await api.post(`/api/v1/sales/orders/${id}/bill`, { ...money });
  return data as BilledOut;
}

export async function listBills(branchId?: number): Promise<SalesBill[]> {
  const { data } = await api.get<SalesBill[]>("/api/v1/sales/bills", {
    params: branchId ? { branch_id: branchId } : undefined,
  });
  return data;
}


/** v2 §4 counter sale: an invoice with no order behind it. */
export async function createDirectBill(
  payload: {
    customer_id: number;
    branch_id?: number;
    lines: SaleLineIn[];
  } & Record<string, unknown>,
): Promise<BilledOut & { doc_no: string | null }> {
  const { data } = await api.post("/api/v1/sales/bills", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data as BilledOut & { doc_no: string | null };
}

/** v2 §4 sales return (credit note): goods back in, party credited. */
export interface SalesReturn {
  id: number;
  doc_no: string | null;
  status: string;
  customer_id: number;
  orig_bill_id: number | null;
  grand_total: string;
  paid_amount?: string;
  balance_amount?: string;
  return_date?: string;
}

export async function createReturn(
  payload: {
    customer_id: number;
    branch_id?: number;
    orig_bill_id?: number;
    lines: SaleLineIn[];
  } & Record<string, unknown>,
): Promise<SalesReturn & BilledOut> {
  const { data } = await api.post("/api/v1/sales/returns", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data as SalesReturn & BilledOut;
}

export async function listReturns(branchId?: number): Promise<SalesReturn[]> {
  const { data } = await api.get<SalesReturn[]>("/api/v1/sales/returns", {
    params: branchId ? { branch_id: branchId } : undefined,
  });
  return data;
}
