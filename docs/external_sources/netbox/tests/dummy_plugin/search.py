from netbox.search import SearchIndex
from netbox.tests.dummy_plugin.models import DummyModel


class DummyModelIndex(SearchIndex):
    model = DummyModel
    fields = (
        ('name', 100),
    )


indexes = (
    DummyModelIndex,
)
