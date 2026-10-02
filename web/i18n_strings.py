"""Single source of truth for UI strings (English + Persian).

The Django context processor exposes the active language's dict as `i18n`
and the full dictionary as JSON for the client-side switcher, so templates
render server-side with zero flash while JS can re-apply instantly.
"""

LANG_COOKIE = "promptya-lang"
THEME_COOKIE = "promptya-theme"

EN = {
    "search_placeholder": "Search prompts...",
    "toggle_theme": "Toggle dark or light mode",
    "switch_language": "Switch language",
    "lang_switch_label": "FA",
    "create": "Create",
    "login": "Log in",
    "signup": "Sign up",
    "home": "Home",
    "explore": "Explore",
    "trending": "Trending",
    "saved": "Saved",
    "categories": "Categories",
    "sidebar_tagline": "Promptya — built for prompt creators",
    "notifications": "Notifications",
    "profile": "Profile",
    "for_you": "For You",
    "latest": "Latest",
    "following": "Following",
    "trending_now": "Trending now",
    "popular_categories": "Popular categories",
    "creators_to_follow": "Creators to follow",
    "just_added": "Just added",
    "posts": "posts",
    "no_categories_yet": "No categories with posts yet.",
    "no_creators_yet": "No creators yet.",
    "results_for": "Results for “{query}”",
    "search_title": "Search",
    "search_hint": "Type something in the search bar above — titles, prompts, tags, AI models or creators.",
    "welcome_back": "Welcome back",
    "login_tagline": "Log in to share prompts, save ideas and follow creators.",
    "username_or_email": "Username or email",
    "password": "Password",
    "no_account": "No account?",
    "create_account": "Create your account",
    "signup_tagline": "Join the community of prompt creators.",
    "username": "Username",
    "email": "Email",
    "password_min": "Password",
    "password_hint": "(min 8 chars)",
    "have_account": "Already have an account?",
    "mark_all_read": "Mark all as read",
    "no_notifications": "No notifications yet.",
    "verified": "Verified creator",
    "liked_your_post": "liked your post",
    "saved_your_post": "saved your post",
    "commented_on_your_post": "commented on your post",
    "started_following_you": "started following you",
    "followers": "followers",
    "level": "Level",
    "follow": "Follow",
    "following_btn": "Following",
    "offline_title": "You're offline",
    "offline_body": "Promptya isn't available right now, but your cached pages still work. Check your connection and try again.",
    "try_again": "Try again",
    "views": "views",
    "prompt": "PROMPT",
    "copy": "Copy",
    "model": "Model:",
    "copies": "copies",
    "comments": "comments",
    "comments_title": "Comments",
    "comment_placeholder": "Share your thoughts…",
    "comment_btn": "Comment",
    "login_to_join": "Log in to join the conversation.",
    "share_a_prompt": "Share a prompt",
    "title": "Title",
    "type": "Type",
    "prompt_type": "Prompt",
    "image": "Image",
    "video": "Video",
    "audio": "Audio",
    "category": "Category",
    "choose_category": "Choose a category…",
    "ai_model": "AI model",
    "optional": "(optional)",
    "the_prompt": "The prompt",
    "description": "Description",
    "title_placeholder": "e.g. Cinematic portrait generator",
    "ai_model_placeholder": "e.g. GPT-5, Midjourney, Sora",
    "prompt_placeholder": "Paste the prompt you used…",
    "description_placeholder": "What makes this prompt special?",
    "media_label": "Media",
    "upload_media": "Upload media",
    "upload_drop": "Drag & drop or click to choose a file",
    "upload_image": "Upload image",
    "upload_video": "Upload video",
    "upload_audio": "Upload audio",
    "remove_file": "Remove file",
    "publish": "Publish",
    "nothing_here": "Nothing here yet.",
    "share_first_prompt": "Share your first prompt",
    "post_count": "{n} posts",
    "level_n": "Level {n}",
    # Profile edit
    "edit_profile": "Edit profile",
    "view_profile": "View profile",
    "display_name": "Display name",
    "display_name_placeholder": "How should we call you?",
    "biography": "Biography",
    "biography_placeholder": "Tell the community about yourself…",
    "account_info": "Account info",
    "username_hint": "3–150 chars: letters, numbers and _ . + - @",
    "change_photo": "Change photo",
    "remove_photo": "Remove photo",
    "save_changes": "Save changes",
    "saving": "Saving…",
    "saved_check": "Saved ✓",
    "change_password": "Change password",
    "current_password": "Current password",
    "new_password": "New password",
    "confirm_password": "Confirm new password",
    "update_password": "Update password",
    "change_password_hint": "Use at least 8 characters with a mix of letters and numbers.",
    "pw_weak": "Weak",
    "pw_fair": "Fair",
    "pw_good": "Good",
    "pw_strong": "Strong",
    # Home feed
    "recommended_hint": "Tuned for you — based on what you like, save and follow.",
    "suggested_for_you": "Suggested for you",
    # Player
    "player_play": "Play",
    "player_pause": "Pause",
    "player_mute": "Mute",
    "player_unmute": "Unmute",
    "player_fullscreen": "Fullscreen",
    "player_speed": "Playback speed",
    "player_error": "This media could not be loaded.",
    "player_seek": "Seek",
    "player_volume": "Volume",
    "player_pip": "Picture in picture",
    "player_normal": "Normal",
    # Chrome: navigation, menus, footer
    "primary_nav": "Primary",
    "skip_to_content": "Skip to content",
    "search_label": "Search prompts",
    "open_menu": "Open menu",
    "close_menu": "Close menu",
    "logout": "Log out",
    "like_action": "Like",
    "save_action": "Save",
    "theme_to_light": "Switch to light mode",
    "theme_to_dark": "Switch to dark mode",
    "footer_tagline": "A network for prompt creators — see the result, read the prompt, remix it.",
    "footer_explore": "Explore",
    "footer_account": "Your account",
    "footer_rights": "All rights reserved.",
    # Upload component (server-rendered strings; errors live in JS_STRINGS)
    "upload_bad_type": "File type not allowed.",
    "upload_too_large": "File is too large.",
    "upload_max_image": "Maximum 10 MB.",
    "upload_max_video": "Maximum 200 MB.",
    "upload_max_audio": "Maximum 30 MB.",
    "prompt_required": "The prompt text is required for a prompt post.",
    "media_required_image": "Choose an image for this post.",
    "media_required_video": "Choose a video for this post.",
    "media_required_audio": "Choose an audio file for this post.",
    # AI studio (image generation)
    "studio": "AI Studio",
    "studio_subtitle": "Copy a prompt from the library below — or write your own — and let the model paint it.",
    "studio_model": "Model",
    "studio_composer": "Compose",
    "studio_prompt_label": "Your prompt",
    "studio_prompt_placeholder": "A sunset over mountains, cinematic light, 35mm…",
    "studio_generate": "Generate image",
    "studio_generating": "Developing…",
    "studio_elapsed": "{n}s",
    "studio_done_toast": "Image ready ✨",
    "studio_reference": "Reference output",
    "studio_reference_clear": "Clear reference",
    "studio_result_title": "Result",
    "studio_canvas_empty": "Write a prompt or take one from the library — your image lands here.",
    "studio_quota_cta": "Create an account to generate",
    # Credits & rewards
    "studio_credits_title": "Your credits",
    "studio_credits_unit": "credits",
    "studio_cost_label": "Cost per image",
    "studio_credits_foot": "Credits never expire, and a failed generation is refunded automatically.",
    "studio_signup_credits": "credits when you sign up",
    "studio_cost_per_image": "credits per image",
    "studio_earn_cta": "Earn more credits",
    "studio_earn_title": "Earn more credits",
    "studio_earn_hint": "Every reward below is verified — nothing here pays for a click.",
    "studio_challenge_done": "Earned ✓",
    "studio_challenge_claim": "Claim reward",
    "studio_challenge_auto": "Automatic",
    "studio_no_challenges": "No rewards are running right now.",
    "studio_referral_label": "Your invite link",
    "studio_referral_copy": "Copy link",
    "studio_referral_copied": "Invite link copied",
    "studio_challenge_done_toast": "Reward claimed — +{n} credits",
    "studio_challenge_evidence_prompt": "Paste the Instagram post link (https://instagram.com/p/…):",
    "studio_source_label": "Reference image",
    "studio_source_hint": "Add a picture to remix it instead of starting from text — image-to-image.",
    "studio_insufficient": "You need {n} more credits to generate this image.",
    "studio_insufficient_cta": "See ways to earn credits",
    "studio_balance_after": "{n} credits left",
    "studio_remix": "Remix in AI Studio",
    "studio_use_prompt_title": "Generate your own version of this prompt",
    "studio_library_title": "Prompt library",
    "studio_library_hint": "Real prompts from the community, next to what they produced. Take one.",
    "studio_use_prompt": "Use prompt",
    "studio_copy_prompt": "Copy",
    "studio_empty_library": "No shared prompts yet — publish the first one.",
    "studio_my_generations": "My generations",
    "studio_no_generations": "Nothing here yet. Your images will stack up on this shelf.",
    "studio_needs_js": "Turn on JavaScript to see your generations.",
    "studio_prompt_required": "Write a prompt first.",
    "studio_max_length": "Prompts are limited to {n} characters.",
    "studio_provider_error": "The model couldn't finish this image.",
    "studio_disabled": "Generation is switched off right now.",
    "studio_login_required": "Log in to generate images.",
    "studio_ready": "Ready",
    "studio_failed": "Failed",
    "studio_download": "Download",
    "studio_use_again": "Reuse prompt",
    "login_to_generate": "Log in to generate",
}

