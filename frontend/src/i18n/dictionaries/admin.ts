import { Dictionary } from '../types';

/** The Admin workspace: Command Center, Users, Roles, Departments, Positions,
 *  Audit Logs and Settings. */
export const admin: Dictionary = {
  // --- Command Center ----------------------------------------------------

  // --- Users -------------------------------------------------------------
  'admin.users.title': { en: 'Users & Access Management', ar: 'المستخدمون وإدارة الوصول' },
  'admin.users.subtitle': {
    en: 'Provision platform accounts, assign roles, and control who can sign in to SmartHR.',
    ar: 'أنشئ حسابات النظام، وأسند الأدوار، وتحكّم بمن يمكنه تسجيل الدخول إلى SmartHR.',
  },
  'admin.users.editUser': { en: 'Edit user', ar: 'تعديل المستخدم' },

  // --- Roles & permissions ----------------------------------------------

  // --- Departments -------------------------------------------------------

  // --- Positions ---------------------------------------------------------

  // --- Audit logs --------------------------------------------------------

  // --- Audit actions -----------------------------------------------------

  // --- Settings ----------------------------------------------------------

  // --- Users page (full) --------------------------------------------------
  'admin.users.searchAll': {
    en: 'Search by name, email, department, or position…',
    ar: 'ابحث بالاسم أو البريد الإلكتروني أو القسم أو المسمى الوظيفي…',
  },
  'admin.users.noneFound': { en: 'No user accounts found', ar: 'لم يتم العثور على حسابات مستخدمين' },
  'admin.users.moreActions': { en: 'More actions', ar: 'إجراءات أخرى' },
  'admin.users.provisionTitle': {
    en: 'Provision New User Account',
    ar: 'إنشاء حساب مستخدم جديد',
  },
  'admin.users.provisionSubtitle': {
    en: 'Create sign-in credentials and assign a platform role.',
    ar: 'أنشئ بيانات دخول وأسند دورًا في النظام.',
  },
  'admin.users.workEmail': { en: 'Work Email', ar: 'البريد الإلكتروني للعمل' },
  'admin.users.emailPlaceholder': { en: 'person@example.com', ar: 'person@example.com' },
  'admin.users.initialPassword': { en: 'Initial Password', ar: 'كلمة المرور الأولية' },
  'admin.users.atLeast8': { en: 'At least 8 characters', ar: 'ثمانية أحرف على الأقل' },
  'admin.users.platformRole': { en: 'Platform Role', ar: 'دور المستخدم' },
  'admin.users.accountStatus': { en: 'Account Status', ar: 'حالة الحساب' },
  'admin.users.editTitle': { en: 'Edit User Account', ar: 'تعديل حساب المستخدم' },
  'admin.users.resetPassword': { en: 'Reset Password', ar: 'إعادة تعيين كلمة المرور' },
  'admin.users.leaveBlank': {
    en: 'Leave blank to keep the current password',
    ar: 'اتركه فارغًا للإبقاء على كلمة المرور الحالية',
  },
  'admin.users.deleteTitle': { en: 'Delete User Account', ar: 'حذف حساب المستخدم' },
  'admin.users.deleteBody': {
    en: 'This permanently removes the sign-in account.',
    ar: 'يؤدي هذا إلى حذف حساب الدخول نهائيًا.',
  },
  'admin.users.exportCsv': { en: 'Export CSV', ar: 'تصدير CSV' },
  'admin.users.allRoles': { en: 'All Roles', ar: 'كل الأدوار' },
  'admin.users.allStatuses': { en: 'All Statuses', ar: 'كل الحالات' },
  'admin.users.loading': { en: 'Loading user accounts…', ar: 'جارٍ تحميل حسابات المستخدمين…' },
  'admin.users.loadFailed': { en: 'Could not load users.', ar: 'تعذّر تحميل المستخدمين.' },
  'admin.users.unableToLoad': { en: 'Unable to load users', ar: 'تعذّر تحميل المستخدمين' },
  'admin.users.errorLoading': { en: 'Error loading users', ar: 'خطأ أثناء تحميل المستخدمين' },
  'admin.users.retry': { en: 'Retry', ar: 'إعادة المحاولة' },
  'admin.users.deactivateAccount': { en: 'Deactivate account', ar: 'إلغاء تفعيل الحساب' },
  'admin.users.activateAccount': { en: 'Activate account', ar: 'تفعيل الحساب' },
  'admin.users.deleteAccount': { en: 'Delete account', ar: 'حذف الحساب' },
  'admin.users.createAccount': { en: 'Create Account', ar: 'إنشاء الحساب' },
  'admin.users.saveChanges': { en: 'Save Changes', ar: 'حفظ التغييرات' },
  'admin.users.deleteAccountBtn': { en: 'Delete Account', ar: 'حذف الحساب' },
  'admin.users.rolesFailed': { en: 'Failed to load roles', ar: 'تعذّر تحميل الأدوار' },
  'admin.users.rolesIncomplete': {
    en: 'The role picker may be incomplete.',
    ar: 'قد تكون قائمة الأدوار غير مكتملة.',
  },
  'admin.users.validationError': { en: 'Validation Error', ar: 'خطأ في التحقق' },
  'admin.users.emailRequired': { en: 'Work email is required.', ar: 'البريد الإلكتروني للعمل مطلوب.' },
  'admin.users.passwordMin': {
    en: 'Password must be at least 8 characters.',
    ar: 'يجب ألا تقل كلمة المرور عن 8 أحرف.',
  },
  'admin.users.selectRole': { en: 'Select a role for the account.', ar: 'اختر دورًا للحساب.' },
  'admin.users.createdOk': { en: 'User Created Successfully', ar: 'تم إنشاء المستخدم بنجاح' },
  'admin.users.createFailed': { en: 'Failed to create user', ar: 'تعذّر إنشاء المستخدم' },
  'admin.users.unexpectedError': { en: 'Unexpected error', ar: 'خطأ غير متوقع' },
  'admin.users.newPasswordMin': {
    en: 'New password must be at least 8 characters.',
    ar: 'يجب ألا تقل كلمة المرور الجديدة عن 8 أحرف.',
  },
  'admin.users.updatedOk': { en: 'User Updated', ar: 'تم تحديث المستخدم' },
  'admin.users.updateFailed': { en: 'Update failed', ar: 'فشل التحديث' },
  'admin.users.activatedOk': { en: 'User Activated', ar: 'تم تفعيل المستخدم' },
  'admin.users.deactivatedOk': { en: 'User Deactivated', ar: 'تم إلغاء تفعيل المستخدم' },
  'admin.users.actionFailed': { en: 'Action failed', ar: 'فشل الإجراء' },
  'admin.users.deletedOk': { en: 'User Account Deleted', ar: 'تم حذف حساب المستخدم' },
  'admin.users.deleteFailed': { en: 'Delete failed', ar: 'فشل الحذف' },
  'admin.users.exportStarted': { en: 'Export Started', ar: 'بدأ التصدير' },
  'admin.users.firstAccountHint': {
    en: 'Use “+ Add User” to provision the first account.',
    ar: 'استخدم «+ إضافة مستخدم» لإنشاء أول حساب.',
  },
  'admin.users.adjustFilters': {
    en: 'Try adjusting your search or filters.',
    ar: 'جرّب تعديل البحث أو عوامل التصفية.',
  },
  'admin.users.noLinkedEmployeeShort': { en: 'No linked employee', ar: 'لا يوجد موظف مرتبط' },

  // --- Roles & permissions -------------------------------------------------
  'rbac.title': { en: 'Roles & Permissions', ar: 'الأدوار والصلاحيات' },
  'rbac.subtitle': {
    en: 'Configure granular capability matrices and security clearance across functional organizational domains.',
    ar: 'اضبط مصفوفات الصلاحيات التفصيلية ومستويات التصريح الأمني عبر مجالات المؤسسة الوظيفية.',
  },
  'rbac.badge': { en: 'RBAC Matrix v3.2', ar: 'مصفوفة الصلاحيات الإصدار 3.2' },
  'rbac.discard': { en: 'Discard Changes', ar: 'تجاهل التغييرات' },
  'rbac.save': { en: 'Save Changes', ar: 'حفظ التغييرات' },
  'rbac.matrixFor': { en: 'Permission Matrix:', ar: 'مصفوفة الصلاحيات:' },
  'rbac.privilegesEnabled': {
    en: '{count} of 40 Privileges Enabled',
    ar: '{count} من 40 صلاحية مُفعّلة',
  },
  'rbac.enableAll': { en: 'Enable All', ar: 'تفعيل الكل' },
  'rbac.revokeAll': { en: 'Revoke All', ar: 'سحب الكل' },
  'rbac.disableAll': { en: 'Disable All', ar: 'تعطيل الكل' },
  'rbac.col.category': { en: 'Functional Category', ar: 'الفئة الوظيفية' },
  'rbac.col.view': { en: 'View', ar: 'عرض' },
  'rbac.col.create': { en: 'Create', ar: 'إنشاء' },
  'rbac.col.edit': { en: 'Edit', ar: 'تعديل' },
  'rbac.col.delete': { en: 'Delete', ar: 'حذف' },
  'rbac.col.rowAction': { en: 'Row Action', ar: 'إجراء الصف' },
  'rbac.lockedAdmin': { en: 'Locked (Admin)', ar: 'مقفل (مسؤول النظام)' },
  'rbac.cascadeNotice': {
    en: 'Policy changes will cascade automatically across active user sessions upon saving.',
    ar: 'ستُطبَّق تغييرات السياسة تلقائيًا على جلسات المستخدمين النشطة عند الحفظ.',
  },
  'rbac.unsaved': { en: 'Unsaved edits pending', ar: 'توجد تعديلات غير محفوظة' },
  'rbac.systemNotice': { en: 'System Notice', ar: 'تنبيه النظام' },
  'rbac.adminImmutable': {
    en: 'The Admin system role has irrevocable full platform privileges.',
    ar: 'دور مسؤول النظام يملك صلاحيات كاملة وغير قابلة للسحب على المنصة.',
  },
  'rbac.resetComplete': { en: 'Reset Complete', ar: 'تمت إعادة التعيين' },
  'rbac.resetMessage': {
    en: 'Reverted permissions for {role} to default enterprise baseline.',
    ar: 'أُعيدت صلاحيات {role} إلى الإعدادات المؤسسية الافتراضية.',
  },
  'rbac.appliedInSession': {
    en: 'Permissions Applied In-Session',
    ar: 'طُبّقت الصلاحيات ضمن الجلسة',
  },
  'rbac.appliedMessage': {
    en: 'Access policies for "{role}" updated locally. Persisting them needs a permissions table, which this database does not have.',
    ar: 'حُدِّثت سياسات الوصول لدور "{role}" محليًا. حفظها بشكل دائم يتطلب جدول صلاحيات غير موجود في قاعدة البيانات هذه.',
  },
  'rbac.switchConfirm': {
    en: 'You have unsaved changes. Switch role anyway?',
    ar: 'لديك تغييرات غير محفوظة. هل تريد تبديل الدور على أي حال؟',
  },
  'rbac.currentlyEditing': { en: 'Currently Editing', ar: 'قيد التحرير حاليًا' },
  'rbac.clickToConfigure': { en: 'Click to Configure', ar: 'انقر للإعداد' },
  'rbac.core': { en: 'Core', ar: 'أساسي' },
  'rbac.users': { en: 'users', ar: 'مستخدمين' },
  'rbac.adminRootNotice': {
    en: 'The Administrator role retains immutable root authorization across every endpoint.',
    ar: 'يحتفظ دور مسؤول النظام بصلاحية جذرية ثابتة على جميع نقاط النظام.',
  },
  'rbac.toggleNotice': {
    en: 'Toggle specific CRUD permissions for each operational functional module below.',
    ar: 'فعّل أو عطّل صلاحيات العرض والإنشاء والتعديل والحذف لكل وحدة تشغيلية أدناه.',
  },
  'rbac.toggleFor': { en: 'Toggle {action} for {category}', ar: 'تبديل صلاحية {action} لـ {category}' },

  // Permission categories (presentation labels for the matrix rows).
  'rbac.cat.Employees.label': { en: 'Employees Directory', ar: 'دليل الموظفين' },
  'rbac.cat.Employees.desc': {
    en: 'Access and manage employee profiles, compensation, personal data, and emergency contacts',
    ar: 'الاطلاع على ملفات الموظفين والرواتب والبيانات الشخصية وجهات الاتصال في الطوارئ وإدارتها',
  },
  'rbac.cat.Recruitment.label': { en: 'Recruitment & Jobs', ar: 'التوظيف والوظائف' },
  'rbac.cat.Recruitment.desc': {
    en: 'Requisitions, candidate pipelines, interview evaluations, and job offers',
    ar: 'طلبات التوظيف ومسارات المرشحين وتقييمات المقابلات وعروض العمل',
  },
  'rbac.cat.Attendance.label': { en: 'Time & Attendance', ar: 'الوقت والحضور' },
  'rbac.cat.Attendance.desc': {
    en: 'Timecard approvals, shift rosters, overtime logging, and biometric check-ins',
    ar: 'اعتماد سجلات الدوام وجداول المناوبات وتسجيل العمل الإضافي والحضور البيومتري',
  },
  'rbac.cat.Leave.label': { en: 'Leave & PTO Management', ar: 'إدارة الإجازات' },
  'rbac.cat.Leave.desc': {
    en: 'Time-off requests, vacation approvals, sick leave balances, and parental leaves',
    ar: 'طلبات الإجازة واعتماد الإجازات السنوية وأرصدة الإجازات المرضية وإجازات الأمومة والأبوة',
  },
  'rbac.cat.Training.label': { en: 'Learning & Development', ar: 'التعلّم والتطوير' },
  'rbac.cat.Training.desc': {
    en: 'Skill development programs, certification tracking, and compliance courses',
    ar: 'برامج تطوير المهارات وتتبّع الشهادات ودورات الامتثال',
  },
  'rbac.cat.Performance.label': { en: 'Performance & Reviews', ar: 'الأداء والتقييمات' },
  'rbac.cat.Performance.desc': {
    en: 'Quarterly OKRs, 360-degree appraisals, manager feedback, and promotion tracks',
    ar: 'الأهداف الربعية وتقييمات 360 درجة وملاحظات المدير ومسارات الترقية',
  },
  'rbac.cat.Reports.label': { en: 'Analytics & Reporting', ar: 'التحليلات والتقارير' },
  'rbac.cat.Reports.desc': {
    en: 'Executive headcount analytics, attrition rates, diversity metrics, and payroll exports',
    ar: 'تحليلات أعداد الموظفين ومعدلات ترك العمل ومؤشرات التنوع وتصدير كشوف الرواتب',
  },
  'rbac.cat.Users.label': { en: 'User Administration', ar: 'إدارة المستخدمين' },
  'rbac.cat.Users.desc': {
    en: 'Create user logins, assign organizational roles, reset credentials, and suspend accounts',
    ar: 'إنشاء حسابات الدخول وإسناد الأدوار التنظيمية وإعادة تعيين بيانات الاعتماد وإيقاف الحسابات',
  },
  'rbac.cat.Settings.label': { en: 'Company & App Settings', ar: 'إعدادات الشركة والتطبيق' },
  'rbac.cat.Settings.desc': {
    en: 'Enterprise configuration, working policy rules, legal entities, and notification triggers',
    ar: 'إعدادات المؤسسة وقواعد سياسات العمل والكيانات القانونية ومحفّزات الإشعارات',
  },
  'rbac.cat.Audit Logs.label': { en: 'Audit & Security Logs', ar: 'سجلات التدقيق والأمان' },
  'rbac.cat.Audit Logs.desc': {
    en: 'Immutable records of system actions, access attempts, role modifications, and data exports',
    ar: 'سجلات غير قابلة للتعديل لإجراءات النظام ومحاولات الوصول وتغييرات الأدوار وعمليات تصدير البيانات',
  },

  // Role descriptions (presentation copy for the four staff roles).
  'rbac.role.Admin.desc': {
    en: 'Full administrative control over the entire SmartHR platform, data, security, and global settings.',
    ar: 'تحكّم إداري كامل في منصة SmartHR وبياناتها وأمانها وإعداداتها العامة.',
  },
  'rbac.role.HR.desc': {
    en: 'Human Resources specialists with elevated personnel management, recruitment, and organizational permissions.',
    ar: 'أخصائيو الموارد البشرية بصلاحيات موسّعة لإدارة شؤون الموظفين والتوظيف والتنظيم.',
  },
  'rbac.role.Manager.desc': {
    en: 'Team leaders with oversight over their direct reports, department requisitions, performance reviews, and leave approvals.',
    ar: 'قادة الفرق المشرفون على التابعين لهم وطلبات توظيف القسم وتقييمات الأداء واعتماد الإجازات.',
  },
  'rbac.role.Employee.desc': {
    en: 'Standard team members with self-service access to own profile, leave requests, attendance, and learning modules.',
    ar: 'أعضاء الفريق بصلاحيات خدمة ذاتية للاطلاع على ملفهم وطلبات إجازاتهم وحضورهم ووحدات التعلّم.',
  },

  // --- Settings ------------------------------------------------------------
  'settings.title': { en: 'Enterprise System Settings', ar: 'إعدادات النظام المؤسسية' },
  'settings.subtitle': {
    en: 'Global environment policies, security authentication parameters, company structure, and REST backend integration endpoints.',
    ar: 'سياسات البيئة العامة وإعدادات المصادقة الأمنية وهيكل الشركة ونقاط تكامل الواجهة الخلفية.',
  },
  'settings.tenant': { en: 'Tenant: smarthr-prod-us', ar: 'المستأجر: smarthr-prod-us' },
  'settings.tab.general': { en: 'General', ar: 'عام' },
  'settings.tab.company': { en: 'Company Profile', ar: 'ملف الشركة' },
  'settings.tab.security': { en: 'Users & Security', ar: 'المستخدمون والأمان' },
  'settings.tab.notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'settings.tab.workmode': { en: 'Work Mode & Hours', ar: 'نمط العمل وساعاته' },
  'settings.tab.system': { en: 'FastAPI & System', ar: 'الواجهة الخلفية والنظام' },

  'settings.localization.title': {
    en: 'Platform Localization & Formatting',
    ar: 'توطين المنصة وتنسيق البيانات',
  },
  'settings.localization.subtitle': {
    en: 'Configure system-wide language, timezone, date representations, and financial currency.',
    ar: 'اضبط لغة النظام والمنطقة الزمنية وصيغة التاريخ والعملة المالية.',
  },
  'settings.field.language': { en: 'System Default Language', ar: 'لغة النظام الافتراضية' },
  'settings.field.timezone': { en: 'Primary Enterprise Timezone', ar: 'المنطقة الزمنية الرئيسية' },
  'settings.field.dateFormat': { en: 'Standard Date Format', ar: 'صيغة التاريخ المعتمدة' },
  'settings.field.currency': { en: 'Financial Reporting Currency', ar: 'عملة التقارير المالية' },
  'settings.lang.enUS': { en: 'English (United States)', ar: 'الإنجليزية (الولايات المتحدة)' },
  'settings.lang.enGB': { en: 'English (United Kingdom)', ar: 'الإنجليزية (المملكة المتحدة)' },
  'settings.lang.frFR': { en: 'French (France)', ar: 'الفرنسية (فرنسا)' },
  'settings.lang.deDE': { en: 'German (Germany)', ar: 'الألمانية (ألمانيا)' },
  'settings.lang.jaJP': { en: 'Japanese (Japan)', ar: 'اليابانية (اليابان)' },
  'settings.tz.la': { en: 'America/Los_Angeles (PST/PDT)', ar: 'أمريكا/لوس أنجلوس (PST/PDT)' },
  'settings.tz.ny': { en: 'America/New_York (EST/EDT)', ar: 'أمريكا/نيويورك (EST/EDT)' },
  'settings.tz.london': { en: 'Europe/London (GMT/BST)', ar: 'أوروبا/لندن (GMT/BST)' },
  'settings.tz.tokyo': { en: 'Asia/Tokyo (JST)', ar: 'آسيا/طوكيو (JST)' },

  'settings.compliance.title': {
    en: 'Compliance & Data Retention',
    ar: 'الامتثال والاحتفاظ بالبيانات',
  },
  'settings.compliance.subtitle': {
    en: 'Configure automated record purging and retention rules per legal jurisdiction.',
    ar: 'اضبط قواعد حذف السجلات والاحتفاظ بها تلقائيًا حسب الولاية القانونية.',
  },
  'settings.compliance.auditRetention': {
    en: 'Automated Audit Retention',
    ar: 'الاحتفاظ الآلي بسجلات التدقيق',
  },
  'settings.compliance.auditRetentionDesc': {
    en: 'Retain immutable audit trails for 7 full calendar years.',
    ar: 'الاحتفاظ بسجلات تدقيق غير قابلة للتعديل لمدة 7 سنوات ميلادية كاملة.',
  },
  'settings.compliance.enabled': { en: 'Enabled', ar: 'مُفعَّل' },
  'settings.compliance.gdpr': {
    en: 'GDPR Employee Right to Erasure',
    ar: 'حق الموظف في محو بياناته (GDPR)',
  },
  'settings.compliance.gdprDesc': {
    en: 'Automated pseudonymization workflows for offboarded talent.',
    ar: 'إخفاء هوية بيانات الموظفين المنتهية خدماتهم تلقائيًا.',
  },
  'settings.compliance.compliant': { en: 'Compliant', ar: 'مطابق' },

  'settings.brand.title': { en: 'SmartHR Brand Engine', ar: 'هوية SmartHR البصرية' },
  'settings.brand.subtitle': { en: 'Global branding identity', ar: 'الهوية العامة للعلامة' },
  'settings.brand.tagline': {
    en: 'Enterprise workforce suite tailored for fast-growing global organizations.',
    ar: 'منظومة متكاملة لإدارة القوى العاملة مصمَّمة للمؤسسات العالمية سريعة النمو.',
  },
  'settings.brand.palette': { en: 'Color Accent Palette', ar: 'لوحة الألوان المعتمدة' },
  'settings.brand.swatchSidebar': { en: 'Light Sidebar: #FFFFFF', ar: 'الشريط الجانبي الفاتح: ‎#FFFFFF' },
  'settings.brand.swatchPrimary': { en: 'Primary: #A44820', ar: 'اللون الأساسي: ‎#A44820' },
  'settings.brand.swatchSoft': { en: 'Soft Sand: #FEE1C7', ar: 'الرملي الفاتح: ‎#FEE1C7' },
  'settings.brand.swatchCanvas': { en: 'Light Canvas: #F8FAFC', ar: 'الخلفية الفاتحة: ‎#F8FAFC' },

  'settings.company.title': {
    en: 'Corporate Entity Profile',
    ar: 'بيانات الكيان المؤسسي',
  },
  'settings.company.subtitle': {
    en: 'Official legal registration, headquarters address, and tax compliance details.',
    ar: 'بيانات التسجيل القانوني وعنوان المقر الرئيسي وتفاصيل الامتثال الضريبي.',
  },
  'settings.company.legalName': { en: 'Company Legal Name', ar: 'الاسم القانوني للشركة' },
  'settings.company.tax': { en: 'Tax Identification / EIN', ar: 'الرقم الضريبي' },
  'settings.company.website': { en: 'Corporate Website URL', ar: 'الموقع الإلكتروني للشركة' },
  'settings.company.hrEmail': { en: 'Corporate HR Contact Email', ar: 'بريد التواصل مع الموارد البشرية' },
  'settings.company.address': { en: 'Headquarters Address', ar: 'عنوان المقر الرئيسي' },
  'settings.offices.title': { en: 'Regional Offices', ar: 'المكاتب الإقليمية' },
  'settings.offices.subtitle': { en: 'Operational campuses', ar: 'المقار التشغيلية' },
  'settings.offices.primary': { en: 'Primary Campus (240 Capacity)', ar: 'المقر الرئيسي (سعة 240)' },
  'settings.offices.satellite': { en: 'Satellite (90 Capacity)', ar: 'مكتب فرعي (سعة 90)' },
  'settings.offices.international': { en: 'International (65 Capacity)', ar: 'مكتب دولي (سعة 65)' },

  'settings.auth.title': {
    en: 'Enterprise Authentication & MFA',
    ar: 'المصادقة المؤسسية والتحقق متعدد العوامل',
  },
  'settings.auth.subtitle': {
    en: 'Configure single sign-on (SSO), multi-factor enforcement, and session timeouts.',
    ar: 'اضبط الدخول الموحّد (SSO) وإلزامية التحقق متعدد العوامل ومهلة انتهاء الجلسة.',
  },
  'settings.auth.mfa': {
    en: 'Require Multi-Factor Authentication (MFA)',
    ar: 'إلزام التحقق متعدد العوامل (MFA)',
  },
  'settings.auth.mfaDesc': {
    en: 'Enforce Authenticator apps (TOTP) or WebAuthn hardware keys for all users.',
    ar: 'فرض استخدام تطبيقات المصادقة (TOTP) أو مفاتيح WebAuthn على جميع المستخدمين.',
  },
  'settings.auth.sso': {
    en: 'SAML 2.0 / Okta Enterprise Single Sign-On',
    ar: 'الدخول الموحّد المؤسسي SAML 2.0 / Okta',
  },
  'settings.auth.ssoDesc': {
    en: 'Authorize automated provisioning through corporate identity providers.',
    ar: 'السماح بإنشاء الحسابات تلقائيًا عبر مزوّدي الهوية المؤسسية.',
  },
  'settings.auth.sessionTimeout': { en: 'Inactivity Session Expiration', ar: 'انتهاء الجلسة عند الخمول' },
  'settings.auth.passwordPolicy': { en: 'Password Complexity Standard', ar: 'معيار تعقيد كلمة المرور' },
  'settings.auth.min15': { en: '15 Minutes', ar: '15 دقيقة' },
  'settings.auth.min30': { en: '30 Minutes', ar: '30 دقيقة' },
  'settings.auth.min60': { en: '60 Minutes (Recommended)', ar: '60 دقيقة (موصى به)' },
  'settings.auth.min120': { en: '120 Minutes', ar: '120 دقيقة' },
  'settings.auth.pwStandard': { en: 'Standard (8+ chars)', ar: 'قياسي (8 محارف فأكثر)' },
  'settings.auth.pwStrict': {
    en: 'Strict (12+ chars, special char & symbol)',
    ar: 'صارم (12 محرفًا فأكثر مع رمز خاص)',
  },
  'settings.auth.pwEnterprise': { en: 'Enterprise Custom', ar: 'مخصص للمؤسسة' },
  'settings.posture.title': { en: 'Security Posture', ar: 'الوضع الأمني' },
  'settings.posture.subtitle': { en: 'Hardening summary', ar: 'ملخص إجراءات التحصين' },
  'settings.posture.zeroTrust': { en: 'Zero-Trust Architecture', ar: 'بنية انعدام الثقة' },
  'settings.posture.zeroTrustDesc': {
    en: 'All session tokens are hashed using AES-256 with rotating enterprise signing keys.',
    ar: 'تُشفَّر جميع رموز الجلسات بخوارزمية AES-256 مع مفاتيح توقيع مؤسسية متبدّلة.',
  },
  'settings.posture.activeSessions': { en: 'Active Sessions', ar: 'الجلسات النشطة' },
  'settings.posture.concurrent': { en: '384 Concurrent Logins', ar: '384 جلسة دخول متزامنة' },

  'settings.dispatch.title': { en: 'Automated Dispatch Channels', ar: 'قنوات الإرسال الآلي' },
  'settings.dispatch.subtitle': {
    en: 'Configure email dispatch and instant messaging webhook integrations.',
    ar: 'اضبط إرسال البريد الإلكتروني وتكاملات الرسائل الفورية.',
  },
  'settings.dispatch.email': { en: 'Transactional Email Notifications', ar: 'رسائل البريد الإلكتروني التلقائية' },
  'settings.dispatch.emailDesc': {
    en: 'Deliver onboarding welcomes, password reset links, and leave approvals via SMTP/SES.',
    ar: 'إرسال رسائل الترحيب وروابط إعادة تعيين كلمة المرور واعتمادات الإجازات عبر SMTP/SES.',
  },
  'settings.dispatch.slack': { en: 'Slack Enterprise Webhook Sync', ar: 'مزامنة Slack المؤسسية' },
  'settings.dispatch.slackDesc': {
    en: 'Post real-time hiring updates and milestone announcements to',
    ar: 'نشر تحديثات التوظيف والإنجازات لحظيًا في',
  },
  'settings.dispatch.digest': { en: 'Weekly Executive Digest', ar: 'الملخص التنفيذي الأسبوعي' },
  'settings.dispatch.digestDesc': {
    en: 'Distribute automated Friday PDF metrics summaries to VP & Director roles.',
    ar: 'إرسال ملخص مؤشرات أسبوعي بصيغة PDF إلى المدراء التنفيذيين كل يوم جمعة.',
  },
  'settings.channel.title': { en: 'Channel Status', ar: 'حالة القنوات' },
  'settings.channel.subtitle': { en: 'Gateway integrations', ar: 'تكاملات البوابات' },
  'settings.channel.emailGateway': { en: 'Email Gateway:', ar: 'بوابة البريد الإلكتروني:' },
  'settings.channel.operational': { en: 'Operational', ar: 'تعمل' },
  'settings.channel.slackWebhooks': { en: 'Slack Webhooks:', ar: 'روابط Slack:' },
  'settings.channel.active': { en: 'Active', ar: 'نشطة' },
  'settings.channel.inAppBanner': { en: 'In-App Banner:', ar: 'شريط التنبيه داخل التطبيق:' },
  'settings.channel.healthy': { en: 'Healthy', ar: 'سليم' },

  'settings.work.title': {
    en: 'Workplace Flexibility & Standard Operating Hours',
    ar: 'مرونة مكان العمل وساعات الدوام المعتمدة',
  },
  'settings.work.subtitle': {
    en: 'Define corporate operating schedules, mandatory in-office minimums, and core collaboration windows.',
    ar: 'حدّد جداول الدوام والحد الأدنى لأيام الحضور بالمقر وساعات التعاون الأساسية.',
  },
  'settings.work.dailyHours': { en: 'Standard Daily Work Hours', ar: 'ساعات العمل اليومية المعتمدة' },
  'settings.work.hybridMin': {
    en: 'Hybrid In-Office Minimum Days / Week',
    ar: 'الحد الأدنى لأيام الحضور أسبوعيًا (نمط هجين)',
  },
  'settings.work.coreStart': { en: 'Core Hours Start (Local Time)', ar: 'بداية الساعات الأساسية (بالتوقيت المحلي)' },
  'settings.work.coreEnd': { en: 'Core Hours End (Local Time)', ar: 'نهاية الساعات الأساسية (بالتوقيت المحلي)' },
  'settings.work.override': {
    en: 'Allow Manager Work Mode Overrides',
    ar: 'السماح للمدراء بتعديل نمط العمل',
  },
  'settings.work.overrideDesc': {
    en: 'Permit team managers to approve temporary full-remote periods for project sprints.',
    ar: 'السماح لمدراء الفرق باعتماد فترات عمل عن بُعد مؤقتة أثناء مراحل المشاريع.',
  },
  'settings.policy.title': { en: 'Current Policy Snapshot', ar: 'لمحة عن السياسة الحالية' },
  'settings.policy.subtitle': { en: 'Applied to 428 employees', ar: 'مطبَّقة على 428 موظفًا' },
  'settings.policy.hybridDefault': { en: 'Hybrid Default (3:2)', ar: 'النمط الهجين الافتراضي (3:2)' },
  'settings.policy.hybridDesc': {
    en: 'Tuesday & Thursday are designated campus collaboration days.',
    ar: 'الثلاثاء والخميس يومان مخصّصان للتعاون داخل المقر.',
  },

  'settings.api.title': { en: 'FastAPI REST Integration Endpoint', ar: 'نقطة تكامل الواجهة الخلفية REST' },
  'settings.api.subtitle': {
    en: 'Specify the base URL of your FastAPI backend service. The SmartHRApi client service layer is pre-structured for seamless contract binding.',
    ar: 'حدّد العنوان الأساسي لخدمة الواجهة الخلفية. طبقة SmartHRApi مهيّأة مسبقًا للربط المباشر بها.',
  },
  'settings.api.test': { en: 'Test Connection', ar: 'اختبار الاتصال' },
  'settings.api.baseUrl': { en: 'FastAPI Server Base URL', ar: 'العنوان الأساسي لخادم الواجهة الخلفية' },
  'settings.api.helper': {
    en: 'Default local endpoint for the upcoming FastAPI service (e.g. uvicorn main:app --reload)',
    ar: 'العنوان المحلي الافتراضي لخدمة الواجهة الخلفية (مثال: uvicorn main:app --reload)',
  },
  'settings.api.verified': { en: 'FastAPI Endpoint Handshake Verified', ar: 'تم التحقق من الاتصال بالواجهة الخلفية' },
  'settings.api.ready': { en: 'Architecture Ready for FastAPI Integration', ar: 'البنية جاهزة للتكامل مع الواجهة الخلفية' },
  'settings.api.verifiedDesc': {
    en: 'Ready to stream REST endpoints from {url}. All payload schemas match Pydantic models.',
    ar: 'جاهز لاستقبال نقاط REST من {url}. جميع مخططات البيانات مطابقة لنماذج Pydantic.',
  },
  'settings.api.readyDesc': {
    en: 'Currently running on SmartHRApi in-memory asynchronous client. When the FastAPI backend is launched, set the API Base URL above and requests will map 1:1 to your Python endpoints.',
    ar: 'يعمل النظام حاليًا عبر عميل SmartHRApi غير المتزامن. عند تشغيل الواجهة الخلفية، اضبط العنوان الأساسي أعلاه لتُوجَّه الطلبات مباشرةً إلى نقاط Python.',
  },
  'settings.api.contract': { en: 'Prepared REST Endpoints Contract', ar: 'عقد نقاط REST المُعدّ مسبقًا' },
  'settings.api.listUsers': { en: 'List and filter users', ar: 'عرض المستخدمين وتصفيتهم' },
  'settings.api.createUser': { en: 'Create new user account', ar: 'إنشاء حساب مستخدم جديد' },
  'settings.api.listDepartments': { en: 'List departments & headcount', ar: 'عرض الأقسام وأعداد الموظفين' },
  'settings.api.updateRbac': { en: 'Update RBAC matrix', ar: 'تحديث مصفوفة الصلاحيات' },
  'settings.api.auditLedger': { en: 'Retrieve system audit ledger', ar: 'جلب سجل تدقيق النظام' },
  'settings.api.testedTitle': { en: 'FastAPI Connection Verified', ar: 'تم التحقق من اتصال الواجهة الخلفية' },
  'settings.api.testedMessage': {
    en: 'Handshake successful with {url} (Latency: 28ms). Ready for REST contract binding.',
    ar: 'نجح الاتصال بـ {url} (زمن الاستجابة: 28 مللي ثانية). جاهز لربط عقد REST.',
  },

  'settings.maintenance.title': { en: 'System Maintenance & Telemetry', ar: 'صيانة النظام والقياسات' },
  'settings.maintenance.subtitle': {
    en: 'Control platform maintenance mode and error tracking telemetry.',
    ar: 'تحكّم في وضع الصيانة وتتبّع الأخطاء.',
  },
  'settings.maintenance.mode': { en: 'Maintenance Mode', ar: 'وضع الصيانة' },
  'settings.maintenance.modeDesc': {
    en: 'Block non-admin logins and display an enterprise maintenance banner.',
    ar: 'منع دخول غير المسؤولين وعرض شريط صيانة للمستخدمين.',
  },
  'settings.maintenance.telemetry': { en: 'Error Diagnostics Telemetry', ar: 'قياسات تشخيص الأخطاء' },
  'settings.maintenance.telemetryDesc': {
    en: 'Stream unhandled client-side exceptions to system admin monitoring.',
    ar: 'إرسال أخطاء الواجهة غير المعالجة إلى مراقبة مسؤول النظام.',
  },
  'settings.runtime.title': { en: 'Runtime Diagnostics', ar: 'تشخيص بيئة التشغيل' },
  'settings.runtime.subtitle': { en: 'Build & Environment', ar: 'الإصدار والبيئة' },
  'settings.runtime.frontend': { en: 'Frontend Version:', ar: 'إصدار الواجهة:' },
  'settings.runtime.backend': { en: 'Backend Adapter:', ar: 'محوّل الواجهة الخلفية:' },
  'settings.runtime.node': { en: 'Node Environment:', ar: 'بيئة التشغيل:' },
  'settings.runtime.tenant': { en: 'Active Tenant ID:', ar: 'معرّف المستأجر النشط:' },

  'settings.saved': { en: 'Settings Saved', ar: 'تم حفظ الإعدادات' },
  'settings.savedMessage': {
    en: 'Configuration saved on this device. Sharing it across users needs a settings table, which this database does not have.',
    ar: 'حُفظت الإعدادات على هذا الجهاز. مشاركتها بين المستخدمين تتطلب جدول إعدادات غير موجود في قاعدة البيانات هذه.',
  },
  'settings.saveFailed': { en: 'Save Failed', ar: 'فشل الحفظ' },
  'settings.storageUnavailable': {
    en: 'Browser storage unavailable.',
    ar: 'تخزين المتصفح غير متاح.',
  },

  'settings.offices.sf': { en: 'San Francisco HQ', ar: 'المقر الرئيسي — سان فرانسيسكو' },
  'settings.offices.sfAddress': {
    en: '500 Howard Street, Suite 800',
    ar: '500 شارع هوارد، جناح 800',
  },
  'settings.offices.ny': { en: 'New York Design Hub', ar: 'مركز التصميم — نيويورك' },
  'settings.offices.nyAddress': { en: '140 Broadway, 22nd Floor', ar: '140 برودواي، الطابق 22' },
  'settings.offices.london': { en: 'London EMEA Office', ar: 'مكتب لندن — أوروبا والشرق الأوسط' },
  'settings.offices.londonAddress': {
    en: '10 Finsbury Square, London',
    ar: '10 ميدان فينسبري، لندن',
  },

  // --- Departments ---------------------------------------------------------
  'dept.title': { en: 'Departments', ar: 'الأقسام' },
  'dept.subtitle': {
    en: 'Organisational units, their headcount, defined roles, and open requisitions.',
    ar: 'الوحدات التنظيمية وأعداد موظفيها والمسميات المعرّفة والوظائف الشاغرة.',
  },
  'dept.search': { en: 'Search departments by name…', ar: 'ابحث عن قسم بالاسم…' },
  'dept.add': { en: 'Add Department', ar: 'إضافة قسم' },
  'dept.addSubtitle': { en: 'Create a new organisational unit.', ar: 'أنشئ وحدة تنظيمية جديدة.' },
  'dept.edit': { en: 'Edit Department', ar: 'تعديل القسم' },
  'dept.editAria': { en: 'Edit department', ar: 'تعديل القسم' },
  'dept.delete': { en: 'Delete Department', ar: 'حذف القسم' },
  'dept.deleteAria': { en: 'Delete department', ar: 'حذف القسم' },
  'dept.name': { en: 'Department Name', ar: 'اسم القسم' },
  'dept.namePlaceholder': { en: 'e.g. Engineering', ar: 'مثال: الهندسة' },
  'dept.cannotUndo': { en: 'This cannot be undone.', ar: 'لا يمكن التراجع عن هذا الإجراء.' },
  'dept.loading': { en: 'Loading departments…', ar: 'جارٍ تحميل الأقسام…' },
  'dept.loadError': { en: 'Could not load departments.', ar: 'تعذّر تحميل الأقسام.' },
  'dept.loadErrorTitle': { en: 'Unable to load departments', ar: 'تعذّر تحميل الأقسام' },
  'dept.errorLoading': { en: 'Error loading departments', ar: 'خطأ في تحميل الأقسام' },
  'dept.viewPositions': { en: 'View Positions', ar: 'عرض المسميات الوظيفية' },
  'dept.totalHeadcount': { en: 'Total Headcount', ar: 'إجمالي الموظفين' },
  'dept.definedPositions': { en: 'Defined Positions', ar: 'المسميات المعرّفة' },
  'dept.openRequisitions': { en: 'Open Requisitions', ar: 'الوظائف الشاغرة' },
  'dept.viewCards': { en: 'Cards', ar: 'بطاقات' },
  'dept.viewTable': { en: 'Table', ar: 'جدول' },
  'dept.colEmployees': { en: 'Employees', ar: 'الموظفون' },
  'dept.colPositions': { en: 'Positions', ar: 'المسميات' },
  'dept.colOpenJobs': { en: 'Open Jobs', ar: 'الوظائف المفتوحة' },
  'dept.colRequisitions': { en: 'Requisitions', ar: 'طلبات التوظيف' },
  'dept.create': { en: 'Create Department', ar: 'إنشاء قسم' },
  'dept.empty': { en: 'No departments found', ar: 'لا توجد أقسام' },
  'dept.emptyHint': {
    en: 'Use “+ Add Department” to create the first organisational unit.',
    ar: 'استخدم «+ إضافة قسم» لإنشاء أول وحدة تنظيمية.',
  },
  'dept.searchHint': { en: 'Try adjusting your search.', ar: 'جرّب تعديل كلمات البحث.' },
  'dept.nameRequired': { en: 'Department name is required.', ar: 'اسم القسم مطلوب.' },
  'dept.created': { en: 'Department Created', ar: 'تم إنشاء القسم' },
  'dept.createFailed': { en: 'Failed to create department', ar: 'تعذّر إنشاء القسم' },
  'dept.updated': { en: 'Department Updated', ar: 'تم تحديث القسم' },
  'dept.deleted': { en: 'Department Deleted', ar: 'تم حذف القسم' },

  // --- Positions -----------------------------------------------------------
  'pos.title': { en: 'Positions & Job Architecture', ar: 'المسميات الوظيفية وهيكل الوظائف' },
  'pos.subtitle': {
    en: 'Role definitions per department and the headcount currently assigned to each.',
    ar: 'تعريفات المسميات لكل قسم وعدد الموظفين المسندين لكل منها.',
  },
  'pos.search': {
    en: 'Search by position title or department…',
    ar: 'ابحث بالمسمى الوظيفي أو القسم…',
  },
  'pos.empty': { en: 'No positions found', ar: 'لا توجد مسميات وظيفية' },
  'pos.emptyHint': {
    en: 'Use “+ Add Position” to define the first role.',
    ar: 'استخدم «+ إضافة مسمى» لتعريف أول مسمى وظيفي.',
  },
  'pos.searchHint': {
    en: 'Try adjusting your search or department filter.',
    ar: 'جرّب تعديل البحث أو تصفية القسم.',
  },
  'pos.add': { en: 'Add Position', ar: 'إضافة مسمى وظيفي' },
  'pos.addSubtitle': {
    en: 'Define a role and the department that owns it.',
    ar: 'عرّف المسمى الوظيفي والقسم التابع له.',
  },
  'pos.edit': { en: 'Edit Position', ar: 'تعديل المسمى الوظيفي' },
  'pos.editAria': { en: 'Edit position', ar: 'تعديل المسمى الوظيفي' },
  'pos.delete': { en: 'Delete Position', ar: 'حذف المسمى الوظيفي' },
  'pos.deleteAria': { en: 'Delete position', ar: 'حذف المسمى الوظيفي' },
  'pos.titleField': { en: 'Position Title', ar: 'المسمى الوظيفي' },
  'pos.titlePlaceholder': { en: 'e.g. Backend Engineer', ar: 'مثال: مهندس برمجيات خلفية' },
  'pos.cannotUndo': { en: 'This cannot be undone.', ar: 'لا يمكن التراجع عن هذا الإجراء.' },
  'pos.exportCsv': { en: 'Export CSV', ar: 'تصدير CSV' },
  'pos.total': { en: 'Total Positions', ar: 'إجمالي المسميات' },
  'pos.departmentsCovered': { en: 'Departments Covered', ar: 'الأقسام المشمولة' },
  'pos.assignedHeadcount': { en: 'Assigned Headcount', ar: 'الموظفون المسندون' },
  'pos.unstaffedRoles': { en: 'Unstaffed Roles', ar: 'مسميات بلا موظفين' },
  'pos.allDepartments': { en: 'All Departments', ar: 'كل الأقسام' },
  'pos.colPosition': { en: 'Position', ar: 'المسمى الوظيفي' },
  'pos.colAssigned': { en: 'Assigned Employees', ar: 'الموظفون المسندون' },
  'pos.colStaffing': { en: 'Staffing', ar: 'حالة الإشغال' },
  'pos.loading': { en: 'Loading positions…', ar: 'جارٍ تحميل المسميات…' },
  'pos.loadError': { en: 'Could not load positions.', ar: 'تعذّر تحميل المسميات.' },
  'pos.loadErrorTitle': { en: 'Unable to load positions', ar: 'تعذّر تحميل المسميات' },
  'pos.errorLoading': { en: 'Error loading positions', ar: 'خطأ في تحميل المسميات' },
  'pos.deptLoadFailed': { en: 'Failed to load departments', ar: 'تعذّر تحميل الأقسام' },
  'pos.deptPickerIncomplete': {
    en: 'The department picker may be incomplete.',
    ar: 'قد تكون قائمة الأقسام غير مكتملة.',
  },
  'pos.titleRequired': { en: 'Position title is required.', ar: 'المسمى الوظيفي مطلوب.' },
  'pos.selectDepartment': {
    en: 'Select the department this position belongs to.',
    ar: 'اختر القسم الذي ينتمي إليه هذا المسمى.',
  },
  'pos.created': { en: 'Position Created', ar: 'تم إنشاء المسمى الوظيفي' },
  'pos.createFailed': { en: 'Failed to create position', ar: 'تعذّر إنشاء المسمى الوظيفي' },
  'pos.updated': { en: 'Position Updated', ar: 'تم تحديث المسمى الوظيفي' },
  'pos.deleted': { en: 'Position Deleted', ar: 'تم حذف المسمى الوظيفي' },
  'pos.create': { en: 'Create Position', ar: 'إنشاء مسمى وظيفي' },
  'pos.exportStarted': { en: 'Export Started', ar: 'بدأ التصدير' },
  'pos.unassigned': { en: 'Unassigned', ar: 'غير مسند' },
  'pos.staffed': { en: 'Staffed', ar: 'مشغول' },
  'pos.unstaffed': { en: 'Unstaffed', ar: 'شاغر' },

  // --- Audit logs ----------------------------------------------------------
  'audit.title': { en: 'Security & Audit Logs', ar: 'سجلات الأمان والتدقيق' },
  'audit.subtitle': {
    en: 'Append-only ledger recording administrative mutations, privileged account changes, sign-in events, and system changes.',
    ar: 'سجل غير قابل للتعديل يوثّق التغييرات الإدارية وتعديلات الحسابات ذات الصلاحيات وعمليات تسجيل الدخول وتغييرات النظام.',
  },
  'audit.tableView': { en: 'Table view', ar: 'عرض جدولي' },
  'audit.timelineView': { en: 'Timeline view', ar: 'عرض زمني' },
  'audit.table': { en: 'Table', ar: 'جدول' },
  'audit.timeline': { en: 'Timeline', ar: 'الخط الزمني' },
  'audit.search': {
    en: 'Search user, action, entity, record…',
    ar: 'ابحث في المستخدم أو الإجراء أو الكيان أو السجل…',
  },
  'audit.inspection': { en: 'Audit Record Inspection', ar: 'فحص سجل التدقيق' },
  'audit.export': { en: 'Export Audit Trail', ar: 'تصدير سجل التدقيق' },
  'audit.reset': { en: 'Reset', ar: 'إعادة تعيين' },
  'audit.loading': { en: 'Loading audit trail…', ar: 'جارٍ تحميل سجل التدقيق…' },
  'audit.colTimestamp': { en: 'Timestamp', ar: 'الطابع الزمني' },
  'audit.colActionType': { en: 'Action Type', ar: 'نوع الإجراء' },
  'audit.colDescription': { en: 'Activity Description', ar: 'وصف النشاط' },
  'audit.colEntity': { en: 'Target Entity', ar: 'الكيان المستهدف' },
  'audit.colRecord': { en: 'Record', ar: 'السجل' },
  'audit.colDetails': { en: 'Details', ar: 'التفاصيل' },
  'audit.inspect': { en: 'Inspect', ar: 'فحص' },
  'audit.target': { en: 'Target:', ar: 'الهدف:' },
  'audit.occurredAt': { en: 'Occurred At', ar: 'وقت الحدوث' },
  'audit.operator': { en: 'Authorized Operator', ar: 'المستخدم المُنفِّذ' },
  'audit.summary': { en: 'Action Summary', ar: 'ملخص الإجراء' },
  'audit.storedRecord': {
    en: 'Stored Record (audit_logs row)',
    ar: 'السجل المخزَّن (صف من audit_logs)',
  },
  'audit.errorLoading': { en: 'Error loading audit logs', ar: 'خطأ في تحميل سجلات التدقيق' },
  'audit.unreachable': {
    en: 'Could not reach the audit trail.',
    ar: 'تعذّر الوصول إلى سجل التدقيق.',
  },
  'audit.allActions': { en: 'All Actions', ar: 'كل الإجراءات' },
  'audit.allEntities': { en: 'All Entities', ar: 'كل الكيانات' },
  'audit.exported': { en: 'Audit Log Exported', ar: 'تم تصدير سجل التدقيق' },
  'audit.allTime': { en: 'All Time', ar: 'كل الفترات' },
  'audit.past24h': { en: 'Past 24 Hours', ar: 'آخر 24 ساعة' },
  'audit.past7d': { en: 'Past 7 Days', ar: 'آخر 7 أيام' },
  'audit.past30d': { en: 'Past 30 Days', ar: 'آخر 30 يومًا' },
  'audit.emptyNone': { en: 'No audit entries recorded yet', ar: 'لا توجد سجلات تدقيق بعد' },
  'audit.emptyFiltered': { en: 'No audit entries found', ar: 'لا توجد سجلات مطابقة' },
  'audit.emptyNoneHint': {
    en: 'The trail fills as people sign in and administrative records are created, updated or deleted.',
    ar: 'يمتلئ السجل تلقائيًا مع تسجيل الدخول وإنشاء السجلات الإدارية وتعديلها وحذفها.',
  },
  'audit.emptyFilteredHint': {
    en: 'No events match your current filter parameters.',
    ar: 'لا توجد أحداث تطابق عوامل التصفية الحالية.',
  },
  'audit.clearFilters': { en: 'Clear Filter Criteria', ar: 'مسح عوامل التصفية' },
  'audit.noRole': { en: 'No role', ar: 'بدون دور' },
  'audit.noAccount': { en: 'No account on record', ar: 'لا يوجد حساب مسجَّل' },

  'users.nowStatus': { en: '{email} is now {status}.', ar: 'أصبح {email} {status}.' },

  // --- Admin command centre ------------------------------------------------
  'dash.title': { en: 'SmartHR Command Center', ar: 'مركز قيادة SmartHR' },
  'dash.subtitle': {
    en: 'Live workforce metrics, aggregated from the database on each request.',
    ar: 'مؤشرات القوى العاملة الحيّة، تُحتسب من قاعدة البيانات مع كل طلب.',
  },
  'dash.loadingTitle': { en: 'Loading dashboard metrics', ar: 'جارٍ تحميل مؤشرات لوحة المعلومات' },
  'dash.loadingBody': {
    en: 'Counting employees, recruitment, attendance and leave from the live tables.',
    ar: 'جارٍ احتساب الموظفين والتوظيف والحضور والإجازات من الجداول الحيّة.',
  },
  'dash.loadingLive': {
    en: 'Loading live workforce metrics…',
    ar: 'جارٍ تحميل مؤشرات القوى العاملة…',
  },
  'dash.unavailable': { en: 'Dashboard metrics are unavailable', ar: 'مؤشرات لوحة المعلومات غير متاحة' },
  'dash.unreachable': {
    en: 'The statistics endpoint is unreachable.',
    ar: 'تعذّر الوصول إلى واجهة الإحصائيات.',
  },
  'dash.totalEmployees': { en: 'Total Employees', ar: 'إجمالي الموظفين' },
  'dash.totalEmployeesHint': {
    en: 'Counted from the employees table',
    ar: 'محسوب من جدول الموظفين',
  },
  'dash.userAccounts': { en: 'User Accounts', ar: 'حسابات المستخدمين' },
  'dash.signInsHint': {
    en: 'Sign-ins counted from the audit trail',
    ar: 'عمليات الدخول محسوبة من سجل التدقيق',
  },
  'dash.departments': { en: 'Departments', ar: 'الأقسام' },
  'dash.departmentsHint': {
    en: 'Departments and positions on record',
    ar: 'الأقسام والمسميات المسجَّلة',
  },
  'dash.openJobs': { en: 'Open Jobs', ar: 'الوظائف المفتوحة' },
  'dash.openJobsHint': { en: 'Requisitions with status open', ar: 'طلبات توظيف بحالة «مفتوحة»' },
  'dash.attentionHint': {
    en: 'Derived from pending leave, scheduled interviews, recruitment backlog, access gaps and the audit trail',
    ar: 'مستخلص من الإجازات المعلّقة والمقابلات المجدولة وتراكم التوظيف وفجوات الوصول وسجل التدقيق',
  },
  'dash.employeeDistribution': { en: 'Employee Distribution', ar: 'توزيع الموظفين' },
  'dash.recruitmentPipeline': { en: 'Recruitment Pipeline', ar: 'مسار التوظيف' },
  'dash.attendanceToday': { en: 'Attendance Today', ar: 'الحضور اليوم' },
  'dash.shortcuts': { en: 'Command Shortcuts', ar: 'اختصارات سريعة' },
  'dash.shortcutsHint': {
    en: 'High-frequency administrative workflows',
    ar: 'الإجراءات الإدارية الأكثر استخدامًا',
  },
  'dash.recentActivity': { en: 'Recent System Activity', ar: 'نشاط النظام الأخير' },
  'dash.recentActivityHint': {
    en: 'Real-time audit telemetry of privilege changes, employee creation, and administrative events',
    ar: 'رصد فوري لتغييرات الصلاحيات وإنشاء الموظفين والأحداث الإدارية',
  },
  'dash.liveOps': {
    en: 'SmartHR Enterprise Command Engine — Live Ops',
    ar: 'محرّك القيادة المؤسسي في SmartHR — تشغيل مباشر',
  },
  'dash.tracking': { en: 'Tracking', ar: 'قيد المتابعة' },
  'dash.nothingNeedsAttention': {
    en: 'Nothing currently needs attention.',
    ar: 'لا يوجد ما يستدعي الانتباه حاليًا.',
  },
  'dash.systemAudit': { en: 'System Audit', ar: 'تدقيق النظام' },
  'dash.addEmployee': { en: 'Add Employee', ar: 'إضافة موظف' },
  'dash.acknowledgeAll': { en: 'Acknowledge All', ar: 'إقرار الكل' },
  'dash.noPendingItems': {
    en: 'No pending approvals, recruitment backlog or access gaps were found.',
    ar: 'لا توجد موافقات معلّقة أو تراكم في التوظيف أو فجوات وصول.',
  },
  'dash.viewOrg': { en: 'View Org', ar: 'عرض الهيكل' },
  'dash.roster': { en: 'Roster', ar: 'قائمة الموظفين' },
  'dash.addUser': { en: 'Add User', ar: 'إضافة مستخدم' },
  'dash.addDept': { en: 'Add Dept', ar: 'إضافة قسم' },
  'dash.postJob': { en: 'Post Job', ar: 'نشر وظيفة' },
  'dash.exportLog': { en: 'Export Log', ar: 'تصدير السجل' },
  'dash.fullAuditStream': { en: 'Full Audit Stream', ar: 'سجل التدقيق الكامل' },
  'dash.colActivity': { en: 'Activity', ar: 'النشاط' },
  'dash.colTargetEntity': { en: 'Target Entity', ar: 'الكيان المستهدف' },
  'dash.colTimestamp': { en: 'Timestamp', ar: 'الطابع الزمني' },
  'dash.recordsInvolved': { en: 'Records Involved', ar: 'السجلات المعنيّة' },
  'dash.severityLevel': { en: 'Severity Level', ar: 'مستوى الأهمية' },
  'dash.itemAcknowledged': { en: 'Item acknowledged', ar: 'تم الإقرار بالعنصر' },
  'dash.attentionCleared': { en: 'Attention Center cleared', ar: 'تم إخلاء مركز الاهتمام' },
  'dash.attentionClearedHint': {
    en: 'Hidden for this session. Items return until the underlying records are cleared.',
    ar: 'مخفي لهذه الجلسة فقط. ستعود العناصر حتى تُعالَج السجلات الأصلية.',
  },
  'dash.checkingOpenItems': { en: 'Checking for open items…', ar: 'جارٍ البحث عن عناصر مفتوحة…' },
  'dash.nothingNeedsAttentionTitle': { en: 'Nothing needs attention', ar: 'لا يوجد ما يستدعي الانتباه' },
  'dash.urgent': { en: 'Urgent', ar: 'عاجل' },
  'dash.actionRequired': { en: 'Action Required', ar: 'مطلوب إجراء' },
  'dash.noDeptEmployees': {
    en: 'No employees are assigned to a department yet.',
    ar: 'لا يوجد موظفون مسندون إلى أقسام بعد.',
  },
  'dash.noApplications': {
    en: 'No applications have been recorded yet.',
    ar: 'لم تُسجَّل أي طلبات توظيف بعد.',
  },
  'dash.noDate': { en: 'No date', ar: 'بدون تاريخ' },
  'dash.noAttendanceToday': {
    en: 'No attendance has been logged today.',
    ar: 'لم يُسجَّل أي حضور اليوم.',
  },
};
