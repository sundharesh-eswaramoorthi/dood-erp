import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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

import { createUnit, listUnits, type Unit } from "./api";

export function UnitsPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({ code: "", name: "" });
  const units = useQuery({ queryKey: ["units"], queryFn: listUnits });
  const create = useMutation({
    mutationFn: () => createUnit({ code: form.code, name: form.name }),
    onSuccess: () => {
      setForm({ code: "", name: "" });
      qc.invalidateQueries({ queryKey: ["units"] });
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Units of Measure
      </Typography>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add unit
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Code"
                required
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                sx={{ width: 140 }}
              />
              <TextField
                label="Name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                sx={{ flex: 1 }}
              />
              <Button
                type="submit"
                variant="contained"
                sx={{ height: 56 }}
                disabled={create.isPending || !form.code || !form.name}
              >
                Add
              </Button>
            </Stack>
          </Box>
          {create.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              Could not create unit (duplicate code?).
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
              </TableRow>
            </TableHead>
            <TableBody>
              {(units.data ?? []).map((u: Unit) => (
                <TableRow key={u.id}>
                  <TableCell>
                    <code>{u.code}</code>
                  </TableCell>
                  <TableCell>{u.name}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  );
}
