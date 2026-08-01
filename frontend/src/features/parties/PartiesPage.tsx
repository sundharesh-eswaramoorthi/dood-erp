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
  FormControlLabel,
  Link as MuiLink,
  MenuItem,
  Stack,
  Switch,
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
import { Link as RouterLink } from "react-router-dom";

import { listBranches } from "../users/api";
import {
  createParty,
  getActivity,
  listAreas,
  listParties,
  updateParty,
  type PartyFilters,
  type PartyListItem,
  type PartyUpdate,
} from "./api";

const EMPTY = {
  name: "",
  area: "",
  party_type: "customer",
  phone: "",
  gstin: "",
  credit_limit: "",
  opening_balance: "",
  opening_balance_side: "receivable",
};

const SORTS = [
  { value: "created", label: "Newest" },
  { value: "name", label: "Name" },
  { value: "code", label: "Code" },
  { value: "area", label: "Area" },
  { value: "receivable", label: "Receivable" },
  { value: "payable", label: "Payable" },
];

/** Outstanding reads from the party's net balance: + they owe us, − we owe them. */
function outstanding(p: PartyListItem) {
  const net = Number(p.net_balance);
  if (net > 0) return { label: `₹${net.toLocaleString("en-IN")}`, color: "error" as const, note: "receivable" };
  if (net < 0) return { label: `₹${(-net).toLocaleString("en-IN")}`, color: "success" as const, note: "payable" };
  return { label: "—", color: "default" as const, note: "" };
}

