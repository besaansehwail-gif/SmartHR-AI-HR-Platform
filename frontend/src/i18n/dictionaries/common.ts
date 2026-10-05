import { Dictionary } from '../types';

/**
 * Strings that appear on more than one screen: actions, states, table
 * furniture, validation, and the status vocabularies the backend uses.
 *
 * **Status tokens are translated for display only.** `applications.status`,
 * `jobs.status`, `interviews.status` and the rest stay exactly the English
 * tokens the API reads and writes - `status.stage.shortlisted` is what a
 * recruiter *sees*, never what is sent. Nothing here reaches a request body.
 */
export const common: Dictionary = {
  // --- Brand -------------------------------------------------------------
  'app.name': { en: 'SmartHR', ar: 'SmartHR' },
  'app.tagline': {
    en: 'People • Intelligence • Growth',
    ar: 'الأفراد • الذكاء • النمو',
  },
  'app.connected': { en: 'Connected to the SmartHR API', ar: 'متصل بواجهة SmartHR' },
  'app.skipToContent': { en: 'Skip to main content', ar: 'تخطٍ إلى المحتوى الرئيسي' },

  // --- Actions -----------------------------------------------------------
  'action.saveChanges': { en: 'Save changes', ar: 'حفظ التغييرات' },
  'action.cancel': { en: 'Cancel', ar: 'إلغاء' },
  'action.close': { en: 'Close', ar: 'إغلاق' },
  'action.delete': { en: 'Delete', ar: 'حذف' },
  'action.search': { en: 'Search', ar: 'بحث' },
  'action.retry': { en: 'Try again', ar: 'إعادة المحاولة' },
  'action.refresh': { en: 'Refresh', ar: 'تحديث' },
  'action.reject': { en: 'Reject', ar: 'رفض' },
  'action.signOut': { en: 'Sign out', ar: 'تسجيل الخروج' },

  // --- States ------------------------------------------------------------
  'state.loading': { en: 'Loading…', ar: 'جارٍ التحميل…' },
  'state.saving': { en: 'Saving…', ar: 'جارٍ الحفظ…' },
  'state.unknown': { en: 'Unknown', ar: 'غير معروف' },
  'state.error': { en: 'Something went wrong', ar: 'حدث خطأ ما' },

  // --- Table / list furniture -------------------------------------------
  'table.actions': { en: 'Actions', ar: 'الإجراءات' },
  'table.email': { en: 'Email', ar: 'البريد الإلكتروني' },
  'table.phone': { en: 'Phone', ar: 'الهاتف' },
  'table.status': { en: 'Status', ar: 'الحالة' },
  'table.department': { en: 'Department', ar: 'القسم' },
  'table.position': { en: 'Position', ar: 'المسمى الوظيفي' },
  'table.date': { en: 'Date', ar: 'التاريخ' },
  'table.createdAt': { en: 'Created', ar: 'تاريخ الإنشاء' },
  'table.location': { en: 'Location', ar: 'الموقع' },
  'table.rating': { en: 'Rating', ar: 'التقييم' },

  // --- Filters / search --------------------------------------------------

  // --- Validation --------------------------------------------------------

  // --- Feedback ----------------------------------------------------------

  // --- Confirmation ------------------------------------------------------

  // --- Language switcher -------------------------------------------------
  'language.label': { en: 'Language', ar: 'اللغة' },
  'language.change': { en: 'Change language', ar: 'تغيير اللغة' },

  // --- Roles (the five seeded roles) -------------------------------------
  'role.1': { en: 'Admin', ar: 'مدير النظام' },
  'role.2': { en: 'HR', ar: 'الموارد البشرية' },
  'role.3': { en: 'Manager', ar: 'مدير' },
  'role.4': { en: 'Employee', ar: 'موظف' },
  'role.5': { en: 'Applicant', ar: 'متقدّم للوظيفة' },
  'role.signedIn': { en: 'Signed in', ar: 'مسجّل الدخول' },
  'role.smarthrUser': { en: 'SmartHR user', ar: 'مستخدم SmartHR' },

  // --- Account status ----------------------------------------------------
  'status.active': { en: 'Active', ar: 'نشط' },
  'status.inactive': { en: 'Inactive', ar: 'غير نشط' },
  'status.yes': { en: 'Yes', ar: 'نعم' },

  // --- Recruitment pipeline stages (applications.status) -----------------
  'status.stage.applied': { en: 'Applied', ar: 'تم التقديم' },
  'status.stage.screening': { en: 'Screening', ar: 'الفرز' },
  'status.stage.shortlisted': { en: 'Shortlisted', ar: 'القائمة المختصرة' },
  'status.stage.interview': { en: 'Interview', ar: 'المقابلة' },
  'status.stage.assessment': { en: 'Assessment', ar: 'التقييم' },
  'status.stage.offer': { en: 'Offer', ar: 'العرض' },
  'status.stage.hired': { en: 'Hired', ar: 'تم التوظيف' },
  'status.stage.rejected': { en: 'Rejected', ar: 'مرفوض' },

  // --- Job statuses (jobs.status) ---------------------------------------
  'status.job.open': { en: 'Open', ar: 'مفتوحة' },
  'status.job.on_hold': { en: 'On hold', ar: 'مُعلّقة' },
  'status.job.closed': { en: 'Closed', ar: 'مغلقة' },
  'status.job.draft': { en: 'Draft', ar: 'مسودة' },

  // --- Interview statuses ------------------------------------------------
  'status.interview.scheduled': { en: 'Scheduled', ar: 'مجدولة' },
  'status.interview.in_progress': { en: 'In progress', ar: 'جارية' },
  'status.interview.completed': { en: 'Completed', ar: 'مكتملة' },
  'status.interview.cancelled': { en: 'Cancelled', ar: 'ملغاة' },

  // --- Attendance statuses (Title Case in this database) ----------------
  'status.attendance.Present': { en: 'Present', ar: 'حاضر' },
  'status.attendance.Absent': { en: 'Absent', ar: 'غائب' },
  'status.attendance.Late': { en: 'Late', ar: 'متأخر' },
  'status.attendance.Leave': { en: 'On leave', ar: 'في إجازة' },
  'status.attendance.Remote': { en: 'Remote', ar: 'عن بُعد' },

  // --- Leave statuses (Title Case in this database) ---------------------
  'status.leave.Pending': { en: 'Pending', ar: 'قيد الانتظار' },
  'status.leave.Approved': { en: 'Approved', ar: 'موافق عليها' },
  'status.leave.Rejected': { en: 'Rejected', ar: 'مرفوضة' },

  // --- Training statuses -------------------------------------------------
  'status.training.assigned': { en: 'Assigned', ar: 'مُسندة' },
  'status.training.in_progress': { en: 'In progress', ar: 'قيد التنفيذ' },
  'status.training.completed': { en: 'Completed', ar: 'مكتملة' },
  'status.training.cancelled': { en: 'Cancelled', ar: 'ملغاة' },

  // --- Employment types (jobs.employment_type) --------------------------
  'employment.full_time': { en: 'Full-time', ar: 'دوام كامل' },
  'employment.part_time': { en: 'Part-time', ar: 'دوام جزئي' },
  'employment.contract': { en: 'Contract', ar: 'عقد' },
  'employment.internship': { en: 'Internship', ar: 'تدريب' },
  'employment.temporary': { en: 'Temporary', ar: 'مؤقت' },

  // --- Units / counts ----------------------------------------------------
  'unit.hours': { en: '{count} hour(s)', ar: '{count} ساعة' },

  'role.name.Admin': { en: 'Admin', ar: 'مسؤول النظام' },
  'role.name.HR': { en: 'HR', ar: 'الموارد البشرية' },
  'role.name.Manager': { en: 'Manager', ar: 'مدير' },
  'role.name.Employee': { en: 'Employee', ar: 'موظف' },
  'role.name.Applicant': { en: 'Applicant', ar: 'متقدّم للوظيفة' },

  // Notification categories (the `notifications.type` free-text column, folded
  // onto the small vocabulary the three UI shapes render).
  'notif.type.all': { en: 'All Notifications', ar: 'كل الإشعارات' },
  'notif.type.leave': { en: 'Leave Updates', ar: 'تحديثات الإجازات' },
  'notif.type.attendance': { en: 'Attendance', ar: 'الحضور' },
  'notif.type.training': { en: 'Training Reminders', ar: 'تذكيرات التدريب' },
  'notif.type.performance': { en: 'Performance', ar: 'الأداء' },
  'notif.type.company': { en: 'Company Announcements', ar: 'إعلانات الشركة' },
  'notif.type.approval': { en: 'Approvals', ar: 'الموافقات' },
  'notif.type.info': { en: 'Information', ar: 'معلومات' },
  'notif.type.success': { en: 'Success', ar: 'نجاح' },
  'notif.type.warning': { en: 'Warning', ar: 'تحذير' },
  'notif.type.alert': { en: 'Alert', ar: 'تنبيه' },
  'notif.markAllRead': { en: 'Mark All as Read', ar: 'تعليم الكل كمقروء' },
  'notif.markRead': { en: 'Mark as Read', ar: 'تعليم كمقروء' },
  'notif.markUnread': { en: 'Mark as Unread', ar: 'تعليم كغير مقروء' },
  'notif.unread': { en: 'Unread', ar: 'غير مقروء' },
  'notif.loadFailed': { en: 'Failed to load notifications', ar: 'تعذّر تحميل الإشعارات' },
  'notif.updateFailed': { en: 'Failed to update notifications', ar: 'تعذّر تحديث الإشعارات' },
  'notif.updated': { en: 'Notifications Updated', ar: 'تم تحديث الإشعارات' },
  'notif.emptyFilter': {
    en: 'No notifications in this filter.',
    ar: 'لا توجد إشعارات ضمن هذه التصفية.',
  },
  'error.unexpected': { en: 'Unexpected error', ar: 'خطأ غير متوقع' },

  'action.updateFailed': { en: 'Update failed', ar: 'فشل التحديث' },
  'action.deleteFailed': { en: 'Delete failed', ar: 'فشل الحذف' },
  'validation.error': { en: 'Validation Error', ar: 'خطأ في التحقق' },

  'app.restoringSession': { en: 'Restoring your session…', ar: 'جارٍ استعادة جلستك…' },

  'filter.allStatusesLabel': { en: 'All Statuses', ar: 'كل الحالات' },

  'table.employee': { en: 'Employee', ar: 'الموظف' },

  // The two Title Case attendance tokens this database also stores.
  'status.attendance.On Leave': { en: 'On Leave', ar: 'في إجازة' },
  'status.attendance.Half Day': { en: 'Half Day', ar: 'نصف يوم' },

  'status.leave.Cancelled': { en: 'Cancelled', ar: 'ملغى' },
  // leave_requests.leave_type is free text; these are the values in use. An
  // unrecognised value is shown exactly as stored rather than as a key.
  'leave.type.Annual Leave': { en: 'Annual Leave', ar: 'إجازة سنوية' },
  'leave.type.Sick Leave': { en: 'Sick Leave', ar: 'إجازة مرضية' },
  'leave.type.Emergency Leave': { en: 'Emergency Leave', ar: 'إجازة طارئة' },
  'leave.type.Unpaid Leave': { en: 'Unpaid Leave', ar: 'إجازة بدون راتب' },
};
