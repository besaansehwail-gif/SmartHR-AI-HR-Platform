import { Dictionary } from '../types';

/**
 * The shared presentational components in `components/ui/` - the states,
 * tables, modals and pagination every page reuses.
 *
 * These pay for themselves: translating `LoadingState` once translates the
 * loading state of forty screens, which is why the shared components were
 * worth doing before any individual page.
 */
export const ui: Dictionary = {
  // --- States ------------------------------------------------------------
  'ui.loading': { en: 'Loading', ar: 'جارٍ التحميل' },
  'ui.loadingDescription': {
    en: 'Fetching the latest records…',
    ar: 'جارٍ جلب أحدث السجلات…',
  },
  'ui.errorTitle': { en: 'Something went wrong', ar: 'حدث خطأ ما' },
  'ui.forbiddenTitle': { en: 'Access restricted', ar: 'الوصول مقيّد' },
  'ui.offlineTitle': { en: 'Cannot reach the server', ar: 'تعذّر الوصول إلى الخادم' },
  'ui.tryAgain': { en: 'Try again', ar: 'إعادة المحاولة' },

  // --- Table -------------------------------------------------------------

  // --- Pagination --------------------------------------------------------

  // --- Modal / dialog ----------------------------------------------------
  'ui.modal.close': { en: 'Close dialog', ar: 'إغلاق النافذة' },

  // --- Form --------------------------------------------------------------
  'ui.form.optional': { en: 'Optional', ar: 'اختياري' },
  'ui.form.required': { en: 'Required', ar: 'مطلوب' },

  // --- Charts ------------------------------------------------------------

  // --- Attention centre (every dashboard) --------------------------------
  'ui.attention.title': { en: 'Attention Center', ar: 'مركز الاهتمام' },
  'ui.attention.acknowledge': { en: 'Acknowledge', ar: 'إقرار' },

  // --- Data-availability notices (the schema-cannot-answer cases) --------

  // --- Pagination (aria) ---------------------------------------------------
  'ui.pagination.label': { en: 'Pagination', ar: 'ترقيم الصفحات' },
  'ui.pagination.previousPage': { en: 'Previous page', ar: 'الصفحة السابقة' },
  'ui.pagination.nextPage': { en: 'Next page', ar: 'الصفحة التالية' },

  // --- Search input --------------------------------------------------------
  'ui.search.placeholder': { en: 'Search…', ar: 'بحث…' },
  'ui.search.label': { en: 'Search', ar: 'بحث' },
  'ui.search.clear': { en: 'Clear search', ar: 'مسح البحث' },

  // --- Breadcrumbs ---------------------------------------------------------
  'ui.breadcrumb.label': { en: 'Breadcrumb', ar: 'مسار التنقل' },
  'ui.breadcrumb.home': { en: 'Workspace home', ar: 'الصفحة الرئيسية لمساحة العمل' },

  // --- Toast ---------------------------------------------------------------
  'ui.toast.dismiss': { en: 'Dismiss notification', ar: 'إخفاء الإشعار' },

  // --- Charts (empty states and work-mode legend) -------------------------
  'ui.chart.noDepartments': {
    en: 'No departments with employees yet.',
    ar: 'لا توجد أقسام بها موظفون بعد.',
  },
  'ui.chart.noPipeline': {
    en: 'No applications in the pipeline.',
    ar: 'لا توجد طلبات في مسار التوظيف.',
  },
  'ui.chart.nothingYet': { en: 'Nothing to show yet.', ar: 'لا يوجد ما يُعرض بعد.' },

  // --- Badges --------------------------------------------------------------
  'badge.workMode.remote': { en: 'Remote', ar: 'عن بُعد' },
  'badge.workMode.hybrid': { en: 'Hybrid', ar: 'هجين' },
  'badge.workMode.onsite': { en: 'On-site', ar: 'من المقر' },
  'badge.status.Active': { en: 'Active', ar: 'نشط' },
  'badge.status.Inactive': { en: 'Inactive', ar: 'غير نشط' },
  'badge.status.Pending': { en: 'Pending', ar: 'قيد الانتظار' },
  'badge.status.Suspended': { en: 'Suspended', ar: 'موقوف' },
  'badge.status.Restructuring': { en: 'Restructuring', ar: 'قيد إعادة الهيكلة' },
  'badge.status.Draft': { en: 'Draft', ar: 'مسودة' },
  'badge.status.Archived': { en: 'Archived', ar: 'مؤرشف' },
  'badge.action.CREATE': { en: 'CREATE', ar: 'إنشاء' },
  'badge.action.UPDATE': { en: 'UPDATE', ar: 'تعديل' },
  'badge.action.DELETE': { en: 'DELETE', ar: 'حذف' },
  'badge.action.APPROVE': { en: 'APPROVE', ar: 'موافقة' },
  'badge.action.SECURITY': { en: 'SECURITY', ar: 'أمان' },
  'badge.action.EXPORT': { en: 'EXPORT', ar: 'تصدير' },
  'badge.action.LOGIN': { en: 'LOGIN', ar: 'تسجيل دخول' },

  'ui.pagination.showing': { en: 'Showing', ar: 'عرض' },
  'ui.pagination.of': { en: 'of', ar: 'من' },
  'ui.pagination.records': { en: 'records', ar: 'سجلًا' },
};
