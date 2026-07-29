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
import { useState } from "react";

import { createUser, listBranches, listRoles, listUsers, type Role, type User } from "./api";

const EMPTY = { username: "", password: "", full_name: "", is_superuser: false, roles: [] as string[], branches: [] as string[] };

export function UsersPage() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const branches = useQuery({ queryKey: ["branches"], queryFn: listBranches });

  const [f, setF] = useState(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      createUser({
        username: f.username,
        password: f.password,
        full_name: f.full_name || undefined,
        is_superuser: f.is_superuser,
        role_ids: f.roles.map(Number),
        branch_ids: f.branches.map(Number),
      }),
    onSuccess: (u) => {
      setMsg(`Created user '${u.username}'.`);
      setF(EMPTY);
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMsg(d || "Create failed");
    },
  });

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Users &amp; Roles
      </Typography>
      {msg && <Alert severity={msg.includes("failed") || msg.includes("taken") ? "error" : "success"}>{msg}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add user
          </Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); if (f.username && f.password) create.mutate(); }}>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField label="Username" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} sx={{ flex: 1 }} />
                <TextField label="Password" type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} sx={{ flex: 1 }} />
                <TextField label="Full name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} sx={{ flex: 1 }} />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
                <TextField
                  label="Roles" select SelectProps={{ multiple: true }}
                  value={f.roles} onChange={(e) => setF({ ...f, roles: e.target.value as unknown as string[] })}
                  sx={{ minWidth: 220 }}
                >
                  {(roles.data ?? []).map((r) => (<MenuItem key={r.id} value={String(r.id)}>{r.name}</MenuItem>))}
                </TextField>
                <TextField
                  label="Branch access" select SelectProps={{ multiple: true }}
                  value={f.branches} onChange={(e) => setF({ ...f, branches: e.target.value as unknown as string[] })}
                  sx={{ minWidth: 200 }}
                >
                  {(branches.data ?? []).map((b) => (<MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>))}
                </TextField>
                <FormControlLabel
                  control={<Checkbox checked={f.is_superuser} onChange={(e) => setF({ ...f, is_superuser: e.target.checked })} />}
                  label="Super user"
                />
                <Button type="submit" variant="contained" sx={{ height: 56, ml: "auto" }} disabled={create.isPending}>
                  Create
                </Button>
              </Stack>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Users</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Username</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Roles</TableCell>
                <TableCell>Branches</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(users.data ?? []).map((u: User) => (
                <TableRow key={u.id}>
                  <TableCell>
                    {u.username} {u.is_superuser && <Chip size="small" color="secondary" label="super" />}
                  </TableCell>
                  <TableCell>{u.full_name || "—"}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {u.roles.map((r) => (<Chip key={r} size="small" label={r} />))}
                      {u.is_superuser && u.roles.length === 0 && <Typography variant="caption" color="text.secondary">all (*)</Typography>}
                    </Stack>
                  </TableCell>
                  <TableCell>{u.branch_ids.join(", ") || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Roles &amp; permissions</Typography>
          <Stack spacing={1.5}>
            {(roles.data ?? []).map((r: Role) => (
              <Box key={r.id}>
                <Typography variant="subtitle2">{r.name}</Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                  {r.code === "super_user" ? (
                    <Chip size="small" color="primary" label="* (all permissions)" />
                  ) : r.permissions.length === 0 ? (
                    <Typography variant="caption" color="text.secondary">none</Typography>
                  ) : (
                    r.permissions.map((p) => (<Chip key={p} size="small" variant="outlined" label={p} />))
                  )}
                </Stack>
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
