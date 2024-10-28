from rest_framework import serializers

from netbox.api.serializers.base import *
from netbox.api.serializers.features import *
from netbox.api.serializers.generic import *
from netbox.api.serializers.nested import *


#
# Base model serializers
#

class NetBoxModelSerializer(TaggableModelSerializer, CustomFieldModelSerializer, ValidatedModelSerializer):
    """
    Adds support for custom fields and tags.
    """
    pass


class NestedGroupModelSerializer(NetBoxModelSerializer):
    """
    Extends PrimaryModelSerializer to include MPTT support.
    """
    _depth = serializers.IntegerField(source='level', read_only=True)


class BulkOperationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
