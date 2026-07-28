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
}

export interface ProductCreate {
  code: string;
  name: string;
  base_unit_id: number;
  category_id?: number | null;
  allow_negative_stock?: boolean;
  hsn_code?: string | null;
  gst_rate?: string | null;
}

export async function listProducts(q?: string): Promise<Product[]> {
  const { data } = await api.get<Product[]>("/api/v1/products", { params: q ? { q } : {} });
  return data;
}

export async function createProduct(payload: ProductCreate): Promise<Product> {
  const { data } = await api.post<Product>("/api/v1/products", payload);
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
