import { api } from "../../lib/api";

export interface Party {
  id: number;
  party_code: string;
  name: string;
  area: string;
  gstin: string | null;
  phone: string | null;
  pan: string | null;
  credit_limit: string | null;
  opening_balance: string;
  opening_balance_side: string;
  opening_as_of: string | null;
  is_active: boolean;
  serving_branch_id: number;
}

/** List rows carry live outstanding so the grid can show/sort on it. */
export interface PartyListItem extends Party {
  net_balance: string;
  receivable: string;
  payable: string;
}

export interface AddressInput {
  line1: string;
  label?: string;
  line2?: string;
  city?: string;
  state?: string;
  pincode?: string;
  lat?: string | null;
  lng?: string | null;
  /** pasted Google Maps URL; lat/lng are read out of it server-side */
  map_link?: string | null;
  is_default?: boolean;
}

export interface ContactInput {
  name: string;
  phone?: string;
  email?: string;
  designation?: string;
  relationship?: string;
  is_primary?: boolean;
}

export interface PartyCreate {
  name: string;
  area: string;
  gstin?: string | null;
  phone?: string | null;
  pan?: string | null;
  credit_limit?: string | null;
  opening_balance?: string;
  opening_balance_side?: string;
  opening_as_of?: string | null;
  is_active?: boolean;
  /** required: which branch serves this party */
  serving_branch_id: number;
  address?: AddressInput | null;
  contacts?: ContactInput[];
}

/** Editing a party never posts its address or contacts — those are their own
 *  sub-resources once the party exists. */
export type PartyUpdate = Partial<Omit<PartyCreate, "address" | "contacts">>;

export interface PartyFilters {
  q?: string;
  area?: string;
  is_active?: boolean;
  serving_branch_id?: number;
  tag_id?: number;
  sort?: string;
  direction?: "asc" | "desc";
  limit?: number;
  offset?: number;
}

export interface Contact {
  id: number;
  name: string;
  phone: string | null;
  email: string | null;
  designation: string | null;
  relationship: string | null;
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
  map_link: string | null;
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

export async function listParties(filters: PartyFilters = {}): Promise<PartyListItem[]> {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== null),
  );
  const { data } = await api.get<PartyListItem[]>("/api/v1/parties", { params });
  return data;
}

export async function listAreas(): Promise<string[]> {
  const { data } = await api.get<string[]>("/api/v1/parties/areas");
  return data;
}

export async function updateParty(id: number, payload: PartyUpdate): Promise<Party> {
  const { data } = await api.put<Party>(`/api/v1/parties/${id}`, payload);
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
  payload: {
    name: string;
    phone?: string;
    email?: string;
    designation?: string;
    relationship?: string;
    is_primary?: boolean;
  },
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
    map_link?: string | null;
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
  opening_balance: string;
  opening_balance_side: string;
  credit_limit: string | null;
  credit_available: string | null;
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
