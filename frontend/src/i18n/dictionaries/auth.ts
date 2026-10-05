import { Dictionary } from '../types';

/**
 * Sign-in and applicant registration - the two screens reachable without a
 * token, and therefore the only ones where the language switcher has to work
 * before there is a session to remember it in. It does: the preference lives
 * in localStorage, which is readable signed out.
 */
export const auth: Dictionary = {
  // --- Sign in -----------------------------------------------------------
  'auth.title': { en: 'SmartHR', ar: 'SmartHR' },
  'auth.signIn': { en: 'Sign In', ar: 'تسجيل الدخول' },

  // --- Applicant registration -------------------------------------------
  'register.title': { en: 'Create your applicant account', ar: 'أنشئ حساب المتقدّم' },
  'register.fullName': { en: 'Full name', ar: 'الاسم الكامل' },
  'register.fullNamePlaceholder': { en: 'Your full name', ar: 'اسمك الكامل' },
  'register.email': { en: 'Email', ar: 'البريد الإلكتروني' },
  'register.emailPlaceholder': { en: 'you@example.com', ar: 'you@example.com' },
  'register.password': { en: 'Password', ar: 'كلمة المرور' },
  'register.passwordHint': {
    en: 'At least 8 characters.',
    ar: 'ثمانية أحرف على الأقل.',
  },
  'register.submit': { en: 'Create account', ar: 'إنشاء الحساب' },
  'register.submitting': { en: 'Creating your account…', ar: 'جارٍ إنشاء حسابك…' },
  'register.haveAccount': { en: 'Already have an account?', ar: 'لديك حساب بالفعل؟' },
  'register.failed': {
    en: 'The account could not be created.',
    ar: 'تعذّر إنشاء الحساب.',
  },
  'register.staffNote': {
    en: 'This form creates job-seeker accounts only. Staff accounts are created by an administrator.',
    ar: 'هذا النموذج ينشئ حسابات الباحثين عن عمل فقط. أمّا حسابات الموظفين فيُنشئها مدير النظام.',
  },
};
