import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControlLabel,
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
import { errorMessage } from "../../lib/api";
import { useAuth } from "../../store/auth";
import { getPrintSettings, savePrintSettings, type PrintSettings } from "../printing/api";
import { useState } from "react";

import {
  createBranch,
  createDocumentType,
  createGodown,
  createTag,
  createTaxRate,
  getFeatureFlags,
  listBranchesAdmin,
  listDocumentTypes,
  listGodownsAdmin,
  listTags,
  listTaxRates,
  setFeatureFlag,
  updateBranch,
  updateDocumentType,
  updateGodown,
  type Branch,
  type DocumentType,
  type GodownAdmin,
  type Tag,
  type TaxRate,
  listNumbering,
  updateNumbering,
} from "./api";

const EMPTY_BRANCH = { name: "", code: "", address: "", phone: "", gstin: "", state_code: "" };
const EMPTY_GODOWN = { name: "", branch_id: "", code: "" };

export function SettingsPage() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const [tax, setTax] = useState({ name: "", rate: "" });
  const [tag, setTag] = useState({ name: "", color: "#B96D28" });

  const [branchForm, setBranchForm] = useState(EMPTY_BRANCH);
  const [godownForm, setGodownForm] = useState(EMPTY_GODOWN);
  const [docType, setDocType] = useState("");
  const [printForm, setPrintForm] = useState<Partial<PrintSettings>>({});
  const [err, setErr] = useState<string | null>(null);

  const taxRates = useQuery({ queryKey: ["tax-rates"], queryFn: listTaxRates });
  const tags = useQuery({ queryKey: ["tags"], queryFn: listTags });
  const flags = useQuery({ queryKey: ["feature-flags"], queryFn: getFeatureFlags });
  const branches = useQuery({ queryKey: ["branches-admin"], queryFn: () => listBranchesAdmin() });
  const godowns = useQuery({ queryKey: ["godowns-admin"], queryFn: listGodownsAdmin });
  const printCfg = useQuery({ queryKey: ["print-settings"], queryFn: getPrintSettings });
  const docTypes = useQuery({
    queryKey: ["document-types", "all"],
    queryFn: () => listDocumentTypes("party", true),
  });

  const fail = (e: unknown) => {
    setErr(errorMessage(e, "Action failed"));
  };
  const refetchOrg = () => {
    setErr(null);
    qc.invalidateQueries({ queryKey: ["branches-admin"] });
    qc.invalidateQueries({ queryKey: ["godowns-admin"] });
    qc.invalidateQueries({ queryKey: ["branches"] });
    qc.invalidateQueries({ queryKey: ["godowns"] });
  };

  const savePrint = useMutation({
    mutationFn: () => savePrintSettings(printForm),
    onSuccess: () => {
      setPrintForm({});
      setErr(null);
      qc.invalidateQueries({ queryKey: ["print-settings"] });
    },
    onError: fail,
  });

  const addBranch = useMutation({
    mutationFn: () =>
      createBranch({
        name: branchForm.name,
        code: branchForm.code || null,
        address: branchForm.address || null,
        phone: branchForm.phone || null,
        gstin: branchForm.gstin || null,
        state_code: branchForm.state_code || null,
      }),
    onSuccess: () => {
      setBranchForm(EMPTY_BRANCH);
      refetchOrg();
    },
    onError: fail,
  });
  const toggleBranch = useMutation({
    mutationFn: (b: Branch) => updateBranch(b.id, { is_active: !b.is_active }),
    onSuccess: refetchOrg,
    onError: fail,
  });
  const addGodown = useMutation({
    mutationFn: () =>
      createGodown({
        name: godownForm.name,
        branch_id: Number(godownForm.branch_id),
        code: godownForm.code || null,
      }),
    onSuccess: () => {
      setGodownForm(EMPTY_GODOWN);
      refetchOrg();
    },
    onError: fail,
  });
  const toggleGodown = useMutation({
    mutationFn: (g: GodownAdmin) => updateGodown(g.id, { is_active: !g.is_active }),
    onSuccess: refetchOrg,
    onError: fail,
  });
  const addDocType = useMutation({
    mutationFn: () => createDocumentType({ name: docType, applies_to: "party" }),
    onSuccess: () => {
      setDocType("");
      setErr(null);
      qc.invalidateQueries({ queryKey: ["document-types"] });
    },
    onError: fail,
  });
  const toggleDocType = useMutation({
    mutationFn: (d: DocumentType) => updateDocumentType(d.id, { is_active: !d.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["document-types"] }),
    onError: fail,
  });

  const addTax = useMutation({
    mutationFn: () => createTaxRate({ name: tax.name, rate: tax.rate }),
    onSuccess: () => {
      setTax({ name: "", rate: "" });
      qc.invalidateQueries({ queryKey: ["tax-rates"] });
    },
  });
  const addTag = useMutation({
    mutationFn: () => createTag({ name: tag.name, color: tag.color }),
    onSuccess: () => {
      setTag({ name: "", color: "#B96D28" });
      qc.invalidateQueries({ queryKey: ["tags"] });
    },
  });
  const toggleFlag = useMutation({
    mutationFn: (p: { name: string; enabled: boolean }) => setFeatureFlag(p.name, p.enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feature-flags"] }),
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Settings
      </Typography>
      {err && <Alert severity="error" onClose={() => setErr(null)}>{err}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Branches</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>GSTIN</TableCell>
                <TableCell>Address</TableCell>
                <TableCell>Phone</TableCell>
                <TableCell align="right">Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(branches.data ?? []).map((b) => (
                <TableRow key={b.id} sx={{ opacity: b.is_active ? 1 : 0.5 }}>
                  <TableCell>{b.name}</TableCell>
                  <TableCell><code>{b.code || "-"}</code></TableCell>
                  <TableCell>{b.gstin || "-"}</TableCell>
                  <TableCell>{b.address || "-"}</TableCell>
                  <TableCell>{b.phone || "-"}</TableCell>
                  <TableCell align="right">
                    <FormControlLabel
                      control={<Switch size="small" checked={b.is_active}
                        onChange={() => toggleBranch.mutate(b)} />}
                      label={b.is_active ? "Active" : "Inactive"}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Box component="form" sx={{ mt: 2 }}
            onSubmit={(e) => { e.preventDefault(); if (branchForm.name) addBranch.mutate(); }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1} flexWrap="wrap" useFlexGap>
              <TextField size="small" label="Name" required value={branchForm.name}
                onChange={(e) => setBranchForm({ ...branchForm, name: e.target.value })} sx={{ minWidth: 170 }} />
              <TextField size="small" label="Code" value={branchForm.code}
                onChange={(e) => setBranchForm({ ...branchForm, code: e.target.value })} sx={{ width: 110 }} />
              <TextField size="small" label="GSTIN" value={branchForm.gstin}
                onChange={(e) => setBranchForm({ ...branchForm, gstin: e.target.value.toUpperCase() })} sx={{ width: 190 }} />
              <TextField size="small" label="State code" value={branchForm.state_code}
                onChange={(e) => setBranchForm({ ...branchForm, state_code: e.target.value })} sx={{ width: 110 }} />
              <TextField size="small" label="Address" value={branchForm.address}
                onChange={(e) => setBranchForm({ ...branchForm, address: e.target.value })} sx={{ flex: 1, minWidth: 200 }} />
              <TextField size="small" label="Phone" value={branchForm.phone}
                onChange={(e) => setBranchForm({ ...branchForm, phone: e.target.value })} sx={{ width: 150 }} />
              <Button type="submit" variant="contained" disabled={addBranch.isPending || !branchForm.name}>
                Add branch
              </Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            GSTIN, address and state code print on this branch's invoices.
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Godowns</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Code</TableCell>
                <TableCell>Branch</TableCell>
                <TableCell align="right">Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(godowns.data ?? []).map((g) => (
                <TableRow key={g.id} sx={{ opacity: g.is_active ? 1 : 0.5 }}>
                  <TableCell>{g.name}</TableCell>
                  <TableCell><code>{g.code || "-"}</code></TableCell>
                  <TableCell>
                    {(branches.data ?? []).find((b) => b.id === g.branch_id)?.name ?? g.branch_id}
                  </TableCell>
                  <TableCell align="right">
                    <FormControlLabel
                      control={<Switch size="small" checked={g.is_active}
                        onChange={() => toggleGodown.mutate(g)} />}
                      label={g.is_active ? "Active" : "Inactive"}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Box component="form" sx={{ mt: 2 }}
            onSubmit={(e) => { e.preventDefault(); if (godownForm.name && godownForm.branch_id) addGodown.mutate(); }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField size="small" label="Name" required value={godownForm.name}
                onChange={(e) => setGodownForm({ ...godownForm, name: e.target.value })} sx={{ minWidth: 180 }} />
              <TextField size="small" label="Code" value={godownForm.code}
                onChange={(e) => setGodownForm({ ...godownForm, code: e.target.value })} sx={{ width: 120 }} />
              <TextField size="small" label="Branch" select required value={godownForm.branch_id}
                onChange={(e) => setGodownForm({ ...godownForm, branch_id: e.target.value })} sx={{ minWidth: 170 }}>
                {/* Branches are org-visible, but a godown can only be created in
                    one you work in — offering the rest just earns a 403. */}
                {(branches.data ?? [])
                  .filter((b) => b.is_active && me?.branch_ids.includes(b.id))
                  .map((b) => (
                    <MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>
                  ))}
              </TextField>
              <Button type="submit" variant="contained"
                disabled={addGodown.isPending || !godownForm.name || !godownForm.branch_id}>
                Add godown
              </Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            A godown holding stock cannot be deactivated or moved to another branch.
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Printing</Typography>
          <Typography variant="caption" color="text.secondary">
            The default paper for invoices. Thermal formats drop the HSN, discount and
            tax-summary columns to fit the roll; the figures are identical either way.
          </Typography>
          {printCfg.data && (
            <Stack spacing={2} sx={{ mt: 2 }}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} flexWrap="wrap" useFlexGap>
                <TextField
                  size="small" label="Default paper" select sx={{ minWidth: 190 }}
                  value={printForm.default_format ?? printCfg.data.default_format}
                  onChange={(e) => setPrintForm({ ...printForm, default_format: e.target.value as PrintSettings["default_format"] })}
                >
                  <MenuItem value="a4">A4</MenuItem>
                  <MenuItem value="a5">A5</MenuItem>
                  <MenuItem value="thermal80">Thermal 80mm</MenuItem>
                  <MenuItem value="thermal58">Thermal 58mm</MenuItem>
                </TextField>
                {([
                  ["show_hsn", "Show HSN"],
                  ["show_tax_summary", "Tax summary"],
                  ["show_amount_in_words", "Amount in words"],
                ] as const).map(([k, label]) => (
                  <FormControlLabel
                    key={k}
                    control={
                      <Switch
                        size="small"
                        checked={(printForm[k] ?? printCfg.data![k]) as boolean}
                        onChange={(e) => setPrintForm({ ...printForm, [k]: e.target.checked })}
                      />
                    }
                    label={label}
                  />
                ))}
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                  size="small" label="Terms" sx={{ flex: 1 }}
                  value={printForm.terms ?? printCfg.data.terms}
                  onChange={(e) => setPrintForm({ ...printForm, terms: e.target.value })}
                />
                <TextField
                  size="small" label="Footer text" sx={{ flex: 1 }}
                  value={printForm.footer_text ?? printCfg.data.footer_text}
                  onChange={(e) => setPrintForm({ ...printForm, footer_text: e.target.value })}
                />
                <Button variant="contained" onClick={() => savePrint.mutate()}
                  disabled={savePrint.isPending || !Object.keys(printForm).length}>
                  Save
                </Button>
              </Stack>
            </Stack>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Party document types</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
            {(docTypes.data ?? []).map((d) => (
              <Chip
                key={d.id}
                label={d.name}
                variant={d.is_active ? "filled" : "outlined"}
                color={d.is_active ? "default" : "warning"}
                onClick={() => toggleDocType.mutate(d)}
              />
            ))}
          </Stack>
          <Box component="form"
            onSubmit={(e) => { e.preventDefault(); if (docType) addDocType.mutate(); }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField size="small" label="New document type" value={docType}
                onChange={(e) => setDocType(e.target.value)} />
              <Button type="submit" variant="outlined" disabled={addDocType.isPending || !docType}>
                Add
              </Button>
            </Stack>
          </Box>
          <Typography variant="caption" color="text.secondary">
            These fill the document dropdown on a party. Click a chip to activate/deactivate it.
          </Typography>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            GST tax rates
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (tax.name && tax.rate) addTax.mutate();
            }}
          >
            <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
              <TextField
                label="Name"
                value={tax.name}
                onChange={(e) => setTax({ ...tax, name: e.target.value })}
                sx={{ flex: 1 }}
              />
              <TextField
                label="Rate %"
                value={tax.rate}
                onChange={(e) => setTax({ ...tax, rate: e.target.value })}
                sx={{ width: 120 }}
              />
              <Button type="submit" variant="contained" disabled={addTax.isPending}>
                Add
              </Button>
            </Stack>
          </Box>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell align="right">Rate %</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(taxRates.data ?? []).map((t: TaxRate) => (
                <TableRow key={t.id}>
                  <TableCell>{t.name}</TableCell>
                  <TableCell align="right">{t.rate}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Tags
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (tag.name) addTag.mutate();
            }}
          >
            <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
              <TextField
                label="Name"
                value={tag.name}
                onChange={(e) => setTag({ ...tag, name: e.target.value })}
                sx={{ flex: 1 }}
              />
              <TextField
                label="Color"
                type="color"
                value={tag.color}
                onChange={(e) => setTag({ ...tag, color: e.target.value })}
                sx={{ width: 80 }}
              />
              <Button type="submit" variant="contained" disabled={addTag.isPending}>
                Add
              </Button>
            </Stack>
          </Box>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {(tags.data ?? []).map((t: Tag) => (
              <Chip
                key={t.id}
                label={t.name}
                sx={{ bgcolor: t.color, color: "#fff", fontWeight: 600 }}
              />
            ))}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Feature flags
          </Typography>
          <Divider sx={{ mb: 1 }} />
          <Stack>
            {Object.entries(flags.data ?? {}).map(([name, enabled]) => (
              <FormControlLabel
                key={name}
                control={
                  <Switch
                    checked={enabled}
                    onChange={(e) => toggleFlag.mutate({ name, enabled: e.target.checked })}
                  />
                }
                label={name.replace(/_/g, " ")}
              />
            ))}
            {Object.keys(flags.data ?? {}).length === 0 && (
              <Typography color="text.secondary" variant="body2">
                No feature flags configured.
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>

      <NumberingCard />
    </Stack>
  );
}


/** v2 §9 "customisable document numbers" — every document's prefix, width and
 *  next number, editable in one place. */
function NumberingCard() {
  const qc = useQueryClient();
  const series = useQuery({ queryKey: ["numbering"], queryFn: listNumbering });
  const [draft, setDraft] = useState<Record<number, { prefix: string; pad_width: string; next_value: string }>>({});
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const save = useMutation({
    mutationFn: (args: { id: number; body: { prefix?: string; pad_width?: number; next_value?: number } }) =>
      updateNumbering(args.id, args.body),
    onSuccess: (row) => {
      setMsg({
        text: `${row.label}: the next number will be ${row.sample}. Documents already issued keep their old numbers.`,
        ok: true,
      });
      setDraft((d) => {
        const n = { ...d };
        delete n[row.id];
        return n;
      });
      qc.invalidateQueries({ queryKey: ["numbering"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not update the series"), ok: false }),
  });

  const rows = series.data ?? [];

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>Document numbering</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Each document type gets its own prefix and running number, per financial year.
          Changing a prefix affects only documents issued from now on.
        </Typography>
        {msg && (
          <Alert severity={msg.ok ? "success" : "error"} sx={{ mb: 2 }} onClose={() => setMsg(null)}>
            {msg.text}
          </Alert>
        )}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Document</TableCell>
              <TableCell>Year</TableCell>
              <TableCell>Prefix</TableCell>
              <TableCell>Digits</TableCell>
              <TableCell>Next number</TableCell>
              <TableCell>Preview</TableCell>
              <TableCell align="right" />
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => {
              const d = draft[r.id] ?? {
                prefix: r.prefix,
                pad_width: String(r.pad_width),
                next_value: String(r.next_value),
              };
              const set = (k: keyof typeof d, v: string) =>
                setDraft((s) => ({ ...s, [r.id]: { ...d, [k]: v } }));
              const dirty =
                d.prefix !== r.prefix ||
                d.pad_width !== String(r.pad_width) ||
                d.next_value !== String(r.next_value);
              const preview = `${d.prefix}${d.next_value.padStart(Number(d.pad_width) || 1, "0")}`;
              return (
                <TableRow key={r.id}>
                  <TableCell>{r.label}</TableCell>
                  <TableCell>{r.fin_year}</TableCell>
                  <TableCell>
                    <TextField size="small" value={d.prefix} onChange={(e) => set("prefix", e.target.value)} sx={{ width: 110 }} />
                  </TableCell>
                  <TableCell>
                    <TextField size="small" value={d.pad_width} onChange={(e) => set("pad_width", e.target.value)} sx={{ width: 70 }} />
                  </TableCell>
                  <TableCell>
                    <TextField size="small" value={d.next_value} onChange={(e) => set("next_value", e.target.value)} sx={{ width: 90 }} />
                  </TableCell>
                  <TableCell><code>{preview}</code></TableCell>
                  <TableCell align="right">
                    <Button
                      size="small"
                      disabled={!dirty || save.isPending}
                      onClick={() =>
                        save.mutate({
                          id: r.id,
                          body: {
                            prefix: d.prefix,
                            pad_width: Number(d.pad_width) || r.pad_width,
                            next_value: Number(d.next_value) || r.next_value,
                          },
                        })
                      }
                    >
                      Save
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography color="text.secondary" variant="body2">No numbering series yet.</Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
