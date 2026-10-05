import { Dictionary } from '../types';

/**
 * Navigation: sidebar items, workspace switcher, page titles and the command
 * palette.
 *
 * Keys are the `PageId` union from `components/layout/Sidebar.tsx`, so adding
 * a screen means adding `nav.<pageId>` and `page.<pageId>` here. A missing key
 * renders the key itself in development, which is loud enough to notice.
 */
export const nav: Dictionary = {
  // --- Workspaces --------------------------------------------------------
  'workspace.applicant': { en: 'Applicant', ar: 'المتقدّم' },
  'workspace.applicant.short': { en: 'Me', ar: 'أنا' },
  'workspace.applicant.section': { en: 'My Job Search', ar: 'بحثي عن عمل' },
  'workspace.employee': { en: 'Employee', ar: 'الموظف' },
  'workspace.employee.short': { en: 'Me', ar: 'أنا' },
  'workspace.employee.section': { en: 'My Workspace', ar: 'مساحتي' },
  'workspace.manager': { en: 'Manager', ar: 'المدير' },
  'workspace.manager.short': { en: 'Team', ar: 'الفريق' },
  'workspace.manager.section': { en: 'Team Operations', ar: 'عمليات الفريق' },
  'workspace.hr': { en: 'HR', ar: 'الموارد البشرية' },
  'workspace.hr.short': { en: 'HR', ar: 'م.ب' },
  'workspace.hr.section': { en: 'HR Operations', ar: 'عمليات الموارد البشرية' },
  'workspace.admin': { en: 'Admin', ar: 'الإدارة' },
  'workspace.admin.short': { en: 'Sys', ar: 'نظام' },
  'workspace.admin.section': { en: 'Administration', ar: 'إدارة النظام' },
  'workspace.switch': { en: 'Switch workspace', ar: 'تبديل مساحة العمل' },

  // --- Sidebar labels: Applicant ----------------------------------------
  'nav.app-dashboard': { en: 'Dashboard', ar: 'لوحة المعلومات' },
  'nav.app-opportunities': { en: 'Opportunities', ar: 'الفرص' },
  'nav.app-profile': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'nav.app-cv': { en: 'My CV', ar: 'سيرتي الذاتية' },
  'nav.app-applications': { en: 'My Applications', ar: 'طلباتي' },
  'nav.app-agent': { en: 'Career Agent', ar: 'مساعد المسار المهني' },
  'nav.app-ai-interview': { en: 'AI Interview', ar: 'المقابلة الذكية' },

  // --- Sidebar labels: Employee -----------------------------------------
  'nav.emp-dashboard': { en: 'Dashboard', ar: 'لوحة المعلومات' },
  'nav.emp-profile': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'nav.emp-attendance': { en: 'My Attendance', ar: 'حضوري' },
  'nav.emp-leave': { en: 'My Leave', ar: 'إجازاتي' },
  'nav.emp-training': { en: 'My Training', ar: 'تدريبي' },
  'nav.emp-performance': { en: 'My Performance', ar: 'أدائي' },
  'nav.emp-career': { en: 'Career Growth', ar: 'التطور المهني' },
  'nav.emp-notifications': { en: 'Notifications', ar: 'الإشعارات' },

  // --- Sidebar labels: Manager ------------------------------------------
  'nav.mgr-dashboard': { en: 'Dashboard', ar: 'لوحة المعلومات' },
  'nav.mgr-team': { en: 'My Team', ar: 'فريقي' },
  'nav.mgr-attendance': { en: 'Attendance', ar: 'الحضور' },
  'nav.mgr-leave': { en: 'Leave Requests', ar: 'طلبات الإجازة' },
  'nav.mgr-performance': { en: 'Performance', ar: 'الأداء' },
  'nav.mgr-insights': { en: 'Workforce Insights', ar: 'رؤى القوى العاملة' },
  'nav.mgr-notifications': { en: 'Notifications', ar: 'الإشعارات' },

  // --- Sidebar labels: HR -----------------------------------------------
  'nav.hr-dashboard': { en: 'HR Dashboard', ar: 'لوحة الموارد البشرية' },
  'nav.hr-employees': { en: 'Employees', ar: 'الموظفون' },
  'nav.hr-employee-360': { en: 'Employee 360', ar: 'الملف الشامل للموظف' },
  'nav.hr-jobs': { en: 'Recruitment', ar: 'التوظيف' },
  'nav.hr-candidates': { en: 'Candidates', ar: 'المرشحون' },
  'nav.hr-ai-agent': { en: 'AI Screening Agent', ar: 'وكيل الفرز الذكي' },
  'nav.hr-ai-interview-analytics': { en: 'AI Interview Analytics', ar: 'تحليلات المقابلة الذكية' },
  'nav.hr-interviews': { en: 'Interviews', ar: 'المقابلات' },
  'nav.hr-training': { en: 'Training & Learning', ar: 'التدريب والتعلّم' },
  'nav.hr-reports': { en: 'Reports & Analytics', ar: 'التقارير والتحليلات' },
  'nav.hr-notifications': { en: 'Notifications', ar: 'الإشعارات' },

  // --- Sidebar labels: Admin --------------------------------------------
  'nav.dashboard': { en: 'Command Center', ar: 'مركز التحكّم' },
  'nav.users': { en: 'Users', ar: 'المستخدمون' },
  'nav.roles': { en: 'Roles & Permissions', ar: 'الأدوار والصلاحيات' },
  'nav.departments': { en: 'Departments', ar: 'الأقسام' },
  'nav.positions': { en: 'Positions', ar: 'المسميات الوظيفية' },
  'nav.audit': { en: 'Audit Logs', ar: 'سجلات التدقيق' },
  'nav.settings': { en: 'Settings', ar: 'الإعدادات' },

  // --- Top-bar page titles ----------------------------------------------
  'page.app-dashboard': { en: 'Applicant Dashboard', ar: 'لوحة معلومات المتقدّم' },
  'page.app-opportunities': { en: 'Opportunities', ar: 'الفرص المتاحة' },
  'page.app-profile': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'page.app-cv': { en: 'My CV', ar: 'سيرتي الذاتية' },
  'page.app-applications': { en: 'My Applications', ar: 'طلباتي' },
  'page.app-agent': { en: 'AI Career Agent', ar: 'مساعد المسار المهني الذكي' },
  'page.app-ai-interview': { en: 'AI Interview', ar: 'المقابلة الذكية' },
  'page.emp-dashboard': { en: 'My Dashboard', ar: 'لوحة معلوماتي' },
  'page.emp-profile': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'page.emp-attendance': { en: 'My Attendance', ar: 'سجل حضوري' },
  'page.emp-leave': { en: 'My Leave', ar: 'إجازاتي' },
  'page.emp-training': { en: 'My Training', ar: 'تدريبي' },
  'page.emp-performance': { en: 'My Performance', ar: 'أدائي' },
  'page.emp-career': { en: 'Career Growth', ar: 'التطور المهني' },
  'page.emp-notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'page.mgr-dashboard': { en: 'Manager Dashboard', ar: 'لوحة معلومات المدير' },
  'page.mgr-team': { en: 'My Team', ar: 'فريقي' },
  'page.mgr-attendance': { en: 'Team Attendance', ar: 'حضور الفريق' },
  'page.mgr-leave': { en: 'Leave Requests', ar: 'طلبات الإجازة' },
  'page.mgr-performance': { en: 'Team Performance', ar: 'أداء الفريق' },
  'page.mgr-insights': { en: 'Workforce Insights', ar: 'رؤى القوى العاملة' },
  'page.mgr-notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'page.hr-dashboard': { en: 'HR Dashboard', ar: 'لوحة الموارد البشرية' },
  'page.hr-employees': { en: 'Employees', ar: 'الموظفون' },
  'page.hr-employee-360': { en: 'Employee 360', ar: 'الملف الشامل للموظف' },
  'page.hr-jobs': { en: 'Recruitment & Jobs', ar: 'التوظيف والوظائف' },
  'page.hr-candidates': { en: 'Candidate Pipeline', ar: 'مسار المرشحين' },
  'page.hr-ai-agent': {
    en: 'SmartHR Internal AI Agent',
    ar: 'الوكيل الذكي الداخلي في SmartHR',
  },
  'page.hr-interviews': { en: 'Interviews', ar: 'المقابلات' },
  'page.hr-ai-interview-analytics': { en: 'AI Interview Analytics', ar: 'تحليلات المقابلة الذكية' },
  'page.hr-training': { en: 'Training & Learning', ar: 'التدريب والتعلّم' },
  'page.hr-reports': { en: 'Reports & Analytics', ar: 'التقارير والتحليلات' },
  'page.hr-notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'page.dashboard': { en: 'Command Center', ar: 'مركز التحكّم' },
  'page.users': { en: 'User Management', ar: 'إدارة المستخدمين' },
  'page.roles': { en: 'Roles & Permissions', ar: 'الأدوار والصلاحيات' },
  'page.departments': { en: 'Departments', ar: 'الأقسام' },
  'page.positions': { en: 'Positions', ar: 'المسميات الوظيفية' },
  'page.audit': { en: 'Audit Logs', ar: 'سجلات التدقيق' },
  'page.settings': { en: 'Settings', ar: 'الإعدادات' },

  // --- Top bar -----------------------------------------------------------
  'topbar.openNavigation': { en: 'Open navigation', ar: 'فتح القائمة' },
  'topbar.collapseSidebar': { en: 'Collapse sidebar', ar: 'طيّ الشريط الجانبي' },
  'topbar.expandSidebar': { en: 'Expand sidebar', ar: 'توسيع الشريط الجانبي' },
  'topbar.mainNavigation': { en: 'Main navigation', ar: 'القائمة الرئيسية' },
  'topbar.commandHint': { en: 'Ctrl K', ar: 'Ctrl K' },
  'topbar.notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'topbar.markAllRead': { en: 'Mark all read', ar: 'تعليم الكل كمقروء' },
  'topbar.myProfile': { en: 'My profile', ar: 'ملفي الشخصي' },

  // --- Command palette ---------------------------------------------------
  'palette.placeholder': {
    en: 'Search pages and actions…',
    ar: 'ابحث في الصفحات والإجراءات…',
  },
  'palette.noMatches': { en: 'No matches', ar: 'لا توجد نتائج مطابقة' },
  'palette.pages': { en: 'Pages', ar: 'الصفحات' },
  'palette.actions': { en: 'Actions', ar: 'الإجراءات' },
  'palette.close': { en: 'to close', ar: 'للإغلاق' },

  // --- Quick actions (top bar + command palette) ------------------------
  'quick.group.selfService': { en: 'Self-service', ar: 'الخدمة الذاتية' },
  'quick.group.teamManagement': { en: 'Team management', ar: 'إدارة الفريق' },
  'quick.group.hrOperations': { en: 'HR operations', ar: 'عمليات الموارد البشرية' },
  'quick.group.administration': { en: 'Administration', ar: 'إدارة النظام' },
  'quick.request-leave': { en: 'Request leave', ar: 'طلب إجازة' },
  'quick.view-payslip': { en: 'View my records', ar: 'عرض سجلاتي' },
  'quick.update-profile': { en: 'Update my profile', ar: 'تحديث ملفي الشخصي' },
  'quick.mgr-approve-leave': { en: 'Review leave requests', ar: 'مراجعة طلبات الإجازة' },
  'quick.mgr-conduct-review': { en: 'Appraise a team member', ar: 'تقييم أحد أعضاء الفريق' },
  'quick.mgr-check-attendance': { en: 'Verify team attendance', ar: 'التحقق من حضور الفريق' },
  'quick.add-employee': { en: 'Add an employee', ar: 'إضافة موظف' },
  'quick.post-job': { en: 'Post a job requisition', ar: 'نشر وظيفة شاغرة' },
  'quick.schedule-interview': { en: 'Schedule an interview', ar: 'جدولة مقابلة' },
  'quick.add-user': { en: 'Add a system user', ar: 'إضافة مستخدم للنظام' },
  'quick.add-department': { en: 'Add a department', ar: 'إضافة قسم' },
  'quick.export-audit': { en: 'Export the audit trail', ar: 'تصدير سجل التدقيق' },

  // --- Top-bar extras ----------------------------------------------------
  'topbar.searchRecords': { en: 'Search records, actions…', ar: 'ابحث في السجلات والإجراءات…' },
  'topbar.searchAria': { en: 'Search records and actions', ar: 'البحث في السجلات والإجراءات' },
  'topbar.quickAction': { en: 'Quick action', ar: 'إجراء سريع' },
  'topbar.accountMenu': { en: 'Account menu', ar: 'قائمة الحساب' },
  'topbar.notificationsUnreadAria': {
    en: 'Notifications, {count} unread',
    ar: 'الإشعارات، {count} غير مقروء',
  },
  'topbar.newCount': { en: '{count} new', ar: '{count} جديد' },
  'topbar.caughtUp': { en: 'You are all caught up', ar: 'لا يوجد جديد لديك' },
  'topbar.caughtUpHint': {
    en: 'Notifications addressed to your account appear here.',
    ar: 'تظهر هنا الإشعارات الموجّهة إلى حسابك.',
  },
  'topbar.openNotificationCenter': {
    en: 'Open notification center',
    ar: 'فتح مركز الإشعارات',
  },
  'topbar.unread': { en: 'Unread', ar: 'غير مقروء' },
  'topbar.myNotifications': { en: 'My notifications', ar: 'إشعاراتي' },
  'topbar.workspaceHome': { en: '{workspace} workspace home', ar: 'الصفحة الرئيسية لمساحة {workspace}' },

  'palette.run': { en: 'Run', ar: 'تشغيل' },
  'palette.toOpen': { en: 'to open', ar: 'للفتح' },
  'palette.noMatchesFor': {
    en: 'Nothing you can open matches “{query}”.',
    ar: 'لا يوجد ما يمكنك فتحه يطابق «{query}».',
  },
  'palette.resultCount': { en: '{count} result(s)', ar: '{count} نتيجة' },

  // --- Quick-action confirmations (App.tsx) -------------------------------
  'quick.toast.notificationsUpdated': { en: 'Notifications updated', ar: 'تم تحديث الإشعارات' },
  'quick.toast.allMarkedRead': { en: 'All notifications marked as read.', ar: 'تم تعليم جميع الإشعارات كمقروءة.' },
  'quick.toast.notificationsFailed': { en: 'Could not update notifications', ar: 'تعذّر تحديث الإشعارات' },
  'quick.toast.notificationsFailedBody': { en: 'Nothing was changed. Please try again.', ar: 'لم يتم تغيير أي شيء. يُرجى المحاولة مرة أخرى.' },
  'quick.toast.navigated': { en: 'Opened {page}', ar: 'تم فتح {page}' },

  // --- Access guard (App.tsx) --------------------------------------------
  'access.restricted': { en: 'Access restricted', ar: 'الوصول مقيّد' },
  'access.restrictedBody': {
    en: 'Your role ({role}) does not have access to this section. If you believe this is wrong, ask an administrator to review your role assignment.',
    ar: 'دورك ({role}) لا يمنحك صلاحية الوصول إلى هذا القسم. إن كنت ترى أن هذا غير صحيح، فاطلب من مدير النظام مراجعة الدور المسنَد إليك.',
  },
};
