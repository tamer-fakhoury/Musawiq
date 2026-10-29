"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";
import {
  CONCEPT_STATUSES,
  SORT_OPTIONS,
  formatDate,
  formatMoney,
  formatScore,
  statusLabel,
  type Category,
  type Concept,
} from "@/lib/concepts";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function ConceptsPage() {
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [sort, setSort] = useState("created_at");
  const [direction, setDirection] = useState("desc");

  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<Concept | null>(null);

  const fetchConcepts = useCallback(async () => {
    const params = new URLSearchParams();
    if (search.trim()) {
      params.set("search", search.trim());
    }
    if (statusFilter) {
      params.set("status", statusFilter);
    }
    if (categoryFilter) {
      params.set("category_id", categoryFilter);
    }
    if (createdFrom) {
      params.set("created_from", createdFrom);
    }
    if (createdTo) {
      params.set("created_to", createdTo);
    }
    params.set("sort", sort);
    params.set("direction", direction);

    return apiFetch<Concept[]>(
      `/product-concepts?${params.toString()}`,
    );
  }, [
    categoryFilter,
    createdFrom,
    createdTo,
    direction,
    search,
    sort,
    statusFilter,
  ]);

  const loadConcepts = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      const data = await fetchConcepts();
      setConcepts(Array.isArray(data) ? data : []);
    } catch (error) {
      setListError(errorMessage(error, "تعذر تحميل المفاهيم."));
    } finally {
      setLoading(false);
    }
  }, [fetchConcepts]);

  useEffect(() => {
    let active = true;
    fetchConcepts()
      .then((data) => {
        if (active) {
          setConcepts(Array.isArray(data) ? data : []);
          setListError(null);
          setLoading(false);
        }
      })
      .catch((error) => {
        if (active) {
          setListError(errorMessage(error, "تعذر تحميل المفاهيم."));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [fetchConcepts]);

  useEffect(() => {
    let active = true;
    apiFetch<Category[]>("/categories")
      .then((data) => {
        if (active) {
          setCategories(Array.isArray(data) ? data : []);
        }
      })
      .catch(() => {
        if (active) {
          setCategories([]);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const categoryNames = new Map(
    categories.map((category) => [category.id, category.name]),
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const price = Number(values.get("price") ?? 0);
    const cost = Number(values.get("cost") ?? 0);

    setFormError(null);
    setNotice(null);

    if (!Number.isFinite(price) || price <= 0) {
      setFormError("السعر يجب أن يكون أكبر من صفر.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0) {
      setFormError("التكلفة يجب ألا تكون سالبة.");
      return;
    }

    setCreating(true);
    try {
      await apiFetch<Concept>("/product-concepts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: String(values.get("name") ?? ""),
          description: String(values.get("description") ?? ""),
          category_id: String(values.get("category_id") ?? ""),
          price_minor: Math.round(price * 100),
          cost_minor: Math.round(cost * 100),
          currency: String(values.get("currency") ?? "USD"),
        }),
      });
      form.reset();
      setNotice("تم إنشاء المفهوم كمسودة.");
      await loadConcepts();
    } catch (error) {
      setFormError(errorMessage(error, "تعذر إنشاء المفهوم."));
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) {
      return;
    }
    const values = new FormData(event.currentTarget);
    const price = Number(values.get("price") ?? 0);
    const cost = Number(values.get("cost") ?? 0);
    setFormError(null);
    setNotice(null);

    if (!Number.isFinite(price) || price <= 0) {
      setFormError("السعر يجب أن يكون أكبر من صفر.");
      return;
    }
    if (!Number.isFinite(cost) || cost < 0) {
      setFormError("التكلفة يجب ألا تكون سالبة.");
      return;
    }

    try {
      await apiFetch<Concept>(`/product-concepts/${editing.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: String(values.get("name") ?? ""),
          description: String(values.get("description") ?? ""),
          price_minor: Math.round(price * 100),
          cost_minor: Math.round(cost * 100),
          currency: String(values.get("currency") ?? editing.currency),
          version: editing.version,
        }),
      });
      setEditing(null);
      setNotice("تم حفظ التعديلات.");
      await loadConcepts();
    } catch (error) {
      setFormError(
        errorMessage(error, "تعذر حفظ التعديلات. قد تكون النسخة قديمة."),
      );
    }
  }

  async function archive(concept: Concept) {
    setFormError(null);
    setNotice(null);
    try {
      await apiFetch<Concept>(`/product-concepts/${concept.id}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: concept.version }),
      });
      setNotice("تم أرشفة المفهوم.");
      await loadConcepts();
    } catch (error) {
      setFormError(errorMessage(error, "تعذر أرشفة المفهوم."));
    }
  }

  async function unarchive(concept: Concept) {
    setFormError(null);
    setNotice(null);
    try {
      await apiFetch<Concept>(`/product-concepts/${concept.id}/unarchive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: concept.version }),
      });
      setNotice("تمت استعادة المفهوم.");
      await loadConcepts();
    } catch (error) {
      setFormError(errorMessage(error, "تعذر استعادة المفهوم."));
    }
  }

  async function remove(concept: Concept) {
    if (!window.confirm(`حذف المفهوم «${concept.name}» نهائياً؟`)) {
      return;
    }
    setFormError(null);
    setNotice(null);
    try {
      await apiFetch<void>(`/product-concepts/${concept.id}`, {
        method: "DELETE",
      });
      setNotice("تم حذف المفهوم.");
      await loadConcepts();
    } catch (error) {
      setFormError(
        errorMessage(
          error,
          "تعذر حذف المفهوم. المفاهيم التي تم تقييمها يجب أرشفتها.",
        ),
      );
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">المفاهيم</h1>
          <p className="mt-1 text-sm text-zinc-500">
            أنشئ مفاهيم المنتجات وأدر دورة حياتها قبل الانتقال إلى التقييم
            والاختبار.
          </p>
        </div>

        {formError ? (
          <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {formError}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className="rounded-md bg-green-50 p-3 text-sm text-green-700">
            {notice}
          </p>
        ) : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">إنشاء مفهوم</h2>
          <form onSubmit={handleCreate} className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="name">
                الاسم
              </label>
              <input id="name" name="name" required className={fieldClass} />
            </div>
            <div>
              <label className={labelClass} htmlFor="description">
                الوصف
              </label>
              <input
                id="description"
                name="description"
                required
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="category_id">
                الفئة
              </label>
              <select
                id="category_id"
                name="category_id"
                required
                className={fieldClass}
                defaultValue=""
              >
                <option value="" disabled>
                  اختر فئة
                </option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="currency">
                العملة
              </label>
              <input
                id="currency"
                name="currency"
                defaultValue="USD"
                maxLength={3}
                dir="ltr"
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="price">
                السعر
              </label>
              <input
                id="price"
                name="price"
                type="number"
                min="0.01"
                step="0.01"
                required
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="cost">
                التكلفة
              </label>
              <input
                id="cost"
                name="cost"
                type="number"
                min="0"
                step="0.01"
                required
                className={fieldClass}
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={creating}
                className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {creating ? "جارٍ الحفظ…" : "حفظ كمسودة"}
              </button>
            </div>
          </form>
        </section>

        {editing ? (
          <section className="rounded-lg border border-amber-300 bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-base font-semibold">
                تعديل «{editing.name}» (النسخة {editing.version})
              </h2>
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
              >
                إلغاء
              </button>
            </div>
            <form
              key={`${editing.id}-${editing.version}`}
              onSubmit={handleEdit}
              className="mt-4 grid gap-4 md:grid-cols-2"
            >
              <div>
                <label className={labelClass} htmlFor="edit-name">
                  الاسم
                </label>
                <input
                  id="edit-name"
                  name="name"
                  required
                  defaultValue={editing.name}
                  className={fieldClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="edit-description">
                  الوصف
                </label>
                <input
                  id="edit-description"
                  name="description"
                  required
                  defaultValue={editing.description ?? ""}
                  className={fieldClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="edit-currency">
                  العملة
                </label>
                <input
                  id="edit-currency"
                  name="currency"
                  defaultValue={editing.currency}
                  maxLength={3}
                  dir="ltr"
                  className={fieldClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="edit-price">
                  السعر
                </label>
                <input
                  id="edit-price"
                  name="price"
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  defaultValue={(editing.price_minor / 100).toFixed(2)}
                  className={fieldClass}
                />
              </div>
              <div>
                <label className={labelClass} htmlFor="edit-cost">
                  التكلفة
                </label>
                <input
                  id="edit-cost"
                  name="cost"
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  defaultValue={(editing.cost_minor / 100).toFixed(2)}
                  className={fieldClass}
                />
              </div>
              <div className="flex items-end">
                <button
                  type="submit"
                  className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
                >
                  حفظ التعديلات
                </button>
              </div>
            </form>
          </section>
        ) : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">قائمة المفاهيم</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            <div className="md:col-span-2">
              <label className={labelClass} htmlFor="search">
                البحث
              </label>
              <input
                id="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="ابحث بالاسم أو الوصف"
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="status-filter">
                الحالة
              </label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className={fieldClass}
              >
                <option value="">كل الحالات</option>
                {CONCEPT_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {statusLabel(status)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="category-filter">
                الفئة
              </label>
              <select
                id="category-filter"
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
                className={fieldClass}
              >
                <option value="">كل الفئات</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="created-from">
                من تاريخ
              </label>
              <input
                id="created-from"
                type="date"
                value={createdFrom}
                onChange={(event) => setCreatedFrom(event.target.value)}
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="created-to">
                إلى تاريخ
              </label>
              <input
                id="created-to"
                type="date"
                value={createdTo}
                onChange={(event) => setCreatedTo(event.target.value)}
                className={fieldClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="sort">
                الترتيب حسب
              </label>
              <select
                id="sort"
                value={sort}
                onChange={(event) => setSort(event.target.value)}
                className={fieldClass}
              >
                {SORT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="direction">
                الاتجاه
              </label>
              <select
                id="direction"
                value={direction}
                onChange={(event) => setDirection(event.target.value)}
                className={fieldClass}
              >
                <option value="desc">تنازلي</option>
                <option value="asc">تصاعدي</option>
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => void loadConcepts()}
                className="rounded-md border border-zinc-300 px-3 py-2 text-sm"
              >
                تحديث
              </button>
            </div>
          </div>

          {loading ? (
            <p className="mt-4 text-sm text-zinc-500">جارٍ التحميل…</p>
          ) : null}
          {listError ? (
            <p className="mt-4 text-sm text-red-700">{listError}</p>
          ) : null}
          {!loading && !listError && concepts.length === 0 ? (
            <p className="mt-4 text-sm text-zinc-500">لا توجد مفاهيم مطابقة.</p>
          ) : null}
          {!loading && !listError && concepts.length > 0 ? (
            <ul className="mt-4 divide-y divide-zinc-200">
              {concepts.map((concept) => (
                <li
                  key={concept.id}
                  className="flex flex-wrap items-start justify-between gap-3 py-4"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{concept.name}</p>
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-700">
                        {statusLabel(concept.status)}
                      </span>
                      {concept.is_negative_margin ? (
                        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                          هامش سالب
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm text-zinc-600">
                      {concept.description}
                    </p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {categoryNames.get(concept.category_id) ?? concept.category_id}
                      {" • "}
                      {formatMoney(concept.price_minor, concept.currency)}
                      {" • "}
                      هامش {concept.gross_margin_percent.toFixed(1)}%
                      {" • "}
                      الدرجة {formatScore(concept)}
                      {" • "}
                      {formatDate(concept.created_at)}
                      {" • "}
                      النسخة {concept.version}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {concept.status === "draft" ? (
                      <button
                        type="button"
                        onClick={() => setEditing(concept)}
                        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                      >
                        تعديل
                      </button>
                    ) : null}
                    {concept.status === "archived" ? (
                      <button
                        type="button"
                        onClick={() => void unarchive(concept)}
                        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                      >
                        استعادة
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void archive(concept)}
                        className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
                      >
                        أرشفة
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void remove(concept)}
                      className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-700"
                    >
                      حذف
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </AppShell>
  );
}
