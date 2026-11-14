export type SignupFields = {
  email: string;
  password: string;
  confirmPassword: string;
};

export type SignupErrors = Partial<Record<keyof SignupFields, string>>;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MIN_PASSWORD_LENGTH = 12;

export function validateSignup(
  fields: SignupFields,
  locale: "ar" | "en" = "ar",
): SignupErrors {
  const errors: SignupErrors = {};
  const text =
    locale === "en"
      ? {
          emailRequired: "Email is required.",
          emailInvalid: "Enter a valid email address.",
          passwordRequired: "Password is required.",
          passwordShort: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
          confirmRequired: "Password confirmation is required.",
          passwordMismatch: "Passwords do not match.",
        }
      : {
          emailRequired: "البريد الإلكتروني مطلوب.",
          emailInvalid: "أدخل بريدًا إلكترونيًا صالحًا.",
          passwordRequired: "كلمة المرور مطلوبة.",
          passwordShort: `يجب أن تكون كلمة المرور ${MIN_PASSWORD_LENGTH} حرفًا على الأقل.`,
          confirmRequired: "تأكيد كلمة المرور مطلوب.",
          passwordMismatch: "كلمتا المرور غير متطابقتين.",
        };

  if (!fields.email.trim()) {
    errors.email = text.emailRequired;
  } else if (!EMAIL_PATTERN.test(fields.email.trim())) {
    errors.email = text.emailInvalid;
  }

  if (!fields.password) {
    errors.password = text.passwordRequired;
  } else if (fields.password.length < MIN_PASSWORD_LENGTH) {
    errors.password = text.passwordShort;
  }

  if (!fields.confirmPassword) {
    errors.confirmPassword = text.confirmRequired;
  } else if (fields.password !== fields.confirmPassword) {
    errors.confirmPassword = text.passwordMismatch;
  }

  return errors;
}

export function hasErrors(errors: SignupErrors): boolean {
  return Object.keys(errors).length > 0;
}
