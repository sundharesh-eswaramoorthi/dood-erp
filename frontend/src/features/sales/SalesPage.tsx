import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
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
import { useEffect, useMemo, useState } from "react";

import { errorMessage } from "../../lib/api";
import { useAuth } from "../../store/auth";
import { billPayments, listAccounts, listPaymentTypes } from "../accounts/api";
import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import { listParties } from "../parties/api";
import { listProducts } from "../products/api";
import { listGodowns } from "../stock/api";
import { listBranches } from "../users/api";
import {
  billOrder,
  cancelOrder,
  createDirectBill,
  createOrder,
  deliverOrder,
  getOrder,
  listBills,
  listOrders,
  type SaleOrder,
  type SalesBill,
} from "./api";
import {
  SaleLinesEditor,
  emptyLine,
  isComplete,
  toPayload,
  toPreviewLines,
  type SaleLine,
} from "./SaleLines";

const STATUS_COLOR: Record<string, "warning" | "success" | "default"> = {
  pending: "warning",
  delivered: "success",
  cancelled: "default",
};

type Note = { text: string; severity: "success" | "error" | "warning" };

export function SalesPage() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const allGodowns = useQuery({ queryKey: ["godowns", "all"], queryFn: () => listGodowns(true) });
  const allBranches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const orders = useQuery({ queryKey: ["sale-orders"], queryFn: listOrders });
  const bills = useQuery({ queryKey: ["sales-bills"], queryFn: listBills });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const [note, setNote] = useState<Note | null>(null);
  const [billing, setBilling] = useState<number | null>(null);
  const [historyFor, setHistoryFor] = useState<number | null>(null);

  // only branches this user may post into — the server refuses the rest
  const branches = useMemo(
    () => (allBranches.data ?? []).filter((b) => me?.branch_ids.includes(b.id)),
    [allBranches.data, me],
  );
  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  const ok = (text: string) => setNote({ text, severity: "success" });
  const fail = (e: unknown, fallback: string) =>
    setNote({ text: errorMessage(e, fallback), severity: "error" });

  // ---- header state, shared by both documents ----
  const [customer, setCustomer] = useState("");
  const [branch, setBranch] = useState("");
  useEffect(() => {
    if (parties.data?.length && !customer) setCustomer(String(parties.data[0].id));
    if (branches.length && !branch) setBranch(String(branches[0].id));
  }, [parties.data, branches, customer, branch]);

  // a document ships out of its own branch's godowns and no others
  const godowns = useMemo(
    () => (allGodowns.data ?? []).filter((g) => String(g.branch_id) === branch),
    [allGodowns.data, branch],
  );

  const cancel = useMutation({
    mutationFn: (id: number) => cancelOrder(id),
    onSuccess: () => {
      ok("Order cancelled — reservation released.");
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e) => fail(e, "Could not cancel the order"),
  });

  const deliver = useMutation({
    mutationFn: (id: number) => deliverOrder(id),
    onSuccess: (d) => {
      ok(`Dispatched ${d.doc_no} — stock moved once, reservation released, order delivered.`);
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e) => fail(e, "Could not dispatch the delivery"),
  });

  const bill = useMutation({
    mutationFn: (args: { id: number; money: Record<string, unknown>; supply: string }) =>
      billOrder(args.id, args.money, args.supply),
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
      qc.invalidateQueries({ queryKey: ["stock-current"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e) => fail(e, "Could not post the bill"),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Sales
      </Typography>
      {note && (
        <Alert severity={note.severity} onClose={() => setNote(null)}>
          {note.text}
        </Alert>
      )}

      <SaleDocumentCard
        title="New sale order"
        subtitle="reserves stock — nothing moves until delivery"
        actionLabel="Place order"
        customer={customer}
        onCustomer={setCustomer}
        branch={branch}
        onBranch={setBranch}
        parties={parties.data ?? []}
        branches={branches}
        godowns={godowns}
        accounts={accounts.data ?? []}
        paymentTypes={paymentTypes.data ?? []}
        showMoney={false}
        onSubmit={async (payload) => {
          const o = await createOrder(payload as Parameters<typeof createOrder>[0]);
          setNote({
            text:
              `Order ${o.doc_no} placed — stock reserved.` +
              (o.credit_warning ? ` ${o.credit_warning}` : ""),
            severity: o.credit_warning ? "warning" : "success",
          });
          qc.invalidateQueries({ queryKey: ["sale-orders"] });
          qc.invalidateQueries({ queryKey: ["stock-current"] });
        }}
        onError={(e) => fail(e, "Could not place the order")}
      />

      <SaleDocumentCard
        title="Counter sale"
        subtitle="invoice without an order — the bill moves the stock itself"
        actionLabel="Save & print"
        customer={customer}
        onCustomer={setCustomer}
        branch={branch}
        onBranch={setBranch}
        parties={parties.data ?? []}
        branches={branches}
        godowns={godowns}
        accounts={accounts.data ?? []}
        paymentTypes={paymentTypes.data ?? []}
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
          qc.invalidateQueries({ queryKey: ["stock-current"] });
          qc.invalidateQueries({ queryKey: ["accounts"] });
          // v2 §4: a counter sale ends with paper in the customer's hand
          window.open(`/print/sales_bill/${b.id}`, "_blank");
        }}
        onError={(e) => fail(e, "Could not post the counter sale")}
      />

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Orders
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Status</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {(orders.data ?? []).map((o: SaleOrder) => (
                <TableRow key={o.id}>
                  <TableCell><code>{o.doc_no}</code></TableCell>
                  <TableCell>{partyName(o.customer_id)}</TableCell>
                  <TableCell>
                    <Chip size="small" label={o.status} color={STATUS_COLOR[o.status] ?? "default"} />
                  </TableCell>
                  <TableCell align="right">
                    {o.status === "pending" && (
                      <>
                        <Button size="small" onClick={() => deliver.mutate(o.id)} disabled={deliver.isPending}>
                          Deliver
                        </Button>
                        <Button size="small" color="secondary" onClick={() => cancel.mutate(o.id)} disabled={cancel.isPending}>
                          Cancel
                        </Button>
                      </>
                    )}
                    {o.status === "delivered" && (
                      <Button size="small" onClick={() => setBilling(o.id)} disabled={bill.isPending}>
                        Bill
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(orders.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography color="text.secondary">No orders yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Sales bills
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>Customer</TableCell>
                <TableCell>Source</TableCell>
                <TableCell align="right">Grand total</TableCell>
                <TableCell align="right">Balance</TableCell>
                <TableCell align="right">Payments</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(bills.data ?? []).map((b: SalesBill) => (
                <TableRow key={b.id}>
                  <TableCell><code>{b.doc_no}</code></TableCell>
                  <TableCell>{partyName(b.customer_id)}</TableCell>
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
                    <Typography color="text.secondary">No bills yet.</Typography>
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
        accounts={accounts.data ?? []}
        paymentTypes={paymentTypes.data ?? []}
        products={products.data ?? []}
        posting={bill.isPending}
        onClose={() => setBilling(null)}
        onPost={(money, supply) => billing && bill.mutate({ id: billing, money, supply })}
      />
    </Stack>
  );
}

/** The sale order and the counter sale differ only in whether stock is reserved
 *  or moved and whether money changes hands now, so they share one editor. */
function SaleDocumentCard({
  title,
  subtitle,
  actionLabel,
  customer,
  onCustomer,
  branch,
  onBranch,
  parties,
  branches,
  godowns,
  accounts,
  paymentTypes,
  showMoney,
  onSubmit,
  onError,
}: {
  title: string;
  subtitle: string;
  actionLabel: string;
  customer: string;
  onCustomer: (v: string) => void;
  branch: string;
  onBranch: (v: string) => void;
  parties: { id: number; name: string }[];
  branches: { id: number; name: string }[];
  godowns: { id: number; name: string; branch_id: number }[];
  accounts: { id: number; name: string }[];
  paymentTypes: { id: number; name: string }[];
  showMoney: boolean;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  onError: (e: unknown) => void;
}) {
  const [lines, setLines] = useState<SaleLine[]>([emptyLine()]);
  const [money, setMoney] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [supply, setSupply] = useState("intra");
  const [posting, setPosting] = useState(false);

  // a line's godown has to belong to the chosen branch — switching branch
  // repoints every line rather than leaving one pointing somewhere invalid
  useEffect(() => {
    const valid = new Set(godowns.map((g) => String(g.id)));
    const fallback = godowns[0] ? String(godowns[0].id) : "";
    setLines((ls) =>
      ls.map((l) => (l.godown_id && valid.has(l.godown_id) ? l : { ...l, godown_id: fallback })),
    );
  }, [godowns]);

  const previewLines = toPreviewLines(lines);
  const preview = useQuery({
    queryKey: ["money-preview", previewLines, money, supply],
    queryFn: () => previewMoney(previewLines, money, supply),
    enabled: previewLines.length > 0,
  });

  const ready = !!customer && !!branch && lines.some(isComplete);

  const submit = async () => {
    if (!ready) return;
    setPosting(true);
    try {
      await onSubmit({
        customer_id: Number(customer),
        branch_id: Number(branch),
        supply_type: supply,
        ...(showMoney ? moneyPayload(money) : {}),
        lines: toPayload(lines),
      });
      setLines([emptyLine(godowns[0] ? String(godowns[0].id) : "")]);
      setMoney({ ...EMPTY_MONEY });
    } catch (e) {
      onError(e);
    } finally {
      setPosting(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="caption" color="text.secondary">{subtitle}</Typography>

        <Box component="form" onSubmit={(e) => { e.preventDefault(); submit(); }} sx={{ mt: 2 }}>
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
              <TextField
                label="Customer" select size="small" value={customer}
                onChange={(e) => onCustomer(e.target.value)} sx={{ minWidth: 220 }}
              >
                {parties.map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
              </TextField>
              <TextField
                label="Branch" select size="small" value={branch}
                onChange={(e) => onBranch(e.target.value)} sx={{ minWidth: 180 }}
                helperText="the godowns below are this branch's"
              >
                {branches.map((b) => (<MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>))}
              </TextField>
              <TextField
                label="Supply" select size="small" value={supply}
                onChange={(e) => setSupply(e.target.value)} sx={{ minWidth: 190 }}
              >
                <MenuItem value="intra">Intra (CGST+SGST)</MenuItem>
                <MenuItem value="inter">Inter (IGST)</MenuItem>
              </TextField>
            </Stack>

            <SaleLinesEditor
              lines={lines}
              onChange={setLines}
              godowns={godowns}
              onPriceModeHint={(inclusive) =>
                inclusive && setMoney((m) => ({ ...m, price_mode: "inclusive" }))
              }
            />

            <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
              {showMoney && (
                <Box sx={{ flex: 1 }}>
                  <MoneyFields value={money} onChange={setMoney} accounts={accounts}
                    paymentTypes={paymentTypes} compact />
                </Box>
              )}
              <Box sx={{ p: 2, bgcolor: "#FCFAF6", borderRadius: 1, ml: showMoney ? 0 : "auto" }}>
                <MoneyTotalsPanel totals={preview.data?.totals} />
                <Button
                  type="submit" variant="contained" fullWidth sx={{ mt: 2 }}
                  disabled={posting || !ready}
                >
                  {actionLabel}
                </Button>
              </Box>
            </Stack>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

/** v2 §4: the order supplies the lines, this collects the money block and
 *  shows server-computed totals before the invoice is posted. */
function BillDialog({
  orderId,
  accounts,
  paymentTypes,
  products,
  posting,
  onClose,
  onPost,
}: {
  orderId: number | null;
  accounts: { id: number; name: string }[];
  paymentTypes: { id: number; name: string }[];
  products: { id: number; gst_rate: string | null }[];
  posting: boolean;
  onClose: () => void;
  onPost: (money: Record<string, unknown>, supply: string) => void;
}) {
  const [mny, setMny] = useState<MoneyHeader>({ ...EMPTY_MONEY });
  const [supply, setSupply] = useState("intra");

  const order = useQuery({
    queryKey: ["sale-order", orderId],
    queryFn: () => getOrder(orderId!),
    enabled: orderId != null,
  });

  const previewLines = (order.data?.lines ?? []).map((l) => ({
    qty: l.entered_qty,
    rate: l.rate,
    gst_rate: products.find((p) => p.id === l.product_id)?.gst_rate ?? "0",
  }));

  const preview = useQuery({
    queryKey: ["money-preview", previewLines, mny, supply],
    queryFn: () => previewMoney(previewLines, mny, supply),
    enabled: previewLines.length > 0,
  });

  return (
    <Dialog open={orderId != null} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Bill order {order.data?.doc_no ?? ""}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction="row" spacing={2} alignItems="center">
            <TextField
              size="small" label="Supply" select value={supply}
              onChange={(e) => setSupply(e.target.value)} sx={{ width: 190 }}
            >
              <MenuItem value="intra">Intra (CGST+SGST)</MenuItem>
              <MenuItem value="inter">Inter (IGST)</MenuItem>
            </TextField>
            <Typography variant="body2" color="text.secondary">
              {previewLines.length} line{previewLines.length === 1 ? "" : "s"} from the order
            </Typography>
          </Stack>
          <Divider />
          <Stack direction={{ xs: "column", md: "row" }} spacing={3} alignItems="flex-start">
            <Box sx={{ flex: 1 }}>
              <MoneyFields value={mny} onChange={setMny} accounts={accounts}
                paymentTypes={paymentTypes} compact />
            </Box>
            <Box sx={{ p: 2, bgcolor: "#FCFAF6", borderRadius: 1 }}>
              <MoneyTotalsPanel totals={preview.data?.totals} />
            </Box>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={posting || !previewLines.length}
          onClick={() => onPost(moneyPayload(mny), supply)}
        >
          Post bill
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** v2 §3 "Payment history" — what has settled this invoice and what is left. */
function PaymentHistoryDialog({
  billId,
  onClose,
}: {
  billId: number | null;
  onClose: () => void;
}) {
  const history = useQuery({
    queryKey: ["bill-payments", billId],
    queryFn: () => billPayments("sales", billId!),
    enabled: billId != null,
  });
  const h = history.data;

  return (
    <Dialog open={billId != null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Payment history</DialogTitle>
      <DialogContent>
        {h ? (
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <Chip label={`Invoice ₹${h.invoice_total}`} />
              <Chip color="success" label={`Settled ₹${h.settled}`} />
              <Chip color={Number(h.outstanding) > 0 ? "error" : "default"}
                label={`Outstanding ₹${h.outstanding}`} />
            </Stack>
            <Divider />
            {h.payments.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Nothing has been settled against this invoice yet.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell align="right">Amount</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {h.payments.map((p, i) => (
                    <TableRow key={i}>
                      <TableCell>{p.effective_date}</TableCell>
                      <TableCell>
                        {p.doc_no ?? p.source_doc_type.replace(/_/g, " ")}
                      </TableCell>
                      <TableCell>{p.payment_type ?? "—"}</TableCell>
                      <TableCell align="right">₹{p.amount}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Stack>
        ) : (
          <Typography color="text.secondary">Loading…</Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
