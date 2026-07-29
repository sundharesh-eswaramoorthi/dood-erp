import { api } from "../../lib/api";

export interface Party {
  id: number;
  party_code: string;
  name: string;
  party_type: string;
  gstin: string | null;
  phone: string | null;
  pan: string | null;
  credit_limit: string | null;
  branch_id: number;
}

export interface PartyCreate {
  name: string;
  party_type: string;
  gstin?: string | null;
  phone?: string | null;
  pan?: string | null;
  credit_limit?: string | null;
}

export interface Contact {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  designation: string | null;
  is_primary: boolean;
}

export interface Address {
  id: number;
  label: string | null;
  line1: string;
  line2: string | null;
  city: string | null;
  state: string | null;
  pincode: string | null;
  lat: string | null;
  lng: string | null;
  place_id: string | null;
  is_default: boolean;
}

export interface GstReg {
  id: number;
  gstin: string;
  state_code: string | null;
  legal_name: string | null;
  is_default: boolean;
}

export interface PartyDocument {
  id: number;
  doc_type: string;
  file_name: string;
  storage_key: string;
  content_type: string | null;
}

export interface TagRef {
  id: number;
  name: string;
  color: string;
}

export interface PartyDetail extends Party {
  contacts: Contact[];
  addresses: Address[];
  gst_registrations: GstReg[];
  documents: PartyDocument[];
  tags: TagRef[];
}

export interface ActivityItem {
  topic: string;
  payload: Record<string, unknown>;
  at: string;
}
export interface Activity {
  count: number;
  items: ActivityItem[];
}

export async function listParties(q?: string): Promise<Party[]> {
  const { data } = await api.get<Party[]>("/api/v1/parties", { params: q ? { q } : {} });
  return data;
}

export async function createParty(payload: PartyCreate): Promise<Party> {
  const { data } = await api.post<Party>("/api/v1/parties", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function getParty(id: number): Promise<PartyDetail> {
  const { data } = await api.get<PartyDetail>(`/api/v1/parties/${id}`);
  return data;
}

export async function addContact(
  id: number,
  payload: { name: string; phone?: string; email?: string; designation?: string; is_primary?: boolean },
): Promise<Contact> {
  const { data } = await api.post<Contact>(`/api/v1/parties/${id}/contacts`, payload);
  return data;
}

export async function addAddress(
  id: number,
  payload: {
    line1: string;
    label?: string;
    city?: string;
    state?: string;
    pincode?: string;
    lat?: string | null;
    lng?: string | null;
  },
): Promise<Address> {
  const { data } = await api.post<Address>(`/api/v1/parties/${id}/addresses`, payload);
  return data;
}

export async function addGst(
  id: number,
  payload: { gstin: string; legal_name?: string; is_default?: boolean },
): Promise<GstReg> {
  const { data } = await api.post<GstReg>(`/api/v1/parties/${id}/gst-registrations`, payload);
  return data;
}

export async function getActivity(): Promise<Activity> {
  const { data } = await api.get<Activity>("/api/v1/activity");
  return data;
}

export async function addTag(id: number, tagId: number): Promise<TagRef[]> {
  const { data } = await api.post<TagRef[]>(`/api/v1/parties/${id}/tags`, { tag_id: tagId });
  return data;
}

export async function removeTag(id: number, tagId: number): Promise<TagRef[]> {
  const { data } = await api.delete<TagRef[]>(`/api/v1/parties/${id}/tags/${tagId}`);
  return data;
}

export async function addDocument(
  id: number,
  payload: { doc_type: string; file_name: string; storage_key: string },
): Promise<PartyDocument> {
  const { data } = await api.post<PartyDocument>(`/api/v1/parties/${id}/documents`, payload);
  return data;
}

export interface LedgerEntry {
  id: number;
  entry_side: string;
  amount: string;
  source_doc_type: string;
  source_doc_id: number;
  effective_date: string;
}
export interface PartyLedger {
  party_id: number;
  net_balance: string;
  receivable: string;
  payable: string;
  entries: LedgerEntry[];
}

export async function getLedger(id: number): Promise<PartyLedger> {
  const { data } = await api.get<PartyLedger>(`/api/v1/parties/${id}/ledger`);
  return data;
}

export async function addLedgerEntry(
  id: number,
  payload: { entry_side: string; amount: string; note?: string },
): Promise<PartyLedger> {
  const { data } = await api.post<PartyLedger>(`/api/v1/parties/${id}/ledger/entries`, payload);
  return data;
}
