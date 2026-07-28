import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  FormControlLabel,
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

import {
  createTag,
  createTaxRate,
  getFeatureFlags,
  listTags,
  listTaxRates,
  setFeatureFlag,
  type Tag,
  type TaxRate,
} from "./api";

export function SettingsPage() {
  const qc = useQueryClient();
  const [tax, setTax] = useState({ name: "", rate: "" });
  const [tag, setTag] = useState({ name: "", color: "#B96D28" });

  const taxRates = useQuery({ queryKey: ["tax-rates"], queryFn: listTaxRates });
  const tags = useQuery({ queryKey: ["tags"], queryFn: listTags });
  const flags = useQuery({ queryKey: ["feature-flags"], queryFn: getFeatureFlags });

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
    </Stack>
  );
}
