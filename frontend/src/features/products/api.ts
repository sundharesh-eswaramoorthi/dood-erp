import { api } from "../../lib/api";

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  is_active: boolean;
}

export interface Product {
  id: number;
  code: string;
  name: string;
  category_id: number | null;
  base_unit_id: number;
  allow_negative_stock: boolean;
  reorder_default: string | null;
  hsn_code: string | null;
  gst_rate: string | null;
  is_active: boolean;
  // v2 §2 pricing master
  sale_price: string | null;
  purchase_price: string | null;
  price_inclusive: boolean;
  sub_unit_id: number | null;
  sub_unit_qty: string | null;
  opening_qty: string | null;
  opening_rate: string | null;
  opening_as_of: string | null;
  opening_godown_id: number | null;
  // present on list rows only
  stock_qty?: string;
  stock_value?: string;
  avg_cost?: string;
  min_stock_qty?: string | null;
  low_stock?: boolean;
}

export interface ProductCreate {
  code: string;
  name: string;
  base_unit_id: number;
  category_id?: number | null;
  allow_negative_stock?: boolean;
  hsn_code?: string | null;
  gst_rate?: string | null;
  sale_price?: string | null;
  purchase_price?: string | null;
  price_inclusive?: boolean;
  sub_unit_id?: number | null;
  sub_unit_qty?: string | null;
  min_stock_qty?: string | null;
  opening_qty?: string | null;
  opening_rate?: string | null;
  opening_as_of?: string | null;
  opening_godown_id?: number | null;
  is_active?: boolean;
}

export type ProductUpdate = Partial<Omit<ProductCreate, "code" | "base_unit_id">>;

export interface ProductFilters {
  q?: string;
  category_id?: number;
  is_active?: boolean;
  low_stock?: boolean;
  sort?: string;
  direction?: "asc" | "desc";
}

export async function listProducts(filters: ProductFilters | string = {}): Promise<Product[]> {
  // a bare string keeps the older `listProducts("rice")` callers working
  const f: ProductFilters = typeof filters === "string" ? { q: filters } : filters;
  const params = Object.fromEntries(
    Object.entries(f).filter(([, v]) => v !== undefined && v !== "" && v !== null),
  );
  const { data } = await api.get<Product[]>("/api/v1/products", { params });
  return data;
}

export async function createProduct(payload: ProductCreate): Promise<Product> {
  const { data } = await api.post<Product>("/api/v1/products", payload);
  return data;
}

export async function updateProduct(id: number, payload: ProductUpdate): Promise<Product> {
  const { data } = await api.put<Product>(`/api/v1/products/${id}`, payload);
  return data;
}

export async function listCategories(): Promise<Category[]> {
  const { data } = await api.get<Category[]>("/api/v1/products/categories");
  return data;
}

export async function createCategory(payload: { name: string }): Promise<Category> {
  const { data } = await api.post<Category>("/api/v1/products/categories", payload);
  return data;
}
