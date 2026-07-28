import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Link as MuiLink,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { addAddress, addContact, addGst, addLedgerEntry, getLedger, getParty } from "./api";

export function PartyDetailPage() {
  const { id } = useParams();
  const partyId = Number(id);
  const qc = useQueryClient();
  const party = useQuery({ queryKey: ["party", partyId], queryFn: () => getParty(partyId) });

  const [contact, setContact] = useState({ name: "", phone: "" });
  const [address, setAddress] = useState({ line1: "", city: "", lat: "", lng: "" });
  const [gstin, setGstin] = useState("");
  const [ledger, setLedger] = useState({ side: "debit", amount: "", note: "" });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["party", partyId] });
  const ledgerQ = useQuery({ queryKey: ["ledger", partyId], queryFn: () => getLedger(partyId) });
  const mLedger = useMutation({
    mutationFn: () =>
      addLedgerEntry(partyId, { entry_side: ledger.side, amount: ledger.amount, note: ledger.note }),
    onSuccess: () => {
      setLedger({ side: "debit", amount: "", note: "" });
      qc.invalidateQueries({ queryKey: ["ledger", partyId] });
    },
  });

  const mContact = useMutation({
    mutationFn: () => addContact(partyId, { name: contact.name, phone: contact.phone }),
    onSuccess: () => {
      setContact({ name: "", phone: "" });
      invalidate();
    },
  });
  const mAddress = useMutation({
    mutationFn: () =>
      addAddress(partyId, {
        line1: address.line1,
        city: address.city,
        lat: address.lat || null,
        lng: address.lng || null,
      }),
    onSuccess: () => {
      setAddress({ line1: "", city: "", lat: "", lng: "" });
      invalidate();
    },
  });
  const mGst = useMutation({
    mutationFn: () => addGst(partyId, { gstin }),
    onSuccess: () => {
      setGstin("");
      invalidate();
    },
  });

  if (party.isLoading) return <Typography>Loading…</Typography>;
  if (party.isError || !party.data) return <Typography>Party not found.</Typography>;
  const p = party.data;

  return (
    <Stack spacing={3}>
      <Box>
        <MuiLink component={Link} to="/" underline="hover">
          ← Parties
        </MuiLink>
        <Stack direction="row" spacing={2} alignItems="baseline" sx={{ mt: 1 }}>
          <Typography variant="h4" fontWeight={800}>
            {p.name}
          </Typography>
          <Chip label={p.party_code} />
          <Chip label={p.party_type} color="secondary" variant="outlined" />
        </Stack>
        <Typography color="text.secondary">
          Phone {p.phone || "—"} · PAN {p.pan || "—"} · Credit limit {p.credit_limit || "—"}
        </Typography>
      </Box>

      <Card>
        <CardContent>
          <Typography variant="h6">Contacts</Typography>
          <Divider sx={{ my: 1 }} />
          {p.contacts.map((c) => (
            <Typography key={c.id} variant="body2">
              • {c.name} {c.phone ? `· ${c.phone}` : ""} {c.is_primary ? "★" : ""}
            </Typography>
          ))}
          {p.contacts.length === 0 && (
            <Typography color="text.secondary" variant="body2">
              No contacts yet.
            </Typography>
          )}
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (contact.name) mContact.mutate();
            }}
          >
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <TextField
                size="small"
                label="Name"
                value={contact.name}
                onChange={(e) => setContact({ ...contact, name: e.target.value })}
              />
              <TextField
                size="small"
                label="Phone"
                value={contact.phone}
                onChange={(e) => setContact({ ...contact, phone: e.target.value })}
              />
              <Button type="submit" variant="contained" disabled={mContact.isPending}>
                Add contact
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6">Addresses (with map location)</Typography>
          <Divider sx={{ my: 1 }} />
          {p.addresses.map((a) => (
            <Typography key={a.id} variant="body2">
              • {a.line1}
              {a.city ? `, ${a.city}` : ""}
              {a.lat && a.lng ? ` · 📍 ${a.lat}, ${a.lng}` : ""}
            </Typography>
          ))}
          {p.addresses.length === 0 && (
            <Typography color="text.secondary" variant="body2">
              No addresses yet.
            </Typography>
          )}
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (address.line1) mAddress.mutate();
            }}
          >
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="Line 1"
                value={address.line1}
                onChange={(e) => setAddress({ ...address, line1: e.target.value })}
              />
              <TextField
                size="small"
                label="City"
                value={address.city}
                onChange={(e) => setAddress({ ...address, city: e.target.value })}
              />
              <TextField
                size="small"
                label="Lat"
                value={address.lat}
                onChange={(e) => setAddress({ ...address, lat: e.target.value })}
                sx={{ width: 120 }}
              />
              <TextField
                size="small"
                label="Lng"
                value={address.lng}
                onChange={(e) => setAddress({ ...address, lng: e.target.value })}
                sx={{ width: 120 }}
              />
              <Button type="submit" variant="contained" disabled={mAddress.isPending}>
                Add address
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6">GST registrations</Typography>
          <Divider sx={{ my: 1 }} />
          {p.gst_registrations.map((g) => (
            <Typography key={g.id} variant="body2">
              • <code>{g.gstin}</code> {g.state_code ? `(state ${g.state_code})` : ""}{" "}
              {g.is_default ? "★" : ""}
            </Typography>
          ))}
          {p.gst_registrations.length === 0 && (
            <Typography color="text.secondary" variant="body2">
              No GST registrations yet.
            </Typography>
          )}
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (gstin.length === 15) mGst.mutate();
            }}
          >
            <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
              <TextField
                size="small"
                label="GSTIN (15 chars)"
                value={gstin}
                onChange={(e) => setGstin(e.target.value.toUpperCase())}
                sx={{ width: 260 }}
              />
              <Button
                type="submit"
                variant="contained"
                disabled={mGst.isPending || gstin.length !== 15}
              >
                Add GSTIN
              </Button>
            </Stack>
            {mGst.isError && (
              <Typography color="error" variant="caption">
                Could not add (duplicate GSTIN?)
              </Typography>
            )}
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6">Ledger (outstanding)</Typography>
          <Stack direction="row" spacing={2} sx={{ my: 1 }}>
            <Chip color="primary" label={`Receivable ₹${ledgerQ.data?.receivable ?? "0.00"}`} />
            <Chip label={`Payable ₹${ledgerQ.data?.payable ?? "0.00"}`} />
            <Chip color="secondary" variant="outlined" label={`Net ₹${ledgerQ.data?.net_balance ?? "0.00"}`} />
          </Stack>
          <Divider sx={{ my: 1 }} />
          {(ledgerQ.data?.entries ?? []).map((e) => (
            <Typography key={e.id} variant="body2" sx={{ fontFamily: "monospace" }}>
              {e.effective_date} · {e.entry_side === "debit" ? "Dr" : "Cr"} ₹{e.amount} ·{" "}
              {e.source_doc_type} #{e.source_doc_id}
            </Typography>
          ))}
          {(ledgerQ.data?.entries ?? []).length === 0 && (
            <Typography color="text.secondary" variant="body2">
              No ledger entries yet.
            </Typography>
          )}
          <Box
            component="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (ledger.amount) mLedger.mutate();
            }}
          >
            <Stack direction="row" spacing={1} sx={{ mt: 2 }} alignItems="center">
              <TextField
                size="small"
                label="Side"
                select
                value={ledger.side}
                onChange={(e) => setLedger({ ...ledger, side: e.target.value })}
                sx={{ width: 160 }}
              >
                <MenuItem value="debit">Debit (they owe us)</MenuItem>
                <MenuItem value="credit">Credit (we owe them)</MenuItem>
              </TextField>
              <TextField
                size="small"
                label="Amount"
                value={ledger.amount}
                onChange={(e) => setLedger({ ...ledger, amount: e.target.value })}
                sx={{ width: 140 }}
              />
              <TextField
                size="small"
                label="Note"
                value={ledger.note}
                onChange={(e) => setLedger({ ...ledger, note: e.target.value })}
              />
              <Button type="submit" variant="contained" disabled={mLedger.isPending}>
                Post entry
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}