FA = {
    "search_placeholder": "جستجوی پرامپت‌ها…",
    "toggle_theme": "تغییر حالت شب و روز",
    "switch_language": "تغییر زبان",
    "lang_switch_label": "EN",
    "create": "ساختن",
    "login": "ورود",
    "signup": "ثبت‌نام",
    "home": "خانه",
    "explore": "کاوش",
    "trending": "پرطرفدار",
    "saved": "ذخیره‌شده",
    "categories": "دسته‌بندی‌ها",
    "sidebar_tagline": "پرامپتیا — ساخته‌شده برای سازندگان پرامپت",
    "notifications": "اعلان‌ها",
    "profile": "پروفایل",
    "for_you": "مخصوص شما",
    "latest": "جدیدترین",
    "following": "دنبال‌شده‌ها",
    "trending_now": "پرطرفدارترین‌ها",
    "popular_categories": "دسته‌بندی‌های محبوب",
    "creators_to_follow": "سازندگان پیشنهادی",
    "just_added": "تازه اضافه‌شده",
    "posts": "پست",
    "no_categories_yet": "هنوز دسته‌بندی‌ای با پست وجود ندارد.",
    "no_creators_yet": "هنوز سازنده‌ای وجود ندارد.",
    "results_for": "نتایج برای «{query}»",
    "search_title": "جستجو",
    "search_hint": "چیزی در نوار جستجوی بالا بنویسید — عنوان‌ها، پرامپت‌ها، برچسب‌ها، مدل‌های هوش مصنوعی یا سازندگان.",
    "welcome_back": "خوش آمدید",
    "login_tagline": "برای اشتراک پرامپت، ذخیره ایده‌ها و دنبال کردن سازندگان وارد شوید.",
    "username_or_email": "نام کاربری یا ایمیل",
    "password": "گذرواژه",
    "no_account": "حساب ندارید؟",
    "create_account": "حساب خود را بسازید",
    "signup_tagline": "به جمع سازندگان پرامپت بپیوندید.",
    "username": "نام کاربری",
    "email": "ایمیل",
    "password_min": "گذرواژه",
    "password_hint": "(حداقل ۸ کاراکتر)",
    "have_account": "قبلاً حساب ساخته‌اید؟",
    "mark_all_read": "علامت‌گذاری همه به‌عنوان خوانده‌شده",
    "no_notifications": "هنوز اعلانی وجود ندارد.",
    "verified": "سازندهٔ تأییدشده",
    "liked_your_post": "پست شما را پسندید",
    "saved_your_post": "پست شما را ذخیره کرد",
    "commented_on_your_post": "روی پست شما نظر گذاشت",
    "started_following_you": "شما را دنبال کرد",
    "followers": "دنبال‌کننده",
    "level": "سطح",
    "follow": "دنبال کردن",
    "following_btn": "دنبال می‌کنید",
    "offline_title": "شما آفلاین هستید",
    "offline_body": "پرامپتیا در دسترس نیست، اما صفحه‌های ذخیره‌شده کار می‌کنند. اتصال خود را بررسی و دوباره تلاش کنید.",
    "try_again": "تلاش دوباره",
    "views": "بازدید",
    "prompt": "پرامپت",
    "copy": "کپی",
    "model": "مدل:",
    "copies": "کپی",
    "comments": "نظر",
    "comments_title": "نظرها",
    "comment_placeholder": "نظر خود را بنویسید…",
    "comment_btn": "ثبت نظر",
    "login_to_join": "برای گفتگو وارد شوید.",
    "share_a_prompt": "اشتراک یک پرامپت",
    "title": "عنوان",
    "type": "نوع",
    "prompt_type": "پرامپت",
    "image": "تصویر",
    "video": "ویدیو",
    "audio": "صدا",
    "category": "دسته‌بندی",
    "choose_category": "یک دسته‌بندی انتخاب کنید…",
    "ai_model": "مدل هوش مصنوعی",
    "optional": "(اختیاری)",
    "the_prompt": "متن پرامپت",
    "description": "توضیحات",
    "title_placeholder": "مثلاً: تولید پرتره سینمایی",
    "ai_model_placeholder": "مثلاً: GPT-5، Midjourney، Sora",
    "prompt_placeholder": "پرامپتی که استفاده کردید را بچسبانید…",
    "description_placeholder": "چه چیز این پرامپت را خاص می‌کند؟",
    "media_label": "رسانه",
    "upload_media": "بارگذاری رسانه",
    "upload_drop": "فایل را بکشید و رها کنید یا کلیک کنید",
    "upload_image": "بارگذاری تصویر",
    "upload_video": "بارگذاری ویدیو",
    "upload_audio": "بارگذاری صدا",
    "remove_file": "حذف فایل",
    "publish": "انتشار",
    "nothing_here": "هنوز چیزی اینجا نیست.",
    "share_first_prompt": "اولین پرامپت خود را به اشتراک بگذارید",
    "post_count": "{n} پست",
    "level_n": "سطح {n}",
    # Profile edit
    "edit_profile": "ویرایش پروفایل",
    "view_profile": "مشاهده پروفایل",
    "display_name": "نام نمایشی",
    "display_name_placeholder": "چطور صدایتان کنیم؟",
    "biography": "بیوگرافی",
    "biography_placeholder": "خودتان را به جامعه معرفی کنید…",
    "account_info": "اطلاعات حساب",
    "username_hint": "۳ تا ۱۵۰ نویسه: حروف، اعداد و _ . + - @",
    "change_photo": "تغییر عکس",
    "remove_photo": "حذف عکس",
    "save_changes": "ذخیره تغییرات",
    "saving": "در حال ذخیره…",
    "saved_check": "ذخیره شد ✓",
    "change_password": "تغییر گذرواژه",
    "current_password": "گذرواژه فعلی",
    "new_password": "گذرواژه جدید",
    "confirm_password": "تکرار گذرواژه جدید",
    "update_password": "به‌روزرسانی گذرواژه",
    "change_password_hint": "حداقل ۸ کاراکتر با ترکیبی از حروف و اعداد.",
    "pw_weak": "ضعیف",
    "pw_fair": "متوسط",
    "pw_good": "خوب",
    "pw_strong": "قوی",
    # Home feed
    "recommended_hint": "مخصوص شما — بر اساس لایک‌ها، ذخیره‌ها و دنبال‌کردن‌هایتان.",
    "suggested_for_you": "پیشنهاد برای شما",
    # Player
    "player_play": "پخش",
    "player_pause": "توقف",
    "player_mute": "بی‌صدا",
    "player_unmute": "با صدا",
    "player_fullscreen": "تمام‌صفحه",
    "player_speed": "سرعت پخش",
    "player_error": "بارگیری این رسانه ممکن نشد.",
    "player_seek": "جابه‌جایی زمان",
    "player_volume": "صدا",
    "player_pip": "تصویر در تصویر",
    "player_normal": "معمولی",
    # Chrome: navigation, menus, footer
    "primary_nav": "ناوبری اصلی",
    "skip_to_content": "پرش به محتوا",
    "search_label": "جستجوی پرامپت‌ها",
    "open_menu": "باز کردن منو",
    "close_menu": "بستن منو",
    "logout": "خروج",
    "like_action": "پسندیدن",
    "save_action": "ذخیره",
    "theme_to_light": "تغییر به حالت روز",
    "theme_to_dark": "تغییر به حالت شب",
    "footer_tagline": "شبکه‌ای برای سازندگان پرامپت — نتیجه را ببین، پرامپت را بخوان و آن را از نو بساز.",
    "footer_explore": "کاوش",
    "footer_account": "حساب من",
    "footer_rights": "همه حقوق محفوظ است.",
    # Upload component
    "upload_bad_type": "نوع فایل مجاز نیست.",
    "upload_too_large": "حجم فایل بیش از حد مجاز است.",
    "upload_max_image": "حداکثر ۱۰ مگابایت.",
    "upload_max_video": "حداکثر ۲۰۰ مگابایت.",
    "upload_max_audio": "حداکثر ۳۰ مگابایت.",
    "prompt_required": "متن پرامپت برای پست پرامپتی الزامی است.",
    "media_required_image": "برای این پست یک تصویر انتخاب کنید.",
    "media_required_video": "برای این پست یک ویدیو انتخاب کنید.",
    "media_required_audio": "برای این پست یک فایل صوتی انتخاب کنید.",
    # استودیوی هوش مصنوعی
    "studio": "استودیوی هوش مصنوعی",
    "studio_subtitle": "یک پرامپت از کتابخانهٔ پایین بردارید — یا خودتان بنویسید — و بگذارید مدل آن را بسازد.",
    "studio_model": "مدل",
    "studio_composer": "نوشتن پرامپت",
    "studio_prompt_label": "پرامپت شما",
    "studio_prompt_placeholder": "غروب روی کوه‌ها، نور سینمایی، ۳۵ میلی‌متری…",
    "studio_generate": "ساخت تصویر",
    "studio_generating": "در حال ساخت…",
    "studio_elapsed": "{n} ثانیه",
    "studio_done_toast": "تصویر آماده شد ✨",
    "studio_reference": "خروجی مرجع",
    "studio_reference_clear": "حذف مرجع",
    "studio_result_title": "نتیجه",
    "studio_canvas_empty": "یک پرامپت بنویسید یا از کتابخانه انتخاب کنید — تصویر شما اینجا ساخته می‌شود.",
    "studio_quota_cta": "برای ساخت تصویر حساب بسازید",
    # اعتبار و پاداش‌ها
    "studio_credits_title": "اعتبار شما",
    "studio_credits_unit": "اعتبار",
    "studio_cost_label": "هزینهٔ هر تصویر",
    "studio_credits_foot": "اعتبارها منقضی نمی‌شوند و در صورت خطا به‌طور خودکار برمی‌گردند.",
    "studio_signup_credits": "اعتبار هنگام ثبت‌نام",
    "studio_cost_per_image": "اعتبار برای هر تصویر",
    "studio_earn_cta": "کسب اعتبار بیشتر",
    "studio_earn_title": "کسب اعتبار بیشتر",
    "studio_earn_hint": "همهٔ پاداش‌های زیر تأییدشده‌اند — به صرف کلیک چیزی پرداخت نمی‌شود.",
    "studio_challenge_done": "دریافت شد ✓",
    "studio_challenge_claim": "دریافت پاداش",
    "studio_challenge_auto": "خودکار",
    "studio_no_challenges": "در حال حاضر پاداشی فعال نیست.",
    "studio_referral_label": "لینک دعوت شما",
    "studio_referral_copy": "کپی لینک",
    "studio_referral_copied": "لینک دعوت کپی شد",
    "studio_challenge_done_toast": "پاداش دریافت شد — {n} اعتبار",
    "studio_challenge_evidence_prompt": "لینک پست اینستاگرام را بچسبانید (‏https://instagram.com/p/…):",
    "studio_source_label": "تصویر مرجع",
    "studio_source_hint": "یک تصویر اضافه کنید تا به‌جای شروع از متن، آن را بازسازی کنیم — تصویر به تصویر.",
    "studio_insufficient": "برای ساخت این تصویر به {n} اعتبار بیشتر نیاز دارید.",
    "studio_insufficient_cta": "راه‌های کسب اعتبار",
    "studio_balance_after": "{n} اعتبار باقی مانده",
    "studio_remix": "بازسازی در استودیوی هوش مصنوعی",
    "studio_use_prompt_title": "نسخهٔ خودتان را از این پرامپت بسازید",
    "studio_library_title": "کتابخانهٔ پرامپت",
    "studio_library_hint": "پرامپت‌های واقعی کاربران، در کنار خروجی‌شان. یکی بردارید.",
    "studio_use_prompt": "استفاده از پرامپت",
    "studio_copy_prompt": "کپی",
    "studio_empty_library": "هنوز پرامپت اشتراکی وجود ندارد — اولین را منتشر کنید.",
    "studio_my_generations": "ساخته‌های من",
    "studio_no_generations": "هنوز چیزی اینجا نیست. تصاویر شما در این قفسه جمع می‌شوند.",
    "studio_needs_js": "برای دیدن تصاویر خود جاوااسکریپت را فعال کنید.",
    "studio_prompt_required": "اول یک پرامپت بنویسید.",
    "studio_max_length": "حداکثر {n} نویسه برای پرامپت.",
    "studio_provider_error": "مدل نتوانست این تصویر را کامل کند.",
    "studio_disabled": "ساخت تصویر در حال حاضر خاموش است.",
    "studio_login_required": "برای ساخت تصویر وارد شوید.",
    "studio_ready": "آماده",
    "studio_failed": "ناموفق",
    "studio_download": "دانلود",
    "studio_use_again": "استفادهٔ دوباره",
    "login_to_generate": "برای ساخت وارد شوید",
}