export function PartiesPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [filters, setFilters] = useState<PartyFilters>({ sort: "created", direction: "desc" });
  const [editing, setEditing] = useState<PartyListItem | null>(null);

  const parties = useQuery({
    queryKey: ["parties", filters],
    queryFn: () => listParties(filters),
  });
  const areas = useQuery({ queryKey: ["party-areas"], queryFn: listAreas });
  const branches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  const activity = useQuery({ queryKey: ["activity"], queryFn: getActivity, refetchInterval: 3000 });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["parties"] });
    qc.invalidateQueries({ queryKey: ["party-areas"] });
  };

  const create = useMutation({
    mutationFn: () =>
      createParty({
        name: form.name,
        area: form.area,
        party_type: form.party_type,
        phone: form.phone || null,
        gstin: form.gstin || null,
        credit_limit: form.credit_limit || null,
        opening_balance: form.opening_balance || "0",
        opening_balance_side: form.opening_balance_side,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      invalidate();
    },
  });

  const save = useMutation({
    mutationFn: (payload: { id: number; body: PartyUpdate }) =>
      updateParty(payload.id, payload.body),
    onSuccess: () => {
      setEditing(null);
      invalidate();
    },
  });

  const patch = (k: keyof PartyFilters, v: unknown) =>
    setFilters((f) => ({ ...f, [k]: v === "" ? undefined : v }));

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>
          Parties
        </Typography>
        <Typography color="text.secondary">
          Customers and suppliers across every branch — one list, with live outstanding.
        </Typography>
      </Box>

      <Card elevation={1}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add party
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                  label="Name"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  sx={{ flex: 2 }}
                />
                <TextField
                  label="Area"
                  required
                  value={form.area}
                  onChange={(e) => setForm({ ...form, area: e.target.value })}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Type"
                  select
                  value={form.party_type}
                  onChange={(e) => setForm({ ...form, party_type: e.target.value })}
                  sx={{ flex: 1, minWidth: 130 }}
                >
                  <MenuItem value="customer">Customer</MenuItem>
                  <MenuItem value="supplier">Supplier</MenuItem>
                  <MenuItem value="both">Both</MenuItem>
                </TextField>
                <TextField
                  label="Phone"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  sx={{ flex: 1 }}
                />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
                <TextField
                  label="GSTIN"
                  value={form.gstin}
                  onChange={(e) => setForm({ ...form, gstin: e.target.value })}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Credit limit"
                  value={form.credit_limit}
                  onChange={(e) => setForm({ ...form, credit_limit: e.target.value })}
                  helperText="Blank = no limit"
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Opening balance"
                  value={form.opening_balance}
                  onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Opening side"
                  select
                  value={form.opening_balance_side}
                  onChange={(e) => setForm({ ...form, opening_balance_side: e.target.value })}
                  sx={{ flex: 1, minWidth: 150 }}
                >
                  <MenuItem value="receivable">Receivable</MenuItem>
                  <MenuItem value="payable">Payable</MenuItem>
                </TextField>
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  disabled={create.isPending || !form.name || !form.area}
                  sx={{ height: 56 }}
                >
                  Add
                </Button>
              </Stack>
            </Stack>
          </Box>
          {create.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              Could not create party — name and area are required.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card elevation={1}>
        <CardContent>
          <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={2}
            sx={{ mb: 2 }}
            alignItems={{ md: "center" }}
          >
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              Party list
            </Typography>
            <TextField
              size="small"
              label="Search"
              placeholder="name, code, phone, area"
              value={filters.q ?? ""}
              onChange={(e) => patch("q", e.target.value)}
              sx={{ minWidth: 220 }}
            />
            <TextField
              size="small"
              label="Area"
              select
              value={filters.area ?? ""}
              onChange={(e) => patch("area", e.target.value)}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="">All areas</MenuItem>
              {(areas.data ?? []).map((a) => (
                <MenuItem key={a} value={a}>
                  {a}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Type"
              select
              value={filters.party_type ?? ""}
              onChange={(e) => patch("party_type", e.target.value)}
              sx={{ minWidth: 130 }}
            >
              <MenuItem value="">All types</MenuItem>
              <MenuItem value="customer">Customer</MenuItem>
              <MenuItem value="supplier">Supplier</MenuItem>
              <MenuItem value="both">Both</MenuItem>
            </TextField>
            <TextField
              size="small"
              label="Status"
              select
              value={filters.is_active === undefined ? "" : String(filters.is_active)}
              onChange={(e) =>
                patch("is_active", e.target.value === "" ? "" : e.target.value === "true")
              }
              sx={{ minWidth: 120 }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">Active</MenuItem>
              <MenuItem value="false">Inactive</MenuItem>
            </TextField>
            <TextField
              size="small"
              label="Sort"
              select
              value={filters.sort ?? "created"}
              onChange={(e) => patch("sort", e.target.value)}
              sx={{ minWidth: 130 }}
            >
              {SORTS.map((s) => (
                <MenuItem key={s.value} value={s.value}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
            <Button
              size="small"
              onClick={() => patch("direction", filters.direction === "asc" ? "desc" : "asc")}
            >
              {filters.direction === "asc" ? "↑ Asc" : "↓ Desc"}
            </Button>
          </Stack>

          {parties.isLoading ? (
            <Typography color="text.secondary">Loading…</Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Code</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Area</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Phone</TableCell>
                  <TableCell align="right">Outstanding</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(parties.data ?? []).map((p) => {
                  const out = outstanding(p);
                  return (
                    <TableRow key={p.id} sx={{ opacity: p.is_active ? 1 : 0.5 }}>
                      <TableCell>
                        <code>{p.party_code}</code>
                      </TableCell>
                      <TableCell>
                        <MuiLink component={RouterLink} to={`/parties/${p.id}`} underline="hover">
                          {p.name}
                        </MuiLink>
                      </TableCell>
                      <TableCell>{p.area || "—"}</TableCell>
                      <TableCell>
                        <Chip size="small" label={p.party_type} />
                      </TableCell>
                      <TableCell>{p.phone || "—"}</TableCell>
                      <TableCell align="right">
                        <Typography
                          variant="body2"
                          color={out.color === "default" ? "text.secondary" : `${out.color}.main`}
                        >
                          {out.label}
                        </Typography>
                        {out.note && (
                          <Typography variant="caption" color="text.secondary">
                            {out.note}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={p.is_active ? "Active" : "Inactive"}
                          color={p.is_active ? "success" : "default"}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Button size="small" onClick={() => setEditing(p)}>
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {(parties.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8}>
                      <Typography color="text.secondary">No parties match these filters.</Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card elevation={1} sx={{ bgcolor: "#FCFAF6" }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="h6">Recent activity</Typography>
            <Chip size="small" color="secondary" label={`${activity.data?.count ?? 0} events`} />
          </Stack>
          <Stack spacing={0.5} sx={{ mt: 1.5 }}>
            {(activity.data?.items ?? []).map((it, i) => (
              <Typography key={i} variant="body2" sx={{ fontFamily: "monospace" }}>
                {new Date(it.at).toLocaleTimeString()} · {it.topic} · {JSON.stringify(it.payload)}
              </Typography>
            ))}
            {(activity.data?.items ?? []).length === 0 && (
              <Typography color="text.secondary" variant="body2">
                No activity yet.
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      <EditDialog
        party={editing}
        branches={branches.data ?? []}
        saving={save.isPending}
        error={save.isError}
        onClose={() => setEditing(null)}
        onSave={(body) => editing && save.mutate({ id: editing.id, body })}
      />
    </Stack>
  );
}

function EditDialog({
  party,
  branches,
  saving,
  error,
  onClose,
  onSave,
}: {
  party: PartyListItem | null;
  branches: { id: number; name: string }[];
  saving: boolean;
  error: boolean;
  onClose: () => void;
  onSave: (body: PartyUpdate) => void;
}) {
  const [draft, setDraft] = useState<PartyUpdate>({});
  const [key, setKey] = useState<number | null>(null);

  // Reset the draft whenever a different party is opened.
  if (party && key !== party.id) {
    setKey(party.id);
    setDraft({
      name: party.name,
      area: party.area,
      party_type: party.party_type,
      phone: party.phone ?? "",
      gstin: party.gstin ?? "",
      pan: party.pan ?? "",
      credit_limit: party.credit_limit ?? "",
      opening_balance: party.opening_balance,
      opening_balance_side: party.opening_balance_side,
      serving_branch_id: party.serving_branch_id,
      is_active: party.is_active,
    });
  }

  const set = (k: keyof PartyUpdate, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <Dialog open={!!party} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Edit {party?.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Name"
              value={draft.name ?? ""}
              onChange={(e) => set("name", e.target.value)}
              fullWidth
            />
            <TextField
              label="Area"
              value={draft.area ?? ""}
              onChange={(e) => set("area", e.target.value)}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Type"
              select
              value={draft.party_type ?? "customer"}
              onChange={(e) => set("party_type", e.target.value)}
              fullWidth
            >
              <MenuItem value="customer">Customer</MenuItem>
              <MenuItem value="supplier">Supplier</MenuItem>
              <MenuItem value="both">Both</MenuItem>
            </TextField>
            <TextField
              label="Serving branch"
              select
              value={draft.serving_branch_id ?? ""}
              onChange={(e) => set("serving_branch_id", Number(e.target.value))}
              fullWidth
            >
              {branches.map((b) => (
                <MenuItem key={b.id} value={b.id}>
                  {b.name}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Phone"
              value={draft.phone ?? ""}
              onChange={(e) => set("phone", e.target.value)}
              fullWidth
            />
            <TextField
              label="GSTIN"
              value={draft.gstin ?? ""}
              onChange={(e) => set("gstin", e.target.value)}
              fullWidth
            />
            <TextField
              label="PAN"
              value={draft.pan ?? ""}
              onChange={(e) => set("pan", e.target.value)}
              fullWidth
            />
          </Stack>
          <Divider />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Credit limit"
              value={draft.credit_limit ?? ""}
              onChange={(e) => set("credit_limit", e.target.value)}
              helperText="Blank = no limit"
              fullWidth
            />
            <TextField
              label="Opening balance"
              value={draft.opening_balance ?? ""}
              onChange={(e) => set("opening_balance", e.target.value)}
              helperText="Re-posts to the ledger as a correction"
              fullWidth
            />
            <TextField
              label="Opening side"
              select
              value={draft.opening_balance_side ?? "receivable"}
              onChange={(e) => set("opening_balance_side", e.target.value)}
              fullWidth
            >
              <MenuItem value="receivable">Receivable</MenuItem>
              <MenuItem value="payable">Payable</MenuItem>
            </TextField>
          </Stack>
          <FormControlLabel
            control={
              <Switch
                checked={draft.is_active ?? true}
                onChange={(e) => set("is_active", e.target.checked)}
              />
            }
            label="Active"
          />
          {error && <Alert severity="error">Could not save — check the values.</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={saving}
          onClick={() =>
            onSave({
              ...draft,
              credit_limit: draft.credit_limit === "" ? null : draft.credit_limit,
              phone: draft.phone === "" ? null : draft.phone,
              gstin: draft.gstin === "" ? null : draft.gstin,
              pan: draft.pan === "" ? null : draft.pan,
            })
          }
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
