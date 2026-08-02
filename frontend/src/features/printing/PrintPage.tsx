import { Box, Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { getPrintDoc, type PrintFormat } from "./api";
import "./print.css";

const FORMATS: { value: PrintFormat; label: string }[] = [
  { value: "a4", label: "A4" },
  { value: "a5", label: "A5" },
  { value: "thermal80", label: "Thermal 80mm" },
  { value: "thermal58", label: "Thermal 58mm" },
];

const money = (v: string | undefined) =>
  v == null ? "" : Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nz = (v: string | undefined) => v != null && Number(v) !== 0;

/** v2 §9: one payload, four papers. The layout narrows for a till roll rather
 *  than being a second template — the figures must not diverge. */
export function PrintPage() {
  const { docType = "sales_bill", docId = "0" } = useParams();
  const [search] = useSearchParams();
  const [format, setFormat] = useState<PrintFormat>("a4");

  const doc = useQuery({
    queryKey: ["print", docType, docId],
    queryFn: () => getPrintDoc(docType, Number(docId)),
  });

  // the org's default unless the caller asked for a specific paper
  useEffect(() => {
    const wanted = search.get("format") as PrintFormat | null;
    if (wanted) setFormat(wanted);
    else if (doc.data?.settings.default_format) setFormat(doc.data.settings.default_format);
  }, [doc.data, search]);

  if (doc.isLoading) return <Typography sx={{ p: 3 }}>Loading…</Typography>;
  if (doc.isError || !doc.data) return <Typography sx={{ p: 3 }}>Document not found.</Typography>;

  const d = doc.data;
  const s = d.settings;
  const thermal = format.startsWith("thermal");
  const addr = d.party.address;
  const showHsn = s.show_hsn && !thermal;

  return (
    <div className="print-root">
      <Stack direction="row" spacing={2} className="no-print" sx={{ mb: 2, justifyContent: "center" }}>
        <TextField
          size="small" select label="Paper" value={format}
          onChange={(e) => setFormat(e.target.value as PrintFormat)} sx={{ width: 180 }}
        >
          {FORMATS.map((f) => (<MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>))}
        </TextField>
        <Button variant="contained" onClick={() => window.print()}>Print</Button>
        <Button onClick={() => window.close()}>Close</Button>
      </Stack>

      <div className={`print-sheet ${format}`}>
        <div className="print-head">
          <div className="print-org">{d.org.name}</div>
          <div className="print-branch">
            {d.branch.name}
            {d.branch.address ? ` · ${d.branch.address}` : ""}
            {d.branch.phone ? ` · ${d.branch.phone}` : ""}
          </div>
          {d.branch.gstin && <div className="print-branch">GSTIN: {d.branch.gstin}</div>}
          <div className="print-title">{d.title}</div>
          {d.document.status === "cancelled" && (
            <div style={{ marginTop: 4 }}><span className="print-cancelled">CANCELLED</span></div>
          )}
        </div>

        <div className="print-meta">
          <div>
            <div className="print-label">{d.party_label}</div>
            <div><strong>{d.party.name}</strong>{d.party.party_code ? ` (${d.party.party_code})` : ""}</div>
            {addr && (
              <div>
                {[addr.line1, addr.line2, addr.city, addr.state, addr.pincode].filter(Boolean).join(", ")}
              </div>
            )}
            {d.party.area && <div>Area: {d.party.area}</div>}
            {d.party.phone && <div>Ph: {d.party.phone}</div>}
            {d.party.gstin && <div>GSTIN: {d.party.gstin}</div>}
          </div>
          <div style={{ textAlign: thermal ? "left" : "right" }}>
            <div><span className="print-label">No: </span><strong>{d.document.doc_no}</strong></div>
            <div><span className="print-label">Date: </span>{d.document.date}</div>
            {d.document.supplier_invoice_no && (
              <div><span className="print-label">Supplier inv: </span>{d.document.supplier_invoice_no}</div>
            )}
            {d.document.payment_type && (
              <div><span className="print-label">Paid by: </span>{d.document.payment_type}</div>
            )}
            {(d.document.revision_no ?? 1) > 1 && (
              <div><span className="print-label">Revision: </span>{d.document.revision_no}</div>
            )}
          </div>
        </div>

        <table className="print-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Item</th>
              {showHsn && <th>HSN</th>}
              <th className="num">Qty</th>
              <th className="num">Rate</th>
              {!thermal && <th className="num">Disc</th>}
              <th className="num hide-58">GST%</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {d.lines.map((l) => (
              <tr key={l.line_no}>
                <td>{l.line_no}</td>
                <td>
                  {l.product}
                  {l.remarks && <div style={{ color: "#666" }}>{l.remarks}</div>}
                </td>
                {showHsn && <td>{l.hsn_code ?? "-"}</td>}
                <td className="num">{Number(l.entered_qty).toLocaleString("en-IN")} {l.unit ?? ""}</td>
                <td className="num">{money(l.rate)}</td>
                {!thermal && (
                  <td className="num">
                    {money(String(Number(l.discount_amount) + Number(l.header_discount_alloc)))}
                  </td>
                )}
                <td className="num hide-58">{Number(l.gst_rate)}</td>
                <td className="num">{money(l.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <table className="print-totals">
          <tbody>
            <tr><td>Gross</td><td className="num">{money(d.totals.gross_total)}</td></tr>
            {nz(d.totals.line_discount_total) && (
              <tr><td>Line discount</td><td className="num">-{money(d.totals.line_discount_total)}</td></tr>
            )}
            {nz(d.totals.discount_amount) && (
              <tr><td>Discount</td><td className="num">-{money(d.totals.discount_amount)}</td></tr>
            )}
            <tr><td>Taxable</td><td className="num">{money(d.totals.taxable_total)}</td></tr>
            <tr><td>GST</td><td className="num">{money(d.totals.tax_total)}</td></tr>
            {nz(d.totals.card_charges) && (
              <tr><td>Card charges</td><td className="num">{money(d.totals.card_charges)}</td></tr>
            )}
            {nz(d.totals.round_off) && (
              <tr><td>Round off</td><td className="num">{money(d.totals.round_off)}</td></tr>
            )}
            <tr className="grand"><td>Total</td><td className="num">{money(d.totals.grand_total)}</td></tr>
            {nz(d.totals.paid_amount) && (
              <>
                <tr><td>Paid</td><td className="num">-{money(d.totals.paid_amount)}</td></tr>
                <tr className="grand"><td>Balance</td><td className="num">{money(d.totals.balance_amount)}</td></tr>
              </>
            )}
          </tbody>
        </table>

        {s.show_amount_in_words && <div className="print-words">{d.amount_in_words}</div>}

        {s.show_tax_summary && !thermal && d.tax_summary.length > 0 && (
          <table className="print-table" style={{ marginTop: 12, width: "70%" }}>
            <thead>
              <tr>
                <th>GST %</th><th className="num">Taxable</th>
                <th className="num">CGST</th><th className="num">SGST</th><th className="num">IGST</th>
              </tr>
            </thead>
            <tbody>
              {d.tax_summary.map((t, i) => (
                <tr key={i}>
                  <td>{Number(t.gst_rate)}%</td>
                  <td className="num">{money(t.taxable)}</td>
                  <td className="num">{money(t.cgst)}</td>
                  <td className="num">{money(t.sgst)}</td>
                  <td className="num">{money(t.igst)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {d.payments.length > 0 && !thermal && (
          <Box sx={{ mt: 1.5 }}>
            <div className="print-label">Payments received</div>
            {d.payments.map((p, i) => (
              <div key={i}>
                {p.effective_date} · {p.doc_no ?? "with invoice"}
                {p.payment_type ? ` · ${p.payment_type}` : ""} · {money(p.amount)}
              </div>
            ))}
          </Box>
        )}

        <div className="print-foot">
          <div>
            {s.terms && <div>{s.terms}</div>}
            {s.footer_text && <div>{s.footer_text}</div>}
          </div>
          <div style={{ textAlign: thermal ? "center" : "right", marginTop: thermal ? 12 : 24 }}>
            For {d.org.name}
            <div style={{ marginTop: thermal ? 8 : 32 }}>Authorised Signatory</div>
          </div>
        </div>
      </div>
    </div>
  );
}