STRINGS = {"en": EN, "fa": FA}

# ---------------------------------------------------------------------------
# SEO / page-content strings
# ---------------------------------------------------------------------------
# Everything a crawler reads that is *not* chrome: page titles, meta
# descriptions, the H1 of each page, breadcrumb labels, related-content headings
# and pagination text.  Kept apart from STRINGS because none of it is rewritten
# client-side (the language switch reloads, so Django re-renders the page), and
# because these are the strings that must exist in both languages for the two
# indexes to be genuinely parallel.
#
# `{n}`, `{name}`, `{tag}`, `{title}`, `{author}`, `{username}`, `{count}`,
# `{query}`, `{type}` are substituted by web_extras.fmt / web.seo.fmt_value.
# Every entry has a Persian twin; web/test_seo.py asserts that.

SEO_STRINGS = {
    "en": {
        "site_name": "Promptya",
        "site_description": (
            "Promptya is a bilingual community for AI prompt creators. Browse, "
            "save and remix image, video and audio results, and read the exact "
            "prompt behind every one."
        ),
        # Home
        "home_title": "Promptya — Free AI Prompts to Share, Browse and Remix",
        "home_description": (
            "Discover free AI prompts on Promptya: browse image, video and audio "
            "results, read the exact prompt behind each one, and remix it in the "
            "built-in AI studio."
        ),
        "home_h1": "Discover AI prompts worth remixing",
        # Explore
        "explore_title": "Explore AI Prompts, Categories and Creators · Promptya",
        "explore_description": (
            "Explore trending AI prompts, popular categories and the AI creators "
            "worth following on Promptya — Persian and English, image, video, "
            "audio and text prompts."
        ),
        "explore_intro": (
            "A starting point for finding prompts: what the community is using "
            "right now, grouped by category and by creator."
        ),
        # AI Studio
        "studio_title": "AI Image Generator & Free AI Studio · Promptya",
        "studio_description": (
            "Generate AI images free with Promptya's studio. Take a prompt from "
            "the community library or write your own, then generate your version "
            "with built-in credits."
        ),
        "studio_h1_note": "Free AI image generation, powered by the community prompt library.",
        # Search (noindex, but still needs a real title and description)
        "search_title": "Search AI Prompts · Promptya",
        "search_description": (
            "Search AI prompts by title, prompt text, tag, category, AI model or "
            "creator across the Promptya community."
        ),
        "search_results_title_fmt": "Search results for “{query}” · Promptya",
        # Category
        "category_title_fmt": "{name} AI Prompts · Promptya",
        "category_description_fmt": (
            "Browse free {count} community AI prompts in the {name} category on "
            "Promptya. Copy the exact prompt text, see the result it produced, "
            "and remix it in the AI studio."
        ),
        "category_h1_fmt": "{name} AI prompts",
        "category_intro_fmt": (
            "Every public prompt published in {name}, newest first. Each one "
            "shows the result and the exact prompt behind it."
        ),
        "category_empty": "No public prompts in this category yet.",
        # Tag
        "tag_title_fmt": "#{tag} AI Prompts and Examples · Promptya",
        "tag_description_fmt": (
            "Browse {count} free AI prompts tagged {tag} on Promptya — the "
            "prompt text, the result it produced, and the model it was written for."
        ),
        "tag_h1_fmt": "#{tag} AI prompts",
        "tag_intro_fmt": (
            "Community prompts tagged {tag}. Each one shows the output it "
            "produced and the exact prompt that generated it."
        ),
        "tag_empty": "No public prompts carry this tag yet.",
        # Post
        "post_title_fmt": "{title} — AI Prompt by @{author} · Promptya",
        "post_title_prompt_fmt": "{title} — Free AI Prompt by @{author} · Promptya",
        "post_description_fmt": "{text} Free AI prompt by @{author} on Promptya.",
        "post_fallback_fmt": (
            "A free {type} AI prompt by @{author} on Promptya, with the exact "
            "prompt text and the result it produced."
        ),
        "post_type_prompt": "prompt",
        "post_type_image": "image",
        "post_type_video": "video",
        "post_type_audio": "audio",
        "post_about_heading": "About this prompt",
        "post_related_heading": "Related prompts",
        "post_more_in_category": "More in {name}",
        "post_creator_heading": "Published by",
        "post_tags_heading": "Tags",
        "post_empty": "This prompt has no text or media yet.",
        # Profile
        "profile_title_fmt": "{name} (@{username}) — AI Prompts on Promptya",
        "profile_description_fmt": (
            "{count} AI prompts published by @{username} on Promptya. Follow "
            "their latest image, video, audio and text prompts."
        ),
        "profile_h1_posts_fmt": "{count} AI prompts by @{username}",
        "profile_empty": "This creator has not published any public prompts yet.",
        "profile_thin_note": (
            "This creator has no public prompts yet, so the page is kept out of "
            "the search index until they publish."
        ),
        # Feed variants (noindex alternates of home/explore)
        "feed_h1_fmt": "{tab} AI prompts",
        # Private / utility pages
        "login_title": "Log in · Promptya",
        "signup_title": "Create your account · Promptya",
        "create_title": "Share an AI prompt · Promptya",
        "create_description": "Publish an AI prompt or an image, video or audio result to the Promptya community.",
        "saved_title": "Saved prompts · Promptya",
        "notifications_title": "Notifications · Promptya",
        "profile_edit_title": "Edit your profile · Promptya",
        "offline_title": "You're offline · Promptya",
        # Breadcrumbs & navigation
        "breadcrumb_home": "Home",
        "breadcrumb_explore": "Explore",
        "breadcrumb_categories": "Categories",
        "breadcrumb_tag": "Tag",
        "breadcrumb_profile": "Creator",
        "breadcrumb_post": "Prompt",
        "breadcrumb_label": "Breadcrumb",
        "breadcrumb_current": "Current page",
        # Pagination
        "pagination_label": "Pagination",
        "pagination_previous": "Previous",
        "pagination_next": "Next",
        "pagination_page_fmt": "Page {n}",
        "pagination_current_fmt": "Page {n}, current page",
        "load_more_fmt": "Load more prompts (page {n})",
        "listing_count_fmt": "{count} prompts",
        "see_all_fmt": "See all {count} prompts",
        # Errors
        "not_found_title": "Page not found · Promptya",
        "not_found_body": "That page doesn't exist, or it was removed. Try the home page, explore the categories, or search the prompt library.",
        "server_error_title": "Something went wrong · Promptya",
        "server_error_body": "Promptya hit an unexpected error. Please try again in a moment.",
        "error_go_home": "Go to the home page",
        "error_explore": "Explore prompts",
    },
    "fa": {
        "site_name": "پرامپتیا",
        "site_description": (
            "پرامپتیا یک جامعهٔ دوزبانه برای سازندگان پرامپت هوش مصنوعی است. "
            "پرامپت‌ها و نتایج تصویری، ویدیویی و صوتی را ببینید، ذخیره کنید و "
            "بازسازی کنید، و پشت هر نتیجه دقیقاً همان پرامپت اصلی را بخوانید."
        ),
        # Home
        "home_title": "پرامپتیا — پرامپت‌های هوش مصنوعی رایگان برای اشتراک و بازسازی",
        "home_description": (
            "پرامپت‌های هوش مصنوعی رایگان را در پرامپتیا کشف کنید: نتایج تصویری، "
            "ویدیویی و صوتی را ببینید، پرامپت دقیق پشت هر نتیجه را بخوانید و آن را "
            "در استودیوی هوش مصنوعی برای خودتان بازسازی کنید."
        ),
        "home_h1": "کشف پرامپت‌های هوش مصنوعی که ارزش بازسازی دارند",
        # Explore
        "explore_title": "کاوش پرامپت‌ها، دسته‌بندی‌ها و سازندگان هوش مصنوعی · پرامپتیا",
        "explore_description": (
            "پرامپت‌های پرطرفدار، دسته‌بندی‌های محبوب و سازندگان قابل دنبال‌کردن "
            "هوش مصنوعی را در پرامپتیا کاوش کنید — فارسی و انگلیسی، پرامپت‌های "
            "تصویر، ویدیو، صدا و متن."
        ),
        "explore_intro": (
            "نقطهٔ شروعی برای پیدا کردن پرامپت: آنچه جامعه همین حالا استفاده می‌کند، "
            "گروه‌بندی‌شده بر اساس دسته‌بندی و سازنده."
        ),
        # AI Studio
        "studio_title": "ساخت تصویر با هوش مصنوعی و استودیوی رایگان · پرامپتیا",
        "studio_description": (
            "با استودیوی پرامپتیا رایگان تصویر هوش مصنوعی بسازید. یک پرامپت از "
            "کتابخانهٔ جامعه بردارید یا خودتان بنویسید و با اعتبار رایگان نسخهٔ "
            "خودتان را بسازید."
        ),
        "studio_h1_note": "ساخت رایگان تصویر با هوش مصنوعی، بر پایهٔ کتابخانهٔ پرامپت‌های جامعه.",
        # Search (noindex, but still needs a real title and description)
        "search_title": "جستجوی پرامپت‌های هوش مصنوعی · پرامپتیا",
        "search_description": (
            "در پرامپت‌های هوش مصنوعی بر اساس عنوان، متن پرامپت، برچسب، دسته‌بندی، "
            "مدل هوش مصنوعی یا سازنده در جامعهٔ پرامپتیا جستجو کنید."
        ),
        "search_results_title_fmt": "نتایج جستجو برای «{query}» · پرامپتیا",
        # Category
        "category_title_fmt": "پرامپت‌های {name} · پرامپتیا",
        "category_description_fmt": (
            "{count} پرامپت هوش مصنوعی رایگان از کاربران را در دسته‌بندی {name} در "
            "پرامپتیا ببینید. متن دقیق پرامپت را بردارید، نتیجه‌ای که ساخته را ببینید "
            "و آن را در استودیوی هوش مصنوعی بازسازی کنید."
        ),
        "category_h1_fmt": "پرامپت‌های {name}",
        "category_intro_fmt": (
            "همهٔ پرامپت‌های عمومی منتشرشده در {name}، از جدیدترین به قدیمی‌ترین. "
            "هر مورد نتیجه و متن دقیق پرامپت پشت آن را نشان می‌دهد."
        ),
        "category_empty": "هنوز پرامپت عمومی در این دسته‌بندی نیست.",
        # Tag
        "tag_title_fmt": "پرامپت‌ها و نمونه‌های #{tag} · پرامپتیا",
        "tag_description_fmt": (
            "{count} پرامپت هوش مصنوعی رایگان با برچسب {tag} را در پرامپتیا ببینید — "
            "متن پرامپت، نتیجه‌ای که ساخته و مدلی که برای آن نوشته شده است."
        ),
        "tag_h1_fmt": "پرامپت‌های #{tag}",
        "tag_intro_fmt": (
            "پرامپت‌های جامعه با برچسب {tag}. هر مورد خروجی‌ای که ساخته و متن دقیق "
            "پرامپتی که آن را ساخته نشان می‌دهد."
        ),
        "tag_empty": "هنوز پرامپت عمومی با این برچسب نیست.",
        # Post
        "post_title_fmt": "{title} — پرامپت هوش مصنوعی از @{author} · پرامپتیا",
        "post_title_prompt_fmt": "{title} — پرامپت هوش مصنوعی رایگان از @{author} · پرامپتیا",
        "post_description_fmt": "{text} پرامپت هوش مصنوعی رایگان از @{author} در پرامپتیا.",
        "post_fallback_fmt": (
            "یک پرامپت هوش مصنوعی رایگان {type} از @{author} در پرامپتیا، همراه با متن "
            "دقیق پرامپت و نتیجه‌ای که ساخته است."
        ),
        "post_type_prompt": "متنی",
        "post_type_image": "تصویری",
        "post_type_video": "ویدیویی",
        "post_type_audio": "صوتی",
        "post_about_heading": "دربارهٔ این پرامپت",
        "post_related_heading": "پرامپت‌های مرتبط",
        "post_more_in_category": "بیشتر در {name}",
        "post_creator_heading": "منتشرکننده",
        "post_tags_heading": "برچسب‌ها",
        "post_empty": "این پرامپت هنوز متن یا رسانه‌ای ندارد.",
        # Profile
        "profile_title_fmt": "{name} (@{username}) — پرامپت‌های هوش مصنوعی در پرامپتیا",
        "profile_description_fmt": (
            "{count} پرامپت هوش مصنوعی منتشرشده توسط @{username} در پرامپتیا. جدیدترین "
            "پرامپت‌های تصویری، ویدیویی، صوتی و متنی او را دنبال کنید."
        ),
        "profile_h1_posts_fmt": "{count} پرامپت هوش مصنوعی از @{username}",
        "profile_empty": "این سازنده هنوز هیچ پرامپت عمومی منتشر نکرده است.",
        "profile_thin_note": (
            "این سازنده هنوز پرامپت عمومی ندارد، بنابراین صفحه تا زمان انتشار او از "
            "نمایهٔ جستجو بیرون نگه داشته می‌شود."
        ),
        # Feed variants (noindex alternates of home/explore)
        "feed_h1_fmt": "پرامپت‌های هوش مصنوعی {tab}",
        # Private / utility pages
        "login_title": "ورود · پرامپتیا",
        "signup_title": "ساخت حساب · پرامپتیا",
        "create_title": "اشتراک یک پرامپت هوش مصنوعی · پرامپتیا",
        "create_description": "یک پرامپت هوش مصنوعی یا نتیجهٔ تصویری، ویدیویی یا صوتی را در جامعهٔ پرامپتیا منتشر کنید.",
        "saved_title": "پرامپت‌های ذخیره‌شده · پرامپتیا",
        "notifications_title": "اعلان‌ها · پرامپتیا",
        "profile_edit_title": "ویرایش پروفایل · پرامپتیا",
        "offline_title": "شما آفلاین هستید · پرامپتیا",
        # Breadcrumbs & navigation
        "breadcrumb_home": "خانه",
        "breadcrumb_explore": "کاوش",
        "breadcrumb_categories": "دسته‌بندی‌ها",
        "breadcrumb_tag": "برچسب",
        "breadcrumb_profile": "سازنده",
        "breadcrumb_post": "پرامپت",
        "breadcrumb_label": "مسیر صفحه",
        "breadcrumb_current": "صفحهٔ جاری",
        # Pagination
        "pagination_label": "صفحه‌بندی",
        "pagination_previous": "قبلی",
        "pagination_next": "بعدی",
        "pagination_page_fmt": "صفحهٔ {n}",
        "pagination_current_fmt": "صفحهٔ {n}، صفحهٔ جاری",
        "load_more_fmt": "بارگذاری پرامپت‌های بیشتر (صفحهٔ {n})",
        "listing_count_fmt": "{count} پرامپت",
        "see_all_fmt": "دیدن همهٔ {count} پرامپت",
        # Errors
        "not_found_title": "صفحه پیدا نشد · پرامپتیا",
        "not_found_body": "این صفحه وجود ندارد یا حذف شده است. صفحهٔ خانه را ببینید، دسته‌بندی‌ها را کاوش کنید یا در کتابخانهٔ پرامپت‌ها جستجو کنید.",
        "server_error_title": "خطایی رخ داد · پرامپتیا",
        "server_error_body": "پرامپتیا با خطای غیرمنتظره‌ای روبه‌رو شد. لطفاً کمی بعد دوباره تلاش کنید.",
        "error_go_home": "رفتن به صفحهٔ خانه",
        "error_explore": "کاوش پرامپت‌ها",
    },
}

