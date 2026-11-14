"use client";

import { useEffect, useState, type FormEvent } from "react";

import { AppShell } from "@/components/app-shell";
import { ApiError, apiFetch } from "@/lib/api";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm outline-none focus:border-zinc-900";
const labelClass = "block text-sm font-medium text-zinc-700";

type Category = { id: string; name: string };
type Niche = { id: string; name: string; category_id: string };
type Segment = {
  id: string;
  label: string;
  locations: unknown[];
  age_min: number;
  age_max: number;
  interests: string[];
  languages: string[];
};
type Profile = {
  id: string;
  version: number;
  status: string;
  is_current: boolean;
  niche_ids: string[];
  languages: string[];
  notes: string | null;
  segments: Segment[];
};

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export default function AudiencesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [niches, setNiches] = useState<Niche[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const [nicheId, setNicheId] = useState("");
  const [languages, setLanguages] = useState("ar,en");
  const [notes, setNotes] = useState("");
  const [segmentLabel, setSegmentLabel] = useState("Core");
  const [locations, setLocations] = useState("SA");
  const [ageMin, setAgeMin] = useState("18");
  const [ageMax, setAgeMax] = useState("45");
  const [interests, setInterests] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch<Category[]>("/categories"),
      apiFetch<Profile>("/audience-profiles/current").catch(() => null),
    ])
      .then(([categoryData, profileData]) => {
        if (!active) return;
        setCategories(categoryData);
        setCategoryId(categoryData[0]?.id ?? "");
        setProfile(profileData);
      })
      .catch((loadError) => {
        if (active) setError(errorMessage(loadError, "تعذر تحميل الجمهور."));
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!categoryId) return;
    let active = true;
    apiFetch<Niche[]>(`/niches?category_id=${categoryId}`)
      .then((data) => {
        if (active) {
          setNiches(data);
          setNicheId(data[0]?.id ?? "");
        }
      })
      .catch(() => {
        if (active) setNiches([]);
      });
    return () => {
      active = false;
    };
  }, [categoryId]);

  async function reloadProfile() {
    try {
      setProfile(await apiFetch<Profile>("/audience-profiles/current"));
    } catch {
      setProfile(null);
    }
  }

  async function createProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch<Profile>("/audience-profiles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          niche_ids: nicheId ? [nicheId] : [],
          languages: languages.split(",").map((item) => item.trim()).filter(Boolean),
          notes: notes || null,
        }),
      });
      await reloadProfile();
      setNotice("تم إنشاء ملف الجمهور.");
    } catch (createError) {
      setError(errorMessage(createError, "تعذر إنشاء ملف الجمهور."));
    } finally {
      setBusy(false);
    }
  }

  async function addSegment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const segments = [
        ...profile.segments.map((segment) => ({
          label: segment.label,
          locations: segment.locations,
          age_min: segment.age_min,
          age_max: segment.age_max,
          interests: segment.interests,
          languages: segment.languages,
        })),
        {
          label: segmentLabel,
          locations: locations.split(",").map((item) => item.trim()).filter(Boolean),
          age_min: Number(ageMin),
          age_max: Number(ageMax),
          genders: [],
          interests: interests.split(",").map((item) => item.trim()).filter(Boolean),
          languages: [],
        },
      ];
      await apiFetch(`/audience-profiles/${profile.id}/segments`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segments }),
      });
      await reloadProfile();
      setNotice("تم حفظ الشريحة.");
    } catch (segmentError) {
      setError(errorMessage(segmentError, "تعذر حفظ الشريحة."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">الجمهور</h1>
          <p className="mt-1 text-sm text-zinc-500">
            أنشئ ملف الجمهور وشرائحه المستخدمة في التقييم والتوصيات.
          </p>
        </div>
        {error ? <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
        {notice ? <p role="status" className="rounded-md bg-green-50 p-3 text-sm text-green-700">{notice}</p> : null}

        <section className="rounded-lg border border-zinc-200 bg-white p-5">
          <h2 className="text-base font-semibold">ملف الجمهور</h2>
          {profile ? (
            <div className="mt-3 space-y-2 text-sm">
              <p>الإصدار: {profile.version} • الحالة: {profile.status}</p>
              <p>اللغات: {profile.languages.join(", ") || "—"}</p>
              <p>الملاحظات: {profile.notes || "—"}</p>
              <ul className="mt-3 space-y-2">
                {profile.segments.map((segment) => (
                  <li key={segment.id} className="rounded-md bg-zinc-50 p-3">
                    {segment.label} • {segment.age_min}-{segment.age_max}
                    {" • "}
                    {segment.locations.map(String).join(", ") || "بدون مواقع"}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="mt-3 text-sm text-zinc-500">لا يوجد ملف جمهور حالي.</p>
          )}
          <form onSubmit={createProfile} className="mt-4 grid gap-4 md:grid-cols-2">
            <div>
              <label className={labelClass} htmlFor="audience-category">الفئة</label>
              <select id="audience-category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)} className={fieldClass}>
                {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="audience-niche">النيتش</label>
              <select id="audience-niche" value={nicheId} onChange={(event) => setNicheId(event.target.value)} className={fieldClass}>
                {niches.map((niche) => <option key={niche.id} value={niche.id}>{niche.name}</option>)}
              </select>
            </div>
            <div>
              <label className={labelClass} htmlFor="audience-languages">اللغات</label>
              <input id="audience-languages" value={languages} onChange={(event) => setLanguages(event.target.value)} className={fieldClass} />
            </div>
            <div>
              <label className={labelClass} htmlFor="audience-notes">ملاحظات</label>
              <input id="audience-notes" value={notes} onChange={(event) => setNotes(event.target.value)} className={fieldClass} />
            </div>
            <div className="flex items-end">
              <button type="submit" disabled={busy || !nicheId} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                إنشاء ملف جديد
              </button>
            </div>
          </form>
        </section>

        {profile ? (
          <section className="rounded-lg border border-zinc-200 bg-white p-5">
            <h2 className="text-base font-semibold">إضافة شريحة</h2>
            <form onSubmit={addSegment} className="mt-4 grid gap-4 md:grid-cols-3">
              <div><label className={labelClass} htmlFor="segment-label">الاسم</label><input id="segment-label" value={segmentLabel} onChange={(event) => setSegmentLabel(event.target.value)} className={fieldClass} /></div>
              <div><label className={labelClass} htmlFor="segment-locations">المواقع</label><input id="segment-locations" value={locations} onChange={(event) => setLocations(event.target.value)} className={fieldClass} /></div>
              <div><label className={labelClass} htmlFor="segment-interests">الاهتمامات</label><input id="segment-interests" value={interests} onChange={(event) => setInterests(event.target.value)} className={fieldClass} /></div>
              <div><label className={labelClass} htmlFor="segment-age-min">العمر من</label><input id="segment-age-min" type="number" value={ageMin} onChange={(event) => setAgeMin(event.target.value)} className={fieldClass} /></div>
              <div><label className={labelClass} htmlFor="segment-age-max">العمر إلى</label><input id="segment-age-max" type="number" value={ageMax} onChange={(event) => setAgeMax(event.target.value)} className={fieldClass} /></div>
              <div className="flex items-end"><button type="submit" disabled={busy} className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">حفظ الشريحة</button></div>
            </form>
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
