import { api } from "../../lib/api";

export interface SaleOrder {
  id: number;
  doc_no: string | null;
  status: string;
  customer_id: number;
  order_date?: string;
}

export async function createOrder(payload: {
  customer_id: number;
  lines: { product_id: number; godown_id: number; entered_qty: string; entered_unit_id: number; rate: string }[];
}): Promise<SaleOrder> {
  const { data } = await api.post<SaleOrder>("/api/v1/sales/orders", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function listOrders(): Promise<SaleOrder[]> {
  const { data } = await api.get<SaleOrder[]>("/api/v1/sales/orders");
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
}

export interface BilledOut {
  doc_no: string | null;
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
  supplyType = "intra",
): Promise<BilledOut> {
  const { data } = await api.post(`/api/v1/sales/orders/${id}/bill`, {
    supply_type: supplyType,
    ...money,
  });
  return data as BilledOut;
}

export async function listBills(): Promise<SalesBill[]> {
  const { data } = await api.get<SalesBill[]>("/api/v1/sales/bills");
  return data;
}


/** v2 §4 counter sale: an invoice with no order behind it. */
export interface DirectBillLine {
  product_id: number;
  godown_id: number;
  entered_qty: string;
  entered_unit_id: number;
  rate: string;
  gst_rate?: string;
  discount_pct?: string;
}

export async function createDirectBill(
  payload: { customer_id: number; supply_type?: string; lines: DirectBillLine[] } & Record<string, unknown>,
): Promise<BilledOut & { doc_no: string | null }> {
  const { data } = await api.post("/api/v1/sales/bills", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data as BilledOut & { doc_no: string | null };
}
