from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

# Fields to track in the audit log
TRACKED_FIELDS = ["quantity", "state", "quality_tier", "subcategory", "reviewed_by_id", "locked_by_id"]


@receiver(pre_save, sender="records.ActivityRecord")
def capture_pre_save_state(sender, instance, **kwargs):
    """Snapshot the old values before save so post_save can diff them."""
    if instance.pk:
        try:
            instance._pre_save_snapshot = sender.objects.get(pk=instance.pk)
        except sender.DoesNotExist:
            instance._pre_save_snapshot = None
    else:
        instance._pre_save_snapshot = None


@receiver(post_save, sender="records.ActivityRecord")
def write_revision_entries(sender, instance, created, **kwargs):
    """Write one RecordRevision row per changed tracked field."""
    if created:
        return  # no diff on creation

    snapshot = getattr(instance, "_pre_save_snapshot", None)
    if snapshot is None:
        return

    from apps.records.models import RecordRevision

    for field in TRACKED_FIELDS:
        old_val = str(getattr(snapshot, field, "") or "")
        new_val = str(getattr(instance, field, "") or "")
        if old_val != new_val:
            RecordRevision(
                activity_record=instance,
                changed_by=getattr(instance, "_changed_by", None),
                field_name=field,
                old_value=old_val or None,
                new_value=new_val or None,
                change_reason=getattr(instance, "_change_reason", ""),
            ).save()
