"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "ar" | "en";

const STORAGE_KEY = "msq_locale";
let activeLocale: Locale = "ar";

const MESSAGES = {
  ar: {
    __unavailable: "غير متاح",
    "common.error": "حدث خطأ. حاول مرة أخرى.",
    "common.retry": "حاول مرة أخرى",
    "common.loading": "جارٍ التحميل...",
    "common.save": "حفظ",
    "common.cancel": "إلغاء",
    "nav.label": "التنقل الرئيسي",
    "nav.dashboard": "لوحة التحكم",
    "nav.imports": "الاستيراد",
    "nav.audiences": "الجمهور",
    "nav.feedback": "ملاحظات العملاء",
    "nav.concepts": "المفاهيم",
    "nav.evaluations": "التقييم",
    "nav.compare": "المقارنة",
    "nav.recommendations": "التوصيات",
    "nav.landingPages": "الصفحات",
    "nav.campaigns": "الحملات",
    "nav.connections": "الاتصالات",
    "nav.operations": "العمليات",
    "nav.metrics": "المؤشرات",
    "nav.verdicts": "أحكام الاختبار",
    "nav.investment": "الاستثمار",
    "nav.settings": "الإعدادات",
    "app.subtitle": "حلقة تحسين الإعلانات",
    "app.logout": "تسجيل الخروج",
    "app.loggingOut": "جارٍ الخروج...",
    "shell.tagline": "حلقة تحسين الإعلانات",
    "shell.logout": "تسجيل الخروج",
    "shell.loggingOut": "جارٍ الخروج...",
    "locale.switch": "English",
    "language.label": "اللغة",
    "language.arabic": "العربية",
    "language.english": "English",
    "home.title": "لا توجد بيانات بعد",
    "home.body": "ابدأ بإنشاء حملة إعلانية لتسجيل الإشارات وتحليلها.",
    "home.cta": "الانتقال إلى الحملات",
    "login.title": "تسجيل الدخول",
    "login.subtitle": "أدخل بيانات حسابك للوصول إلى متجرك.",
    "login.email": "البريد الإلكتروني",
    "login.password": "كلمة المرور",
    "login.submit": "تسجيل الدخول",
    "login.submitting": "جارٍ تسجيل الدخول...",
    "login.retry": "حاول بعد {seconds} ثانية",
    "login.invalid": "البريد الإلكتروني أو كلمة المرور غير صحيحة.",
    "login.unverified": "تحقق من بريدك الإلكتروني قبل تسجيل الدخول.",
    "login.resend": "إعادة إرسال رسالة التحقق",
    "login.resending": "جارٍ الإرسال...",
    "login.resent": "تم إرسال رسالة تحقق جديدة.",
    "login.rateLimited": "محاولات كثيرة. حاول لاحقًا.",
    "login.generic": "تعذر تسجيل الدخول. حاول مرة أخرى.",
    "login.network": "تعذر الوصول إلى الخادم. حاول مرة أخرى.",
    "login.forgot": "نسيت كلمة المرور؟",
    "login.create": "إنشاء حساب",
    "login.createAccount": "إنشاء حساب",
    "login.noAccount": "ليس لديك حساب؟",
    "login.emailRequired": "البريد الإلكتروني مطلوب.",
    "login.passwordRequired": "كلمة المرور مطلوبة.",
    "signup.title": "إنشاء حساب جديد",
    "signup.subtitle": "أنشئ حسابك للبدء في إعداد متجرك.",
    "signup.email": "البريد الإلكتروني",
    "signup.password": "كلمة المرور",
    "signup.confirm": "تأكيد كلمة المرور",
    "signup.hint": "12 حرفًا على الأقل.",
    "signup.submit": "إنشاء الحساب",
    "signup.submitting": "جارٍ إنشاء الحساب...",
    "signup.haveAccount": "لديك حساب بالفعل؟",
    "signup.login": "تسجيل الدخول",
    "signup.successTitle": "تحقق من بريدك الإلكتروني",
    "signup.successBody": "أرسلنا رسالة تحقق إلى {email}. افتح الرابط لتفعيل حسابك، ثم سجّل الدخول.",
    "signup.resend": "إعادة إرسال رسالة التحقق",
    "signup.resending": "جارٍ الإرسال...",
    "signup.resent": "تم إرسال رسالة تحقق جديدة.",
    "signup.goLogin": "الانتقال إلى تسجيل الدخول",
    "signup.emailRequired": "البريد الإلكتروني مطلوب.",
    "signup.emailInvalid": "أدخل بريدًا إلكترونيًا صالحًا.",
    "signup.passwordRequired": "كلمة المرور مطلوبة.",
    "signup.passwordShort": "يجب أن تكون كلمة المرور 12 حرفًا على الأقل.",
    "signup.confirmRequired": "تأكيد كلمة المرور مطلوب.",
    "signup.passwordMismatch": "كلمتا المرور غير متطابقتين.",
    "forgot.title": "استعادة كلمة المرور",
    "forgot.subtitle": "أدخل بريدك الإلكتروني وسنرسل رابط إعادة التعيين إذا كان الحساب موجودًا.",
    "forgot.email": "البريد الإلكتروني",
    "forgot.submit": "إرسال رابط الاستعادة",
    "forgot.submitting": "جارٍ الإرسال…",
    "forgot.success": "إذا كان البريد مسجلًا فستصل رسالة إعادة التعيين قريبًا.",
    "forgot.back": "العودة لتسجيل الدخول",
    "onboarding.step": "الخطوة الأولى",
    "onboarding.title": "أنشئ متجرك الأول",
    "onboarding.subtitle": "أدخل بيانات المتجر الأساسية. يمكنك تعديلها لاحقًا.",
    "onboarding.name": "اسم المتجر",
    "onboarding.currency": "العملة",
    "onboarding.language": "اللغة",
    "onboarding.timezone": "المنطقة الزمنية",
    "onboarding.country": "الدولة",
    "onboarding.submit": "إنشاء المتجر والمتابعة",
    "onboarding.submitting": "جارٍ إنشاء المتجر...",
    "onboarding.nameRequired": "اسم المتجر مطلوب.",
    "onboarding.sessionExpired": "انتهت صلاحية الجلسة أو رمز الحماية. يرجى تسجيل الدخول مرة أخرى.",
    "onboarding.loginAgain": "تسجيل الدخول من جديد",
    "onboarding.failed": "تعذر إنشاء المتجر. حاول مرة أخرى.",
    "settings.title": "إعدادات المتجر",
    "settings.subtitle": "اختر العملة التي تظهر بها الأسعار والميزانيات.",
    "settings.currency": "العملة",
    "settings.save": "حفظ العملة",
    "settings.saving": "جارٍ الحفظ...",
    "settings.saved": "تم حفظ العملة.",
    "settings.csrfExpired": "انتهت صلاحية الجلسة. يرجى تسجيل الدخول مرة أخرى.",
  },
  en: {
    __unavailable: "Unavailable",
    "common.error": "Something went wrong. Try again.",
    "common.retry": "Try again",
    "common.loading": "Loading...",
    "common.save": "Save",
    "common.cancel": "Cancel",
    "nav.label": "Main navigation",
    "nav.dashboard": "Dashboard",
    "nav.imports": "Imports",
    "nav.audiences": "Audiences",
    "nav.feedback": "Customer feedback",
    "nav.concepts": "Concepts",
    "nav.evaluations": "Evaluations",
    "nav.compare": "Compare",
    "nav.recommendations": "Recommendations",
    "nav.landingPages": "Landing pages",
    "nav.campaigns": "Campaigns",
    "nav.connections": "Connections",
    "nav.operations": "Operations",
    "nav.metrics": "Metrics",
    "nav.verdicts": "Verdict KPIs",
    "nav.investment": "Investment",
    "nav.settings": "Settings",
    "app.subtitle": "Advertising optimization loop",
    "app.logout": "Log out",
    "app.loggingOut": "Logging out...",
    "shell.tagline": "Advertising optimization loop",
    "shell.logout": "Log out",
    "shell.loggingOut": "Logging out...",
    "locale.switch": "العربية",
    "language.label": "Language",
    "language.arabic": "العربية",
    "language.english": "English",
    "home.title": "No data yet",
    "home.body": "Start by creating an advertising campaign to record and analyze signals.",
    "home.cta": "Go to campaigns",
    "login.title": "Log in",
    "login.subtitle": "Enter your account details to access your store.",
    "login.email": "Email address",
    "login.password": "Password",
    "login.submit": "Log in",
    "login.submitting": "Logging in...",
    "login.retry": "Try again in {seconds}s",
    "login.invalid": "Invalid email or password.",
    "login.unverified": "Verify your email before signing in.",
    "login.resend": "Resend verification email",
    "login.resending": "Sending...",
    "login.resent": "A new verification email was sent.",
    "login.rateLimited": "Too many attempts. Try again later.",
    "login.generic": "Unable to sign in. Try again.",
    "login.network": "Cannot reach the server. Try again.",
    "login.forgot": "Forgot password?",
    "login.create": "Create account",
    "login.createAccount": "Create account",
    "login.noAccount": "Don’t have an account?",
    "login.emailRequired": "Email is required.",
    "login.passwordRequired": "Password is required.",
    "signup.title": "Create a new account",
    "signup.subtitle": "Create your account to start setting up your store.",
    "signup.email": "Email address",
    "signup.password": "Password",
    "signup.confirm": "Confirm password",
    "signup.hint": "At least 12 characters.",
    "signup.submit": "Create account",
    "signup.submitting": "Creating account...",
    "signup.haveAccount": "Already have an account?",
    "signup.login": "Log in",
    "signup.successTitle": "Check your email",
    "signup.successBody": "We sent a verification message to {email}. Open the link to activate your account, then log in.",
    "signup.resend": "Resend verification email",
    "signup.resending": "Sending...",
    "signup.resent": "A new verification email was sent.",
    "signup.goLogin": "Go to login",
    "signup.emailRequired": "Email is required.",
    "signup.emailInvalid": "Enter a valid email address.",
    "signup.passwordRequired": "Password is required.",
    "signup.passwordShort": "Password must be at least 12 characters.",
    "signup.confirmRequired": "Password confirmation is required.",
    "signup.passwordMismatch": "Passwords do not match.",
    "forgot.title": "Reset password",
    "forgot.subtitle": "Enter your email and we will send a reset link if the account exists.",
    "forgot.email": "Email",
    "forgot.submit": "Send reset link",
    "forgot.submitting": "Sending…",
    "forgot.success": "If the email is registered, a reset link will arrive shortly.",
    "forgot.back": "Back to sign in",
    "onboarding.step": "First step",
    "onboarding.title": "Create your first store",
    "onboarding.subtitle": "Enter your store details. You can change them later.",
    "onboarding.name": "Store name",
    "onboarding.currency": "Currency",
    "onboarding.language": "Language",
    "onboarding.timezone": "Timezone",
    "onboarding.country": "Country",
    "onboarding.submit": "Create store and continue",
    "onboarding.submitting": "Creating store...",
    "onboarding.nameRequired": "Store name is required.",
    "onboarding.sessionExpired": "Your session or security token expired. Please log in again.",
    "onboarding.loginAgain": "Log in again",
    "onboarding.failed": "Could not create the store. Try again.",
    "settings.title": "Store settings",
    "settings.subtitle": "Choose the currency used for prices and budgets.",
    "settings.currency": "Currency",
    "settings.save": "Save currency",
    "settings.saving": "Saving...",
    "settings.saved": "Currency saved.",
    "settings.csrfExpired": "Your session expired. Please log in again.",
  },
} as const;

