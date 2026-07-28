import { api } from "../../lib/api";

export interface TaxRate {
  id: number;
  name: string;
  rate: string;
  is_active: boolean;
}

export interface Tag {
  id: number;
  name: string;
  color: string;
  is_active: boolean;
}

export async function listTaxRates(): Promise<TaxRate[]> {
  const { data } = await api.get<TaxRate[]>("/api/v1/tax-rates");
  return data;
}

export async function createTaxRate(payload: { name: string; rate: string }): Promise<TaxRate> {
  const { data } = await api.post<TaxRate>("/api/v1/tax-rates", payload);
  return data;
}

export async function listTags(): Promise<Tag[]> {
  const { data } = await api.get<Tag[]>("/api/v1/tags");
  return data;
}

export async function createTag(payload: { name: string; color: string }): Promise<Tag> {
  const { data } = await api.post<Tag>("/api/v1/tags", payload);
  return data;
}

export async function getFeatureFlags(): Promise<Record<string, boolean>> {
  const { data } = await api.get<Record<string, boolean>>("/api/v1/feature-flags");
  return data;
}

export async function setFeatureFlag(name: string, enabled: boolean): Promise<void> {
  await api.put(`/api/v1/settings/feature.${name}`, { value: { enabled } });
}
