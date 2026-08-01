import { api } from "../../lib/api";

/** Header money block shared by every invoice-shaped document (v2 §3/§4). */
export interface MoneyHeader {
  price_mode: string;
  discount_pct: string;
  discount_amount: string | null;
  card_charges: string;
  round_off: string | null;
  paid_amount: string;
  payment_account_id: number | null;
  remarks: string;
}

export const EMPTY_MONEY: MoneyHeader = {
  price_mode: "exclusive",
  discount_pct: "",
  discount_amount: "",
  card_charges: "",
  round_off: "",
  paid_amount: "",
  payment_account_id: null,
  remarks: "",
};

/** Strip the blanks so the API sees "not supplied" rather than "zero". */
export function moneyPayload(m: MoneyHeader) {
  return {
    price_mode: m.price_mode,
    discount_pct: m.discount_pct || "0",
    discount_amount: m.discount_amount || undefined,
    card_charges: m.card_charges || "0",
    round_off: m.round_off ? m.round_off : undefined,   // blank/null => auto
    paid_amount: m.paid_amount || "0",
    payment_account_id: m.paid_amount ? m.payment_account_id ?? undefined : undefined,
    remarks: m.remarks || undefined,
  };
}

export interface MoneyTotals {
  gross_total: string;
  line_discount_total: string;
  discount_amount: string;
  taxable_total: string;
  tax_total: string;
  cgst_total: string;
  sgst_total: string;
  igst_total: string;
  card_charges: string;
  round_off: string;
  grand_total: string;
  paid_amount: string;
  balance_amount: string;
}

export interface PreviewLine {
  qty: string;
  rate: string;
  gst_rate?: string;
  discount_pct?: string;
  discount_amount?: string;
}

export interface PreviewResult {
  lines: { taxable: string; tax: string; line_total: string }[];
  totals: MoneyTotals | null;
}

/** Ask the server to run the real money engine — no duplicate maths here. */
export async function previewMoney(
  lines: PreviewLine[],
  header: MoneyHeader,
  supply_type: string,
): Promise<PreviewResult> {
  const { data } = await api.post<PreviewResult>("/api/v1/money/preview", {
    ...moneyPayload(header),
    supply_type,
    lines: lines.map((l) => ({
      qty: l.qty || "0",
      rate: l.rate || "0",
      gst_rate: l.gst_rate || "0",
      discount_pct: l.discount_pct || "0",
      discount_amount: l.discount_amount || undefined,
    })),
  });
  return data;
}