export type MessageKey = keyof (typeof MESSAGES)["ar"];

export function getLocale(): Locale {
  return activeLocale;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat(activeLocale === "ar" ? "ar" : "en-GB", {
    dateStyle: "medium",
  }).format(parsed);
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions) {
  return new Intl.NumberFormat(activeLocale === "ar" ? "ar" : "en-GB", options).format(
    value,
  );
}

const MINOR_UNITS: Record<string, number> = {
  SAR: 2,
  ILS: 2,
  USD: 2,
  EUR: 2,
  JPY: 0,
  KWD: 3,
  BHD: 3,
  JOD: 3,
  OMR: 3,
};

export function formatCurrency(minor: number, currency: string): string {
  return new Intl.NumberFormat(activeLocale === "ar" ? "ar" : "en-GB", {
    style: "currency",
    currency,
  }).format(minor / 10 ** (MINOR_UNITS[currency] ?? 2));
}

type LanguageContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, values?: Record<string, string | number>) => string;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function storedLocale(): Locale {
  if (typeof window === "undefined") return "ar";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "ar") return stored;
  return document.documentElement.lang === "en" ? "en" : "ar";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("ar");

  useEffect(() => {
    const initial = storedLocale();
    activeLocale = initial;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocaleState(initial);
    document.documentElement.lang = initial;
    document.documentElement.dir = initial === "ar" ? "rtl" : "ltr";
  }, []);

  const setLocale = useCallback((next: Locale) => {
    activeLocale = next;
    setLocaleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    document.cookie = `msq_locale=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
  }, []);

  const t = useCallback(
    (key: MessageKey, values?: Record<string, string | number>) => {
      let template: string = MESSAGES[locale][key] ?? MESSAGES.ar[key];
      if (template === undefined) {
        console.warn("[i18n] missing translation", { locale, key });
        template = MESSAGES[locale].__unavailable;
      }
      if (!values) return template;
      return Object.entries(values).reduce(
        (text, [name, value]) =>
          text.replaceAll(`{${name}}`, String(value)),
        template,
      );
    },
    [locale],
  );

  const value = useMemo(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );
  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (context) return context;
  return {
    locale: "ar",
    setLocale: () => undefined,
    t: (key: MessageKey, values?: Record<string, string | number>) => {
      const template: string = MESSAGES.ar[key] ?? MESSAGES.ar.__unavailable;
      if (!values) return template;
      return Object.entries(values).reduce<string>(
        (text, [name, value]) =>
          text.replaceAll(`{${name}}`, String(value)),
        template,
      );
    },
  };
}

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useLanguage();
  return (
    <div
      role="group"
      aria-label={t("language.label")}
      className="inline-flex rounded-md border border-zinc-300 bg-white p-0.5"
    >
      <button
        type="button"
        onClick={() => setLocale("ar")}
        aria-pressed={locale === "ar"}
        className={`rounded px-2.5 py-1.5 text-sm font-semibold ${
          locale === "ar" ? "bg-zinc-900 text-white" : "text-zinc-700"
        }`}
      >
        {t("language.arabic")}
      </button>
      <button
        type="button"
        onClick={() => setLocale("en")}
        aria-pressed={locale === "en"}
        className={`rounded px-2.5 py-1.5 text-sm font-semibold ${
          locale === "en" ? "bg-zinc-900 text-white" : "text-zinc-700"
        }`}
      >
        {t("language.english")}
      </button>
    </div>
  );
}

export const LocaleProvider = LanguageProvider;
export const useI18n = useLanguage;
export const LocaleSwitcher = LanguageSwitcher;
