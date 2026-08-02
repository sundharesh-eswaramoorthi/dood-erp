import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorMessage } from "../../lib/api";
import { PaymentHistoryDialog } from "../money/PaymentHistoryDialog";
import { listProducts } from "../products/api";
import { billOrder, createDirectBill, listBills, listOrders, type SalesBill } from "./api";
import { BillDialog } from "./BillDialog";
import { SaleDocumentCard } from "./SaleDocumentCard";
import { useSalesHeader } from "./useSalesHeader";
import { invalidateDocument } from "../../app/refresh";

type Note = { text: string; severity: "success" | "error" | "warning" };

export function SalesInvoicesPage() {
  const qc = useQueryClient();
  const h = useSalesHeader();
  const bills = useQuery({ queryKey: [...["sales-bills"], h.branchId], queryFn: () => listBills(h.branchId) });
  const orders = useQuery({ queryKey: [...["sale-orders"], h.branchId], queryFn: () => listOrders(h.branchId) });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });

  const [note, setNote] = useState<Note | null>(null);
  const [billing, setBilling] = useState<number | null>(null);
  const [historyFor, setHistoryFor] = useState<number | null>(null);

  const fail = (e: unknown, fallback: string) =>
    setNote({ text: errorMessage(e, fallback), severity: "error" });

  // orders that have been delivered are waiting to be invoiced
  const billable = (orders.data ?? []).filter((o) => o.status === "delivered");

  const bill = useMutation({
    mutationFn: (args: { id: number; money: Record<string, unknown> }) =>
      billOrder(args.id, args.money),
    onSuccess: (b) => {
      const paid = Number(b.paid_amount ?? 0)
        ? ` · paid ₹${b.paid_amount} · balance ₹${b.balance_amount}`
        : "";
      setNote({
        text:
          `Billed ${b.doc_no}: ₹${b.grand_total} (COGS ₹${b.cogs_total})${paid}.` +
          (b.credit_warning ? ` ${b.credit_warning}` : ""),
        severity: b.credit_warning ? "warning" : "success",
      });
      setBilling(null);
      qc.invalidateQueries({ queryKey: ["sales-bills"] });
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      invalidateDocument(qc);
    },
    onError: (e) => fail(e, "Could not post the bill"),
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Sales invoices</Typography>
        <Typography color="text.secondary">
          A counter sale moves the stock itself. Billing a delivered order moves nothing —
          the goods have already gone.
        </Typography>
      </Box>
      {note && <Alert severity={note.severity} onClose={() => setNote(null)}>{note.text}</Alert>}

      <SaleDocumentCard
        title="Counter sale"
        subtitle="invoice without an order — the bill moves the stock itself"
        actionLabel="Save & print"
        customer={h.customer}
        onCustomer={h.setCustomer}
        branch={h.branch}
        onBranch={h.setBranch}
        parties={h.parties}
        branches={h.branches}
        godowns={h.godowns}
        accounts={h.accounts}
        paymentTypes={h.paymentTypes}
        showMoney
        onSubmit={async (payload) => {
          const b = await createDirectBill(payload as Parameters<typeof createDirectBill>[0]);
          const paid = Number(b.paid_amount ?? 0)
            ? ` · paid ₹${b.paid_amount} · balance ₹${b.balance_amount}`
            : "";
          setNote({
            text:
              `Counter sale ${b.doc_no}: ₹${b.grand_total}${paid}.` +
              (b.credit_warning ? ` ${b.credit_warning}` : ""),
            severity: b.credit_warning ? "warning" : "success",
          });
          qc.invalidateQueries({ queryKey: ["sales-bills"] });
          invalidateDocument(qc);
          // v2 §4: a counter sale ends with paper in the customer's hand
          window.open(`/print/sales_bill/${b.id}`, "_blank");
        }}
        onError={(e) => fail(e, "Could not post the counter sale")}
      />

      {billable.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>Delivered orders awaiting an invoice</Typography>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
              <TextField
                size="small" select label="Order" value={billing ?? ""}
                onChange={(e) => setBilling(Number(e.target.value))} sx={{ minWidth: 260 }}
              >
                {billable.map((o) => (
                  <MenuItem key={o.id} value={o.id}>
                    {o.doc_no} · {h.partyName(o.customer_id)}
                  </MenuItem>
                ))}
              </TextField>
              <Typography variant="caption" color="text.secondary">
                pick one to open the invoice dialog
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Invoices</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Source</TableCell>
                <TableCell align="right">Grand total</TableCell>
                <TableCell align="right">Balance</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {(bills.data ?? []).map((b: SalesBill) => (
                <TableRow key={b.id} sx={{ opacity: b.status === "cancelled" ? 0.5 : 1 }}>
                  <TableCell>
                    <code>{b.doc_no}</code>
                    {b.status === "cancelled" && (
                      <Chip size="small" label="cancelled" sx={{ ml: 0.5 }} />
                    )}
                  </TableCell>
                  <TableCell>{h.partyName(b.customer_id)}</TableCell>
                  <TableCell>
                    {b.sale_order_id
                      ? `Order #${b.sale_order_id}`
                      : <Chip size="small" label="counter" variant="outlined" />}
                  </TableCell>
                  <TableCell align="right">₹{b.grand_total}</TableCell>
                  <TableCell align="right">
                    {b.balance_amount != null && Number(b.balance_amount) > 0 ? (
                      <Typography variant="body2" color="error.main">₹{b.balance_amount}</Typography>
                    ) : (
                      <Chip size="small" color="success" label="paid" variant="outlined" />
                    )}
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setHistoryFor(b.id)}>History</Button>
                    <Button size="small" onClick={() => window.open(`/print/sales_bill/${b.id}`, "_blank")}>
                      Print
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(bills.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No invoices yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <PaymentHistoryDialog billId={historyFor} onClose={() => setHistoryFor(null)} />

      <BillDialog
        orderId={billing}
        accounts={h.accounts}
        paymentTypes={h.paymentTypes}
        products={products.data ?? []}
        posting={bill.isPending}
        onClose={() => setBilling(null)}
        onPost={(money) => billing && bill.mutate({ id: billing, money })}
      />
    </Stack>
  );
}
