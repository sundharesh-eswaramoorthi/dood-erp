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
import { useState } from "react";

import { createParty, getActivity, listParties, type Party } from "./api";

const EMPTY = { name: "", party_type: "customer", phone: "", gstin: "" };

export function PartiesPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);

  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const activity = useQuery({
    queryKey: ["activity"],
    queryFn: getActivity,
    refetchInterval: 3000,
  });

  const create = useMutation({
    mutationFn: () =>
      createParty({
        name: form.name,
        party_type: form.party_type,
        phone: form.phone || null,
        gstin: form.gstin || null,
      }),
    onSuccess: () => {
      setForm(EMPTY);
      qc.invalidateQueries({ queryKey: ["parties"] });
    },
  });

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" fontWeight={800}>
          Parties
        </Typography>
        <Typography color="text.secondary">
          Phase-0 walking skeleton — a scoped write flows Postgres → outbox → Celery →
          Redis/Mongo, then back out through the activity feed.
        </Typography>
      </Box>

      <Card elevation={1}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add customer
          </Typography>
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
              <TextField
                label="Name"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                sx={{ flex: 2 }}
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
              <TextField
                label="GSTIN"
                value={form.gstin}
                onChange={(e) => setForm({ ...form, gstin: e.target.value })}
                sx={{ flex: 1 }}
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={create.isPending || !form.name}
                sx={{ height: 56 }}
              >
                Add
              </Button>
            </Stack>
          </Box>
          {create.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              Could not create party.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card elevation={1}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Customer list
          </Typography>
          {parties.isLoading ? (
            <Typography color="text.secondary">Loading…</Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Code</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Phone</TableCell>
                  <TableCell>GSTIN</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(parties.data ?? []).map((p: Party) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <code>{p.party_code}</code>
                    </TableCell>
                    <TableCell>{p.name}</TableCell>
                    <TableCell>
                      <Chip size="small" label={p.party_type} />
                    </TableCell>
                    <TableCell>{p.phone || "—"}</TableCell>
                    <TableCell>{p.gstin || "—"}</TableCell>
                  </TableRow>
                ))}
                {(parties.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5}>
                      <Typography color="text.secondary">No parties yet.</Typography>
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
            <Typography variant="h6">Recent activity (from Redis)</Typography>
            <Chip size="small" color="secondary" label={`${activity.data?.count ?? 0} events`} />
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Written by the Celery outbox drainer — proof the async pipeline is live.
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 1.5 }}>
            {(activity.data?.items ?? []).map((it, i) => (
              <Typography key={i} variant="body2" sx={{ fontFamily: "monospace" }}>
                {new Date(it.at).toLocaleTimeString()} · {it.topic} ·{" "}
                {JSON.stringify(it.payload)}
              </Typography>
            ))}
            {(activity.data?.items ?? []).length === 0 && (
              <Typography color="text.secondary" variant="body2">
                No activity yet — add a party and watch it appear within ~3s.
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
