from netbox.api.serializers import NetBoxModelSerializer
from rest_framework.serializers import HyperlinkedIdentityField
from rest_framework import serializers

from netbox_rpki import models
from netbox_rpki.object_registry import API_OBJECT_SPECS
from netbox_rpki.object_specs import ObjectSpec


def build_serializer_class(spec: ObjectSpec) -> type[NetBoxModelSerializer]:
    meta_class = type(
        "Meta",
        (),
        {
            "model": spec.model,
            "fields": spec.api.fields,
            "brief_fields": spec.api.brief_fields,
        },
    )

    return type(
        spec.api.serializer_name,
        (NetBoxModelSerializer,),
        {
            "__module__": __name__,
            "url": HyperlinkedIdentityField(view_name=spec.api.detail_view_name),
            "Meta": meta_class,
        },
    )


SERIALIZER_CLASS_MAP = {}
for object_spec in API_OBJECT_SPECS:
    serializer_class = build_serializer_class(object_spec)
    SERIALIZER_CLASS_MAP[object_spec.registry_key] = serializer_class
    globals()[object_spec.api.serializer_name] = serializer_class


class RpkiProviderAccountSerializer(SERIALIZER_CLASS_MAP['rpkiprovideraccount']):
    supports_roa_write = serializers.ReadOnlyField()
    roa_write_mode = serializers.ReadOnlyField()
    roa_write_capability = serializers.ReadOnlyField()
    sync_health = serializers.ReadOnlyField()
    sync_health_display = serializers.ReadOnlyField()
    next_sync_due_at = serializers.DateTimeField(read_only=True)

    class Meta(SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta):
        fields = SERIALIZER_CLASS_MAP['rpkiprovideraccount'].Meta.fields + (
            'supports_roa_write',
            'roa_write_mode',
            'roa_write_capability',
            'sync_health',
            'sync_health_display',
            'next_sync_due_at',
        )


SERIALIZER_CLASS_MAP['rpkiprovideraccount'] = RpkiProviderAccountSerializer
globals()['RpkiProviderAccountSerializer'] = RpkiProviderAccountSerializer


class ROAChangePlanApproveActionSerializer(serializers.Serializer):
    ticket_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    change_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    maintenance_window_start = serializers.DateTimeField(required=False, allow_null=True)
    maintenance_window_end = serializers.DateTimeField(required=False, allow_null=True)
    approval_notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        models.validate_maintenance_window_bounds(
            start_at=attrs.get('maintenance_window_start'),
            end_at=attrs.get('maintenance_window_end'),
        )
        return attrs


__all__ = tuple(spec.api.serializer_name for spec in API_OBJECT_SPECS)
