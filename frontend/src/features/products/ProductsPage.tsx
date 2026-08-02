import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
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
import { useMemo, useState } from "react";

import { useAuth } from "../../store/auth";
import { listGodowns } from "../stock/api";
import { listBranches } from "../users/api";
import { listUnits } from "../units/api";
import {
  createCategory,
  createProduct,
  listCategories,
  listProducts,
  updateProduct,
  type Product,
  type ProductFilters,
  type ProductUpdate,
} from "./api";

const EMPTY = {
  code: "",
  name: "",
  base_unit_id: "",
  category_id: "",
  hsn_code: "",
  gst_rate: "",
  allow_negative_stock: false,
  sale_price: "",
  purchase_price: "",
  price_inclusive: false,
  sub_unit_id: "",
  sub_unit_qty: "",
  min_stock_qty: "",
  opening_qty: "",
  opening_rate: "",
  opening_as_of: "",
  opening_godown_id: "",
  opening_branch_id: "",
};

const money = (v: string | null | undefined) =>
  v == null ? "\u2014" : "\u20b9" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const qtyFmt = (v: string | null | undefined) =>
  v == null ? "\u2014" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

export function ProductsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [newCat, setNewCat] = useState("");

  const [filters, setFilters] = useState<ProductFilters>({ sort: "name", direction: "asc" });
  const [editing, setEditing] = useState<Product | null>(null);

  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const godowns = useQuery({ queryKey: ["godowns", "all"], queryFn: () => listGodowns(true) });
  const { user: me } = useAuth();
  const allBranches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  // offering a branch the user cannot post into just earns them a 403
  const branches = {
    data: (allBranches.data ?? []).filter((b) => me?.branch_ids.includes(b.id)),
  };
  // stock_balance is keyed on (branch, godown), so only offer godowns of the
  // chosen branch — a mismatched pair is refused by the server anyway.
  const openingGodowns = (godowns.data ?? []).filter(
    (g) => String(g.branch_id) === form.opening_branch_id,
  );
  const categories = useQuery({ queryKey: ["categories"], queryFn: listCategories });
  const products = useQuery({ queryKey: ["products", filters], queryFn: () => listProducts(filters) });

  const unitCode = useMemo(() => {
    const m = new Map<number, string>();
    (units.data ?? []).forEach((u) => m.set(u.id, u.code));
    return m;
  }, [units.data]);

  const create = useMutation({
    mutationFn: () =>
      createProduct({
        code: form.code || undefined,
        name: form.name,
        base_unit_id: Number(form.base_unit_id),
        category_id: form.category_id ? Number(form.category_id) : null,
        hsn_code: form.hsn_code || null,
        gst_rate: form.gst_rate || null,
        allow_negative_stock: form.allow_negative_stock,
        sale_price: form.sale_price || null,
        purchase_price: form.purchase_price || null,
        price_inclusive: form.price_inclusive,
        sub_unit_id: form.sub_unit_id ? Number(form.sub_unit_id) : null,
        sub_unit_qty: form.sub_unit_qty || null,
        min_stock_qty: form.min_stock_qty || null,
        opening_qty: form.opening_qty || null,
        opening_rate: form.opening_rate || null,
        opening_as_of: form.opening_as_of || null,
        opening_godown_id: form.opening_godown_id ? Number(form.opening_godown_id) : null,
        opening_branch_id: form.opening_branch_id ? Number(form.opening_branch_id) : null,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["stock-current"] });
    },
  });

  const save = useMutation({
    mutationFn: (a: { id: number; body: ProductUpdate }) => updateProduct(a.id, a.body),
    onSuccess: () => {
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["products"] });
    },
  });

  const patch = (k: keyof ProductFilters, v: unknown) =>
    setFilters((f) => ({ ...f, [k]: v === "" ? undefined : v }));

  const addCat = useMutation({
    mutationFn: () => createCategory({ name: newCat }),
    onSuccess: () => {
      setNewCat("");
      qc.invalidateQueries({ queryKey: ["categories"] });
    },
  });

  const canSubmit = form.name && form.base_unit_id;

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Products
      </Typography>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Categories
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }} alignItems="center">
            {(categories.data ?? []).map((c) => (<Chip key={c.id} label={c.name} />))}
            {(categories.data ?? []).length === 0 && <Typography variant="body2" color="text.secondary">No categories.</Typography>}
          </Stack>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (newCat) addCat.mutate(); }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <TextField size="small" label="New category" value={newCat} onChange={(e) => setNewCat(e.target.value)} />
              <Button type="submit" variant="outlined" disabled={addCat.isPending}>Add category</Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add product
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (canSubmit) create.mutate();
            }}
          >
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                  label="Code"
                  placeholder="auto"
                  value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                  helperText="blank = numbered automatically"
                  sx={{ width: 160 }}
                />
                <TextField
                  label="Name"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Base unit"
                  select
                  required
                  value={form.base_unit_id}
                  onChange={(e) => setForm({ ...form, base_unit_id: e.target.value })}
                  sx={{ width: 160 }}
                >
                  {(units.data ?? []).map((u) => (
                    <MenuItem key={u.id} value={String(u.id)}>
                      {u.code}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
                <TextField
                  label="Category"
                  select
                  value={form.category_id}
                  onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                  sx={{ width: 200 }}
                >
                  <MenuItem value="">
                    <em>None</em>
                  </MenuItem>
                  {(categories.data ?? []).map((c) => (
                    <MenuItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="HSN"
                  value={form.hsn_code}
                  onChange={(e) => setForm({ ...form, hsn_code: e.target.value })}
                  sx={{ width: 140 }}
                />
                <TextField
                  label="GST %"
                  value={form.gst_rate}
                  onChange={(e) => setForm({ ...form, gst_rate: e.target.value })}
                  sx={{ width: 120 }}
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={form.allow_negative_stock}
                      onChange={(e) =>
                        setForm({ ...form, allow_negative_stock: e.target.checked })
                      }
                    />
                  }
                  label="Allow negative stock"
                />
              </Stack>

              <Divider textAlign="left">
                <Typography variant="caption" color="text.secondary">Pricing</Typography>
              </Divider>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                <TextField label="Sale price" value={form.sale_price}
                  onChange={(e) => setForm({ ...form, sale_price: e.target.value })} sx={{ width: 150 }} />
                <TextField label="Purchase price" value={form.purchase_price}
                  onChange={(e) => setForm({ ...form, purchase_price: e.target.value })} sx={{ width: 160 }} />
                <FormControlLabel
                  control={
                    <Checkbox checked={form.price_inclusive}
                      onChange={(e) => setForm({ ...form, price_inclusive: e.target.checked })} />
                  }
                  label="Prices include tax"
                />
                <TextField label="Sub-unit" select value={form.sub_unit_id}
                  onChange={(e) => setForm({ ...form, sub_unit_id: e.target.value })} sx={{ width: 150 }}>
                  <MenuItem value=""><em>None</em></MenuItem>
                  {(units.data ?? []).filter((u) => String(u.id) !== form.base_unit_id).map((u) => (
                    <MenuItem key={u.id} value={String(u.id)}>{u.code}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Sub-units per base" value={form.sub_unit_qty}
                  onChange={(e) => setForm({ ...form, sub_unit_qty: e.target.value })}
                  sx={{ width: 180 }} disabled={!form.sub_unit_id}
                  helperText="e.g. 1 BAG = 50 KG" />
              </Stack>

              <Divider textAlign="left">
                <Typography variant="caption" color="text.secondary">Opening stock &amp; reorder level</Typography>
              </Divider>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                <TextField label="Min stock qty" value={form.min_stock_qty}
                  onChange={(e) => setForm({ ...form, min_stock_qty: e.target.value })} sx={{ width: 150 }} />
                <TextField label="Opening qty" value={form.opening_qty}
                  onChange={(e) => setForm({ ...form, opening_qty: e.target.value })} sx={{ width: 140 }} />
                <TextField label="At price" value={form.opening_rate}
                  onChange={(e) => setForm({ ...form, opening_rate: e.target.value })} sx={{ width: 130 }}
                  disabled={!form.opening_qty} />
                <TextField label="As of" type="date" InputLabelProps={{ shrink: true }}
                  value={form.opening_as_of}
                  onChange={(e) => setForm({ ...form, opening_as_of: e.target.value })} sx={{ width: 170 }}
                  disabled={!form.opening_qty} />
                <TextField label="Branch" select value={form.opening_branch_id}
                  onChange={(e) => setForm({ ...form, opening_branch_id: e.target.value, opening_godown_id: "" })}
                  sx={{ width: 170 }} disabled={!form.opening_qty}>
                  {(branches.data ?? []).map((b) => (
                    <MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Godown" select value={form.opening_godown_id}
                  onChange={(e) => setForm({ ...form, opening_godown_id: e.target.value })}
                  sx={{ width: 170 }} disabled={!form.opening_qty || !form.opening_branch_id}
                  helperText={form.opening_qty && !form.opening_branch_id ? "pick a branch first" : " "}>
                  {openingGodowns.map((g) => (
                    <MenuItem key={g.id} value={String(g.id)}>{g.name}</MenuItem>
                  ))}
                </TextField>
                <Button
                  type="submit"
                  variant="contained"
                  sx={{ height: 56, ml: "auto" }}
                  disabled={create.isPending || !canSubmit}
                >
                  Add product
                </Button>
              </Stack>
            </Stack>
          </Box>
          {create.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              Could not create product (duplicate code?).
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2 }} alignItems={{ md: "center" }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>Product list</Typography>
            <TextField size="small" label="Search" placeholder="name, code, HSN"
              value={filters.q ?? ""} onChange={(e) => patch("q", e.target.value)} sx={{ minWidth: 200 }} />
            <TextField size="small" label="Category" select value={filters.category_id ?? ""}
              onChange={(e) => patch("category_id", e.target.value ? Number(e.target.value) : "")}
              sx={{ minWidth: 150 }}>
              <MenuItem value="">All</MenuItem>
              {(categories.data ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
              ))}
            </TextField>
            <TextField size="small" label="Status" select
              value={filters.is_active === undefined ? "" : String(filters.is_active)}
              onChange={(e) => patch("is_active", e.target.value === "" ? "" : e.target.value === "true")}
              sx={{ minWidth: 120 }}>
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">Active</MenuItem>
              <MenuItem value="false">Inactive</MenuItem>
            </TextField>
            <FormControlLabel
              control={<Checkbox checked={!!filters.low_stock}
                onChange={(e) => patch("low_stock", e.target.checked ? true : "")} />}
              label="Low stock"
            />
            <TextField size="small" label="Sort" select value={filters.sort ?? "name"}
              onChange={(e) => patch("sort", e.target.value)} sx={{ minWidth: 130 }}>
              <MenuItem value="name">Name</MenuItem>
              <MenuItem value="code">Code</MenuItem>
              <MenuItem value="stock">Stock qty</MenuItem>
              <MenuItem value="value">Stock value</MenuItem>
            </TextField>
            <Button size="small" onClick={() => patch("direction", filters.direction === "asc" ? "desc" : "asc")}>
              {filters.direction === "asc" ? "↑ Asc" : "↓ Desc"}
            </Button>
          </Stack>
          <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Unit</TableCell>
                <TableCell align="right">Sale</TableCell>
                <TableCell align="right">Purchase</TableCell>
                <TableCell align="right">Stock qty</TableCell>
                <TableCell align="right">Stock value</TableCell>
                <TableCell>HSN</TableCell>
                <TableCell align="right">GST %</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(products.data ?? []).map((p: Product) => (
                <TableRow key={p.id} sx={{ opacity: p.is_active ? 1 : 0.5 }}>
                  <TableCell>
                    <code>{p.code}</code>
                  </TableCell>
                  <TableCell>
                    {p.name}
                    {p.sub_unit_id && p.sub_unit_qty && (
                      <Typography variant="caption" color="text.secondary" display="block">
                        1 {unitCode.get(p.base_unit_id)} = {qtyFmt(p.sub_unit_qty)} {unitCode.get(p.sub_unit_id)}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>{unitCode.get(p.base_unit_id) ?? p.base_unit_id}</TableCell>
                  <TableCell align="right">
                    {money(p.sale_price)}
                    {p.price_inclusive && p.sale_price && (
                      <Typography variant="caption" color="text.secondary" display="block">incl. tax</Typography>
                    )}
                  </TableCell>
                  <TableCell align="right">{money(p.purchase_price)}</TableCell>
                  <TableCell align="right">
                    {qtyFmt(p.stock_qty)}
                    {p.low_stock && <Chip size="small" color="warning" label="low" sx={{ ml: 0.5 }} />}
                  </TableCell>
                  <TableCell align="right">{money(p.stock_value)}</TableCell>
                  <TableCell>{p.hsn_code || "—"}</TableCell>
                  <TableCell align="right">{p.gst_rate ?? "—"}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setEditing(p)}>Edit</Button>
                  </TableCell>
                </TableRow>
              ))}
              {(products.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={10}>
                    <Typography color="text.secondary">No products match these filters.</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
          </Box>
        </CardContent>
      </Card>

      <EditProductDialog
        product={editing}
        units={units.data ?? []}
        categories={categories.data ?? []}
        saving={save.isPending}
        onClose={() => setEditing(null)}
        onSave={(body) => editing && save.mutate({ id: editing.id, body })}
      />
    </Stack>
  );
}

/** v2 section 2 "Add / Edit Product". Opening stock is absent on purpose: it
 *  has already moved goods, so it is corrected with a stock adjustment. */
function EditProductDialog({
  product,
  units,
  categories,
  saving,
  onClose,
  onSave,
}: {
  product: Product | null;
  units: { id: number; code: string }[];
  categories: { id: number; name: string }[];
  saving: boolean;
  onClose: () => void;
  onSave: (body: ProductUpdate) => void;
}) {
  const [draft, setDraft] = useState<ProductUpdate>({});
  const [key, setKey] = useState<number | null>(null);

  if (product && key !== product.id) {
    setKey(product.id);
    setDraft({
      name: product.name,
      category_id: product.category_id,
      hsn_code: product.hsn_code ?? "",
      gst_rate: product.gst_rate ?? "",
      sale_price: product.sale_price ?? "",
      purchase_price: product.purchase_price ?? "",
      price_inclusive: product.price_inclusive,
      sub_unit_id: product.sub_unit_id,
      sub_unit_qty: product.sub_unit_qty ?? "",
      min_stock_qty: product.min_stock_qty ?? "",
      allow_negative_stock: product.allow_negative_stock,
      is_active: product.is_active,
    });
  }
  const set = (k: keyof ProductUpdate, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <Dialog open={!!product} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Edit {product?.code}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="Name" value={draft.name ?? ""} onChange={(e) => set("name", e.target.value)} fullWidth />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Category" select value={draft.category_id ?? ""}
              onChange={(e) => set("category_id", e.target.value ? Number(e.target.value) : null)} fullWidth>
              <MenuItem value=""><em>None</em></MenuItem>
              {categories.map((c) => (<MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>))}
            </TextField>
            <TextField label="HSN" value={draft.hsn_code ?? ""} onChange={(e) => set("hsn_code", e.target.value)} fullWidth />
            <TextField label="GST %" value={draft.gst_rate ?? ""} onChange={(e) => set("gst_rate", e.target.value)} fullWidth />
          </Stack>
          <Divider />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Sale price" value={draft.sale_price ?? ""} onChange={(e) => set("sale_price", e.target.value)} fullWidth />
            <TextField label="Purchase price" value={draft.purchase_price ?? ""} onChange={(e) => set("purchase_price", e.target.value)} fullWidth />
            <TextField label="Min stock" value={draft.min_stock_qty ?? ""} onChange={(e) => set("min_stock_qty", e.target.value)} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Sub-unit" select value={draft.sub_unit_id ?? ""}
              onChange={(e) => set("sub_unit_id", e.target.value ? Number(e.target.value) : null)} fullWidth>
              <MenuItem value=""><em>None</em></MenuItem>
              {units.filter((u) => u.id !== product?.base_unit_id).map((u) => (
                <MenuItem key={u.id} value={u.id}>{u.code}</MenuItem>
              ))}
            </TextField>
            <TextField label="Sub-units per base" value={draft.sub_unit_qty ?? ""}
              onChange={(e) => set("sub_unit_qty", e.target.value)} fullWidth disabled={!draft.sub_unit_id} />
          </Stack>
          <Stack direction="row" spacing={2}>
            <FormControlLabel
              control={<Checkbox checked={draft.price_inclusive ?? false}
                onChange={(e) => set("price_inclusive", e.target.checked)} />}
              label="Prices include tax"
            />
            <FormControlLabel
              control={<Checkbox checked={draft.allow_negative_stock ?? false}
                onChange={(e) => set("allow_negative_stock", e.target.checked)} />}
              label="Allow negative stock"
            />
            <FormControlLabel
              control={<Checkbox checked={draft.is_active ?? true}
                onChange={(e) => set("is_active", e.target.checked)} />}
              label="Active"
            />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={saving}
          onClick={() => onSave({
            ...draft,
            hsn_code: draft.hsn_code === "" ? null : draft.hsn_code,
            gst_rate: draft.gst_rate === "" ? null : draft.gst_rate,
            sale_price: draft.sale_price === "" ? null : draft.sale_price,
            purchase_price: draft.purchase_price === "" ? null : draft.purchase_price,
            sub_unit_qty: draft.sub_unit_qty === "" ? null : draft.sub_unit_qty,
            min_stock_qty: draft.min_stock_qty === "" ? undefined : draft.min_stock_qty,
          })}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}
