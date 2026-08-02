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
import { useEffect, useState } from "react";

import { errorMessage } from "../../lib/api";
import { useAuth } from "../../store/auth";
import {
  createUser,
  listBranches,
  listRoles,
  listUsers,
  resetPassword,
  updateUser,
  type Branch,
  type Role,
  type User,
} from "./api";

const EMPTY = {
  username: "",
  password: "",
  full_name: "",
  is_superuser: false,
  roles: [] as string[],
  branches: [] as string[],
};

export function UsersPage() {
  const qc = useQueryClient();
  const { user: me } = useAuth();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const roles = useQuery({ queryKey: ["roles"], queryFn: listRoles });
  const branches = useQuery({ queryKey: ["branches"], queryFn: listBranches });

  const [f, setF] = useState(EMPTY);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [pwFor, setPwFor] = useState<User | null>(null);

  const branchName = (id: number) => branches.data?.find((b) => b.id === id)?.name ?? `#${id}`;

  // The form only refuses what the server refuses, so the two never disagree.
  const problem = (): string | null => {
    if (!f.username.trim()) return "Enter a username.";
    if (f.password.length < 4) return "Password must be at least 4 characters.";
    if (f.branches.length === 0) return "Pick at least one branch — a user with no branch sees an empty app.";
    if (f.roles.length === 0 && !f.is_superuser) return "Pick at least one role, or tick Super user.";
    return null;
  };

  const create = useMutation({
    mutationFn: () =>
      createUser({
        username: f.username.trim(),
        password: f.password,
        full_name: f.full_name || undefined,
        is_superuser: f.is_superuser,
        role_ids: f.roles.map(Number),
        branch_ids: f.branches.map(Number),
      }),
    onSuccess: (u) => {
      setMsg({ text: `Created user '${u.username}'. They can sign in now.`, ok: true });
      setF(EMPTY);
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not create the user"), ok: false }),
  });

  const save = useMutation({
    mutationFn: (args: { id: number; patch: Parameters<typeof updateUser>[1] }) =>
      updateUser(args.id, args.patch),
    onSuccess: (u) => {
      setMsg({ text: `Saved '${u.username}'. Role and branch changes apply the next time they sign in.`, ok: true });
      setEditing(null);
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not save the user"), ok: false }),
  });

  const setPw = useMutation({
    mutationFn: (args: { id: number; password: string }) => resetPassword(args.id, args.password),
    onSuccess: (u) => {
      setMsg({ text: `Password reset for '${u.username}'.`, ok: true });
      setPwFor(null);
    },
    onError: (e) => setMsg({ text: errorMessage(e, "Could not reset the password"), ok: false }),
  });

  const submit = () => {
    const p = problem();
    if (p) return setMsg({ text: p, ok: false });
    create.mutate();
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h4" fontWeight={800}>
        Users &amp; Roles
      </Typography>
      {msg && <Alert severity={msg.ok ? "success" : "error"} onClose={() => setMsg(null)}>{msg.text}</Alert>}

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Add user
          </Typography>
          <Box component="form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <Stack spacing={2}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField label="Username" required value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} sx={{ flex: 1 }} />
                <TextField
                  label="Password" type="password" required value={f.password}
                  onChange={(e) => setF({ ...f, password: e.target.value })}
                  helperText="at least 4 characters" sx={{ flex: 1 }}
                />
                <TextField label="Full name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} sx={{ flex: 1 }} />
              </Stack>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="flex-start">
                <TextField
                  label="Roles" select required={!f.is_superuser} SelectProps={{ multiple: true }}
                  value={f.roles} onChange={(e) => setF({ ...f, roles: e.target.value as unknown as string[] })}
                  helperText={f.is_superuser ? "super users get everything" : "what they may do"}
                  sx={{ minWidth: 220 }}
                >
                  {(roles.data ?? []).map((r) => (<MenuItem key={r.id} value={String(r.id)}>{r.name}</MenuItem>))}
                </TextField>
                <TextField
                  label="Branch access" select required SelectProps={{ multiple: true }}
                  value={f.branches} onChange={(e) => setF({ ...f, branches: e.target.value as unknown as string[] })}
                  helperText="at least one — the app is empty without it"
                  sx={{ minWidth: 200 }}
                >
                  {(branches.data ?? []).map((b) => (<MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>))}
                </TextField>
                <FormControlLabel
                  sx={{ mt: 1 }}
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
                <TableCell>Status</TableCell>
                <TableCell align="right" />
              </TableRow>
            </TableHead>
            <TableBody>
              {(users.data ?? []).map((u: User) => (
                <TableRow key={u.id} sx={{ opacity: u.is_active ? 1 : 0.5 }}>
                  <TableCell>
                    {u.username} {u.is_superuser && <Chip size="small" color="secondary" label="super" />}
                    {u.id === me?.id && <Chip size="small" variant="outlined" label="you" sx={{ ml: 0.5 }} />}
                  </TableCell>
                  <TableCell>{u.full_name || "—"}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      {u.roles.map((r) => (<Chip key={r} size="small" label={r} />))}
                      {u.is_superuser && u.roles.length === 0 && <Typography variant="caption" color="text.secondary">all (*)</Typography>}
                    </Stack>
                  </TableCell>
                  <TableCell>{u.branch_ids.map(branchName).join(", ") || "—"}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={u.is_active ? "active" : "disabled"}
                      color={u.is_active ? "success" : "default"}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => setEditing(u)}>Edit</Button>
                    <Button size="small" onClick={() => setPwFor(u)}>Password</Button>
                    <Button
                      size="small"
                      color="secondary"
                      disabled={u.id === me?.id || save.isPending}
                      title={u.id === me?.id ? "You cannot disable your own account" : undefined}
                      onClick={() => save.mutate({ id: u.id, patch: { is_active: !u.is_active } })}
                    >
                      {u.is_active ? "Disable" : "Enable"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {(users.data ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No users yet.</Typography>
                  </TableCell>
                </TableRow>
              )}
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
                  {r.code === "super_user" || r.code === "super_admin" ? (
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

      <EditUserDialog
        user={editing}
        roles={roles.data ?? []}
        branches={branches.data ?? []}
        saving={save.isPending}
        onClose={() => setEditing(null)}
        onSave={(patch) => editing && save.mutate({ id: editing.id, patch })}
      />
      <PasswordDialog
        user={pwFor}
        saving={setPw.isPending}
        onClose={() => setPwFor(null)}
        onSave={(password) => pwFor && setPw.mutate({ id: pwFor.id, password })}
      />
    </Stack>
  );
}

function EditUserDialog({
  user,
  roles,
  branches,
  saving,
  onClose,
  onSave,
}: {
  user: User | null;
  roles: Role[];
  branches: Branch[];
  saving: boolean;
  onClose: () => void;
  onSave: (patch: Parameters<typeof updateUser>[1]) => void;
}) {
  const [draft, setDraft] = useState({
    full_name: "",
    is_superuser: false,
    roles: [] as string[],
    branches: [] as string[],
  });

  useEffect(() => {
    if (!user) return;
    setDraft({
      full_name: user.full_name ?? "",
      is_superuser: user.is_superuser,
      roles: user.role_ids.map(String),
      branches: user.branch_ids.map(String),
    });
  }, [user]);

  return (
    <Dialog open={user != null} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Edit {user?.username}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Full name" value={draft.full_name}
            onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} fullWidth
          />
          <TextField
            label="Roles" select SelectProps={{ multiple: true }} value={draft.roles}
            onChange={(e) => setDraft({ ...draft, roles: e.target.value as unknown as string[] })}
            fullWidth
          >
            {roles.map((r) => (<MenuItem key={r.id} value={String(r.id)}>{r.name}</MenuItem>))}
          </TextField>
          <TextField
            label="Branch access" select SelectProps={{ multiple: true }} value={draft.branches}
            onChange={(e) => setDraft({ ...draft, branches: e.target.value as unknown as string[] })}
            fullWidth
          >
            {branches.map((b) => (<MenuItem key={b.id} value={String(b.id)}>{b.name}</MenuItem>))}
          </TextField>
          <FormControlLabel
            control={
              <Checkbox
                checked={draft.is_superuser}
                onChange={(e) => setDraft({ ...draft, is_superuser: e.target.checked })}
              />
            }
            label="Super user"
          />
          <Typography variant="caption" color="text.secondary">
            Permissions are carried in the sign-in token, so role and branch changes take effect the
            next time this user signs in (within 30 minutes at the latest).
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={saving}
          onClick={() =>
            onSave({
              full_name: draft.full_name || null,
              is_superuser: draft.is_superuser,
              role_ids: draft.roles.map(Number),
              branch_ids: draft.branches.map(Number),
            })
          }
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function PasswordDialog({
  user,
  saving,
  onClose,
  onSave,
}: {
  user: User | null;
  saving: boolean;
  onClose: () => void;
  onSave: (password: string) => void;
}) {
  const [pw, setPw] = useState("");

  useEffect(() => setPw(""), [user]);

  return (
    <Dialog open={user != null} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Reset password for {user?.username}</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus label="New password" type="password" value={pw}
          onChange={(e) => setPw(e.target.value)} fullWidth sx={{ mt: 1 }}
          helperText="at least 4 characters"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={saving || pw.length < 4} onClick={() => onSave(pw)}>
          Set password
        </Button>
      </DialogActions>
    </Dialog>
  );
}
