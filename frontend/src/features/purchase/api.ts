import { api } from "../../lib/api";

export interface BillLineIn {
  product_id: number;
  godown_id?: number;          // v2: per-line godown ("multi godown invoice")
  entered_qty: string;
  entered_unit_id: number;
  rate: string;
  gst_rate?: string;
  discount_pct?: string;
  discount_amount?: string;
  hsn_code?: string;
  remarks?: string;
}

export interface PurchaseBillCreate {
  supplier_id: number;
  godown_id?: number;          // default godown for lines that omit one
  supply_type?: string;
  supplier_invoice_no?: string;
  po_id?: number;
  bill_date?: string;
  price_mode?: string;
  discount_pct?: string;
  discount_amount?: string;
  card_charges?: string;
  round_off?: string;
  paid_amount?: string;
  payment_account_id?: number;
  remarks?: string;
  lines: BillLineIn[];
}

export interface PurchaseBill {
  id: number;
  doc_no: string | null;
  status: string;
  supplier_id: number;
  bill_date?: string;
  gross_total?: string;
  line_discount_total?: string;
  discount_amount?: string;
  taxable_total?: string;
  tax_total?: string;
  card_charges?: string;
  round_off?: string;
  grand_total: string;
  paid_amount?: string;
  balance_amount?: string;
}

export async function createBill(payload: PurchaseBillCreate): Promise<PurchaseBill> {
  const { data } = await api.post<PurchaseBill>("/api/v1/purchase/bills", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function listBills(): Promise<PurchaseBill[]> {
  const { data } = await api.get<PurchaseBill[]>("/api/v1/purchase/bills");
  return data;
}

export async function createReturn(payload: PurchaseBillCreate & { orig_bill_id?: number }): Promise<PurchaseBill> {
  const { data } = await api.post<PurchaseBill>("/api/v1/purchase/returns", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export interface PurchaseOrder {
  id: number;
  doc_no: string | null;
  status: string;
  supplier_id: number;
  order_date?: string;
}

export async function createOrder(payload: {
  supplier_id: number;
  lines: { product_id: number; entered_qty: string; entered_unit_id: number; rate: string }[];
}): Promise<PurchaseOrder> {
  const { data } = await api.post<PurchaseOrder>("/api/v1/purchase/orders", payload);
  return data;
}

export async function listOrders(): Promise<PurchaseOrder[]> {
  const { data } = await api.get<PurchaseOrder[]>("/api/v1/purchase/orders");
  return data;
}
