import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
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

import { listUnits } from "../units/api";
import { createCategory, createProduct, listCategories, listProducts, type Product } from "./api";

const EMPTY = {
  code: "",
  name: "",
  base_unit_id: "",
  category_id: "",
  hsn_code: "",
  gst_rate: "",
  allow_negative_stock: false,
};

export function ProductsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [newCat, setNewCat] = useState("");

  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const categories = useQuery({ queryKey: ["categories"], queryFn: listCategories });
  const products = useQuery({ queryKey: ["products"], queryFn: () => listProducts() });

  const unitCode = useMemo(() => {
    const m = new Map<number, string>();
    (units.data ?? []).forEach((u) => m.set(u.id, u.code));
    return m;
  }, [units.data]);

  const create = useMutation({
    mutationFn: () =>
      createProduct({
        code: form.code,
        name: form.name,
        base_unit_id: Number(form.base_unit_id),
        category_id: form.category_id ? Number(form.category_id) : null,
        hsn_code: form.hsn_code || null,
        gst_rate: form.gst_rate || null,
        allow_negative_stock: form.allow_negative_stock,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      qc.invalidateQueries({ queryKey: ["products"] });
    },
  });

  const addCat = useMutation({
    mutationFn: () => createCategory({ name: newCat }),
    onSuccess: () => {
      setNewCat("");
      qc.invalidateQueries({ queryKey: ["categories"] });
    },
  });

  const canSubmit = form.code && form.name && form.base_unit_id;

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
                  required
                  value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
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
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Base unit</TableCell>
                <TableCell>HSN</TableCell>
                <TableCell>GST %</TableCell>
                <TableCell>Neg?</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(products.data ?? []).map((p: Product) => (
                <TableRow key={p.id}>
                  <TableCell>
                    <code>{p.code}</code>
                  </TableCell>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{unitCode.get(p.base_unit_id) ?? p.base_unit_id}</TableCell>
                  <TableCell>{p.hsn_code || "—"}</TableCell>
                  <TableCell>{p.gst_rate ?? "—"}</TableCell>
                  <TableCell>
                    {p.allow_negative_stock ? <Chip size="small" label="yes" color="warning" /> : "—"}
                  </TableCell>
                </TableRow>
              ))}
              {(products.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No products yet.</Typography>
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