#: Both dictionaries must always carry exactly the same keys; web/test_seo.py
#: fails the build if one language drifts ahead of the other.
SEO_LANGUAGES = tuple(SEO_STRINGS)


# JS-side dynamic strings (toasts etc.) — kept client-only.
JS_STRINGS = {
    "en": {
        "saved_toast": "Saved 🔖",
        "removed_from_saved": "Removed from saved",
        "login_to_do_that": "Log in to do that",
        "something_wrong": "Something went wrong",
        "follow_error": "Could not update follow",
        "copied": "Copied!",
        "copy_toast": "Prompt copied to clipboard",
        "comment_posted": "Comment posted",
        "comment_error": "Could not post comment",
        "published_toast": "Published! 🎉",
        "publish_error": "Could not publish. Check your input and try again.",
        "caught_up_toast": "All caught up ✨",
        "delete": "Delete",
        "profile_saved": "Profile updated",
        "password_changed": "Password changed",
        "passwords_mismatch": "New passwords do not match.",
        "fill_password_fields": "Fill in both password fields.",
        "invalid_image_type": "Please choose a JPG, PNG, WebP or GIF image.",
        "image_too_large": "Image is too large (max 10 MB).",
        "upload_bad_type": "File type not allowed. Allowed:",
        "upload_too_large": "File is too large.",
        "upload_max_image": "Maximum 10 MB.",
        "upload_max_video": "Maximum 200 MB.",
        "upload_max_audio": "Maximum 30 MB.",
        "prompt_required": "The prompt text is required for a prompt post.",
        "media_required_image": "Choose an image for this post.",
        "media_required_video": "Choose a video for this post.",
        "media_required_audio": "Choose an audio file for this post.",
        "date_locale": "en-US",
    },
    "fa": {
        "saved_toast": "ذخیره شد 🔖",
        "removed_from_saved": "از ذخیره‌شده‌ها حذف شد",
        "login_to_do_that": "برای این کار وارد شوید",
        "something_wrong": "مشکلی پیش آمد",
        "follow_error": "دنبال کردن به‌روزرسانی نشد",
        "copied": "کپی شد!",
        "copy_toast": "پرامپت در کلیپ‌بورد کپی شد",
        "comment_posted": "نظر ثبت شد",
        "comment_error": "ثبت نظر ممکن نشد",
        "published_toast": "منتشر شد! 🎉",
        "publish_error": "انتشار ممکن نشد. ورودی خود را بررسی کنید.",
        "caught_up_toast": "همه خوانده شد ✨",
        "delete": "حذف",
        "profile_saved": "پروفایل به‌روزرسانی شد",
        "password_changed": "گذرواژه تغییر کرد",
        "passwords_mismatch": "گذرواژه‌های جدید یکسان نیستند.",
        "fill_password_fields": "هر دو فیلد گذرواژه را پر کنید.",
        "invalid_image_type": "لطفاً تصویری از نوع JPG، PNG، WebP یا GIF انتخاب کنید.",
        "image_too_large": "حجم تصویر بیش از حد مجاز است (حداکثر ۱۰ مگابایت).",
        "upload_bad_type": "نوع فایل مجاز نیست. فرمت‌های مجاز:",
        "upload_too_large": "حجم فایل بیش از حد مجاز است.",
        "upload_max_image": "حداکثر ۱۰ مگابایت.",
        "upload_max_video": "حداکثر ۲۰۰ مگابایت.",
        "upload_max_audio": "حداکثر ۳۰ مگابایت.",
        "prompt_required": "متن پرامپت برای پست پرامپتی الزامی است.",
        "media_required_image": "برای این پست یک تصویر انتخاب کنید.",
        "media_required_video": "برای این پست یک ویدیو انتخاب کنید.",
        "media_required_audio": "برای این پست یک فایل صوتی انتخاب کنید.",
        "date_locale": "fa-IR",
    },
}
