import { api } from "../../lib/api";

export interface Party {
  id: number;
  party_code: string;
  name: string;
  party_type: string;
  gstin: string | null;
  phone: string | null;
  branch_id: number;
}

export interface PartyCreate {
  name: string;
  party_type: string;
  gstin?: string | null;
  phone?: string | null;
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
  const { data } = await api.get<Party[]>("/api/v1/parties", {
    params: q ? { q } : {},
  });
  return data;
}

export async function createParty(payload: PartyCreate): Promise<Party> {
  const { data } = await api.post<Party>("/api/v1/parties", payload, {
    headers: { "Idempotency-Key": crypto.randomUUID() },
  });
  return data;
}

export async function getActivity(): Promise<Activity> {
  const { data } = await api.get<Activity>("/api/v1/activity");
  return data;
}
