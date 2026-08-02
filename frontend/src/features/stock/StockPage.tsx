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

import { type Godown } from "./api";
import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import { errorMessage } from "../../lib/api";
import { listProducts } from "../products/api";
import { listUnits } from "../units/api";
import { getCurrentStock, getMovements, listGodowns, listReorder, postAdjustment, reconcile, setReorder } from "./api";

const REASONS = ["opening", "increase", "decrease", "damage", "shortage"];
const INBOUND = new Set(["opening", "increase"]);

export function StockPage() {
  const qc = useQueryClient();
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });
  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const scope = useBranchScope();
  // godowns of the selected branch only — posting into another
  // branch's godown is refused by the server anyway
  const godowns: { data: Godown[] } = { data: scope.godowns };

  const [productId, setProductId] = useState<number | "">("");
  const [form, setForm] = useState({ godown_id: "", reason: "opening", qty: "", unit_id: "", cost: "" });
  const [reorderQty, setReorderQty] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  // default selected product + its base unit
  useEffect(() => {
    if (productId === "" && products.data && products.data.length > 0) {
      setProductId(products.data[0].id);
    }
  }, [products.data, productId]);
  const selectedProduct = products.data?.find((p) => p.id === productId);
  useEffect(() => {
    if (selectedProduct) setForm((f) => ({ ...f, unit_id: String(selectedProduct.base_unit_id) }));
  }, [selectedProduct]);
  useEffect(() => {
    if (godowns.data && godowns.data.length > 0 && !form.godown_id) {
      setForm((f) => ({ ...f, godown_id: String(godowns.data![0].id) }));
    }
  }, [godowns.data, form.godown_id]);

  const current = useQuery({
    queryKey: ["stock-current", productId],
    queryFn: () => getCurrentStock(productId as number),
    enabled: productId !== "",
  });
  const movements = useQuery({
    queryKey: ["stock-movements", productId],
    queryFn: () => getMovements(productId as number),
    enabled: productId !== "",
  });

  const adjust = useMutation({
    mutationFn: () =>
      postAdjustment({
        godown_id: Number(form.godown_id),
        adj_reason: form.reason,
        lines: [
          {
            product_id: productId as number,
            entered_qty: form.qty,
            entered_unit_id: Number(form.unit_id),
            unit_cost: INBOUND.has(form.reason) ? form.cost || "0" : null,
          },
        ],
      }),
    onSuccess: () => {
      setForm({ ...form, qty: "", cost: "" });
      setMsg(null);
      qc.invalidateQueries({ queryKey: ["stock-current", productId] });
      qc.invalidateQueries({ queryKey: ["stock-movements", productId] });
    },
    onError: (e: unknown) => {
      setMsg(errorMessage(e, "Adjustment failed"));
    },
  });

  const verify = useMutation({
    mutationFn: reconcile,
    onSuccess: (r) => setMsg(r.ok ? "✓ Integrity OK — balances match the ledger." : "⚠ Drift detected!"),
  });

  const reorders = useQuery({ queryKey: ["reorders"], queryFn: listReorder });
  const currentReorder = reorders.data?.find((r) => r.product_id === productId)?.min_qty;
  const mReorder = useMutation({
    mutationFn: () => setReorder({ product_id: productId as number, min_qty: reorderQty }),
    onSuccess: () => {
      setMsg("Reorder level saved — low-stock alerts will use it.");
      setReorderQty("");
      qc.invalidateQueries({ queryKey: ["reorders"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const unitCode = (id: number) => units.data?.find((u) => u.id === id)?.code ?? id;

  return (
    <Stack spacing={3}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Typography variant="h4" fontWeight={800}>
          Stock
        </Typography>
      <BranchFilter
        value={scope.branch}
        onChange={scope.setBranch}
        branches={scope.branches}
        helperText="stock figures below are this branch's"
      />
        <Button variant="outlined" onClick={() => verify.mutate()} sx={{ ml: "auto" }}>
          Verify integrity
        </Button>
      </Stack>
      {msg && <Alert severity={msg.startsWith("✓") ? "success" : "info"}>{msg}</Alert>}

      <TextField
        label="Product"
        select
        value={productId === "" ? "" : String(productId)}
        onChange={(e) => setProductId(Number(e.target.value))}
        sx={{ maxWidth: 360 }}
      >
        {(products.data ?? []).map((p) => (
          <MenuItem key={p.id} value={String(p.id)}>
            {p.code} · {p.name}
          </MenuItem>
        ))}
      </TextField>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Current stock
          </Typography>
          {current.data ? (
            <>
              <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
                <Chip label={`On hand: ${current.data.total_on_hand}`} color="primary" />
                <Chip label={`Reserved: ${current.data.total_reserved}`} />
                <Chip label={`Available: ${current.data.total_available}`} color="secondary" />
              </Stack>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Godown</TableCell>
                    <TableCell align="right">On hand</TableCell>
                    <TableCell align="right">Available</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {current.data.by_godown.map((g) => (
                    <TableRow key={g.godown_id}>
                      <TableCell>
                        {godowns.data?.find((x) => x.id === g.godown_id)?.name ?? g.godown_id}
                      </TableCell>
                      <TableCell align="right">{g.on_hand}</TableCell>
                      <TableCell align="right">{g.available}</TableCell>
                    </TableRow>
                  ))}
                  {current.data.by_godown.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={3}>
                        <Typography color="text.secondary">No stock yet.</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </>
          ) : (
            <Typography color="text.secondary">Select a product.</Typography>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Reorder level
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Current: {currentReorder ? `${currentReorder} (base units)` : "not set"} — stock below this shows in the low-stock alert &amp; dashboard.
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (productId !== "" && reorderQty) mReorder.mutate();
            }}
          >
            <Stack direction="row" spacing={2} alignItems="center">
              <TextField label="Min qty (base)" value={reorderQty} onChange={(e) => setReorderQty(e.target.value)} sx={{ width: 160 }} />
              <Button type="submit" variant="outlined" disabled={mReorder.isPending || productId === ""}>
                Set reorder level
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Stock adjustment
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (productId !== "" && form.godown_id && form.qty) adjust.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
              <TextField
                label="Godown"
                select
                value={form.godown_id}
                onChange={(e) => setForm({ ...form, godown_id: e.target.value })}
                sx={{ width: 180 }}
              >
                {(godowns.data ?? []).map((g) => (
                  <MenuItem key={g.id} value={String(g.id)}>
                    {g.name}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Reason"
                select
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
                sx={{ width: 150 }}
              >
                {REASONS.map((r) => (
                  <MenuItem key={r} value={r}>
                    {r}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Qty"
                value={form.qty}
                onChange={(e) => setForm({ ...form, qty: e.target.value })}
                sx={{ width: 120 }}
              />
              <TextField
                label="Unit"
                select
                value={form.unit_id}
                onChange={(e) => setForm({ ...form, unit_id: e.target.value })}
                sx={{ width: 120 }}
              >
                {(units.data ?? []).map((u) => (
                  <MenuItem key={u.id} value={String(u.id)}>
                    {u.code}
                  </MenuItem>
                ))}
              </TextField>
              {INBOUND.has(form.reason) && (
                <TextField
                  label="Unit cost"
                  value={form.cost}
                  onChange={(e) => setForm({ ...form, cost: e.target.value })}
                  sx={{ width: 120 }}
                />
              )}
              <Button type="submit" variant="contained" disabled={adjust.isPending}>
                Post
              </Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            Increase/opening add stock (need unit cost → updates moving-average); decrease/damage/shortage remove it.
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Movement ledger
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell>
                <TableCell>Type</TableCell>
                <TableCell align="right">Qty (base)</TableCell>
                <TableCell align="right">Unit cost</TableCell>
                <TableCell>Source</TableCell>
                <TableCell>Date</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(movements.data ?? []).map((m) => (
                <TableRow key={m.id}>
                  <TableCell>{m.id}</TableCell>
                  <TableCell>{m.movement_type}</TableCell>
                  <TableCell align="right" sx={{ color: Number(m.signed_qty) < 0 ? "error.main" : "success.main" }}>
                    {m.signed_qty}
                  </TableCell>
                  <TableCell align="right">{m.unit_cost ?? "—"}</TableCell>
                  <TableCell>
                    {m.source_doc_type} #{m.source_doc_id}
                  </TableCell>
                  <TableCell>{m.effective_date}</TableCell>
                </TableRow>
              ))}
              {(movements.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No movements yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  );
}
