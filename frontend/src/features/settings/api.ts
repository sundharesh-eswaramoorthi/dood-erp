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

// ---- branches (v2 §9 "Add branch") ----
export interface Branch {
  id: number;
  name: string;
  code: string | null;
  address: string | null;
  phone: string | null;
  gstin: string | null;
  state_code: string | null;
  is_active: boolean;
}

export async function listBranchesAdmin(includeInactive = true): Promise<Branch[]> {
  const { data } = await api.get<Branch[]>("/api/v1/branches", {
    params: { include_inactive: includeInactive },
  });
  return data;
}

export async function createBranch(payload: Partial<Branch> & { name: string }): Promise<Branch> {
  const { data } = await api.post<Branch>("/api/v1/branches", payload);
  return data;
}

export async function updateBranch(id: number, payload: Partial<Branch>): Promise<Branch> {
  const { data } = await api.put<Branch>(`/api/v1/branches/${id}`, payload);
  return data;
}

// ---- godowns (v2 §2 "Godown management") ----
export interface GodownAdmin {
  id: number;
  name: string;
  branch_id: number;
  code: string | null;
  is_active: boolean;
}

export async function listGodownsAdmin(): Promise<GodownAdmin[]> {
  const { data } = await api.get<GodownAdmin[]>("/api/v1/godowns", {
    params: { include_inactive: true, all_branches: true },
  });
  return data;
}

export async function createGodown(payload: {
  name: string;
  branch_id: number;
  code?: string | null;
}): Promise<GodownAdmin> {
  const { data } = await api.post<GodownAdmin>("/api/v1/godowns", payload);
  return data;
}

export async function updateGodown(
  id: number,
  payload: Partial<GodownAdmin>,
): Promise<GodownAdmin> {
  const { data } = await api.put<GodownAdmin>(`/api/v1/godowns/${id}`, payload);
  return data;
}

// ---- document types (v2 §9 "Add documents (customisable)") ----
export interface DocumentType {
  id: number;
  name: string;
  applies_to: string;
  is_required: boolean;
  is_active: boolean;
  sort_order: number;
}

export async function listDocumentTypes(
  appliesTo = "party",
  includeInactive = false,
): Promise<DocumentType[]> {
  const { data } = await api.get<DocumentType[]>("/api/v1/document-types", {
    params: { applies_to: appliesTo, include_inactive: includeInactive },
  });
  return data;
}

export async function createDocumentType(payload: {
  name: string;
  applies_to?: string;
  is_required?: boolean;
  sort_order?: number;
}): Promise<DocumentType> {
  const { data } = await api.post<DocumentType>("/api/v1/document-types", payload);
  return data;
}

export async function updateDocumentType(
  id: number,
  payload: Partial<DocumentType>,
): Promise<DocumentType> {
  const { data } = await api.put<DocumentType>(`/api/v1/document-types/${id}`, payload);
  return data;
}

// ---- document numbering (v2 §9) ----
export interface NumberingSeries {
  id: number;
  doc_type: string;
  label: string;
  fin_year: string;
  prefix: string;
  pad_width: number;
  next_value: number;
  branch_id: number | null;
  /** what the next allocated number will look like */
  sample: string;
}

export async function listNumbering(): Promise<NumberingSeries[]> {
  const { data } = await api.get<NumberingSeries[]>("/api/v1/numbering-series");
  return data;
}

export async function updateNumbering(
  id: number,
  payload: { prefix?: string; pad_width?: number; next_value?: number },
): Promise<NumberingSeries> {
  const { data } = await api.put<NumberingSeries>(`/api/v1/numbering-series/${id}`, payload);
  return data;
}
