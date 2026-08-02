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
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { BranchFilter } from "../../components/BranchFilter";
import { useBranchScope } from "../../components/useBranchScope";
import { listProducts } from "../products/api";
import { invalidateStock } from "../../app/refresh";
import {
  createTransfer,
  createVerification,
  dispatchTransfer,
  postVerification,
  receiveTransfer,
  type Godown,
  listTransfers,
  type Transfer,
  type TransferRow,
  type Verification,
} from "./api";

export function TransfersPage() {
  const qc = useQueryClient();
  const scope = useBranchScope();
  // The source is a godown of the branch you are working in. The DESTINATION
  // is any godown you can reach, in any of your branches — that is what makes
  // this a branch-to-branch transfer. The server reads the branch off each
  // godown, so choosing one across the line is the whole gesture.
  const godowns: { data: Godown[] } = { data: scope.godowns };
  const destinations = scope.allGodowns;
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });

  const [t, setT] = useState({ from: "", to: "", product: "", qty: "" });
  const [current, setCurrent] = useState<Transfer | null>(null);
  const [v, setV] = useState({ godown: "", product: "", physical: "" });
  const [verif, setVerif] = useState<Verification | null>(null);
  // A transfer used to live only in the screen that created it, so a draft
  // survived a page refresh in the database but nowhere a person could reach.
  const [state, setState] = useState<"open" | "closed">("open");
  const transfers = useQuery({
    queryKey: ["transfers", state],
    queryFn: () => listTransfers(state),
  });

  useEffect(() => {
    const g = godowns.data;
    if (g && g.length >= 1 && !t.from) setT((s) => ({ ...s, from: String(g[0].id) }));
    if (g && g.length >= 1 && !v.godown) setV((s) => ({ ...s, godown: String(g[0].id) }));
  }, [godowns.data, t.from, v.godown]);
  // default the destination to the first godown that is not the source, which
  // may well be in another branch when this one has only the one store
  useEffect(() => {
    if (!t.from || t.to) return;
    const other = destinations.find((g) => String(g.id) !== t.from);
    if (other) setT((s) => ({ ...s, to: String(other.id) }));
  }, [destinations, t.from, t.to]);
  // switching branch repoints the source; a destination that is still reachable
  // stays put so a deliberate cross-branch choice is not silently undone
  useEffect(() => {
    if (t.from && !godowns.data.some((g) => String(g.id) === t.from)) {
      setT((s) => ({ ...s, from: godowns.data[0] ? String(godowns.data[0].id) : "" }));
    }
  }, [godowns.data, t.from]);
  useEffect(() => {
    const p = products.data;
    if (p && p.length && !t.product) setT((s) => ({ ...s, product: String(p[0].id) }));
    if (p && p.length && !v.product) setV((s) => ({ ...s, product: String(p[0].id) }));
  }, [products.data, t.product, v.product]);

  const baseUnitOf = (pid: number) => products.data?.find((p) => p.id === pid)?.base_unit_id ?? 0;
  const branchOfGodown = (id: string) => destinations.find((g) => String(g.id) === id)?.branch_id;
  // the move crosses a branch line when the two godowns sit in different branches
  const crossBranch =
    !!t.from && !!t.to && branchOfGodown(t.from) !== undefined &&
    branchOfGodown(t.from) !== branchOfGodown(t.to);
  const refreshStock = () => invalidateStock(qc);
  const refreshList = () => qc.invalidateQueries({ queryKey: ["transfers"] });

  const mCreate = useMutation({
    mutationFn: () =>
      createTransfer({
        from_godown_id: Number(t.from),
        to_godown_id: Number(t.to),
        lines: [
          {
            product_id: Number(t.product),
            entered_qty: t.qty,
            entered_unit_id: baseUnitOf(Number(t.product)),
          },
        ],
      }),
    onSuccess: (tr) => {
      setCurrent(tr);
      refreshList();
    },
  });
  const mDispatch = useMutation({
    mutationFn: (id: number) => dispatchTransfer(id),
    onSuccess: (tr) => {
      setCurrent(tr);
      refreshStock();
      refreshList();
    },
  });
  const mReceive = useMutation({
    mutationFn: (id: number) => receiveTransfer(id),
    onSuccess: (tr) => {
      setCurrent(tr);
      refreshStock();
      refreshList();
    },
  });

  const mVerify = useMutation({
    mutationFn: async () => {
      const created = await createVerification({
        branch_id: scope.branchId,
        godown_id: Number(v.godown),
        lines: [{ product_id: Number(v.product), physical_qty: v.physical }],
      });
      return postVerification(created.id);
    },
    onSuccess: (res) => {
      setVerif(res);
      refreshStock();
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Transfers &amp; Verification
      </Typography>
      <BranchFilter
        value={scope.branch}
        onChange={scope.setBranch}
        branches={scope.branches}
        helperText="transfers move between godowns"
      />

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Godown transfer
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (t.from && t.to && t.product && t.qty) mCreate.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
              <TextField label="From" select value={t.from} onChange={(e) => setT({ ...t, from: e.target.value })} sx={{ width: 170 }}>
                {(godowns.data ?? []).map((g) => (
                  <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                ))}
              </TextField>
              <TextField
                label="To"
                select
                value={t.to}
                onChange={(e) => setT({ ...t, to: e.target.value })}
                sx={{ width: 220 }}
                helperText={scope.multiBranch ? "any branch you work in" : undefined}
              >
                {destinations.map((g) => (
                  <MenuItem key={g.id} value={String(g.id)}>{scope.godownLabel(g.id)}</MenuItem>
                ))}
              </TextField>
              <TextField label="Product" select value={t.product} onChange={(e) => setT({ ...t, product: e.target.value })} sx={{ width: 220 }}>
                {(products.data ?? []).map((p) => (
                  <MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>
                ))}
              </TextField>
              <TextField label="Qty" value={t.qty} onChange={(e) => setT({ ...t, qty: e.target.value })} sx={{ width: 100 }} />
              <Button type="submit" variant="contained" disabled={mCreate.isPending || t.from === t.to}>
                Create draft
              </Button>
            </Stack>
          </Box>
          {t.from === t.to && (
            <Typography color="error" variant="caption">
              Source and destination godown must differ.
            </Typography>
          )}
          {crossBranch && (
            <Typography color="text.secondary" variant="caption" component="div" sx={{ mt: 1 }}>
              Branch transfer: {scope.branchName(branchOfGodown(t.from)!)} →{" "}
              {scope.branchName(branchOfGodown(t.to)!)}. The goods leave on dispatch at their
              current average cost and arrive at that same cost when received, so the value
              travels with them.
            </Typography>
          )}

          {current && (
            <Alert
              severity={current.status === "received" ? "success" : "info"}
              sx={{ mt: 2 }}
              action={
                current.status === "draft" ? (
                  <Button size="small" onClick={() => mDispatch.mutate(current.id)} disabled={mDispatch.isPending}>
                    Dispatch
                  </Button>
                ) : current.status === "dispatched" ? (
                  <Button size="small" onClick={() => mReceive.mutate(current.id)} disabled={mReceive.isPending}>
                    Receive
                  </Button>
                ) : undefined
              }
            >
              {current.doc_no} · {scope.godownLabel(current.from_godown_id)} →{" "}
              {scope.godownLabel(current.to_godown_id)} ·{" "}
              <Chip size="small" label={current.status} />
              {current.status === "dispatched" && " (in transit)"}
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>Transfers</Typography>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={state}
              onChange={(_, v) => v && setState(v)}
            >
              <ToggleButton value="open">Open</ToggleButton>
              <ToggleButton value="closed">Closed</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Open = a draft waiting to be dispatched, or goods in transit waiting to be
            received. Closed = received or cancelled.
          </Typography>
          <Table size="small" sx={{ mt: 1 }}>
            <TableHead>
              <TableRow>
                <TableCell>Doc</TableCell>
                <TableCell>From</TableCell>
                <TableCell>To</TableCell>
                <TableCell align="right">Items</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(transfers.data ?? []).map((r: TransferRow) => (
                <TableRow key={r.id} sx={{ opacity: r.status === "cancelled" ? 0.5 : 1 }}>
                  <TableCell><code>{r.doc_no}</code></TableCell>
                  <TableCell>{scope.godownLabel(r.from_godown_id)}</TableCell>
                  <TableCell>
                    {scope.godownLabel(r.to_godown_id)}
                    {r.from_branch_id !== r.to_branch_id && (
                      <Chip size="small" variant="outlined" label="branch" sx={{ ml: 0.5 }} />
                    )}
                  </TableCell>
                  <TableCell align="right">{r.line_count}</TableCell>
                  <TableCell align="right">{Number(r.total_qty)}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={r.status}
                      color={
                        r.status === "received" ? "success"
                        : r.status === "dispatched" ? "info"
                        : r.status === "cancelled" ? "default" : "warning"
                      }
                    />
                  </TableCell>
                  <TableCell align="right">
                    {r.status === "draft" && (
                      <Button size="small" onClick={() => mDispatch.mutate(r.id)}
                        disabled={mDispatch.isPending}>
                        Dispatch
                      </Button>
                    )}
                    {r.status === "dispatched" && (
                      <Button size="small" onClick={() => mReceive.mutate(r.id)}
                        disabled={mReceive.isPending}>
                        Receive
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(transfers.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={7}>
                    <Typography color="text.secondary">
                      {state === "open" ? "Nothing waiting." : "Nothing completed yet."}
                    </Typography>
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
            Physical verification (snapshot-delta)
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (v.godown && v.product && v.physical !== "") mVerify.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
              <TextField label="Godown" select value={v.godown} onChange={(e) => setV({ ...v, godown: e.target.value })} sx={{ width: 170 }}>
                {(godowns.data ?? []).map((g) => (
                  <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                ))}
              </TextField>
              <TextField label="Product" select value={v.product} onChange={(e) => setV({ ...v, product: e.target.value })} sx={{ width: 220 }}>
                {(products.data ?? []).map((p) => (
                  <MenuItem key={p.id} value={String(p.id)}>{p.code}</MenuItem>
                ))}
              </TextField>
              <TextField label="Physical count" value={v.physical} onChange={(e) => setV({ ...v, physical: e.target.value })} sx={{ width: 140 }} />
              <Button type="submit" variant="contained" disabled={mVerify.isPending}>
                Count &amp; post
              </Button>
            </Stack>
          </Box>
          {verif && (
            <Alert severity="success" sx={{ mt: 2 }}>
              {verif.doc_no}: system {verif.lines[0]?.system_qty_at_start} → physical{" "}
              {verif.lines[0]?.physical_qty} ⇒ posted delta{" "}
              <strong>{verif.lines[0]?.delta}</strong>
            </Alert>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
