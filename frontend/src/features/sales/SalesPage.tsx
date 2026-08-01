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
import { useEffect, useState } from "react";

import { listAccounts } from "../accounts/api";
import { EMPTY_MONEY, moneyPayload, previewMoney, type MoneyHeader } from "../money/api";
import { MoneyFields, MoneyTotalsPanel } from "../money/MoneyBlock";
import { listParties } from "../parties/api";
import { listProducts } from "../products/api";
import { getCurrentStock, listGodowns } from "../stock/api";
import {
  billOrder,
  cancelOrder,
  createOrder,
  deliverOrder,
  getOrder,
  listBills,
  listOrders,
  type SaleOrder,
  type SalesBill,
} from "./api";

const EMPTY = { customer: "", godown: "", product: "", qty: "", rate: "" };
const STATUS_COLOR: Record<string, "warning" | "success" | "default"> = {
  pending: "warning",
  delivered: "success",
  cancelled: "default",
};

export function SalesPage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const godowns = useQuery({ queryKey: ["godowns"], queryFn: listGodowns });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const orders = useQuery({ queryKey: ["sale-orders"], queryFn: listOrders });
  const bills = useQuery({ queryKey: ["sales-bills"], queryFn: listBills });

  const [f, setF] = useState(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const [billing, setBilling] = useState<number | null>(null);
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });

  useEffect(() => {
    if (parties.data?.length && !f.customer) setF((s) => ({ ...s, customer: String(parties.data![0].id) }));
    if (godowns.data?.length && !f.godown) setF((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (products.data?.length && !f.product) setF((s) => ({ ...s, product: String(products.data![0].id) }));
  }, [parties.data, godowns.data, products.data, f.customer, f.godown, f.product]);

  const baseUnitOf = (pid: number) => products.data?.find((p) => p.id === pid)?.base_unit_id ?? 0;
  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  // live availability of the selected product
  const avail = useQuery({
    queryKey: ["stock-current", Number(f.product)],
    queryFn: () => getCurrentStock(Number(f.product)),
    enabled: !!f.product,
  });

  const create = useMutation({
    mutationFn: () =>
      createOrder({
        customer_id: Number(f.customer),
        lines: [
          { product_id: Number(f.product), godown_id: Number(f.godown), entered_qty: f.qty, entered_unit_id: baseUnitOf(Number(f.product)), rate: f.rate || "0" },
        ],
      }),
    onSuccess: (o) => {
      setMsg(`Order ${o.doc_no} placed — stock reserved.`);
      setF({ ...f, qty: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Order failed");
    },
  });

  const cancel = useMutation({
    mutationFn: (id: number) => cancelOrder(id),
    onSuccess: () => {
      setMsg("Order cancelled — reservation released.");
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
  });

  const deliver = useMutation({
    mutationFn: (id: number) => deliverOrder(id),
    onSuccess: (d) => {
      setMsg(`Dispatched ${d.doc_no} — stock moved once, reservation released, order delivered.`);
      qc.invalidateQueries({ queryKey: ["sale-orders"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Delivery failed");
    },
  });

  const bill = useMutation({
    mutationFn: (args: { id: number; money: Record<string, unknown>; supply: string }) =>
      billOrder(args.id, args.money, args.supply),
    onSuccess: (b) => {
      setMsg(
        `Billed ${b.doc_no}: ₹${b.grand_total} (COGS ₹${b.cogs_total})` +
          (Number(b.paid_amount ?? 0) ? ` · paid ₹${b.paid_amount} · balance ₹${b.balance_amount}` : "") +
          ". Delivered goods → no extra stock movement.",
      );
      setBilling(null);
      qc.invalidateQueries({ queryKey: ["sales-bills"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(typeof d === "string" ? d : "Billing failed");
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Sales
      </Typography>
      {msg && <Alert severity={msg.includes("failed") ? "error" : "success"}>{msg}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            New sale order
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (f.customer && f.godown && f.product && f.qty) create.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField label="Customer" select value={f.customer} onChange={(e) => setF({ ...f, customer: e.target.value })} sx={{ minWidth: 180 }}>
                {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
              </TextField>
              <TextField label="Godown" select value={f.godown} onChange={(e) => setF({ ...f, godown: e.target.value })} sx={{ width: 160 }}>
                {(godowns.data ?? []).map((g) => (<MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>))}
              </TextField>
              <TextField label="Product" select value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })} sx={{ minWidth: 180 }}>
                {(products.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>))}
              </TextField>
              <TextField label="Qty" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} sx={{ width: 100 }} />
              <TextField label="Rate" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} sx={{ width: 110 }} />
              <Button type="submit" variant="contained" sx={{ height: 56 }} disabled={create.isPending}>
                Place order
              </Button>
            </Stack>
          </Box>
          {avail.data && (
            <Typography variant="caption" color="text.secondary">
              Available now: on hand {avail.data.total_on_hand}, reserved {avail.data.total_reserved},{" "}
              <strong>available {avail.data.total_available}</strong>. Placing an order reserves stock (no movement yet).
            </Typography>
          )}
        </CardContent>
      </Card>

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
                  <TableCell><Chip size="small" label={o.status} color={STATUS_COLOR[o.status] ?? "default"} /></TableCell>
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
                <TableCell>Order</TableCell>
                <TableCell align="right">Grand total</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(bills.data ?? []).map((b: SalesBill) => (
                <TableRow key={b.id}>
                  <TableCell><code>{b.doc_no}</code></TableCell>
                  <TableCell>{partyName(b.customer_id)}</TableCell>
                  <TableCell>{b.sale_order_id ? `#${b.sale_order_id}` : "—"}</TableCell>
                  <TableCell align="right">₹{b.grand_total}</TableCell>
                </TableRow>
              ))}
              {(bills.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    <Typography color="text.secondary">No bills yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <BillDialog
        orderId={billing}
        accounts={accounts.data ?? []}
        products={products.data ?? []}
        posting={bill.isPending}
        onClose={() => setBilling(null)}
        onPost={(money, supply) => billing && bill.mutate({ id: billing, money, supply })}
      />
    </Stack>
  );
}

/** v2 §4: the order supplies the lines, this collects the money block and
 *  shows server-computed totals before the invoice is posted. */
function BillDialog({
  orderId,
  accounts,
  products,
  posting,
  onClose,
  onPost,
}: {
  orderId: number | null;
  accounts: { id: number; name: string }[];
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
              <MoneyFields value={mny} onChange={setMny} accounts={accounts} compact />
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
