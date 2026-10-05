import { Dictionary } from '../types';

/**
 * AI Interview (Applicant) - a spoken interview for one of the applicant's jobs.
 *
 * Only the labels around the conversation are translated. The job title and
 * what the applicant and the interviewer actually *say* are shown exactly as
 * stored or transcribed.
 */
export const aiInterview: Dictionary = {
  'aiInterview.title': { en: 'AI Interview', ar: 'المقابلة الذكية' },
  'aiInterview.subtitle': {
    en: 'Talk with the SmartHR AI interviewer by voice.',
    ar: 'تحدّث صوتياً مع محاور SmartHR الذكي.',
  },
  'aiInterview.badge.notConfigured': { en: 'Voice service not configured', ar: 'الخدمة الصوتية غير مهيأة' },

  'aiInterview.notConfigured.title': {
    en: 'The voice service is not available yet',
    ar: 'الخدمة الصوتية غير متاحة بعد',
  },
  'aiInterview.notConfigured.body': {
    en: 'SmartHR has not been connected to its voice service. Please try again later or contact the recruitment team.',
    ar: 'لم يتم ربط SmartHR بخدمته الصوتية بعد. يرجى المحاولة لاحقاً أو التواصل مع فريق التوظيف.',
  },
  'aiInterview.error.statusTitle': {
    en: 'Could not check the voice service',
    ar: 'تعذّر التحقق من الخدمة الصوتية',
  },
  // Phase 11.6.1: failures told apart - never an exception's own text.
  'aiInterview.error.connection': {
    en: 'Could not connect to the interview room. Check your internet connection, then try again.',
    ar: 'تعذّر الاتصال بغرفة المقابلة. تحقّق من اتصالك بالإنترنت ثم حاول مرة أخرى.',
  },
  'aiInterview.error.startFailed': {
    en: 'The interview could not be started. Please try again.',
    ar: 'تعذّر بدء المقابلة. يُرجى المحاولة مرة أخرى.',
  },
  'aiInterview.error.disconnected': {
    en: 'The connection to the interview room was lost.',
    ar: 'انقطع الاتصال بغرفة المقابلة.',
  },
  'aiInterview.error.agentLeft': {
    en: 'The interviewer left before the interview finished.',
    ar: 'غادر المحاور قبل انتهاء المقابلة.',
  },

  // The job this interview is for.
  'aiInterview.job.label': { en: 'Interview for', ar: 'مقابلة لوظيفة' },
  'aiInterview.job.scheduled': { en: 'Scheduled {date}', ar: 'موعدها {date}' },
  'aiInterview.job.noDate': { en: 'No date set', ar: 'لم يُحدَّد موعد' },
  'aiInterview.job.choose': { en: 'Choose an interview', ar: 'اختر مقابلة' },
  'aiInterview.test.label': { en: 'Permanent development test', ar: 'مقابلة اختبار تطوير دائمة' },
  'aiInterview.test.badge': { en: 'DEVELOPMENT TEST', ar: 'اختبار تطوير' },
  'aiInterview.test.alwaysAvailable': {
    en: 'Available whenever you want to test',
    ar: 'متاحة كلما أردت إجراء اختبار',
  },
  'aiInterview.test.notice': {
    en: 'Development/testing only. This is not a real candidate interview.',
    ar: 'للتطوير والاختبار فقط. هذه ليست مقابلة مرشح فعلية.',
  },

  // Before starting.
  'aiInterview.ready.title': {
    en: "You're ready for your AI interview",
    ar: 'أنت جاهز لمقابلتك الذكية',
  },
  'aiInterview.ready.body': {
    en: "You'll answer questions about your experience and the position you're applying for. Make sure your microphone is working and you're somewhere quiet.",
    ar: 'ستجيب عن أسئلة حول خبرتك والوظيفة التي تقدّمت إليها. تأكّد من أن الميكروفون يعمل وأنك في مكان هادئ.',
  },
  'aiInterview.ready.tipOneAtATime': {
    en: 'The interviewer asks one question at a time.',
    ar: 'يطرح المحاور سؤالاً واحداً في كل مرة.',
  },
  'aiInterview.ready.tipPause': {
    en: 'Take your time - you can pause while you think.',
    ar: 'خذ وقتك، ويمكنك التوقف للتفكير.',
  },
  'aiInterview.ready.tipMicOnly': {
    en: 'Only your microphone is sent to the interviewer. The camera preview stays on your device.',
    ar: 'يُرسَل صوت الميكروفون فقط إلى المحاور، وتبقى معاينة الكاميرا على جهازك.',
  },

  // Before Start: how the interview and the answers are used. Each line states
  // only what SmartHR does - the transcript text is stored (never the audio),
  // each answer is analysed by AI, Admin/HR can read both, and nothing in it
  // is a hiring decision.
  'aiInterview.notice.title': {
    en: 'Before you start: how this interview works',
    ar: 'قبل أن تبدأ: كيف تعمل هذه المقابلة',
  },
  'aiInterview.notice.ai': {
    en: 'You will be interviewed by an AI interviewer, not a person.',
    ar: 'سيُجري معك المقابلة محاور يعمل بالذكاء الاصطناعي، وليس شخصاً.',
  },
  'aiInterview.notice.stored': {
    en: 'Your spoken answers are turned into text, and that text is saved. SmartHR does not save a recording of your voice.',
    ar: 'تُحوَّل إجاباتك المنطوقة إلى نص، ويُحفظ هذا النص. لا يحفظ SmartHR تسجيلاً لصوتك.',
  },
  'aiInterview.notice.analysed': {
    en: 'Each answer is analysed by AI to summarise what you said.',
    ar: 'تُحلَّل كل إجابة بالذكاء الاصطناعي لتلخيص ما قلته.',
  },
  'aiInterview.notice.hrReview': {
    en: 'The HR team can read your answers and the AI analysis.',
    ar: 'يمكن لفريق الموارد البشرية الاطلاع على إجاباتك وعلى تحليل الذكاء الاصطناعي.',
  },
  'aiInterview.notice.noDecision': {
    en: 'The AI does not make hiring decisions - people at the company do.',
    ar: 'لا يتخذ الذكاء الاصطناعي قرارات التوظيف، بل يتخذها موظفو الشركة.',
  },

  // Start window (Phase 10) - from the interview's opens_at / closes_at.
  'aiInterview.window.early': {
    en: 'You can start this interview from {time}. The Start button becomes available then.',
    ar: 'يمكنك بدء هذه المقابلة ابتداءً من {time}. سيصبح زر البدء متاحاً عندها.',
  },
  'aiInterview.window.open': {
    en: 'Available now - please start before {time}.',
    ar: 'متاحة الآن - يُرجى البدء قبل {time}.',
  },
  'aiInterview.window.late': {
    en: 'The time to start this interview ended at {time}. Please contact HR to reschedule.',
    ar: 'انتهى وقت بدء هذه المقابلة في {time}. يُرجى التواصل مع الموارد البشرية لإعادة جدولتها.',
  },

  // Why a Start was refused - by the backend's `code` (Phase 10).
  'aiInterview.errorCode.too_early': {
    en: 'This interview is not open yet. You can start it from {time}.',
    ar: 'هذه المقابلة غير متاحة بعد. يمكنك بدؤها ابتداءً من {time}.',
  },
  'aiInterview.errorCode.too_late': {
    en: 'The time to start this interview ended at {time}. Please contact HR to reschedule.',
    ar: 'انتهى وقت بدء هذه المقابلة في {time}. يُرجى التواصل مع الموارد البشرية لإعادة جدولتها.',
  },
  'aiInterview.errorCode.attempts_exhausted': {
    en: 'You have used all your attempts for this AI interview, so it cannot be started again. Please contact HR if you need help.',
    ar: 'لقد استخدمت جميع محاولاتك لهذه المقابلة الذكية، لذا لا يمكن بدؤها مرة أخرى. يُرجى التواصل مع الموارد البشرية إذا احتجت إلى مساعدة.',
  },
  'aiInterview.errorCode.attempt_finished': {
    en: 'This interview attempt has already ended and cannot be continued.',
    ar: 'انتهت محاولة المقابلة هذه بالفعل ولا يمكن متابعتها.',
  },
  'aiInterview.errorCode.session_active': {
    en: 'This interview is already running in another window or tab. Close it before starting again.',
    ar: 'هذه المقابلة قيد التشغيل بالفعل في نافذة أو علامة تبويب أخرى. أغلقها قبل البدء من جديد.',
  },
  'aiInterview.errorCode.completed': {
    en: 'This AI interview has already been completed and cannot be started again.',
    ar: 'اكتملت هذه المقابلة الذكية بالفعل ولا يمكن بدؤها مرة أخرى.',
  },
  'aiInterview.errorCode.not_approved': {
    en: 'This interview is not open for an AI interview: your application is not at the interview stage.',
    ar: 'هذه المقابلة غير متاحة كمقابلة ذكية: طلبك ليس في مرحلة المقابلة.',
  },
  'aiInterview.errorCode.not_found': {
    en: 'This interview could not be found or is no longer available.',
    ar: 'تعذّر العثور على هذه المقابلة أو لم تعد متاحة.',
  },
  'aiInterview.errorCode.not_configured': {
    en: 'The voice service is not available yet. Please try again later.',
    ar: 'الخدمة الصوتية غير متاحة بعد. يُرجى المحاولة لاحقاً.',
  },
  'aiInterview.complete.review': {
    en: 'This interview is finished. The HR team can now review your answers.',
    ar: 'انتهت هذه المقابلة. يمكن لفريق الموارد البشرية الآن مراجعة إجاباتك.',
  },

  // No interview.
  'aiInterview.noInterview.title': { en: 'No AI interview scheduled', ar: 'لا توجد مقابلة ذكية مجدولة' },
  'aiInterview.noInterview.body': {
    en: "When HR schedules an AI interview, you'll see it here.",
    ar: 'عندما يحدد فريق الموارد البشرية موعد مقابلة ذكية، ستظهر هنا.',
  },
  'aiInterview.noInterview.viewApplications': { en: 'View My Applications', ar: 'عرض طلباتي' },

  // The one applicant-facing state panel (Phase 11.6.1: each from a real source,
  // see viewStateOf in pages/applicant/aiInterviewRules.ts).
  'aiInterview.state.connecting': { en: 'Connecting…', ar: 'جارٍ الاتصال…' },
  'aiInterview.state.connectingHint': {
    en: 'Connecting you to the interview room.',
    ar: 'جارٍ توصيلك بغرفة المقابلة.',
  },
  'aiInterview.state.waiting': { en: 'Connected', ar: 'تم الاتصال' },
  'aiInterview.state.waitingHint': {
    en: 'The interviewer is joining. The interview starts when they speak.',
    ar: 'المحاور ينضم الآن. تبدأ المقابلة عندما يتحدث.',
  },
  'aiInterview.state.reconnecting': { en: 'Reconnecting…', ar: 'جارٍ إعادة الاتصال…' },
  'aiInterview.state.reconnectingHint': {
    en: 'The connection dropped. Please wait while it reconnects.',
    ar: 'انقطع الاتصال. يُرجى الانتظار حتى تتم إعادة الاتصال.',
  },
  'aiInterview.state.ending': { en: 'Finishing the interview', ar: 'جارٍ إنهاء المقابلة' },
  'aiInterview.state.endingHint': {
    en: 'The interviewer is closing the interview. Please listen.',
    ar: 'المحاور يختتم المقابلة. يُرجى الاستماع.',
  },
  'aiInterview.state.speaking': { en: 'Interviewer is speaking', ar: 'المحاور يتحدث' },
  'aiInterview.state.speakingHint': { en: 'Listen to the interviewer.', ar: 'استمع إلى المحاور.' },
  'aiInterview.state.yourTurn': { en: 'Your turn — speak now', ar: 'دورك — تحدّث الآن' },
  'aiInterview.state.yourTurnHint': {
    en: 'Take your time. You can pause while you think.',
    ar: 'خذ وقتك، ويمكنك التوقف للتفكير.',
  },
  'aiInterview.state.thinking': { en: 'Thinking…', ar: 'يفكّر…' },
  'aiInterview.state.thinkingHint': {
    en: 'Please wait - the interviewer will speak next.',
    ar: 'يُرجى الانتظار - سيتحدث المحاور بعد قليل.',
  },
  'aiInterview.state.stopped': { en: 'Interview ended', ar: 'انتهت المقابلة' },
  'aiInterview.state.stoppedHint': {
    en: 'The interview ended before all the questions were asked.',
    ar: 'انتهت المقابلة قبل طرح جميع الأسئلة.',
  },
  'aiInterview.state.failed': { en: 'Something went wrong', ar: 'حدث خطأ ما' },

  'aiInterview.progress.question': {
    en: 'Question {number} of {total}',
    ar: 'السؤال {number} من {total}',
  },
  'aiInterview.mic.label': { en: 'Your microphone', ar: 'الميكروفون الخاص بك' },
  'aiInterview.mic.hint': {
    en: 'The bar should move when you speak.',
    ar: 'يجب أن يتحرك الشريط عندما تتحدث.',
  },
  // LiveKit's own speaking flag for your microphone - about sound, never about the answer.
  'aiInterview.mic.speaking': { en: 'You are speaking.', ar: 'أنت تتحدث.' },
  'aiInterview.mic.notSpeaking': {
    en: 'Not hearing you yet - speak when you are ready.',
    ar: 'لا نسمعك بعد - تحدّث عندما تكون مستعداً.',
  },
  'aiInterview.mic.status.pending': { en: 'Microphone starting…', ar: 'جارٍ تشغيل الميكروفون…' },
  'aiInterview.mic.status.active': { en: 'Microphone on', ar: 'الميكروفون يعمل' },
  'aiInterview.mic.status.denied': { en: 'Microphone blocked', ar: 'الميكروفون محظور' },
  'aiInterview.mic.status.unavailable': { en: 'No microphone found', ar: 'لم يُعثر على ميكروفون' },
  'aiInterview.mic.status.error': { en: 'Microphone problem', ar: 'مشكلة في الميكروفون' },
  'aiInterview.mic.help.denied': {
    en: 'Your browser blocked the microphone. Allow microphone access for this site (usually from the icon next to the address bar), then press Try again.',
    ar: 'حظر المتصفح الميكروفون. اسمح لهذا الموقع باستخدام الميكروفون (عادةً من الأيقونة بجانب شريط العنوان)، ثم اضغط حاول مرة أخرى.',
  },
  'aiInterview.mic.help.unavailable': {
    en: 'No microphone was found. Connect a microphone, then press Try again.',
    ar: 'لم يُعثر على ميكروفون. وصّل ميكروفوناً، ثم اضغط حاول مرة أخرى.',
  },
  'aiInterview.mic.help.error': {
    en: 'Your microphone could not be started. Close other apps that may be using it, then press Try again.',
    ar: 'تعذّر تشغيل الميكروفون. أغلق التطبيقات الأخرى التي قد تستخدمه، ثم اضغط حاول مرة أخرى.',
  },

  // Whose turn - the current step is marked with text, not colour alone.
  'aiInterview.turn.label': { en: 'Whose turn', ar: 'دور من' },
  'aiInterview.turn.interviewer': { en: 'Interviewer speaks', ar: 'المحاور يتحدث' },
  'aiInterview.turn.you': { en: 'Your turn', ar: 'دورك' },
  'aiInterview.turn.thinking': { en: 'Thinking', ar: 'يفكّر' },
  'aiInterview.turn.now': { en: 'Now', ar: 'الآن' },

  // LiveKit's room connection state.
  'aiInterview.connection.label': { en: 'Connection', ar: 'الاتصال' },
  'aiInterview.connection.connecting': { en: 'connecting', ar: 'جارٍ الاتصال' },
  'aiInterview.connection.connected': { en: 'connected', ar: 'متصل' },
  'aiInterview.connection.reconnecting': { en: 'reconnecting', ar: 'جارٍ إعادة الاتصال' },
  'aiInterview.connection.disconnected': { en: 'disconnected', ar: 'غير متصل' },

  // Finished.
  'aiInterview.complete.title': { en: 'Interview complete', ar: 'اكتملت المقابلة' },
  // No one is notified automatically, so nothing more is promised.
  'aiInterview.complete.body': {
    en: 'Thank you for taking part in your interview. You can close this page.',
    ar: 'شكرًا لمشاركتك في المقابلة. يمكنك إغلاق هذه الصفحة.',
  },
  // "Completed" reported before any question was presented: the interview
  // could not go ahead. Neutral - it does not claim a completed interview.
  'aiInterview.ended.title': { en: 'Interview ended', ar: 'انتهت المقابلة' },
  'aiInterview.ended.body': {
    en: 'The interview could not continue. You can close this page.',
    ar: 'تعذر متابعة المقابلة. يمكنك إغلاق هذه الصفحة.',
  },

  // Starting again - deliberately secondary and confirmed.
  'aiInterview.restart.link': { en: 'Start a new interview session', ar: 'بدء جلسة مقابلة جديدة' },
  'aiInterview.restart.confirm': {
    en: 'This starts the interview again from the first question. Continue?',
    ar: 'سيؤدي ذلك إلى بدء المقابلة من جديد من السؤال الأول. هل تريد المتابعة؟',
  },
  'aiInterview.restart.yes': { en: 'Yes, start again', ar: 'نعم، ابدأ من جديد' },
  'aiInterview.restart.cancel': { en: 'Cancel', ar: 'إلغاء' },

  'aiInterview.action.start': { en: 'Start AI Interview', ar: 'بدء المقابلة الذكية' },
  'aiInterview.action.retry': { en: 'Try again', ar: 'حاول مرة أخرى' },
  'aiInterview.action.end': { en: 'End interview', ar: 'إنهاء المقابلة' },
  'aiInterview.action.enableAudio': { en: 'Enable interviewer audio', ar: 'تفعيل صوت المحاور' },
  'aiInterview.language.title': { en: 'Choose interview language', ar: 'اختر لغة المقابلة' },
  'aiInterview.language.subtitle': {
    en: 'Sets speech recognition and GPT-generated replies. Question Bank text and fixed prompts are not translated.',
    ar: 'يحدد لغة التعرّف على الكلام وردود المحاور التي ينشئها GPT. لا تُترجم أسئلة البنك أو العبارات الثابتة.',
  },
  'aiInterview.language.label': { en: 'Language', ar: 'اللغة' },
  'aiInterview.language.choose': { en: 'Select a language', ar: 'اختر لغة' },
  'aiInterview.language.english': { en: 'English', ar: 'الإنجليزية' },
  'aiInterview.language.arabic': { en: 'Arabic', ar: 'العربية' },
  'aiInterview.language.cancel': { en: 'Cancel', ar: 'إلغاء' },
  'aiInterview.language.continue': { en: 'Continue', ar: 'متابعة' },

  'aiInterview.transcript.title': { en: 'Transcript', ar: 'نص المحادثة' },
  'aiInterview.transcript.subtitle': {
    en: 'What the interviewer heard you say, and what it replied. Your answers are saved as text, as explained before you started.',
    ar: 'ما سمعه المحاور منك وما ردّ به. تُحفظ إجاباتك نصاً، كما وُضّح قبل أن تبدأ.',
  },
  'aiInterview.transcript.connecting': {
    en: 'Connecting you to the interviewer…',
    ar: 'جارٍ توصيلك بالمحاور…',
  },
  'aiInterview.transcript.waiting': {
    en: 'Waiting for the interviewer to speak…',
    ar: 'بانتظار أن يتحدث المحاور…',
  },
  'aiInterview.transcript.none': {
    en: 'Nothing was said in this session.',
    ar: 'لم يُقل شيء في هذه الجلسة.',
  },
  'aiInterview.transcript.you': { en: 'You', ar: 'أنت' },
  'aiInterview.transcript.interviewer': { en: 'Interviewer', ar: 'المحاور' },

  // Collapsed support details - not part of the normal applicant view.
  'aiInterview.tech.title': { en: 'Technical details', ar: 'تفاصيل تقنية' },
  'aiInterview.tech.connection': { en: 'Connection', ar: 'الاتصال' },
  'aiInterview.tech.interviewer': { en: 'Interviewer', ar: 'المحاور' },
  'aiInterview.tech.interviewState': { en: 'Interview state', ar: 'حالة المقابلة' },
  'aiInterview.tech.models': {
    en: 'Speech-to-text: {stt} · Interviewer: {llm} · Voice: {tts}',
    ar: 'تحويل الكلام إلى نص: {stt} · المحاور: {llm} · الصوت: {tts}',
  },
  'aiInterview.phase.idle': { en: 'Not connected', ar: 'غير متصل' },
  'aiInterview.phase.connecting': { en: 'Connecting…', ar: 'جارٍ الاتصال…' },
  'aiInterview.phase.connected': { en: 'Connected', ar: 'متصل' },
  'aiInterview.phase.ended': { en: 'Ended', ar: 'انتهت' },
  'aiInterview.phase.error': { en: 'Failed', ar: 'فشل' },
  'aiInterview.agent.absent': { en: 'Not in the room', ar: 'ليس في الغرفة' },
  'aiInterview.agentState.initializing': { en: 'Getting ready', ar: 'يستعد' },
  'aiInterview.agentState.idle': { en: 'Ready', ar: 'جاهز' },
  'aiInterview.agentState.listening': { en: 'Listening', ar: 'يستمع' },
  'aiInterview.agentState.thinking': { en: 'Thinking', ar: 'يفكّر' },
  'aiInterview.agentState.speaking': { en: 'Speaking', ar: 'يتحدث' },
  'aiInterview.interviewState.waiting': { en: 'Waiting', ar: 'في الانتظار' },
  'aiInterview.interviewState.intro': { en: 'Welcome', ar: 'الترحيب' },
  'aiInterview.interviewState.asking': { en: 'Asking a question', ar: 'يطرح سؤالاً' },
  'aiInterview.interviewState.listening': { en: 'Listening', ar: 'يستمع' },
  'aiInterview.interviewState.processing': { en: 'Processing', ar: 'يعالج' },
  'aiInterview.interviewState.follow_up_decision': { en: 'Considering a follow-up', ar: 'يدرس سؤال متابعة' },
  'aiInterview.interviewState.adaptive_selection': { en: 'Choosing the next question', ar: 'يختار السؤال التالي' },
  'aiInterview.interviewState.speaking': { en: 'Responding', ar: 'يرد' },
  'aiInterview.interviewState.ending': { en: 'Closing', ar: 'يختتم' },
  'aiInterview.interviewState.completed': { en: 'Completed', ar: 'اكتملت' },

  // Entry points on My Applications and the Dashboard.
  'aiInterview.entry.title': { en: 'AI interview scheduled', ar: 'مقابلة ذكية مجدولة' },
  'aiInterview.entry.more': {
    en: '+{count} more AI interview(s)',
    ar: '+{count} مقابلات ذكية أخرى',
  },

  // Camera video is transmitted through the LiveKit interview session;
  // face counting remains on-device.
  'aiInterview.camera.notice': {
    en: 'Camera video is used during your AI interview and transmitted through the LiveKit interview session.',
    ar: 'يُستخدم فيديو الكاميرا أثناء مقابلتك الذكية ويُنقل عبر جلسة المقابلة في LiveKit.',
  },
  'aiInterview.camera.label': { en: 'Your camera preview', ar: 'معاينة الكاميرا' },
  'aiInterview.camera.status.pending': { en: 'Starting camera preview…', ar: 'جارٍ تشغيل معاينة الكاميرا…' },
  'aiInterview.camera.status.off': { en: 'Camera preview is off.', ar: 'معاينة الكاميرا متوقفة.' },
  'aiInterview.camera.status.denied': {
    en: 'Camera access was blocked. Allow the camera for this site in your browser to see the preview. The interview works without it.',
    ar: 'تم حظر الوصول إلى الكاميرا. اسمح باستخدام الكاميرا لهذا الموقع في المتصفح لرؤية المعاينة. تعمل المقابلة من دونها.',
  },
  'aiInterview.camera.status.unavailable': {
    en: 'No camera was found on this device. The interview works without it.',
    ar: 'لم يُعثر على كاميرا في هذا الجهاز. تعمل المقابلة من دونها.',
  },
  'aiInterview.camera.status.error': {
    en: 'The camera could not be started - it may be in use by another app. The interview works without it.',
    ar: 'تعذّر تشغيل الكاميرا، فقد تكون مستخدمة من تطبيق آخر. تعمل المقابلة من دونها.',
  },
  'aiInterview.camera.turnOn': { en: 'Turn on camera preview', ar: 'تشغيل معاينة الكاميرا' },
  'aiInterview.camera.retry': { en: 'Try the camera again', ar: 'إعادة محاولة تشغيل الكاميرا' },
  // Stage 2: the local face count shown under the preview (2 = "2+").
  // Never gaze / landmarks / emotion / identity - count only.
  'aiInterview.camera.faces.zero': { en: 'No face detected', ar: 'لم يُكتشَف أي وجه' },
  'aiInterview.camera.faces.one': { en: '1 face detected', ar: 'تم اكتشاف وجه واحد' },
  'aiInterview.camera.faces.two': { en: '2+ faces detected', ar: 'تم اكتشاف وجهين أو أكثر' },
  'aiInterview.camera.faces.unavailable': {
    en: 'Face detection is unavailable on this device. The camera preview still works.',
    ar: 'اكتشاف الوجوه غير متاح على هذا الجهاز. تظل معاينة الكاميرا تعمل.',
  },
  // Stage 3: sustained-condition display (metadata only - calm wording, never
  // a warning, never an accusation; nothing here stops or affects anything).
  'aiInterview.camera.proctor.normal': { en: 'Camera check: normal', ar: 'فحص الكاميرا: طبيعي' },
  'aiInterview.camera.proctor.no_face': { en: 'Camera check: no face detected', ar: 'فحص الكاميرا: لم يُكتشَف أي وجه' },
  'aiInterview.camera.proctor.multiple_faces': { en: 'Camera check: multiple faces detected', ar: 'فحص الكاميرا: تم اكتشاف أكثر من وجه' },
  'aiInterview.camera.proctor.no_face_sustained': {
    en: 'Camera check: no face sustained',
    ar: 'فحص الكاميرا: استمرار عدم ظهور وجه',
  },
  'aiInterview.camera.proctor.multiple_faces_sustained': {
    en: 'Camera check: multiple faces sustained',
    ar: 'فحص الكاميرا: استمرار ظهور أكثر من وجه',
  },
};
