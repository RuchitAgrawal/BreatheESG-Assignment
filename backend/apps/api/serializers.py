from rest_framework import serializers
from apps.core.models import Organization, User
from apps.ingestion.models import SourceFile, SourceRow
from apps.records.models import ActivityRecord, RecordRevision
from apps.emissions.models import EmissionFactor, EmissionCalculation


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug"]


class UserMeSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "organization"]


# ---- Source Files -----------------------------------------------------------

class SourceFileSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.SerializerMethodField()

    class Meta:
        model = SourceFile
        fields = [
            "id", "source_type", "filename", "status",
            "row_count", "error_count", "created_at", "uploaded_by_email",
        ]

    def get_uploaded_by_email(self, obj):
        return obj.uploaded_by.email if obj.uploaded_by else None


# ---- Activity Records -------------------------------------------------------

class ActivityRecordListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for the main table view."""
    source_type = serializers.SerializerMethodField()
    source_filename = serializers.SerializerMethodField()
    co2e_kg = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "activity_date", "category", "subcategory",
            "quantity", "unit", "normalized_quantity", "normalized_unit",
            "scope", "state", "quality_tier", "quality_notes",
            "reviewed_by_id", "reviewed_at", "locked_at",
            "created_at", "source_type", "source_filename", "co2e_kg",
        ]

    def get_source_type(self, obj):
        if obj.source_row:
            return obj.source_row.source_file.source_type
        return None

    def get_source_filename(self, obj):
        if obj.source_row:
            return obj.source_row.source_file.filename
        return None

    def get_co2e_kg(self, obj):
        calc = obj.calculations.filter(is_current=True).first()
        return str(calc.co2e_kg) if calc else None


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = ["id", "name", "source", "category", "factor_value", "unit", "valid_from", "valid_to", "version"]


class EmissionCalculationSerializer(serializers.ModelSerializer):
    emission_factor = EmissionFactorSerializer(read_only=True)

    class Meta:
        model = EmissionCalculation
        fields = [
            "id", "co2e_kg", "calculation_notes", "calculated_at",
            "is_current", "emission_factor",
        ]


class SourceRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceRow
        fields = ["id", "row_index", "raw_payload", "parse_status", "parse_error", "created_at"]


class ActivityRecordLineageSerializer(serializers.ModelSerializer):
    """Full lineage chain for the drawer view."""
    source_row = SourceRowSerializer(read_only=True)
    source_file = serializers.SerializerMethodField()
    calculations = EmissionCalculationSerializer(many=True, read_only=True)
    reviewed_by_email = serializers.SerializerMethodField()
    locked_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ActivityRecord
        fields = [
            "id", "activity_date", "category", "subcategory",
            "quantity", "unit", "normalized_quantity", "normalized_unit",
            "scope", "state", "quality_tier", "quality_notes",
            "reviewed_by_email", "reviewed_at",
            "locked_by_email", "locked_at",
            "created_at", "updated_at",
            "source_row", "source_file", "calculations",
        ]

    def get_source_file(self, obj):
        if obj.source_row:
            sf = obj.source_row.source_file
            return {
                "id": str(sf.id),
                "filename": sf.filename,
                "source_type": sf.source_type,
                "file_hash": sf.file_hash,
                "created_at": sf.created_at.isoformat(),
            }
        return None

    def get_reviewed_by_email(self, obj):
        return obj.reviewed_by.email if obj.reviewed_by else None

    def get_locked_by_email(self, obj):
        return obj.locked_by.email if obj.locked_by else None


class RecordRevisionSerializer(serializers.ModelSerializer):
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = RecordRevision
        fields = [
            "id", "field_name", "old_value", "new_value",
            "change_reason", "changed_at", "changed_by_email",
        ]

    def get_changed_by_email(self, obj):
        return obj.changed_by.email if obj.changed_by else "system"


class ActivityRecordUpdateSerializer(serializers.ModelSerializer):
    """For analyst corrections -- only mutable fields."""
    class Meta:
        model = ActivityRecord
        fields = ["quantity", "subcategory"]

    def validate(self, attrs):
        if self.instance and self.instance.state == "locked":
            raise serializers.ValidationError(
                "This record is locked for audit and cannot be modified."
            )
        return attrs
