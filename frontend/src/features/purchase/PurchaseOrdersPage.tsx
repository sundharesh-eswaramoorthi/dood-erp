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
import { useEffect, useState } from "react";

import { ProductPicker } from "../../components/ProductPicker";
import { errorMessage } from "../../lib/api";
import { listAccounts } from "../accounts/api";
import { listParties } from "../parties/api";
import { getFeatureFlags } from "../settings/api";
import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import {
  cancelOrder,
  createOrder,
  listOrders,
  receiveOrder,
  type PurchaseOrder,
} from "./api";

export function PurchaseOrdersPage() {
  const qc = useQueryClient();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const scope = useBranchScope();
  // godowns of the selected branch only — posting into another
  // branch's godown is refused by the server anyway
  const godowns = { data: scope.godowns };
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const flags = useQuery({ queryKey: ["feature-flags"], queryFn: getFeatureFlags });
  const orders = useQuery({
    queryKey: ["purchase-orders"], queryFn: listOrders,
    enabled: !!flags.data?.purchase_order,
  });

  const [f, setF] = useState({ supplier: "", godown: "", product: "" });
  const [po, setPo] = useState({
    product: "", unit_id: "", qty: "", rate: "", gst: "", expected: "", advance: "", account: "",
  });
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (godowns.data?.length && !f.godown) setF((s) => ({ ...s, godown: String(godowns.data![0].id) }));
    if (parties.data?.length && !f.supplier) setF((s) => ({ ...s, supplier: String(parties.data![0].id) }));
  }, [godowns.data, parties.data, f.godown, f.supplier]);

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? id;

  const doPO = useMutation({
    mutationFn: () =>
      createOrder({
        supplier_id: Number(f.supplier),
        godown_id: Number(f.godown) || undefined,
        expected_date: po.expected || null,
        advance_amount: po.advance || "0",
        payment_account_id: po.advance ? Number(po.account) || undefined : undefined,
        lines: [{
          product_id: Number(po.product),
          entered_qty: po.qty,
          entered_unit_id: Number(po.unit_id),
          rate: po.rate || "0",
          gst_rate: po.gst || undefined,
        }],
      }),
    onSuccess: (o) => {
      setMsg(
        `PO ${o.doc_no} created: ₹${o.grand_total}` +
          (Number(o.advance_amount ?? 0) ? ` · advance ₹${o.advance_amount} paid` : ""),
      );
      setPo({ ...po, product: "", qty: "", rate: "", advance: "" });
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e: unknown) => setMsg(errorMessage(e, "PO failed")),
  });

  // Receiving a PO raises the bill for everything still pending. Over-receipt
  // is warned about, not blocked (decision #10).
  const receivePO = useMutation({
    mutationFn: (id: number) => receiveOrder(id),
    onSuccess: (b) => {
      const warn = b.warnings?.length ? ` — ${b.warnings.join("; ")}` : "";
      setMsg(`Posted ${b.doc_no} against the PO: ₹${b.grand_total}${warn}`);
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
      qc.invalidateQueries({ queryKey: ["purchase-bills"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
    onError: (e: unknown) => setMsg(errorMessage(e, "Receive failed")),
  });

  const cancelPO = useMutation({
    mutationFn: (id: number) => cancelOrder(id),
    onSuccess: () => {
      setMsg("Purchase order cancelled");
      qc.invalidateQueries({ queryKey: ["purchase-orders"] });
    },
    onError: (e: unknown) => setMsg(errorMessage(e, "Cancel failed")),
  });

  if (!flags.data?.purchase_order) {
    return (
      <Stack spacing={3}>
        <Typography variant="h4" fontWeight={800}>Purchase orders</Typography>
        <Alert severity="info">
          Purchase orders are switched off. Enable the <code>purchase_order</code> feature flag
          under Settings to use them.
        </Alert>
      </Stack>
    );
  }

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>Purchase orders</Typography>
        <Typography color="text.secondary">
          An order commits to buy; receiving it raises the bill and moves the stock.
        </Typography>
      </Box>
      <BranchFilter
        value={scope.branch}
        onChange={scope.setBranch}
        branches={scope.branches}
        helperText="ordered for this branch"
      />
      {msg && (
        <Alert severity={msg.includes("failed") ? "error" : "success"} onClose={() => setMsg(null)}>
          {msg}
        </Alert>
      )}
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <TextField size="small" label="Supplier" select value={f.supplier}
          onChange={(e) => setF({ ...f, supplier: e.target.value })} sx={{ minWidth: 200 }}>
          {(parties.data ?? []).map((p) => (<MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>))}
        </TextField>
        <TextField size="small" label="Receive into" select value={f.godown}
          onChange={(e) => setF({ ...f, godown: e.target.value })} sx={{ minWidth: 180 }}>
          {(godowns.data ?? []).map((g) => (<MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>))}
        </TextField>
      </Stack>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Purchase orders <Typography component="span" variant="caption" color="text.secondary">(enabled in Settings)</Typography>
            </Typography>
            <Box
              component="form"
              onSubmit={(e) => {
                e.preventDefault();
                if (po.product && po.unit_id && po.qty) doPO.mutate();
              }}
            >
              <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                <ProductPicker
                  value={po.product ? Number(po.product) : null}
                  size="medium"
                  width={230}
                  onChange={(p) =>
                    setPo({
                      ...po,
                      product: p ? String(p.id) : "",
                      unit_id: String(p?.units?.find((u) => u.is_base)?.unit_id ?? p?.base_unit_id ?? ""),
                      gst: p?.gst_rate ?? "",
                      rate: p?.purchase_price ?? po.rate,
                    })
                  }
                />
                <TextField label="Qty" value={po.qty} onChange={(e) => setPo({ ...po, qty: e.target.value })} sx={{ width: 100 }} />
                <TextField label="Rate" value={po.rate} onChange={(e) => setPo({ ...po, rate: e.target.value })} sx={{ width: 110 }} />
                <TextField label="GST %" value={po.gst} onChange={(e) => setPo({ ...po, gst: e.target.value })} sx={{ width: 95 }} />
                <TextField label="Expected" type="date" InputLabelProps={{ shrink: true }}
                  value={po.expected} onChange={(e) => setPo({ ...po, expected: e.target.value })} sx={{ width: 170 }} />
                <TextField label="Advance" value={po.advance}
                  onChange={(e) => setPo({ ...po, advance: e.target.value })} sx={{ width: 110 }}
                  helperText="paid up front" />
                <TextField label="From account" select value={po.account}
                  onChange={(e) => setPo({ ...po, account: e.target.value })}
                  sx={{ width: 170 }} disabled={!po.advance}>
                  {(accounts.data ?? []).map((a) => (<MenuItem key={a.id} value={String(a.id)}>{a.name}</MenuItem>))}
                </TextField>
                <Button type="submit" variant="contained" disabled={doPO.isPending}>Create PO</Button>
              </Stack>
            </Box>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Doc</TableCell>
                  <TableCell>Supplier</TableCell>
                  <TableCell>Expected</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell align="right">Advance</TableCell>
                  <TableCell align="right">Balance</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(orders.data ?? []).map((o: PurchaseOrder) => (
                  <TableRow key={o.id}>
                    <TableCell><code>{o.doc_no}</code></TableCell>
                    <TableCell>{partyName(o.supplier_id)}</TableCell>
                    <TableCell>{o.expected_date || "—"}</TableCell>
                    <TableCell align="right">₹{o.grand_total ?? "0.00"}</TableCell>
                    <TableCell align="right">₹{o.advance_amount ?? "0.00"}</TableCell>
                    <TableCell align="right">₹{o.balance_amount ?? "0.00"}</TableCell>
                    <TableCell>
                      <Chip size="small" label={o.status}
                        color={o.status === "closed" ? "success" : o.status === "cancelled" ? "default" : "warning"} />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" variant="outlined"
                        disabled={receivePO.isPending || o.status === "closed" || o.status === "cancelled"}
                        onClick={() => receivePO.mutate(o.id)}>
                        Receive
                      </Button>
                      <Button size="small" color="inherit"
                        disabled={cancelPO.isPending || o.status === "closed" || o.status === "cancelled"}
                        onClick={() => cancelPO.mutate(o.id)}>
                        Cancel
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(orders.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography color="text.secondary">No purchase orders yet.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <Typography variant="caption" color="text.secondary">
              "Receive" raises the purchase bill for everything still pending and moves the stock.
              Receiving more than ordered is allowed but warns (tolerance is a setting).
            </Typography>
          </CardContent>
        </Card>
    </Stack>
  );
}
