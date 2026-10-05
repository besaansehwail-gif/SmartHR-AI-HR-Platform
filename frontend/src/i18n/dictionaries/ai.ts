import { Dictionary } from '../types';

/**
 * The four AI surfaces: the staff Assistant, the CV analysis modal, the
 * Applicant Career Agent and the Internal HR Agent.
 *
 * **Only the frame is translated, never the answer.** Every string here is UI
 * chrome SmartHR itself writes - a button, a column heading, a disclaimer. The
 * model's reply, the tool trace and every value that came out of a tool are
 * rendered exactly as the backend returned them. The agents already answer in
 * the language they were asked in (it is in their system prompts), so
 * translating their output in the browser would both corrupt it and fight a
 * behaviour that already works.
 *
 * The same rule covers data: a candidate's name, a job title, a CV's contents
 * and a skill string are database values and are never passed through `t()`.
 */
export const ai: Dictionary = {
  // --- Shared AI vocabulary ---------------------------------------------
  'ai.poweredBy': { en: '{provider} • {model}', ar: '{provider} • {model}' },
  'ai.noModel': { en: 'No model configured', ar: 'لم يتم إعداد أي نموذج' },
  'ai.noModelTitle': {
    en: 'No language model is configured',
    ar: 'لم يتم إعداد نموذج لغوي',
  },
  'ai.noModelBody': {
    en: 'It still works: the same SmartHR tools run and the real figures are shown, but the wording is assembled rather than written by a model. Nothing is ever invented.',
    ar: 'لا يزال يعمل: تُشغَّل الأدوات نفسها وتُعرض الأرقام الحقيقية، لكن الصياغة مُجمَّعة آليًا لا مكتوبة بنموذج. ولا يُختلق أي شيء إطلاقًا.',
  },
  'ai.writtenByModel': { en: 'Written by the model', ar: 'مكتوب بواسطة النموذج' },
  'ai.assembledFromTools': {
    en: 'Assembled from tool output',
    ar: 'مُجمَّع من مخرجات الأدوات',
  },
  'ai.viaTransport': { en: 'via {transport}', ar: 'عبر {transport}' },
  'ai.toolsUsed': { en: 'SmartHR tools used ({count})', ar: 'أدوات SmartHR المستخدمة ({count})' },
  'ai.readOnly': { en: 'Read-only', ar: 'قراءة فقط' },
  'ai.thinking': { en: 'Reading your SmartHR data…', ar: 'جارٍ قراءة بيانات SmartHR…' },
  'ai.ask': { en: 'Ask', ar: 'إرسال' },
  'ai.failed': {
    en: 'I could not answer that: {error}',
    ar: 'تعذّر عليّ الإجابة: {error}',
  },
  'ai.failedGeneric': { en: 'I could not answer that.', ar: 'تعذّر عليّ الإجابة.' },

  // --- Staff assistant (the floating panel) ------------------------------
  'ai.assistant.close': { en: 'Close the assistant', ar: 'إغلاق المساعد' },

  // --- CV analysis -------------------------------------------------------
  'ai.cv.reviewNotice': {
    en: 'Extracted by AI — please review',
    ar: 'مُستخرَج بالذكاء الاصطناعي — يُرجى المراجعة',
  },
  'ai.cv.notStated': { en: 'Not stated in the CV', ar: 'غير مذكور في السيرة الذاتية' },
  'ai.cv.fullName': { en: 'Full name', ar: 'الاسم الكامل' },
  'ai.cv.summary': { en: 'Summary', ar: 'نبذة' },
  'ai.cv.skills': { en: 'Skills', ar: 'المهارات' },
  'ai.cv.experience': { en: 'Experience', ar: 'الخبرات' },
  'ai.cv.education': { en: 'Education', ar: 'المؤهلات العلمية' },
  'ai.cv.certifications': { en: 'Certifications', ar: 'الشهادات' },
  'ai.cv.languages': { en: 'Languages', ar: 'اللغات' },
  'ai.cv.analysing': { en: 'Reading the document…', ar: 'جارٍ قراءة المستند…' },
  'ai.cv.foundInText': {
    en: 'Found in the document text (no AI)',
    ar: 'عُثر عليه في نص المستند (بدون ذكاء اصطناعي)',
  },

  // --- Matching (shown to both audiences) --------------------------------
  'ai.match.label': { en: 'AI Match / Recommendation', ar: 'توافق مقترح بالذكاء الاصطناعي' },
  'ai.match.notADecision': {
    en: 'not a hiring decision',
    ar: 'ليس قرار توظيف',
  },
  'ai.match.score': { en: 'Match score', ar: 'نسبة التوافق' },
  'ai.match.matchingSkills': { en: 'Matching skills', ar: 'المهارات المتوافقة' },
  'ai.match.skillGaps': { en: 'Skill gaps', ar: 'الفجوات في المهارات' },
  'ai.match.additionalSkills': { en: 'Other skills on file', ar: 'مهارات أخرى مسجَّلة' },
  'ai.match.notScored': { en: 'Not scored', ar: 'لم تُحتسب' },

  // --- Career Agent (applicant) -----------------------------------------
  'ai.career.title': { en: 'AI Career Agent', ar: 'مساعد المسار المهني الذكي' },
  'ai.career.subtitle': {
    en: 'Ask about opportunities, how well they fit you, or your own applications. Every answer comes from your real SmartHR data.',
    ar: 'اسأل عن الفرص ومدى ملاءمتها لك أو عن طلباتك. كل إجابة مستمدّة من بياناتك الحقيقية في SmartHR.',
  },
  'ai.career.placeholder': {
    en: 'Ask about opportunities, matches or your applications…',
    ar: 'اسأل عن الفرص أو التوافق أو طلباتك…',
  },
  'ai.career.emptyTitle': { en: 'What are you looking for?', ar: 'عمّ تبحث؟' },
  'ai.career.emptyHint': {
    en: 'The agent reads your profile, your CV status, your applications and the live opportunity list. It cannot see anyone else’s data.',
    ar: 'يقرأ المساعد ملفك الشخصي وحالة سيرتك الذاتية وطلباتك وقائمة الفرص الحيّة. ولا يمكنه الاطلاع على بيانات أي شخص آخر.',
  },
  'ai.career.suggestion1': {
    en: 'What opportunities are suitable for me?',
    ar: 'ما الفرص المناسبة لي؟',
  },
  'ai.career.suggestion2': {
    en: 'Find me AI internships',
    ar: 'ابحث لي عن تدريب في الذكاء الاصطناعي',
  },
  'ai.career.suggestion3': { en: 'What are my applications?', ar: 'ما حالة طلباتي؟' },
  'ai.career.suggestion4': {
    en: 'What skills am I missing for the Data Analyst role?',
    ar: 'ما المهارات التي تنقصني لوظيفة محلل بيانات؟',
  },
  'ai.career.whatItCanDo': { en: 'What it can do', ar: 'ما الذي يستطيع فعله' },
  'ai.career.toolCount': {
    en: '{count} SmartHR tools, over {server} (MCP).',
    ar: '{count} أدوات في SmartHR عبر {server} (MCP).',
  },
  'ai.career.applyGateTitle': {
    en: 'It will not apply for you by accident',
    ar: 'لن يقدّم طلبًا نيابةً عنك دون قصد',
  },
  'ai.career.applyGateSubmits': { en: 'Submits an application', ar: 'يقدّم طلبًا' },
  'ai.career.applyGateDoesNot': { en: 'Does not', ar: 'لا يقدّم' },
  'ai.career.needsSayso': { en: 'needs your say-so', ar: 'يتطلّب موافقتك' },
  'ai.career.applyToolAvailable': {
    en: 'Apply tool was available',
    ar: 'كانت أداة التقديم متاحة',
  },
  'ai.career.cannotTitle': { en: 'What it cannot do', ar: 'ما الذي لا يستطيع فعله' },
  'ai.career.cannotBody': {
    en: 'It cannot see another applicant’s profile, CV or applications; it cannot change an application’s stage; and it cannot hire or reject anybody. There is no tool for any of those.',
    ar: 'لا يمكنه الاطلاع على ملف أو سيرة ذاتية أو طلبات متقدّم آخر، ولا يمكنه تغيير مرحلة أي طلب، ولا يمكنه توظيف أحد أو رفضه. لا توجد أداة لأيٍّ من ذلك.',
  },

  // --- Internal HR Agent -------------------------------------------------
  'ai.hr.title': { en: 'SmartHR Internal AI Agent', ar: 'الوكيل الذكي الداخلي في SmartHR' },
  'ai.hr.subtitle': {
    en: 'Screen real candidates against real requisitions. Every figure comes from your own SmartHR database, and the agent can only read it.',
    ar: 'افرز مرشحين حقيقيين مقابل وظائف حقيقية. كل رقم مصدره قاعدة بيانات SmartHR لديك، والوكيل لا يملك سوى صلاحية القراءة.',
  },
  'ai.hr.placeholder': {
    en: 'Ask about a requisition, its candidates or their match…',
    ar: 'اسأل عن وظيفة شاغرة أو مرشحيها أو مدى توافقهم…',
  },
  'ai.hr.emptyTitle': { en: 'Who are you hiring for?', ar: 'لأي وظيفة تبحث عن مرشحين؟' },
  'ai.hr.emptyHint': {
    en: 'Name a requisition and the agent will find it, read what it asks for, score the candidates against it and explain each one.',
    ar: 'اذكر اسم الوظيفة وسيجدها الوكيل، ويقرأ متطلباتها، ويحتسب توافق المرشحين معها، ويشرح نتيجة كل منهم.',
  },
  'ai.hr.thinking': {
    en: 'Reading your SmartHR recruitment data…',
    ar: 'جارٍ قراءة بيانات التوظيف في SmartHR…',
  },
  'ai.hr.candidatesFor': { en: 'Candidates for {title}', ar: 'المرشحون لوظيفة {title}' },
  'ai.hr.screeningResults': { en: 'Screening results', ar: 'نتائج الفرز' },
  'ai.hr.scoredAgainst': {
    en: 'Scored against: {requirements}',
    ar: 'مقارنةً بـ: {requirements}',
  },
  'ai.hr.fromTools': {
    en: 'Straight from the SmartHR tools, not from the reply above.',
    ar: 'مباشرةً من أدوات SmartHR، وليس من الإجابة أعلاه.',
  },
  'ai.hr.relevantExperience': { en: 'Relevant experience', ar: 'الخبرة ذات الصلة' },
  'ai.hr.evidence': { en: 'Evidence', ar: 'الأدلة المتوفّرة' },
  'ai.hr.noEvidenceTitle': {
    en: 'SmartHR holds no evidence for this candidate',
    ar: 'لا توجد لدى SmartHR أي بيانات عن هذا المرشح',
  },
  'ai.hr.noEvidenceGaps': {
    en: 'Nothing on file speaks to: {requirements}. That is missing information, not a low match.',
    ar: 'لا يوجد في الملف ما يتعلّق بـ: {requirements}. هذا نقص في المعلومات وليس ضعفًا في التوافق.',
  },
  'ai.hr.everyRequirementMet': {
    en: 'Every listed requirement is evidenced.',
    ar: 'كل المتطلبات المدرجة مدعومة بأدلة.',
  },
  'ai.hr.noneMatched': {
    en: 'None of the requirements matched.',
    ar: 'لم يتطابق أي من المتطلبات.',
  },
  'ai.hr.relevance.strong': { en: 'Strong relevance', ar: 'صلة قوية' },
  'ai.hr.relevance.some': { en: 'Some relevance', ar: 'صلة جزئية' },
  'ai.hr.relevance.none_evidenced': { en: 'None evidenced', ar: 'لا توجد أدلة' },
  'ai.hr.relevance.none_stated': { en: 'No experience stated', ar: 'لم تُذكر أي خبرة' },
  'ai.hr.relevance.unknown': { en: 'Unknown', ar: 'غير معروف' },
  'ai.hr.cvOnFile': { en: 'CV on file', ar: 'سيرة ذاتية مسجَّلة' },
  'ai.hr.noCvOnFile': { en: 'No CV on file', ar: 'لا توجد سيرة ذاتية' },
  'ai.hr.skillsOnProfile': {
    en: '{count} skill(s) on profile',
    ar: '{count} مهارة في الملف',
  },
  'ai.hr.applicationCount': { en: '{count} application(s)', ar: '{count} طلب' },
  'ai.hr.openInCandidates': { en: 'Open in Candidates', ar: 'فتح في صفحة المرشحين' },
  'ai.hr.decisionIsYours': {
    en: 'The hiring decision is yours. Stages are changed on the Candidates screen, never here.',
    ar: 'قرار التوظيف قرارك. تُغيَّر المراحل من صفحة المرشحين، وليس من هنا.',
  },
  'ai.hr.cannotChangeTitle': { en: 'It cannot change anything', ar: 'لا يمكنه تغيير أي شيء' },
  'ai.hr.whatItCanDo': { en: 'What it can do', ar: 'ما الذي يستطيع فعله' },
  'ai.hr.toolCount': {
    en: '{count} SmartHR tools, over {server} (MCP), up to {steps} per question.',
    ar: '{count} أدوات في SmartHR عبر {server} (MCP)، بحد أقصى {steps} لكل سؤال.',
  },
  'ai.hr.read': { en: 'read', ar: 'قراءة' },
  'ai.hr.whereNumbersComeFrom': {
    en: 'Where the numbers come from',
    ar: 'مصدر الأرقام',
  },
  'ai.hr.readingResult': { en: 'Reading a result', ar: 'كيف تقرأ النتيجة' },
  'ai.hr.readingPercentTerm': { en: 'A percentage', ar: 'النسبة المئوية' },
  'ai.hr.readingPercentBody': {
    en: 'How many of the requirements the requisition lists are evidenced by what SmartHR holds. It is a reading order, not a shortlist.',
    ar: 'عدد متطلبات الوظيفة المدعومة بما لدى SmartHR من بيانات. إنها ترتيب للمراجعة وليست قائمة مختصرة.',
  },
  'ai.hr.readingNotScoredTerm': { en: '“Not scored”', ar: '«لم تُحتسب»' },
  'ai.hr.readingNotScoredBody': {
    en: 'SmartHR holds no CV and no profile skills for that person. That is missing evidence, not a weak candidate — ask them for a CV.',
    ar: 'لا توجد لدى SmartHR سيرة ذاتية ولا مهارات في ملف ذلك الشخص. هذا نقص في الأدلة وليس ضعفًا في المرشح — اطلب منه سيرته الذاتية.',
  },
  'ai.hr.readingGapTerm': { en: 'A skill gap', ar: 'الفجوة في المهارات' },
  'ai.hr.readingGapBody': {
    en: 'The CV and profile do not mention it. That is not the same as the candidate not having it.',
    ar: 'لم تذكره السيرة الذاتية ولا الملف الشخصي. وهذا لا يعني أن المرشح لا يمتلكه.',
  },

  // Example prompts offered on the HR agent's empty state.
  'ai.hr.example1': {
    en: 'Find the best candidates for the Data Analyst position',
    ar: 'اعثر على أفضل المرشحين لوظيفة محلل بيانات',
  },
  'ai.hr.example2': {
    en: 'Rank the candidates for the QA Engineer job',
    ar: 'رتّب المرشحين لوظيفة مهندس ضمان الجودة',
  },
  'ai.hr.example3': {
    en: 'Show me candidates with Python and SQL skills',
    ar: 'أظهر لي المرشحين الذين يتقنون بايثون و SQL',
  },
  'ai.hr.example4': {
    en: 'Which candidates are at the interview stage?',
    ar: 'من هم المرشحون في مرحلة المقابلة؟',
  },

  // --- Staff assistant (full) ---------------------------------------------
  'ai.assistant.fullTitle': { en: 'SmartHR AI Assistant', ar: 'مساعد SmartHR الذكي' },
  'ai.assistant.newConversation': { en: 'Start a new conversation', ar: 'بدء محادثة جديدة' },
  'ai.assistant.fromToolResult': {
    en: 'Answered from a SmartHR MCP tool result',
    ar: 'أُجيب عنه من نتيجة أداة MCP في SmartHR',
  },
  'ai.assistant.inputPlaceholder': { en: 'Ask about your leave…', ar: 'اسأل عن إجازاتك…' },
  'ai.assistant.sendMessage': { en: 'Send message', ar: 'إرسال الرسالة' },
  'ai.assistant.askSmartHR': { en: 'Ask SmartHR', ar: 'اسأل SmartHR' },
  'ai.assistant.unavailable': { en: 'Assistant unavailable', ar: 'المساعد غير متاح' },
  'ai.assistant.reading': {
    en: 'Reading your SmartHR records…',
    ar: 'جارٍ قراءة سجلاتك في SmartHR…',
  },
  'ai.assistant.tryAsking': { en: 'Try asking', ar: 'جرّب أن تسأل' },
  'ai.assistant.ariaOpen': { en: 'Open the SmartHR assistant', ar: 'فتح مساعد SmartHR' },
  'ai.assistant.ariaClose': { en: 'Close the SmartHR assistant', ar: 'إغلاق مساعد SmartHR' },
  'ai.assistant.grounded': {
    en: 'Grounded in your SmartHR records',
    ar: 'مستند إلى سجلاتك في SmartHR',
  },
  'ai.assistant.greeting': {
    en: 'Hello. I am the SmartHR assistant. I answer from your own SmartHR records, never from guesswork.',
    ar: 'مرحبًا. أنا مساعد SmartHR. أجيب من سجلاتك في SmartHR، ولا أعتمد على التخمين إطلاقًا.',
  },
  'ai.assistant.sample1': {
    en: 'How many leave requests do I have?',
    ar: 'كم عدد طلبات الإجازة لديّ؟',
  },
  'ai.assistant.sample2': {
    en: 'Do I have any leave coming up?',
    ar: 'هل لديّ إجازات قادمة؟',
  },
  'ai.assistant.unreachable': {
    en: 'The assistant could not be reached.',
    ar: 'تعذّر الوصول إلى المساعد.',
  },
  'ai.error.forbidden': { en: 'Not permitted for your role', ar: 'غير مسموح به لدورك' },
  'ai.error.no_employee_record': { en: 'No employee record linked', ar: 'لا يوجد سجل موظف مرتبط' },
  'ai.error.database_error': { en: 'Database unavailable', ar: 'قاعدة البيانات غير متاحة' },
  'ai.error.unknown_tool': { en: 'Unknown tool', ar: 'أداة غير معروفة' },
  'ai.error.inactive_account': { en: 'Account inactive', ar: 'الحساب غير نشط' },

  // --- CV analysis modal ---------------------------------------------------
  'ai.cv.modalTitle': { en: 'AI CV Analysis', ar: 'تحليل السيرة الذاتية بالذكاء الاصطناعي' },
  'ai.cv.failed': { en: 'The CV could not be analysed', ar: 'تعذّر تحليل السيرة الذاتية' },
  'ai.cv.whatHappens': { en: 'What happens to this file', ar: 'ما الذي يحدث لهذا الملف' },
  'ai.cv.longDocument': { en: 'Long document', ar: 'مستند طويل' },
  'ai.cv.longDocumentBody': {
    en: 'Only the first part of this CV was analysed, because the document is unusually long.',
    ar: 'تم تحليل الجزء الأول فقط من هذه السيرة الذاتية لأن المستند طويل بشكل غير معتاد.',
  },
  'ai.cv.candidate': { en: 'Candidate', ar: 'المرشح' },
  'ai.cv.reviewAndSave': {
    en: 'Review and save to the candidate',
    ar: 'راجع واحفظ في ملف المرشح',
  },
  'ai.cv.analyseAnother': { en: 'Analyse another CV', ar: 'تحليل سيرة ذاتية أخرى' },
  'ai.cv.chooseFile': { en: 'Choose a CV file', ar: 'اختر ملف السيرة الذاتية' },
  'ai.cv.removeFile': { en: 'Remove file', ar: 'إزالة الملف' },
  'ai.cv.stored': { en: 'CV stored', ar: 'تم تخزين السيرة الذاتية' },
  'ai.cv.literalMatches': {
    en: 'These are literal matches in the extracted text, not model output.',
    ar: 'هذه تطابقات حرفية في النص المستخرج، وليست ناتج النموذج.',
  },
  'ai.cv.savedToDb': { en: 'Saved to PostgreSQL:', ar: 'المحفوظ في قاعدة البيانات:' },
  'ai.cv.uploading': { en: 'Uploading and analysing the CV', ar: 'جارٍ رفع السيرة الذاتية وتحليلها' },
  'ai.cv.extracting': {
    en: 'Extracting text and analysing…',
    ar: 'جارٍ استخراج النص وتحليله…',
  },
  'ai.cv.roleNotStated': { en: 'Role not stated', ar: 'المسمى غير مذكور' },
  'ai.cv.qualificationNotStated': { en: 'Qualification not stated', ar: 'المؤهل غير مذكور' },
  'ai.cv.certNotNamed': { en: 'Certification not named', ar: 'الشهادة غير مسمّاة' },
  'ai.cv.languageNotNamed': { en: 'Language not named', ar: 'اللغة غير مسمّاة' },
  'ai.cv.updateFailed': {
    en: 'The candidate could not be updated.',
    ar: 'تعذّر تحديث بيانات المرشح.',
  },
  'ai.cv.saveToCandidate': { en: 'Save to candidate record', ar: 'الحفظ في سجل المرشح' },
  'ai.cv.unsupportedType': {
    en: 'Only PDF and DOCX CVs are supported.',
    ar: 'يُقبل فقط ملفا PDF وDOCX للسيرة الذاتية.',
  },
  'ai.cv.emptyFile': { en: 'That file is empty.', ar: 'هذا الملف فارغ.' },
  'ai.cv.uploadFailed': {
    en: 'The CV could not be uploaded.',
    ar: 'تعذّر رفع السيرة الذاتية.',
  },
  'ai.cv.uploadAndAnalyse': { en: 'Upload & analyse', ar: 'رفع وتحليل' },
  'ai.cv.noModel': { en: 'No language model is configured', ar: 'لا يوجد نموذج لغوي مُهيّأ' },
  'ai.cv.incomplete': { en: 'The analysis did not complete', ar: 'لم يكتمل التحليل' },
  'ai.cv.storedNotAnalysed': {
    en: 'The CV was stored but could not be analysed.',
    ar: 'تم تخزين السيرة الذاتية لكن تعذّر تحليلها.',
  },

  'ai.assistant.askTitle': { en: 'Ask the SmartHR assistant', ar: 'اسأل مساعد SmartHR' },
};
