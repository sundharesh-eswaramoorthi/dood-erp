import { api } from "../../lib/api";

export type PrintFormat = "a4" | "a5" | "thermal80" | "thermal58";

export interface PrintSettings {
  default_format: PrintFormat;
  show_hsn: boolean;
  show_tax_summary: boolean;
  show_amount_in_words: boolean;
  show_bank_details: boolean;
  footer_text: string;
  terms: string;
}

export interface PrintLine {
  line_no: number;
  product_code: string;
  product: string;
  hsn_code: string | null;
  entered_qty: string;
  unit: string | null;
  rate: string;
  gross_amount: string;
  discount_amount: string;
  header_discount_alloc: string;
  taxable: string;
  gst_rate: string;
  cgst: string;
  sgst: string;
  igst: string;
  line_total: string;
  remarks: string | null;
}

export interface PrintDoc {
  doc_type: string;
  title: string;
  party_label: string;
  settings: PrintSettings;
  org: { name: string };
  branch: {
    name?: string; code?: string; address?: string;
    phone?: string; gstin?: string; state_code?: string;
  };
  party: {
    party_code?: string; name?: string; area?: string; phone?: string;
    gstin?: string; pan?: string;
    address?: { line1?: string; line2?: string; city?: string; state?: string; pincode?: string } | null;
  };
  document: {
    id: number; doc_no: string | null; status: string; date: string;
    doc_datetime: string | null; supply_type: string | null; price_mode: string | null;
    revision_no: number | null; amended_from: number | null; remarks: string | null;
    payment_type: string | null; supplier_invoice_no: string | null;
  };
  lines: PrintLine[];
  tax_summary: { gst_rate: string; taxable: string; cgst: string; sgst: string; igst: string }[];
  totals: Record<string, string>;
  amount_in_words: string;
  payments: { amount: string; doc_no: string | null; effective_date: string; payment_type: string | null }[];
}

export async function getPrintDoc(docType: string, docId: number): Promise<PrintDoc> {
  const { data } = await api.get<PrintDoc>(`/api/v1/print/${docType}/${docId}`);
  return data;
}

export async function getPrintSettings(): Promise<PrintSettings> {
  const { data } = await api.get<PrintSettings>("/api/v1/print/settings");
  return data;
}

export async function savePrintSettings(payload: Partial<PrintSettings>): Promise<PrintSettings> {
  const { data } = await api.put<PrintSettings>("/api/v1/print/settings", payload);
  return data;
}
