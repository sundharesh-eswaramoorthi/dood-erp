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

export async function billOrder(
  id: number,
): Promise<{ doc_no: string | null; grand_total: string; cogs_total: string; taxable_total: string; tax_total: string }> {
  const { data } = await api.post(`/api/v1/sales/orders/${id}/bill`, { supply_type: "intra" });
  return data as never;
}

export async function listBills(): Promise<SalesBill[]> {
  const { data } = await api.get<SalesBill[]>("/api/v1/sales/bills");
  return data;
}
