from dataclasses import dataclass


@dataclass(frozen=True)
class LabelSpec:
    singular: str
    plural: str


@dataclass(frozen=True)
class RouteSpec:
    slug: str

    @property
    def list_url_name(self) -> str:
        return f"plugins:netbox_rpki:{self.slug}_list"

    @property
    def add_url_name(self) -> str:
        return f"plugins:netbox_rpki:{self.slug}_add"


@dataclass(frozen=True)
class ApiSpec:
    serializer_name: str
    viewset_name: str
    basename: str
    fields: tuple[str, ...]
    brief_fields: tuple[str, ...]

    @property
    def detail_view_name(self) -> str:
        return f"plugins-api:netbox_rpki-api:{self.basename}-detail"


@dataclass(frozen=True)
class NavigationSpec:
    group: str
    label: str
    order: int


@dataclass(frozen=True)
class FormSpec:
    class_name: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class FilterFormSpec:
    class_name: str


@dataclass(frozen=True)
class FilterSetSpec:
    class_name: str
    fields: tuple[str, ...]
    search_fields: tuple[str, ...]


@dataclass(frozen=True)
class GraphQLFilterFieldSpec:
    field_name: str
    filter_kind: str


@dataclass(frozen=True)
class GraphQLFilterSpec:
    class_name: str
    fields: tuple[GraphQLFilterFieldSpec, ...]


@dataclass(frozen=True)
class GraphQLTypeSpec:
    class_name: str
    fields: str = "__all__"


@dataclass(frozen=True)
class GraphQLSpec:
    filter: GraphQLFilterSpec
    type: GraphQLTypeSpec
    detail_field_name: str
    list_field_name: str


@dataclass(frozen=True)
class TableSpec:
    class_name: str
    fields: tuple[str, ...]
    default_columns: tuple[str, ...]
    linkify_field: str


@dataclass(frozen=True)
class ViewSpec:
    list_class_name: str
    detail_class_name: str
    edit_class_name: str
    delete_class_name: str
    simple_detail: bool = False


@dataclass(frozen=True)
class ObjectSpec:
    key: str
    model: type
    labels: LabelSpec
    routes: RouteSpec
    api: ApiSpec
    filterset: FilterSetSpec
    graphql: GraphQLSpec | None = None
    navigation: NavigationSpec | None = None
    form: FormSpec | None = None
    filter_form: FilterFormSpec | None = None
    table: TableSpec | None = None
    view: ViewSpec | None = None

    @property
    def list_url_name(self) -> str:
        return self.routes.list_url_name

    @property
    def add_url_name(self) -> str:
        return self.routes.add_url_name

    @property
    def has_menu_item(self) -> bool:
        return self.navigation is not None