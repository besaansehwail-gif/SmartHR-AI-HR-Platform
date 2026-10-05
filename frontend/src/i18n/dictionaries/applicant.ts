import { Dictionary } from '../types';

/** The Applicant portal: dashboard, opportunities, profile, CV, applications. */
export const applicant: Dictionary = {
  // --- Dashboard ---------------------------------------------------------
  'app.dashboard.profileCompleteness': {
    en: 'Profile completeness',
    ar: 'اكتمال الملف الشخصي',
  },
  'app.dashboard.myApplications': { en: 'My applications', ar: 'طلباتي' },
  'app.dashboard.recommended': { en: 'Recommended for you', ar: 'مقترحة لك' },

  // --- Opportunities -----------------------------------------------------
  'app.opportunities.title': { en: 'Opportunities', ar: 'الفرص المتاحة' },
  'app.opportunities.subtitle': {
    en: 'Jobs, internships, training and free courses currently on offer.',
    ar: 'الوظائف والتدريب والدورات المجانية المتاحة حاليًا.',
  },
  'app.opportunities.type.job': { en: 'Jobs', ar: 'وظائف' },
  'app.opportunities.type.internship': { en: 'Internships', ar: 'تدريب عملي' },
  'app.opportunities.type.training': { en: 'Training', ar: 'دورات تدريبية' },
  'app.opportunities.type.free_course': { en: 'Free courses', ar: 'دورات مجانية' },
  'app.opportunities.typeLabel.job': { en: 'Job', ar: 'وظيفة' },
  'app.opportunities.typeLabel.internship': { en: 'Internship', ar: 'تدريب عملي' },
  'app.opportunities.typeLabel.training': { en: 'Training', ar: 'دورة تدريبية' },
  'app.opportunities.typeLabel.free_course': { en: 'Free course', ar: 'دورة مجانية' },
  'app.opportunities.requirements': { en: 'Requirements', ar: 'المتطلبات' },
  'app.opportunities.deadline': { en: 'Closes {date}', ar: 'يُغلق في {date}' },
  'app.opportunities.apply': { en: 'Apply now', ar: 'قدّم الآن' },
  'app.opportunities.backToList': {
    en: 'Back to opportunities',
    ar: 'العودة إلى الفرص',
  },

  // --- Profile -----------------------------------------------------------
  'app.profile.title': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'app.profile.skills': { en: 'Skills', ar: 'المهارات' },
  'app.profile.skillsPlaceholder': {
    en: 'Python, SQL, Project management…',
    ar: 'بايثون، SQL، إدارة المشاريع…',
  },
  'app.profile.saved': { en: 'Profile saved', ar: 'تم حفظ الملف الشخصي' },

  // --- CV ----------------------------------------------------------------
  'app.cv.title': { en: 'My CV', ar: 'سيرتي الذاتية' },

  // --- Applications ------------------------------------------------------
  'app.applications.title': { en: 'My Applications', ar: 'طلباتي' },

  // --- Applicant-facing stage labels -------------------------------------
  // A presentation map, not a second vocabulary: `applications.status` keeps
  // the same eight English tokens the API reads and writes.
  'app.stage.applied': { en: 'Submitted', ar: 'تم الإرسال' },
  'app.stage.screening': { en: 'Under Review', ar: 'قيد المراجعة' },
  'app.stage.shortlisted': { en: 'Shortlisted', ar: 'ضمن القائمة المختصرة' },
  'app.stage.interview': { en: 'Interview', ar: 'مقابلة' },
  'app.stage.assessment': { en: 'Assessment', ar: 'تقييم' },
  'app.stage.offer': { en: 'Offer', ar: 'عرض وظيفي' },
  'app.stage.hired': { en: 'Hired', ar: 'تم القبول' },
  'app.stage.rejected': { en: 'Not selected', ar: 'لم يتم الاختيار' },

  // --- Opportunity detail ------------------------------------------------
  'app.opportunities.loadingOne': { en: 'Loading opportunity', ar: 'جارٍ تحميل الفرصة' },
  'app.opportunities.loadingList': { en: 'Loading opportunities', ar: 'جارٍ تحميل الفرص' },
  'app.opportunities.about': { en: 'About this opportunity', ar: 'عن هذه الفرصة' },
  'app.opportunities.type': { en: 'Type', ar: 'النوع' },
  'app.opportunities.organisation': { en: 'Organisation', ar: 'الجهة' },
  'app.opportunities.employment': { en: 'Employment', ar: 'نوع التوظيف' },
  'app.opportunities.location': { en: 'Location', ar: 'الموقع' },
  'app.opportunities.deadlineLabel': { en: 'Deadline', ar: 'آخر موعد' },
  'app.opportunities.duration': { en: 'Duration', ar: 'المدة' },
  'app.opportunities.requirementsExact': {
    en: 'Exactly as this opportunity lists them.',
    ar: 'كما وردت تمامًا في هذه الفرصة.',
  },
  'app.opportunities.noRequirements': {
    en: 'No requirements listed',
    ar: 'لم تُدرَج أي متطلبات',
  },
  'app.opportunities.howToApply': { en: 'How to apply', ar: 'طريقة التقديم' },
  'app.opportunities.matchSubtitle': {
    en: 'Your listed skills against this opportunity',
    ar: 'مهاراتك المدرجة مقارنةً بهذه الفرصة',
  },
  'app.opportunities.searchLabel': {
    en: 'Search title, description or skills',
    ar: 'ابحث في العنوان أو الوصف أو المهارات',
  },
  'app.opportunities.nothingMatches': { en: 'Nothing matches that', ar: 'لا يوجد ما يطابق ذلك' },
  'app.opportunities.deadlinePassed': {
    en: 'The deadline for this opportunity has passed',
    ar: 'انتهى الموعد النهائي لهذه الفرصة',
  },
  'app.opportunities.uploadCvFirst': {
    en: 'Upload your CV before applying',
    ar: 'ارفع سيرتك الذاتية قبل التقديم',
  },
  'app.opportunities.goToMyCv': { en: 'Go to My CV', ar: 'الانتقال إلى سيرتي الذاتية' },
  'app.opportunities.goToProvider': { en: 'Go to provider', ar: 'الانتقال إلى مقدّم الدورة' },
  'app.opportunities.viewDetails': { en: 'View details', ar: 'عرض التفاصيل' },

  'app.opportunities.notStated': { en: 'Not stated', ar: 'غير مذكور' },
  'app.opportunities.noDeadline': { en: 'No deadline stated', ar: 'لا يوجد موعد نهائي محدد' },
  'app.opportunities.noDescription': {
    en: 'No description was provided for this opportunity.',
    ar: 'لم يُقدَّم وصف لهذه الفرصة.',
  },
  'app.opportunities.noRequirementsHint': {
    en: 'This opportunity does not state any specific requirements.',
    ar: 'لا تذكر هذه الفرصة أي متطلبات محددة.',
  },
  'app.opportunities.cvNeededBody': {
    en: 'Every application carries a CV so the recruiter has something to read. Upload yours on the My CV page and then come back here.',
    ar: 'كل طلب يجب أن يُرفق بسيرة ذاتية ليطّلع عليها المسؤول عن التوظيف. ارفع سيرتك من صفحة «سيرتي الذاتية» ثم عُد إلى هنا.',
  },
  'app.opportunities.closedOn': {
    en: 'Applications closed on {date}.',
    ar: 'أُغلق باب التقديم في {date}.',
  },
  'app.opportunities.appliedStatus': { en: 'Applied — {status}', ar: 'تم التقديم — {status}' },
  'app.opportunities.notFound': { en: 'Not found.', ar: 'غير موجود.' },
  'app.opportunities.noneMatchingSearch': {
    en: 'SmartHR has no open opportunity matching “{search}”. Nothing has been invented to fill the gap — try different words.',
    ar: 'لا توجد لدى SmartHR فرصة مفتوحة تطابق «{search}». لم يُختلق شيء لسدّ الفراغ — جرّب كلمات مختلفة.',
  },
  'app.opportunities.noneOfThisKind': {
    en: 'SmartHR has no open opportunities of this kind right now.',
    ar: 'لا توجد لدى SmartHR فرص مفتوحة من هذا النوع حاليًا.',
  },
  'app.opportunities.tab.all': { en: 'All', ar: 'الكل' },

  // --- Applicant dashboard ------------------------------------------------
  'app.dashboard.loading': { en: 'Loading your dashboard', ar: 'جارٍ تحميل لوحة معلوماتك' },
  'app.dashboard.failed': { en: 'Could not load your dashboard.', ar: 'تعذّر تحميل لوحة معلوماتك.' },
  'app.dashboard.pageSubtitle': {
    en: 'Your job search with SmartHR: your profile, your CV, what is open, and where your applications stand.',
    ar: 'رحلة بحثك عن عمل مع SmartHR: ملفك الشخصي، وسيرتك الذاتية، والفرص المتاحة، وحالة طلباتك.',
  },
  'app.dashboard.openOpportunities': { en: 'Open opportunities', ar: 'فرص مفتوحة' },
  'app.dashboard.profileComplete': { en: 'Profile complete', ar: 'اكتمال الملف' },
  'app.dashboard.cvOnFile': { en: 'CV on file', ar: 'سيرة ذاتية مسجَّلة' },
  'app.dashboard.needCv': {
    en: 'You need a CV before you can apply',
    ar: 'تحتاج إلى سيرة ذاتية قبل التقديم',
  },
  'app.dashboard.uploadBeforeApplying': {
    en: 'Upload one before applying',
    ar: 'ارفع واحدة قبل التقديم',
  },
  'app.dashboard.addSkillsPrompt': {
    en: 'Add your skills to get matched suggestions',
    ar: 'أضف مهاراتك للحصول على اقتراحات مناسبة',
  },
  'app.dashboard.rankedHint': {
    en: 'Ranked by how well your listed skills match what each opportunity requires. A suggestion, not a hiring decision.',
    ar: 'مرتّبة حسب مدى تطابق مهاراتك المدرجة مع متطلبات كل فرصة. اقتراح، وليس قرار توظيف.',
  },
  'app.dashboard.newestHint': {
    en: 'The newest openings. Add skills on My Profile to have these ranked for you.',
    ar: 'أحدث الفرص المتاحة. أضف مهاراتك في ملفك الشخصي ليتم ترتيبها حسب ملاءمتها لك.',
  },
  'app.dashboard.nothingOnOffer': {
    en: 'Nothing on offer right now',
    ar: 'لا توجد فرص متاحة حاليًا',
  },
  'app.dashboard.nothingOnOfferHint': {
    en: 'SmartHR has no open opportunities at the moment. Check back soon.',
    ar: 'لا توجد لدى SmartHR فرص مفتوحة في الوقت الحالي. عاود التحقق قريبًا.',
  },
  'app.dashboard.recentApplications': { en: 'Recent applications', ar: 'أحدث الطلبات' },
  'app.dashboard.recentApplicationsHint': {
    en: 'Your own applications and where each one stands.',
    ar: 'طلباتك أنت وحالة كل منها.',
  },
  'app.dashboard.noApplications': { en: 'No applications yet', ar: 'لا توجد طلبات بعد' },
  'app.dashboard.noApplicationsHint': {
    en: 'When you apply to an opportunity it will appear here with its current stage.',
    ar: 'عند التقديم على فرصة ستظهر هنا مع مرحلتها الحالية.',
  },
  'app.dashboard.askCareerAgent': { en: 'Ask the Career Agent', ar: 'اسأل مساعد المسار المهني' },
  'app.dashboard.openCareerAgent': { en: 'Open Career Agent', ar: 'فتح مساعد المسار المهني' },
  'app.dashboard.uploadMyCv': { en: 'Upload my CV', ar: 'رفع سيرتي الذاتية' },
  'app.dashboard.addMySkills': { en: 'Add my skills', ar: 'إضافة مهاراتي' },
  'app.dashboard.browseAll': { en: 'Browse all', ar: 'تصفّح الكل' },
  'app.dashboard.seeAll': { en: 'See all', ar: 'عرض الكل' },

  // --- Applicant profile --------------------------------------------------
  'app.profile.loading': { en: 'Loading your profile', ar: 'جارٍ تحميل ملفك الشخصي' },
  'app.profile.failed': { en: 'Could not load your profile.', ar: 'تعذّر تحميل ملفك الشخصي.' },
  'app.profile.pageSubtitle': {
    en: 'What recruiters see, and what opportunity matching is based on.',
    ar: 'ما يراه المسؤولون عن التوظيف، وما تُبنى عليه مطابقة الفرص.',
  },
  'app.profile.yourDetails': { en: 'Your details', ar: 'بياناتك' },
  'app.profile.yourDetailsHint': {
    en: 'Only you can change these. SmartHR never fills them in for you.',
    ar: 'أنت وحدك من يمكنه تعديلها. لا يملؤها SmartHR نيابةً عنك أبدًا.',
  },
  'app.profile.firstName': { en: 'First name', ar: 'الاسم الأول' },
  'app.profile.lastName': { en: 'Last name', ar: 'اسم العائلة' },
  'app.profile.phone': { en: 'Phone', ar: 'الهاتف' },
  'app.profile.location': { en: 'Location', ar: 'الموقع' },
  'app.profile.currentSkills': { en: 'Current skills', ar: 'المهارات الحالية' },
  'app.profile.whoCanSee': { en: 'Who can see this', ar: 'من يمكنه الاطلاع على هذا' },
  'app.profile.save': { en: 'Save profile', ar: 'حفظ الملف الشخصي' },
  'app.profile.saveFailed': { en: 'Could not save', ar: 'تعذّر الحفظ' },
  'app.profile.tryAgain': { en: 'Please try again.', ar: 'يُرجى المحاولة مرة أخرى.' },
  'app.profile.noProfile': { en: 'No profile.', ar: 'لا يوجد ملف شخصي.' },

  // --- Applicant CV -------------------------------------------------------
  'app.cv.loading': { en: 'Loading your CV', ar: 'جارٍ تحميل سيرتك الذاتية' },
  'app.cv.failed': { en: 'Could not load your CV.', ar: 'تعذّر تحميل سيرتك الذاتية.' },
  'app.cv.pageSubtitle': {
    en: 'Upload the CV recruiters will read when you apply. PDF or DOCX, up to 5 MB.',
    ar: 'ارفع السيرة الذاتية التي سيقرأها المسؤولون عن التوظيف عند تقديمك. ملف PDF أو DOCX بحجم أقصاه 5 ميغابايت.',
  },
  'app.cv.justUploadedHint': {
    en: 'Read from the text of the document you just uploaded. Nothing here has been saved.',
    ar: 'مقروء من نص المستند الذي رفعته للتو. لم يُحفظ أي شيء مما هنا.',
  },
  'app.cv.skillsFound': { en: 'Skills found in your CV', ar: 'المهارات الموجودة في سيرتك الذاتية' },
  'app.cv.copyToProfile': {
    en: 'Copy and review on My Profile',
    ar: 'انسخها وراجعها في ملفي الشخصي',
  },
  'app.cv.pasteHint': {
    en: 'Paste them into the Skills box on My Profile and save.',
    ar: 'الصقها في خانة المهارات بملفك الشخصي ثم احفظ.',
  },
  'app.cv.onFile': { en: 'CVs on file', ar: 'السير الذاتية المسجَّلة' },
  'app.cv.noneYet': { en: 'None yet', ar: 'لا شيء بعد' },
  'app.cv.onFileBadge': { en: 'On file', ar: 'مسجَّلة' },
  'app.cv.noCvYet': { en: 'No CV yet', ar: 'لا توجد سيرة ذاتية بعد' },
  'app.cv.noCvYetHint': {
    en: 'Upload a PDF or DOCX. You will need one before you can apply to anything.',
    ar: 'ارفع ملف PDF أو DOCX. ستحتاج إليه قبل التقديم على أي فرصة.',
  },
  'app.cv.whatStored': { en: 'What SmartHR stores', ar: 'ما الذي يحفظه SmartHR' },
  'app.cv.acceptedFiles': { en: 'Accepted files', ar: 'الملفات المقبولة' },
  'app.cv.uploadNew': { en: 'Upload a new version', ar: 'رفع نسخة جديدة' },
  'app.cv.uploadMyCv': { en: 'Upload my CV', ar: 'رفع سيرتي الذاتية' },
  'app.cv.uploadFailed': { en: 'Upload failed', ar: 'فشل الرفع' },
  'app.cv.analysisFailed': {
    en: 'The AI analysis could not be completed',
    ar: 'تعذّر إتمام التحليل بالذكاء الاصطناعي',
  },
  'app.cv.roleNotStated': { en: 'Role not stated', ar: 'المسمى غير مذكور' },

  // --- Applicant applications ---------------------------------------------
  'app.applications.loading': { en: 'Loading your applications', ar: 'جارٍ تحميل طلباتك' },
  'app.applications.failed': { en: 'Could not load your applications.', ar: 'تعذّر تحميل طلباتك.' },
  'app.applications.pageSubtitle': {
    en: 'Every application you have submitted, and where each one stands.',
    ar: 'كل طلب قدّمته، وحالة كل منها.',
  },
  'app.applications.totalApplications': { en: 'Total applications', ar: 'إجمالي الطلبات' },
  'app.applications.inProgress': { en: 'In progress', ar: 'قيد المعالجة' },
  'app.applications.notYetDecided': { en: 'Not yet decided', ar: 'لم يُبتّ فيها بعد' },
  'app.applications.interviewsScheduled': { en: 'Interviews scheduled', ar: 'مقابلات مجدولة' },
  'app.applications.noneYet': {
    en: 'You have not applied to anything yet',
    ar: 'لم تتقدّم لأي فرصة بعد',
  },
  'app.applications.noneYetHint': {
    en: 'Find an opportunity that suits you and apply — it will appear here with its stage.',
    ar: 'ابحث عن فرصة تناسبك وقدّم عليها — وستظهر هنا مع مرحلتها.',
  },
  'app.applications.whatYouSee': {
    en: 'What you can and cannot see here',
    ar: 'ما يمكنك وما لا يمكنك رؤيته هنا',
  },
  'app.applications.browseOpportunities': { en: 'Browse opportunities', ar: 'تصفّح الفرص' },
  'app.applications.scheduledInterviews': { en: 'Scheduled interviews', ar: 'المقابلات المجدولة' },

  'app.cv.currentBadge': { en: 'Current', ar: 'الحالية' },

  'app.profile.skillAdded': { en: 'Added', ar: 'مضافة' },

  'app.opps.loadFailed': { en: 'Could not load opportunities.', ar: 'تعذّر تحميل الفرص.' },
  'app.opps.loadOneFailed': {
    en: 'Could not load that opportunity.',
    ar: 'تعذّر تحميل هذه الفرصة.',
  },
  'app.opps.submitted': { en: 'Application submitted', ar: 'تم إرسال الطلب' },
  'app.opps.worthKnowing': { en: 'Worth knowing', ar: 'معلومة مهمة' },
  'app.opps.applyFailed': { en: 'Could not apply', ar: 'تعذّر التقديم' },
  'app.opps.tryAgain': { en: 'Please try again.', ar: 'يُرجى المحاولة مرة أخرى.' },
  'app.common.noData': { en: 'No data.', ar: 'لا توجد بيانات.' },
  'app.cv.copied': { en: 'Copied', ar: 'تم النسخ' },
  'app.cv.notSaved': {
    en: 'Not saved — you decide which of these belong on your profile.',
    ar: 'غير محفوظة — أنت من يقرّر أيها يضاف إلى ملفك.',
  },
  'app.cv.textOnly': {
    en: 'Your CV was uploaded and its text was extracted successfully — only the AI reading of it is unavailable.',
    ar: 'تم رفع سيرتك الذاتية واستخراج نصها بنجاح — القراءة بالذكاء الاصطناعي وحدها غير متاحة.',
  },
  'app.dash.notYet': { en: 'Not yet', ar: 'ليس بعد' },
  'app.profile.skillMissing': { en: 'Missing', ar: 'غير مضافة' },
  'app.apps.organizationFallback': { en: 'SmartHR', ar: 'SmartHR' },
};
