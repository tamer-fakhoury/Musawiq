import { getLocale } from "@/lib/i18n";

type Entry = { ar: string; en: string };

const ERROR_MESSAGES: Record<string, Entry> = {
  http_error: { ar: "تعذر إكمال الطلب.", en: "The request could not be completed." },
  validation_error: { ar: "بعض الحقول غير صالحة.", en: "Some fields are invalid." },
  unauthorized: { ar: "يجب تسجيل الدخول للمتابعة.", en: "Sign in to continue." },
  csrf_invalid: { ar: "انتهت صلاحية الجلسة. أعد المحاولة.", en: "Your session expired. Try again." },
  not_found: { ar: "العنصر غير موجود.", en: "The item was not found." },
  rate_limited: { ar: "محاولات كثيرة. حاول لاحقًا.", en: "Too many attempts. Try again later." },
  invalid_credentials: { ar: "البريد الإلكتروني أو كلمة المرور غير صحيحة.", en: "Invalid email or password." },
  email_unverified: { ar: "يجب تأكيد بريدك الإلكتروني أولًا.", en: "Verify your email first." },
  signup_failed: { ar: "تعذر إنشاء الحساب بهذه البيانات.", en: "Unable to create an account with these details." },
  weak_password: { ar: "كلمة المرور ضعيفة جدًا.", en: "The password is too weak." },
  invalid_email: { ar: "البريد الإلكتروني غير صالح.", en: "The email is invalid." },
  claim_rejected: { ar: "النص يحتوي على ادعاء غير مسموح.", en: "The copy contains a disallowed claim." },
  manual_edits_exist: { ar: "توجد تعديلات يدوية. أكد الاستبدال أولًا.", en: "Manual edits exist. Confirm replacement first." },
  publish_invalid: { ar: "لا يمكن النشر قبل إكمال المتطلبات.", en: "Publishing requirements are incomplete." },
  tracking_invalid: { ar: "معلمات التتبع غير صالحة.", en: "Tracking parameters are invalid." },
  budget_cap_exceeded: { ar: "الميزانية تتجاوز الحد المسموح.", en: "The budget exceeds the allowed cap." },
  gateway_not_supported: { ar: "بوابة الدفع غير مدعومة بعد.", en: "Payment gateway is not supported yet." },
  consent_required: { ar: "يلزم الحصول على الموافقة أولًا.", en: "Consent is required first." },
  page_unavailable: { ar: "هذه الصفحة غير متاحة.", en: "This page is unavailable." },
  handler_not_implemented: { ar: "هذه المهمة غير مدعومة بعد.", en: "This job is not supported yet." },
  ai_unavailable: { ar: "خدمة الذكاء الاصطناعي غير متاحة.", en: "The AI service is unavailable." },
  ai_invalid_output: { ar: "تعذر فهم نتيجة الذكاء الاصطناعي.", en: "The AI response could not be understood." },
  invalid_token: { ar: "الرابط غير صالح أو منتهي.", en: "The link is invalid or expired." },
  profile_required: { ar: "أكمل بيانات الاستثمار أولًا.", en: "Complete the investment profile first." },
  no_snapshot: { ar: "لا توجد لقطة نتائج بعد.", en: "No result snapshot exists yet." },
  rule_set_required: { ar: "اضبط قواعد القرار أولًا.", en: "Configure decision rules first." },
};

const FALLBACK: Entry = {
  ar: "تعذر إكمال الطلب.",
  en: "The request could not be completed.",
};

export function localizeApiError(code: string): string {
  const locale = getLocale();
  const entry = ERROR_MESSAGES[code];
  if (!entry) {
    console.warn("[i18n] missing API error translation", { code, locale });
    return FALLBACK[locale];
  }
  return entry[locale];
}
