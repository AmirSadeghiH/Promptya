"""Custom permissions for administrative operations.

These permissions protect sensitive operations in the admin interface.
They should be assigned to specific staff groups rather than given to all staff.
"""

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


# Permission codenames and human-readable names
ADMIN_PERMISSIONS = [
    # User management
    ("can_activate_users", "Can activate users"),
    ("can_deactivate_users", "Can deactivate users"),
    ("can_verify_user_emails", "Can verify user emails"),
    ("can_unverify_user_emails", "Can unverify user emails"),
    ("can_grant_user_credits", "Can grant credits to users"),
    ("can_revoke_user_credits", "Can revoke credits from users"),
    ("can_change_user_staff", "Can change user staff status"),
    ("can_change_user_superuser", "Can change user superuser status"),

    # Post moderation
    ("can_hide_posts", "Can hide posts (moderation)"),
    ("can_unhide_posts", "Can unhide posts"),
    ("can_soft_delete_posts", "Can soft delete posts"),

    # Comment moderation
    ("can_hide_comments", "Can hide comments (moderation)"),
    ("can_unhide_comments", "Can unhide comments"),

    # Challenge management
    ("can_activate_challenges", "Can activate challenges"),
    ("can_deactivate_challenges", "Can deactivate challenges"),
    ("can_reset_challenges", "Can reset challenge completions"),
    ("can_verify_completions", "Can verify challenge completions"),
    ("can_reject_completions", "Can reject challenge completions"),

    # Credit operations
    ("can_adjust_credits", "Can adjust user credits via admin"),

    # Moderation
    ("can_review_reports", "Can review the moderation report queue"),
    ("can_action_reports", "Can action or dismiss reports"),
    ("can_moderate_users", "Can restrict, suspend or ban users"),

    # Configuration
    ("can_change_ai_config", "Can change AI provider configuration"),

    # Audit
    ("can_view_audit_log", "Can view audit log"),
]


def create_admin_permissions():
    """Create custom admin permissions. Call this from a migration or management command."""
    content_type = ContentType.objects.get(app_label="core", model="auditlog")
    for codename, name in ADMIN_PERMISSIONS:
        Permission.objects.get_or_create(
            codename=codename,
            content_type=content_type,
            defaults={"name": name},
        )


# Permission groups for easy assignment
ADMIN_GROUPS = {
    "moderators": [
        "can_hide_posts",
        "can_unhide_posts",
        "can_soft_delete_posts",
        "can_hide_comments",
        "can_unhide_comments",
        "can_review_reports",
        "can_action_reports",
    ],
    "community_managers": [
        "can_activate_users",
        "can_deactivate_users",
        "can_verify_user_emails",
        "can_unverify_user_emails",
        "can_hide_posts",
        "can_unhide_posts",
        "can_hide_comments",
        "can_unhide_comments",
        "can_review_reports",
        "can_action_reports",
        "can_moderate_users",
    ],
    "operations": [
        "can_activate_users",
        "can_deactivate_users",
        "can_verify_user_emails",
        "can_grant_user_credits",
        "can_revoke_user_credits",
        "can_activate_challenges",
        "can_deactivate_challenges",
        "can_reset_challenges",
        "can_verify_completions",
        "can_reject_completions",
        "can_adjust_credits",
    ],
    "super_admins": [p[0] for p in ADMIN_PERMISSIONS],
}


def setup_admin_groups():
    """Create default admin groups with appropriate permissions."""
    from django.contrib.auth.models import Group

    for group_name, permission_codenames in ADMIN_GROUPS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        permissions = Permission.objects.filter(codename__in=permission_codenames)
        group.permissions.set(permissions)