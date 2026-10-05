import { Dictionary } from '../types';

/**
 * Social Hub - feed, stories, people, connections, messages, profile.
 *
 * Not translated, following the existing rules:
 *
 *   * **post content, comments, story captions and messages** - these are
 *     written by colleagues in whichever language they chose, and are database
 *     values. Re-rendering them in the other language would fabricate a second
 *     version of what somebody said.
 *   * **people's names, email addresses, department and position names,
 *     training titles** - database values, shown exactly as stored.
 *   * **notification sentences** - stored on the `notifications` row, like
 *     every other notification in SmartHR. Only the category label around one
 *     is translated (`social.notify.kind.*`).
 */
export const social: Dictionary = {
  // --- Workspace and navigation ------------------------------------------
  'workspace.social': { en: 'Social', ar: 'المجتمع' },
  'workspace.social.short': { en: 'Social', ar: 'المجتمع' },
  'workspace.social.section': { en: 'Social Hub', ar: 'مركز التواصل' },

  'nav.soc-feed': { en: 'Feed', ar: 'آخر المستجدات' },
  'nav.soc-people': { en: 'People', ar: 'الزملاء' },
  'nav.soc-messages': { en: 'Messages', ar: 'الرسائل' },
  'nav.soc-profile': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'nav.soc-notifications': { en: 'Notifications', ar: 'الإشعارات' },
  'nav.hr-social-moderation': {
    en: 'Social Moderation',
    ar: 'مراجعة محتوى التواصل',
  },

  'page.soc-feed': { en: 'Social Feed', ar: 'آخر المستجدات' },
  'page.soc-people': { en: 'People', ar: 'الزملاء' },
  'page.soc-messages': { en: 'Messages', ar: 'الرسائل' },
  'page.soc-profile': { en: 'Social Profile', ar: 'الملف الاجتماعي' },
  'page.soc-notifications': {
    en: 'Social Notifications',
    ar: 'إشعارات مركز التواصل',
  },
  'page.hr-social-moderation': {
    en: 'Social Moderation',
    ar: 'مراجعة محتوى التواصل',
  },

  // --- Feed ---------------------------------------------------------------
  'social.feed.title': { en: 'Social Feed', ar: 'آخر المستجدات' },
  'social.feed.subtitle': {
    en: 'What your colleagues are sharing across SmartHR.',
    ar: 'ما يشاركه زملاؤك عبر SmartHR.',
  },
  'social.feed.count': {
    en: '{count} posts',
    ar: '{count} منشور',
  },
  'social.empty.findPeople': { en: 'Find people', ar: 'ابحث عن زملاء' },
  'social.feed.scope.all': { en: 'All Posts', ar: 'كل المنشورات' },
  'social.feed.scope.department': { en: 'My Department', ar: 'قسمي' },
  'social.feed.scope.following': { en: 'Following', ar: 'من أتابعهم' },
  'social.feed.scope.company': { en: 'Company Updates', ar: 'أخبار الشركة' },
  'social.feed.scope.companyHint': {
    en: 'Posts from HR and Administration.',
    ar: 'منشورات الموارد البشرية والإدارة.',
  },
  'social.feed.empty.title': { en: 'No posts yet', ar: 'لا توجد منشورات بعد' },
  'social.feed.empty.body': {
    en: 'Be the first to share something with your colleagues.',
    ar: 'كن أول من يشارك شيئًا مع زملائه.',
  },
  'social.feed.empty.department': {
    en: 'Nobody in your department has posted yet.',
    ar: 'لم ينشر أحد في قسمك بعد.',
  },
  'social.feed.empty.following': {
    en: 'Posts from colleagues you are connected with will appear here.',
    ar: 'ستظهر هنا منشورات الزملاء المتصلين بك.',
  },
  'social.feed.empty.company': {
    en: 'There are no company updates yet.',
    ar: 'لا توجد أخبار للشركة بعد.',
  },
  'social.feed.noDepartment': {
    en: 'Your account is not linked to an employee record, so it has no department to filter by.',
    ar: 'حسابك غير مرتبط بسجل موظف، لذا لا يوجد قسم للتصفية حسبه.',
  },
  'social.feed.loadError': {
    en: 'The feed could not be loaded.',
    ar: 'تعذّر تحميل آخر المستجدات.',
  },

  // --- Create post --------------------------------------------------------
  'social.compose.placeholder': {
    en: 'What’s on your mind, {name}?',
    ar: 'بماذا تفكّر يا {name}؟',
  },
  'social.compose.post': { en: 'Post', ar: 'نشر' },
  'social.compose.photo': { en: 'Photo', ar: 'صورة' },
  'social.compose.removePhoto': { en: 'Remove photo', ar: 'إزالة الصورة' },
  'social.compose.audience': { en: 'Share with', ar: 'مشاركة مع' },
  'social.compose.audience.company': { en: 'Everyone', ar: 'الجميع' },
  'social.compose.audience.department': { en: 'My department', ar: 'قسمي' },
  'social.compose.posted': { en: 'Post shared', ar: 'تم نشر المنشور' },
  'social.compose.postedBody': {
    en: 'Your colleagues can see it on the feed.',
    ar: 'يمكن لزملائك رؤيته في آخر المستجدات.',
  },
  'social.compose.failed': { en: 'Could not share the post', ar: 'تعذّر نشر المنشور' },
  'social.compose.imageTooLarge': {
    en: 'Images must be 4 MB or smaller.',
    ar: 'يجب أن تكون الصور بحجم ٤ ميغابايت أو أقل.',
  },
  'social.compose.imageType': {
    en: 'Only PNG, JPEG, GIF and WebP images can be uploaded.',
    ar: 'يمكن رفع صور PNG وJPEG وGIF وWebP فقط.',
  },

  // --- Post card ----------------------------------------------------------
  'social.post.like': { en: 'Like', ar: 'إعجاب' },
  'social.post.liked': { en: 'Liked', ar: 'أعجبني' },
  'social.post.comment': { en: 'Comment', ar: 'تعليق' },
  'social.post.likeCount': { en: '{count} like(s)', ar: '{count} إعجاب' },
  'social.post.commentCount': { en: '{count} comment(s)', ar: '{count} تعليق' },
  'social.post.edited': { en: 'Edited', ar: 'مُعدَّل' },
  'social.post.edit': { en: 'Edit post', ar: 'تعديل المنشور' },
  'social.post.delete': { en: 'Delete post', ar: 'حذف المنشور' },
  'social.post.deleteConfirm': {
    en: 'Delete this post? Its comments and likes go with it, and it cannot be undone.',
    ar: 'هل تريد حذف هذا المنشور؟ ستُحذف تعليقاته وإعجاباته معه، ولا يمكن التراجع.',
  },
  'social.post.deleted': { en: 'Post deleted', ar: 'تم حذف المنشور' },
  'social.post.updated': { en: 'Post updated', ar: 'تم تحديث المنشور' },
  'social.post.saveEdit': { en: 'Save changes', ar: 'حفظ التغييرات' },
  'social.post.toDepartment': { en: 'To {department}', ar: 'إلى {department}' },
  'social.post.imageAlt': {
    en: 'Image attached to a post by {name}',
    ar: 'صورة مرفقة بمنشور من {name}',
  },
  'social.post.actionFailed': {
    en: 'That did not work',
    ar: 'لم تنجح العملية',
  },

  // --- Comments -----------------------------------------------------------
  'social.comments.placeholder': { en: 'Write a comment…', ar: 'اكتب تعليقًا…' },
  'social.comments.send': { en: 'Comment', ar: 'تعليق' },
  'social.comments.empty': {
    en: 'No comments yet — say something.',
    ar: 'لا توجد تعليقات بعد — شارك برأيك.',
  },
  'social.comments.delete': { en: 'Delete comment', ar: 'حذف التعليق' },
  'social.comments.deleted': { en: 'Comment deleted', ar: 'تم حذف التعليق' },
  'social.comments.loadError': {
    en: 'The comments could not be loaded.',
    ar: 'تعذّر تحميل التعليقات.',
  },

  // --- Stories ------------------------------------------------------------
  'social.stories.title': { en: 'Stories', ar: 'القصص' },
  'social.stories.add': { en: 'Add story', ar: 'إضافة قصة' },
  'social.stories.yours': { en: 'Your story', ar: 'قصتك' },
  'social.stories.empty': { en: 'No active stories', ar: 'لا توجد قصص نشطة' },
  'social.stories.create': { en: 'Share a story', ar: 'مشاركة قصة' },
  'social.stories.caption': { en: 'Caption', ar: 'التعليق' },
  'social.stories.captionPlaceholder': {
    en: 'Say something about it…',
    ar: 'قل شيئًا عنها…',
  },
  'social.stories.needSomething': {
    en: 'A story needs an image or some text.',
    ar: 'تحتاج القصة إلى صورة أو نص.',
  },
  'social.stories.shared': { en: 'Story shared', ar: 'تمت مشاركة القصة' },
  'social.stories.sharedBody': {
    en: 'It disappears in 24 hours.',
    ar: 'ستختفي خلال ٢٤ ساعة.',
  },
  'social.stories.expiresIn': { en: 'Expires in {hours}h', ar: 'تنتهي خلال {hours} ساعة' },
  'social.stories.expiringSoon': { en: 'Expires in under an hour', ar: 'تنتهي خلال أقل من ساعة' },
  'social.stories.viewCount': { en: 'Seen by {count}', ar: 'شاهدها {count}' },
  'social.stories.delete': { en: 'Delete story', ar: 'حذف القصة' },
  'social.stories.deleted': { en: 'Story deleted', ar: 'تم حذف القصة' },
  'social.stories.next': { en: 'Next story', ar: 'القصة التالية' },
  'social.stories.previous': { en: 'Previous story', ar: 'القصة السابقة' },
  'social.stories.imageAlt': { en: 'Story by {name}', ar: 'قصة من {name}' },

  // --- People -------------------------------------------------------------
  // --- Notifications ------------------------------------------------------
  //
  // The sentence on a notification is stored text and is rendered exactly as
  // written, like every other database value. These are the labels *around*
  // it: the category of the row, the controls, and the empty states.
  'social.notifications.title': { en: 'Notifications', ar: 'الإشعارات' },
  'social.notifications.subtitle': {
    en: 'Connection requests, reactions and replies from your colleagues.',
    ar: 'طلبات التواصل والتفاعلات والردود من زملائك.',
  },
  'social.notifications.loadError': {
    en: 'Notifications could not be loaded.',
    ar: 'تعذّر تحميل الإشعارات.',
  },
  'social.notifications.markRead': { en: 'Mark read', ar: 'تعليم كمقروء' },
  'social.notifications.markAll': {
    en: 'Mark all read',
    ar: 'تعليم الكل كمقروء',
  },
  'social.notifications.markFailed': {
    en: 'The notification could not be updated.',
    ar: 'تعذّر تحديث الإشعار.',
  },
  'social.notifications.filter.all': { en: 'All', ar: 'الكل' },
  'social.notifications.filter.unread': { en: 'Unread', ar: 'غير المقروءة' },
  'social.notifications.empty.title': {
    en: 'Nothing here yet',
    ar: 'لا يوجد شيء بعد' ,
  },
  'social.notifications.empty.body': {
    en: 'When a colleague connects with you, reacts to a post or replies, it will appear here.',
    ar: 'عندما يتواصل معك زميل أو يتفاعل مع منشور أو يرد، سيظهر ذلك هنا.',
  },
  'social.notifications.empty.unreadTitle': {
    en: 'You are all caught up',
    ar: 'اطّلعت على كل شيء',
  },
  'social.notifications.empty.unreadBody': {
    en: 'Every notification has been read.',
    ar: 'تمت قراءة جميع الإشعارات.',
  },
  'social.notifications.type.social_connection_request': {
    en: 'Connection request',
    ar: 'طلب تواصل',
  },
  'social.notifications.type.social_connection_accepted': {
    en: 'Connection accepted',
    ar: 'تم قبول التواصل',
  },
  'social.notifications.type.social_comment': { en: 'Comment', ar: 'تعليق' },
  'social.notifications.type.social_reaction': { en: 'Reaction', ar: 'تفاعل' },
  'social.notifications.type.social_message': { en: 'Message', ar: 'رسالة' },
  'social.notifications.type.other': { en: 'Update', ar: 'تحديث' },

  'social.stories.expiryNote': {
    en: 'Stories disappear after 24 hours',
    ar: 'تختفي القصص بعد ٢٤ ساعة',
  },

  'social.people.title': { en: 'People', ar: 'الزملاء' },
  'social.people.subtitle': {
    en: 'Discover and connect with colleagues across SmartHR.',
    ar: 'اكتشف زملاءك في SmartHR وتواصل معهم.',
  },
  'social.people.directory': { en: 'Directory', ar: 'دليل الزملاء' },
  'social.people.allPositions': {
    en: 'All positions',
    ar: 'كل المسميات الوظيفية',
  },
  'social.people.clearFilters': {
    en: 'Clear filters',
    ar: 'مسح عوامل التصفية',
  },
  'social.people.search': {
    en: 'Search by name, department or position',
    ar: 'ابحث بالاسم أو القسم أو المسمى الوظيفي',
  },
  'social.people.allDepartments': { en: 'All departments', ar: 'كل الأقسام' },
  'social.people.count': { en: '{count} colleague(s)', ar: '{count} زميل' },
  'social.people.empty.title': { en: 'No colleagues found', ar: 'لم يُعثر على زملاء' },
  'social.people.empty.body': {
    en: 'No one in the directory matches what you searched for.',
    ar: 'لا أحد في الدليل يطابق ما بحثت عنه.',
  },
  'social.people.none.title': {
    en: 'Start connecting with your colleagues',
    ar: 'ابدأ التواصل مع زملائك',
  },
  'social.people.none.body': {
    en: 'Colleagues appear here once they have a SmartHR account they can sign in with.',
    ar: 'يظهر الزملاء هنا بمجرد امتلاكهم حساب SmartHR يمكنهم تسجيل الدخول به.',
  },
  'social.people.accountsOnly': {
    en: 'This directory lists colleagues who have a SmartHR account, because a connection request or a message needs someone who can answer it.',
    ar: 'يعرض هذا الدليل الزملاء الذين لديهم حساب SmartHR، لأن طلب التواصل أو الرسالة يحتاج إلى من يستطيع الرد عليها.',
  },
  'social.people.suggested': { en: 'People you may know', ar: 'أشخاص قد تعرفهم' },
  'social.people.suggestedEmpty': {
    en: 'You are connected with everyone in the directory.',
    ar: 'أنت متصل بجميع من في الدليل.',
  },
  'social.people.noDepartment': { en: 'No department', ar: 'بدون قسم' },
  'social.people.noPosition': { en: 'No position on record', ar: 'لا يوجد مسمى وظيفي مسجّل' },

  // --- Connections --------------------------------------------------------
  'social.connect.connect': { en: 'Connect', ar: 'تواصل' },
  'social.connect.pending': { en: 'Request sent', ar: 'تم إرسال الطلب' },
  'social.connect.accept': { en: 'Accept', ar: 'قبول' },
  'social.connect.reject': { en: 'Decline', ar: 'رفض' },
  'social.connect.connected': { en: 'Connected', ar: 'متصل' },
  'social.connect.disconnect': { en: 'Disconnect', ar: 'إلغاء الاتصال' },
  'social.connect.disconnectConfirm': {
    en: 'Disconnect from {name}?',
    ar: 'إلغاء الاتصال مع {name}؟',
  },
  'social.connect.message': { en: 'Message', ar: 'مراسلة' },
  'social.connect.requestSent': { en: 'Request sent', ar: 'تم إرسال الطلب' },
  'social.connect.requestSentBody': {
    en: '{name} will see it on their Social Hub.',
    ar: 'سيراه {name} في مركز التواصل الخاص به.',
  },
  'social.connect.accepted': { en: 'Connected', ar: 'تم الاتصال' },
  'social.connect.rejected': { en: 'Request declined', ar: 'تم رفض الطلب' },
  'social.connect.removed': { en: 'Disconnected', ar: 'تم إلغاء الاتصال' },
  'social.connect.failed': { en: 'That did not work', ar: 'لم تنجح العملية' },
  'social.connect.requests': { en: 'Connection requests', ar: 'طلبات التواصل' },
  'social.connect.myConnections': { en: 'My connections', ar: 'اتصالاتي' },
  'social.connect.count': { en: '{count} connection(s)', ar: '{count} اتصال' },

  // --- Messages -----------------------------------------------------------
  'social.messages.title': { en: 'Messages', ar: 'الرسائل' },
  'social.messages.subtitle': {
    en: 'Private conversations with your colleagues.',
    ar: 'محادثات خاصة مع زملائك.',
  },
  'social.messages.conversations': { en: 'Conversations', ar: 'المحادثات' },
  'social.messages.empty.title': { en: 'No conversations yet', ar: 'لا توجد محادثات بعد' },
  'social.messages.empty.body': {
    en: 'Open a colleague’s profile and choose Message to start one.',
    ar: 'افتح ملف زميل واختر «مراسلة» لبدء محادثة.',
  },
  'social.messages.pickOne': {
    en: 'Choose a conversation',
    ar: 'اختر محادثة',
  },
  'social.messages.pickOneBody': {
    en: 'Select someone on the left to read and reply.',
    ar: 'اختر شخصًا من القائمة للقراءة والرد.',
  },
  'social.messages.placeholder': { en: 'Write a message…', ar: 'اكتب رسالة…' },
  'social.messages.send': { en: 'Send', ar: 'إرسال' },
  'social.messages.noMessages': {
    en: 'No messages yet — say hello.',
    ar: 'لا توجد رسائل بعد — ألقِ التحية.',
  },
  'social.messages.backToList': { en: 'Back to conversations', ar: 'العودة إلى المحادثات' },
  'social.messages.failed': { en: 'The message was not sent', ar: 'لم تُرسَل الرسالة' },
  'social.messages.loadError': {
    en: 'The conversation could not be loaded.',
    ar: 'تعذّر تحميل المحادثة.',
  },
  'social.messages.privateNote': {
    en: 'Only the two of you can read this conversation.',
    ar: 'أنتما فقط من يمكنكما قراءة هذه المحادثة.',
  },

  // --- Profile ------------------------------------------------------------
  'social.profile.title': { en: 'Profile', ar: 'الملف الشخصي' },
  'social.profile.subtitle': {
    en: 'A colleague’s profile in the employee network.',
    ar: 'ملف زميل في شبكة الموظفين.',
  },
  'social.profile.mineTitle': { en: 'My Profile', ar: 'ملفي الشخصي' },
  'social.profile.mineSubtitle': {
    en: 'How you appear to colleagues across SmartHR.',
    ar: 'كيف تظهر لزملائك في SmartHR.',
  },
  'social.profile.tab.posts': { en: 'Posts', ar: 'المنشورات' },
  'social.profile.tab.about': { en: 'About', ar: 'نبذة' },
  'social.profile.tab.achievements': { en: 'Achievements', ar: 'الإنجازات' },
  'social.profile.edit': { en: 'Edit profile', ar: 'تعديل الملف' },
  'social.profile.save': { en: 'Save profile', ar: 'حفظ الملف' },
  'social.profile.saved': { en: 'Profile updated', ar: 'تم تحديث الملف' },
  'social.profile.saveFailed': { en: 'Could not save the profile', ar: 'تعذّر حفظ الملف' },
  'social.profile.headline': { en: 'Headline', ar: 'العنوان المختصر' },
  'social.profile.headlinePlaceholder': {
    en: 'A line about what you do',
    ar: 'سطر عمّا تقوم به',
  },
  'social.profile.bio': { en: 'About', ar: 'نبذة' },
  'social.profile.bioPlaceholder': {
    en: 'A short introduction for your colleagues',
    ar: 'تعريف قصير لزملائك',
  },
  'social.profile.skills': { en: 'Skills', ar: 'المهارات' },
  'social.profile.skillsPlaceholder': {
    en: 'Separate skills with commas',
    ar: 'افصل بين المهارات بفواصل',
  },
  'social.profile.interests': { en: 'Interests', ar: 'الاهتمامات' },
  'social.profile.interestsPlaceholder': {
    en: 'Separate interests with commas',
    ar: 'افصل بين الاهتمامات بفواصل',
  },
  'social.profile.location': { en: 'Location', ar: 'الموقع' },
  'social.profile.locationPlaceholder': { en: 'Where you are based', ar: 'مقر عملك' },
  'social.profile.changeAvatar': { en: 'Change photo', ar: 'تغيير الصورة' },
  'social.profile.avatarUpdated': { en: 'Photo updated', ar: 'تم تحديث الصورة' },
  'social.profile.avatarAlt': { en: 'Profile photo of {name}', ar: 'الصورة الشخصية لـ {name}' },
  'social.profile.noBio': {
    en: 'Nothing here yet.',
    ar: 'لا يوجد شيء هنا بعد.',
  },
  'social.profile.noBioMine': {
    en: 'Add a short introduction so colleagues know what you work on.',
    ar: 'أضف تعريفًا قصيرًا ليعرف الزملاء ما تعمل عليه.',
  },
  'social.profile.noSkills': { en: 'No skills listed yet.', ar: 'لا توجد مهارات مدرجة بعد.' },
  'social.profile.noPosts': { en: 'No posts yet', ar: 'لا توجد منشورات بعد' },
  'social.profile.noPostsMine': {
    en: 'Anything you share on the feed appears here.',
    ar: 'يظهر هنا كل ما تشاركه في آخر المستجدات.',
  },
  'social.profile.noPostsOther': {
    en: '{name} has not posted anything yet.',
    ar: 'لم ينشر {name} أي شيء بعد.',
  },
  'social.profile.achievements.empty': {
    en: 'No achievements recorded yet',
    ar: 'لا توجد إنجازات مسجّلة بعد',
  },
  'social.profile.achievements.emptyBody': {
    en: 'Completed training and time at SmartHR appear here as they are recorded.',
    ar: 'تظهر هنا الدورات المكتملة ومدة العمل في SmartHR عند تسجيلها.',
  },
  'social.profile.achievements.note': {
    en: 'Built from completed training and joining date only. Performance reviews, attendance and leave are never shown on a social profile.',
    ar: 'مبنية على الدورات المكتملة وتاريخ الالتحاق فقط. لا تُعرض تقييمات الأداء أو الحضور أو الإجازات في الملف الاجتماعي أبدًا.',
  },
  'social.profile.achievement.tenure': {
    en: 'Joined SmartHR',
    ar: 'انضم إلى SmartHR',
  },
  'social.profile.achievement.years': {
    en: '{count} year(s) with the company',
    ar: '{count} سنة في الشركة',
  },
  'social.profile.achievement.training': {
    en: 'Completed training',
    ar: 'دورة مكتملة',
  },
  'social.profile.notFound': {
    en: 'That person is not in the SmartHR directory.',
    ar: 'هذا الشخص ليس ضمن دليل SmartHR.',
  },
  'social.profile.unlinkedAccount': {
    en: 'This account is not linked to an employee record, so SmartHR has no department or position for it.',
    ar: 'هذا الحساب غير مرتبط بسجل موظف، لذا لا يعرف SmartHR قسمه أو مسماه الوظيفي.',
  },
  'social.profile.backToPeople': { en: 'Back to People', ar: 'العودة إلى الزملاء' },

  // --- Notifications ------------------------------------------------------

  // --- AI Moderation ------------------------------------------------------
  //
  // Two audiences, and the split matters. `social.pending.*` is what an
  // AUTHOR sees about their own held content: a status and nothing more.
  // Everything under `social.moderation.*` belongs to the HR review page,
  // which no other role can open.
  'social.pending.badge': { en: 'Pending review', ar: 'قيد المراجعة' },
  'social.pending.notice': {
    en: 'Your content is pending review and is not visible to colleagues yet.',
    ar: 'المحتوى الخاص بك قيد المراجعة ولا يظهر لزملائك بعد.',
  },
  'social.pending.postToast': {
    en: 'Posted - pending review',
    ar: 'تم النشر - قيد المراجعة',
  },
  'social.pending.commentToast': {
    en: 'Comment sent - pending review',
    ar: 'تم إرسال التعليق - قيد المراجعة',
  },
  'social.pending.storyToast': {
    en: 'Story added - pending review',
    ar: 'تمت إضافة القصة - قيد المراجعة',
  },

  'social.moderation.title': { en: 'Social Moderation', ar: 'مراجعة محتوى التواصل' },
  'social.moderation.subtitle': {
    en: 'Content held for review. You decide what happens to it.',
    ar: 'محتوى محجوز للمراجعة. القرار النهائي لك.',
  },
  'social.moderation.loadError': {
    en: 'The moderation queue could not be loaded.',
    ar: 'تعذّر تحميل قائمة المراجعة.',
  },

  'social.moderation.tab.pending': { en: 'Pending review', ar: 'قيد المراجعة' },
  'social.moderation.tab.approved': { en: 'Approved', ar: 'تمت الموافقة' },
  'social.moderation.tab.removed': { en: 'Removed', ar: 'تمت الإزالة' },

  'social.moderation.empty.pending.title': {
    en: 'Nothing waiting',
    ar: 'لا يوجد شيء في الانتظار',
  },
  'social.moderation.empty.pending.body': {
    en: 'Content the AI flags, or could not check, appears here for your decision.',
    ar: 'يظهر هنا المحتوى الذي يشير إليه الذكاء الاصطناعي أو الذي تعذّر فحصه، لتتخذ قرارك بشأنه.',
  },
  'social.moderation.empty.approved.title': {
    en: 'Nothing approved yet',
    ar: 'لم تتم الموافقة على شيء بعد',
  },
  'social.moderation.empty.approved.body': {
    en: 'Content you publish after review is listed here.',
    ar: 'يظهر هنا المحتوى الذي تنشره بعد المراجعة.',
  },
  'social.moderation.empty.removed.title': {
    en: 'Nothing removed',
    ar: 'لم تتم إزالة شيء',
  },
  'social.moderation.empty.removed.body': {
    en: 'Content you remove stays listed here, so the decision remains on record.',
    ar: 'يبقى المحتوى الذي تزيله مدرجاً هنا، ليظل القرار موثّقاً.',
  },

  'social.moderation.type.post': { en: 'Post', ar: 'منشور' },
  'social.moderation.type.comment': { en: 'Comment', ar: 'تعليق' },
  'social.moderation.type.story': { en: 'Story', ar: 'قصة' },

  'social.moderation.flaggedFor': { en: 'Flagged for', ar: 'تم الإشارة إليه بسبب' },
  'social.moderation.severity': { en: 'Severity', ar: 'درجة الخطورة' },
  'social.moderation.severity.low': { en: 'Low', ar: 'منخفضة' },
  'social.moderation.severity.medium': { en: 'Medium', ar: 'متوسطة' },
  'social.moderation.severity.high': { en: 'High', ar: 'مرتفعة' },
  'social.moderation.confidence': { en: 'AI confidence', ar: 'ثقة الذكاء الاصطناعي' },
  'social.moderation.reason': { en: 'Reason', ar: 'السبب' },
  'social.moderation.notScored': { en: 'Not scored', ar: 'لم يتم التقييم' },
  'social.moderation.submitted': { en: 'Submitted', ar: 'تاريخ الإرسال' },

  'social.moderation.category.harassment': { en: 'Harassment', ar: 'تحرّش' },
  'social.moderation.category.bullying': { en: 'Bullying', ar: 'تنمّر' },
  'social.moderation.category.threats': { en: 'Threats', ar: 'تهديد' },
  'social.moderation.category.abusive_language': {
    en: 'Abusive language',
    ar: 'لغة مسيئة',
  },
  'social.moderation.category.hate_speech': {
    en: 'Hateful or discriminatory',
    ar: 'خطاب كراهية أو تمييز',
  },
  'social.moderation.category.sexual_content': {
    en: 'Sexual content',
    ar: 'محتوى جنسي',
  },
  'social.moderation.category.spam': { en: 'Spam', ar: 'رسائل مزعجة' },
  'social.moderation.category.profanity': { en: 'Severe profanity', ar: 'ألفاظ نابية' },

  // The 'unavailable' outcome. Saying WHY the queue has an item in it is the
  // difference between "the AI found a problem" and "the AI never ran", and a
  // reviewer needs to know which one they are looking at.
  'social.moderation.unavailable': {
    en: 'Not checked by AI',
    ar: 'لم يتم فحصه بالذكاء الاصطناعي',
  },
  'social.moderation.unavailable.llm_not_configured': {
    en: 'No language model is configured, so this content was held rather than published unchecked.',
    ar: 'لا يوجد نموذج لغوي مُهيّأ، لذلك تم حجز هذا المحتوى بدلاً من نشره دون فحص.',
  },
  'social.moderation.unavailable.llm_error': {
    en: 'The moderation model could not be reached, so this content was held rather than published unchecked.',
    ar: 'تعذّر الوصول إلى نموذج المراجعة، لذلك تم حجز هذا المحتوى بدلاً من نشره دون فحص.',
  },
  'social.moderation.unavailable.invalid_output': {
    en: 'The moderation model returned something unusable, so this content was held rather than published unchecked.',
    ar: 'أعاد نموذج المراجعة نتيجة غير صالحة، لذلك تم حجز هذا المحتوى بدلاً من نشره دون فحص.',
  },

  'social.moderation.approve': { en: 'Approve', ar: 'موافقة' },
  'social.moderation.remove': { en: 'Remove', ar: 'إزالة' },
  'social.moderation.approved': {
    en: 'Approved - the content is now visible.',
    ar: 'تمت الموافقة - أصبح المحتوى ظاهراً الآن.',
  },
  'social.moderation.removed': {
    en: 'Removed - the content is hidden from the Social Hub.',
    ar: 'تمت الإزالة - أصبح المحتوى مخفياً عن مركز التواصل.',
  },
  'social.moderation.actionFailed': {
    en: 'That decision could not be saved.',
    ar: 'تعذّر حفظ القرار.',
  },
  'social.moderation.note': { en: 'Note (optional)', ar: 'ملاحظة (اختياري)' },
  'social.moderation.notePlaceholder': {
    en: 'Why you decided this. Visible to HR and Admin only.',
    ar: 'سبب قرارك. يظهر لفريق الموارد البشرية والمسؤولين فقط.',
  },
  'social.moderation.reviewedBy': { en: 'Reviewed by', ar: 'روجع بواسطة' },
  'social.moderation.contentGone': {
    en: 'The content has since been deleted by its author.',
    ar: 'تم حذف المحتوى لاحقاً بواسطة كاتبه.',
  },

  'social.moderation.aiNote': {
    en: 'The AI classifies content only. Approving or removing is always your decision, and removing hides content rather than deleting the record.',
    ar: 'يقوم الذكاء الاصطناعي بتصنيف المحتوى فقط. الموافقة أو الإزالة قرارك دائماً، والإزالة تُخفي المحتوى ولا تحذف السجل.',
  },
  'social.moderation.modelLabel': { en: 'Checked by', ar: 'تم الفحص بواسطة' },
  'social.moderation.modelMissing': {
    en: 'No language model is configured, so new content is held for review instead of being checked.',
    ar: 'لا يوجد نموذج لغوي مُهيّأ، لذلك يُحجز المحتوى الجديد للمراجعة بدلاً من فحصه.',
  },
  'social.moderation.disabled': {
    en: 'AI moderation is switched off in this deployment. New content publishes without being checked.',
    ar: 'مراجعة المحتوى بالذكاء الاصطناعي معطّلة في هذا النظام. يُنشر المحتوى الجديد دون فحص.',
  },

  // --- Right rail ---------------------------------------------------------
  'social.rail.connections': { en: 'Connections', ar: 'الاتصالات' },
  'social.rail.requests': { en: 'Requests', ar: 'الطلبات' },
  'social.rail.unread': { en: 'Unread messages', ar: 'رسائل غير مقروءة' },
  'social.rail.viewAll': { en: 'View all', ar: 'عرض الكل' },
  'social.rail.shortcuts': { en: 'Shortcuts', ar: 'اختصارات' },
  'social.rail.noEvents': {
    en: 'SmartHR has no events table, so there is nothing to show here.',
    ar: 'لا يحتوي SmartHR على جدول للفعاليات، لذا لا يوجد ما يُعرض هنا.',
  },

  // --- AI Employee Celebration (Admin + HR) -------------------------------
  // The generated message itself is NOT translated, following the rule the
  // rest of SmartHR follows for model output: it is written about a real
  // person in one language, and re-rendering it in another would fabricate a
  // second version of what was said. Only the labels around it are here.
  'social.celebration.title': {
    en: 'AI Employee Celebration',
    ar: 'تهنئة الموظفين بالذكاء الاصطناعي',
  },
  'social.celebration.occasion': { en: 'Occasion', ar: 'المناسبة' },
  'social.celebration.occasion.work_anniversary': {
    en: 'Work anniversary',
    ar: 'ذكرى الالتحاق بالعمل',
  },
  'social.celebration.occasion.birthday': { en: 'Birthday', ar: 'عيد ميلاد' },
  'social.celebration.occasion.promotion': { en: 'Promotion', ar: 'ترقية' },
  'social.celebration.occasion.graduation': { en: 'Graduation', ar: 'تخرّج' },
  'social.celebration.occasion.wedding': { en: 'Wedding', ar: 'زفاف' },
  'social.celebration.occasion.new_baby': { en: 'New baby', ar: 'مولود جديد' },
  'social.celebration.occasion.none': {
    en: 'Nothing today',
    ar: 'لا شيء اليوم',
  },
  'social.celebration.subtitleAuto': {
    en: 'A daily check finds birthdays, work anniversaries, promotions, graduations, weddings and new babies, then three agents write and review the message. You decide whether it is posted.',
    ar: 'يبحث فحص يومي عن أعياد الميلاد وذكرى الالتحاق بالعمل والترقيات والتخرّج والزفاف والمواليد الجدد، ثم يكتب ثلاثة وكلاء الرسالة ويراجعونها. أنت من يقرر نشرها.',
  },
  'social.celebration.checkNow': { en: 'Check now', ar: 'تحقق الآن' },
  'social.celebration.queueEmpty': {
    en: 'No celebrations are waiting. Nobody is celebrating today, or they have all been handled.',
    ar: 'لا توجد تهانٍ في الانتظار. لا أحد لديه مناسبة اليوم، أو تمت معالجتها جميعاً.',
  },
  'social.celebration.sweepPrepared': {
    en: '{count} celebration(s) prepared.',
    ar: 'تم تجهيز {count} تهنئة.',
  },
  'social.celebration.sweepAlready': {
    en: 'Today’s celebrations were already prepared.',
    ar: 'تم تجهيز تهاني اليوم مسبقاً.',
  },
  'social.celebration.sweepNone': {
    en: 'Nobody is celebrating today.',
    ar: 'لا أحد لديه مناسبة اليوم.',
  },
  'social.celebration.imageAlt': {
    en: 'Celebration banner attached to this post',
    ar: 'لافتة احتفالية مرفقة بهذا المنشور',
  },
  'social.celebration.post': { en: 'Post it', ar: 'انشرها' },
  'social.celebration.posting': { en: 'Posting…', ar: 'جارٍ النشر…' },
  'social.celebration.posted': {
    en: 'Posted to the feed.',
    ar: 'تم النشر في آخر المستجدات.',
  },
  'social.celebration.edit': { en: 'Edit first', ar: 'عدّلها أولاً' },
  'social.celebration.dismiss': { en: 'Dismiss', ar: 'تجاهل' },
  'social.celebration.approved': { en: 'Approved.', ar: 'تمت الموافقة.' },
  'social.celebration.rejected': { en: 'Not approved.', ar: 'لم تتم الموافقة.' },
  'social.celebration.retries': {
    en: 'Rewritten {count} of {max} times.',
    ar: 'أُعيدت كتابتها {count} من {max} مرات.',
  },
  'social.celebration.notPostable': {
    en: 'The reviewer did not approve this draft, so it is not offered for posting. You can run it again.',
    ar: 'لم يوافق المراجع على هذه المسودة، لذا لا تُتاح للنشر. يمكنك إعادة المحاولة.',
  },
  'social.celebration.failed': {
    en: 'The celebration could not be generated.',
    ar: 'تعذّر إنشاء التهنئة.',
  },
  'social.celebration.inComposer': {
    en: 'The celebration is in the composer above. Read it, edit it, then post it yourself.',
    ar: 'التهنئة موجودة في مربع النشر أعلاه. اقرأها وعدّلها ثم انشرها بنفسك.',
  },
  'social.celebration.dataLimit': {
    en: 'Occasions are found only from dates recorded on the employee (Employees page). An employee with a date left blank simply has no such occasion.',
    ar: 'لا يُعثر على المناسبات إلا من التواريخ المسجّلة للموظف (صفحة الموظفين). الموظف الذي تُرك تاريخه فارغاً ليست لديه تلك المناسبة.',
  },
};
