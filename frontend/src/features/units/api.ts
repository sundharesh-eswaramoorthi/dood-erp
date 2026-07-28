import { api } from "../../lib/api";

export interface Unit {
  id: number;
  code: string;
  name: string;
}

export async function listUnits(): Promise<Unit[]> {
  const { data } = await api.get<Unit[]>("/api/v1/units");
  return data;
}

export async function createUnit(payload: { code: string; name: string }): Promise<Unit> {
  const { data } = await api.post<Unit>("/api/v1/units", payload);
  return data;
}
