"""Management command to set up admin permissions and groups."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from core.models import AuditLog
from core.permissions import ADMIN_GROUPS, ADMIN_PERMISSIONS, create_admin_permissions


class Command(BaseCommand):
    help = "Create custom admin permissions and groups for operational access control"

    def handle(self, *args, **options):
        # Ensure permissions exist
        create_admin_permissions()

        # Create groups
        for group_name, permission_codenames in ADMIN_GROUPS.items():
            group, created = Group.objects.get_or_create(name=group_name)
            permissions = Permission.objects.filter(codename__in=permission_codenames)
            group.permissions.set(permissions)

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {group_name}"))
            else:
                self.stdout.write(f"Updated group: {group_name}")

            self.stdout.write(f"  Permissions: {', '.join(permission_codenames)}")

        self.stdout.write(self.style.SUCCESS("Admin permissions and groups configured."))