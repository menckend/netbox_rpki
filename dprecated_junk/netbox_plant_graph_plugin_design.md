# NetBox Plant-Graph Plugin Design Sketch
## Lane-aware, plane-aware topology extension for shuffle-heavy multi-plane RoCE fabrics

**Status:** implementation sketch / handoff document  
**Target platform:** NetBox plugin for NetBox 4.5+  
**Primary objective:** extend NetBox from inventory and structured cabling source-of-truth into a **lane-aware physical plant topology service** for GPU fabrics with shuffle cables/modules and multi-plane path semantics.

---

## 1. Executive summary

This document sketches a NetBox plugin that layers a **plant-graph model** on top of native NetBox inventory and cabling. The plugin is intended for environments with:

- multiple regions, sites, datacenters, halls, and pods
- GPU clusters using **minimum 4-plane** RoCEv2 fabrics
- 800G physical host and switch ports subdivided into **200G child transport units**
- optional need to drill down further into **discrete PAM4 lane primitives**
- shuffle cables and/or shuffle modules at:
  - GPU ↔ leaf
  - leaf ↔ spine
  - spine ↔ meta-spine
- a requirement to expose the resulting topology as a **queryable graph API** for automation, troubleshooting, validation, and visualization

This plugin **does not replace** NetBox core inventory or core cable tracing. Instead:

- **NetBox remains the inventory/cabling source of truth**
- the plugin maintains a **derived, normalized, graph-oriented topology layer**
- advanced consumers query the plugin’s graph API rather than trying to infer topology directly from raw NetBox objects

### Key design principle

The plugin’s topology model must support multiple resolutions:

1. **Container resolution**  
   Example: physical 800G port, patch panel face, cassette connector

2. **Attachment-unit resolution**  
   Example: a 200G child transport unit belonging to one plane

3. **Signal-lane resolution**  
   Example: individual PAM4 electrical/optical lane primitives inside that 200G transport unit

Operationally, the system should default to **attachment-unit resolution**, while allowing optional drill-down to signal-lane resolution for forensic or debugging workflows.

---

## 2. Why a plugin and not a fork?

This design is intentionally **plugin-shaped**.

The plugin should own:

- custom database models
- graph derivation logic
- graph query APIs
- background jobs for sync/rebuild
- custom UI pages for graph exploration and path tracing
- validation and audit workflows
- optional event-driven incremental refresh behavior

The plugin should **not** try to transparently replace all NetBox-native cable/path-trace behavior inside core object pages. That path leads to brittle coupling and a long-term maintenance tax.

### Recommended architecture boundary

**NetBox core owns:**
- devices
- interfaces / child interfaces
- front ports / rear ports
- cables
- cable profiles
- physical placement and inventory hierarchy

**Plugin owns:**
- graph normalization
- plane semantics
- lane-aware topology traversal
- path resolution at multiple granularities
- audit logic
- blast-radius and dependency analysis
- consumer-friendly APIs

---

## 3. Design goals

### Functional goals

The plugin must allow consumers to answer questions such as:

- What is the full physical path from GPU `host123/nic0/plane2-child` to its serving leaf?
- Which exact shuffle modules, cassette positions, and trunks are traversed by a given 200G child transport unit?
- Which exact PAM4 lanes are involved if a 200G child path is mapped incorrectly?
- Which GPU paths in a hall violate plane diversity or disjointness rules?
- What is the blast radius if shuffle module `SM-H1-P12-R3-A` fails?
- Which leaf-to-spine and spine-to-meta-spine paths share passive artifacts that should be plane-isolated?
- Can we render a subgraph for Pod X, Plane Y at either:
  - container level
  - attachment-unit level
  - signal-lane level

### Non-goals

The first implementation should **not** attempt to:

- replace NetBox core trace UX everywhere
- model full telecom/OSP complexity
- solve every optical device type in v1
- create a perfectly normalized abstract graph ontology
- persist redundant graph detail that can be cheaply and deterministically derived

---

## 4. Real-world modeling assumptions

This design assumes the following practical realities:

### 4.1 Host-facing ports are channelized
An 800G GPU NIC port is not the true atomic path endpoint. It is a **container** for multiple lower-speed transport units, for example four 200G child units.

### 4.2 Passive infrastructure is topology-bearing
Shuffle modules, shuffle cables, cassettes, trunks, and patch panels are not decorative metadata. They carry meaningful internal transfer/mapping semantics and therefore must participate in the graph.

### 4.3 Different resolutions are needed for different workflows
Most operational consumers want to reason about **200G attachment units**, not about every individual PAM4 lane. But forensic workflows must be able to drill all the way down when necessary.

### 4.4 Plane identity lives below the device
A physical 800G port may host multiple child transport units that participate in different planes. Therefore plane semantics cannot live only at the device or physical-port layer.

---

## 5. Topology abstraction model

The plugin should distinguish the following concepts cleanly:

### 5.1 Container
A physical connector-bearing object, such as:

- an 800G NIC port
- an 800G switch port
- a panel face
- a cassette connector
- an MPO port on a shuffle module

### 5.2 Attachment Unit
A graph-visible transport endpoint that participates in fabric pathing, such as:

- a 200G child interface of an 800G host port
- a 200G child interface of an 800G switch port
- a grouped set of passive positions associated with one path segment

### 5.3 Signal Lane
The finest transport primitive, such as:

- one PAM4 electrical TX lane
- one PAM4 electrical RX lane
- one optical TX lane
- one optical RX lane

### 5.4 Coarse Transport Edge
A physical connection between two container-level endpoints, usually corresponding to a NetBox cable.

### 5.5 Fine Transport Edge
A derived edge between attachment units or signal lanes after profile and mapping expansion.

### 5.6 Transfer Mapping
An internal mapping relationship inside a plant object or cable assembly, such as:

- identity mapping
- lane shuffle
- polarity swap
- breakout mapping
- cassette remap

---

## 6. Recommended plugin package name

Working name:

`netbox_plant_graph`

Possible alternatives:
- `netbox_fabric_plant`
- `netbox_lanegraph`
- `netbox_roce_topology`

Use a name that is broad enough to support future expansion beyond GPU fabrics if desired.

---

## 7. Proposed plugin package layout

```text
netbox_plant_graph/
├── __init__.py
├── plugin_config.py
├── constants.py
├── choices.py
├── signals.py
├── navigation.py
├── urls.py
├── filtersets.py
├── forms.py
├── tables.py
├── search.py
├── template_extensions.py
├── graphql/
│   ├── __init__.py
│   └── schema.py
├── api/
│   ├── __init__.py
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── models/
│   ├── __init__.py
│   ├── plant.py
│   ├── topology.py
│   ├── mappings.py
│   ├── policies.py
│   └── sync.py
├── jobs/
│   ├── __init__.py
│   ├── full_rebuild.py
│   ├── incremental_refresh.py
│   ├── plane_audit.py
│   └── blast_radius.py
├── services/
│   ├── __init__.py
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   ├── transformer.py
│   │   ├── graph_builder.py
│   │   └── rebuilder.py
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── resolution.py
│   │   ├── traversal.py
│   │   ├── resolver.py
│   │   ├── blast_radius.py
│   │   └── audits.py
│   └── netbox/
│       ├── __init__.py
│       ├── adapters.py
│       └── selectors.py
├── views/
│   ├── __init__.py
│   ├── graph.py
│   ├── paths.py
│   ├── audits.py
│   └── inventory.py
├── templates/netbox_plant_graph/
│   ├── graph_overview.html
│   ├── path_detail.html
│   ├── plane_audit.html
│   ├── blast_radius.html
│   └── includes/
│       ├── object_badges.html
│       └── path_summary.html
├── migrations/
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_sync.py
    ├── test_resolver.py
    ├── test_api.py
    ├── test_graphql.py
    └── fixtures/
```

---

## 8. Plugin configuration skeleton

### `plugin_config.py`

```python
from netbox.plugins import PluginConfig

class PlantGraphConfig(PluginConfig):
    name = "netbox_plant_graph"
    verbose_name = "Plant Graph"
    description = "Lane-aware, plane-aware topology graph for structured GPU fabric cabling"
    version = "0.1.0"
    author = "Your Team"
    author_email = "team@example.com"
    base_url = "plant-graph"
    min_version = "4.5.0"
    required_settings = []
    default_settings = {
        "graph_default_resolution": "attachment_unit",
        "enable_incremental_refresh": True,
        "max_path_depth": 256,
        "materialize_signal_lanes": True,
        "default_plane_field_name": "fabric_plane",
        "default_fabric_field_name": "fabric_name",
    }

config = PlantGraphConfig
```

---

## 9. Core data model

The following models are the core of the plugin.

### 9.1 `PlantNode`

Represents any meaningful graph node corresponding to a physical or logical plant object.

Examples:
- device
- patch panel
- shuffle module
- cassette
- cable assembly
- trunk bundle

Suggested fields:

```python
class PlantNode(NetBoxModel):
    name = models.CharField(max_length=200)
    node_type = models.CharField(max_length=50, choices=PlantNodeTypeChoices)
    role = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=50, blank=True)

    location_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    location_id = models.PositiveBigIntegerField(null=True, blank=True)
    location = GenericForeignKey("location_type", "location_id")

    source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    source = GenericForeignKey("source_type", "source_id")

    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- `source` should point back to the canonical NetBox object where applicable
- `metadata` should store lightweight derived information only, not large denormalized blobs
- `PlantNode` should be the top-level object for graph visualization and blast-radius analysis

---

### 9.2 `TerminationPoint`

Represents a physical connector-bearing endpoint or container.

Examples:
- GPU NIC physical 800G port
- switch physical 800G port
- shuffle module MPO face
- panel front port
- cassette rear port

Suggested fields:

```python
class TerminationPoint(NetBoxModel):
    plant_node = models.ForeignKey("PlantNode", related_name="termination_points", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    tp_type = models.CharField(max_length=50, choices=TerminationPointTypeChoices)

    connector_type = models.CharField(max_length=100, blank=True)
    channel_capacity = models.PositiveIntegerField(default=0)
    speed_gbps = models.PositiveIntegerField(null=True, blank=True)

    source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    source = GenericForeignKey("source_type", "source_id")

    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- `channel_capacity` is a semantic hint, not necessarily a statement about active children
- many `TerminationPoint`s will have a direct source relationship to a NetBox interface, front port, or rear port

---

### 9.3 `AttachmentUnit`

Represents the graph-visible transport endpoint used for normal pathing.

Examples:
- one 200G child interface of an 800G host port
- one 200G child interface of a switch port
- one passive position-group logically associated with a 200G transport path

Suggested fields:

```python
class AttachmentUnit(NetBoxModel):
    termination_point = models.ForeignKey("TerminationPoint", related_name="attachment_units", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    ordinal = models.PositiveIntegerField(default=0)
    unit_type = models.CharField(max_length=50, choices=AttachmentUnitTypeChoices)
    speed_gbps = models.PositiveIntegerField(null=True, blank=True)

    topology_role = models.CharField(max_length=50, blank=True)
    active = models.BooleanField(default=True)

    source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    source = GenericForeignKey("source_type", "source_id")

    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- this should usually be the **default resolution** object for path queries
- host and switch child interfaces should map naturally here
- if a passive artifact does not exist as a NetBox child interface, the plugin may still synthesize attachment units for it

---

### 9.4 `SignalLane`

Represents the finest transport primitive.

Examples:
- one PAM4 electrical TX lane inside a host 200G child
- one optical RX lane inside a cassette-facing position group

Suggested fields:

```python
class SignalLane(NetBoxModel):
    attachment_unit = models.ForeignKey("AttachmentUnit", related_name="signal_lanes", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    lane_index = models.PositiveIntegerField(default=0)

    lane_kind = models.CharField(max_length=50, choices=SignalLaneKindChoices)
    signaling = models.CharField(max_length=32, choices=SignalEncodingChoices, default="pam4")
    nominal_rate_gbps = models.PositiveIntegerField(null=True, blank=True)

    direction_role = models.CharField(max_length=50, blank=True)
    wavelength_group = models.CharField(max_length=64, blank=True)

    source_anchor = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- lane cardinality should be driven by media/profile metadata, not hardcoded assumptions
- not every path query should expand to this level unless requested

---

### 9.5 `CoarseEdge`

Represents a physical connection between two container-level endpoints.

Usually corresponds 1:1 with a NetBox cable.

```python
class CoarseEdge(NetBoxModel):
    edge_type = models.CharField(max_length=50, choices=CoarseEdgeTypeChoices)

    a_tp = models.ForeignKey("TerminationPoint", related_name="coarse_edges_a", on_delete=models.CASCADE)
    b_tp = models.ForeignKey("TerminationPoint", related_name="coarse_edges_b", on_delete=models.CASCADE)

    source_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.PROTECT)
    source_id = models.PositiveBigIntegerField(null=True, blank=True)
    source = GenericForeignKey("source_type", "source_id")

    cable_profile_name = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- do not attempt to store the full expanded lane map here
- store enough information to anchor back to the NetBox cable

---

### 9.6 `FineEdge`

Represents a derived graph edge between attachment units or signal lanes.

```python
class FineEdge(NetBoxModel):
    granularity = models.CharField(max_length=32, choices=GraphResolutionChoices)
    edge_type = models.CharField(max_length=50, choices=FineEdgeTypeChoices)

    a_au = models.ForeignKey("AttachmentUnit", null=True, blank=True, related_name="fine_edges_a_au", on_delete=models.CASCADE)
    b_au = models.ForeignKey("AttachmentUnit", null=True, blank=True, related_name="fine_edges_b_au", on_delete=models.CASCADE)

    a_lane = models.ForeignKey("SignalLane", null=True, blank=True, related_name="fine_edges_a_lane", on_delete=models.CASCADE)
    b_lane = models.ForeignKey("SignalLane", null=True, blank=True, related_name="fine_edges_b_lane", on_delete=models.CASCADE)

    parent_coarse_edge = models.ForeignKey("CoarseEdge", null=True, blank=True, related_name="fine_edges", on_delete=models.CASCADE)
    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- exactly which fields are populated depends on granularity
- this model may be materialized or rebuilt as needed
- if performance/storage becomes an issue later, signal-lane edges can become partially virtualized

---

### 9.7 `TransferMap`

Represents internal mapping between attachment units.

```python
class TransferMap(NetBoxModel):
    owner_node = models.ForeignKey("PlantNode", null=True, blank=True, related_name="transfer_maps", on_delete=models.CASCADE)
    owner_edge = models.ForeignKey("CoarseEdge", null=True, blank=True, related_name="transfer_maps", on_delete=models.CASCADE)

    src_attachment_unit = models.ForeignKey("AttachmentUnit", related_name="transfer_map_sources", on_delete=models.CASCADE)
    dst_attachment_unit = models.ForeignKey("AttachmentUnit", related_name="transfer_map_destinations", on_delete=models.CASCADE)

    mapping_type = models.CharField(max_length=50, choices=TransferMapTypeChoices)
    metadata = models.JSONField(default=dict, blank=True)
```

Examples:
- breakout mapping
- attachment-unit shuffle through a passive module
- attachment-unit polarity remap

---

### 9.8 `LaneMap`

Represents fine-grained mapping between signal lanes.

```python
class LaneMap(NetBoxModel):
    owner_node = models.ForeignKey("PlantNode", null=True, blank=True, related_name="lane_maps", on_delete=models.CASCADE)
    owner_edge = models.ForeignKey("CoarseEdge", null=True, blank=True, related_name="lane_maps", on_delete=models.CASCADE)

    src_lane = models.ForeignKey("SignalLane", related_name="lane_map_sources", on_delete=models.CASCADE)
    dst_lane = models.ForeignKey("SignalLane", related_name="lane_map_destinations", on_delete=models.CASCADE)

    mapping_type = models.CharField(max_length=50, choices=LaneMapTypeChoices)
    metadata = models.JSONField(default=dict, blank=True)
```

Examples:
- lane shuffle
- polarity swap
- host-to-optic internal mapping
- cassette lane remap

---

### 9.9 `FabricPlane`

Represents a plane within a fabric.

```python
class FabricPlane(NetBoxModel):
    fabric_name = models.CharField(max_length=200)
    plane_number = models.PositiveIntegerField()
    description = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("fabric_name", "plane_number")
```

---

### 9.10 `PlaneMembership`

Associates graph objects with planes.

```python
class PlaneMembership(NetBoxModel):
    plane = models.ForeignKey("FabricPlane", related_name="memberships", on_delete=models.CASCADE)

    member_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    member_id = models.PositiveBigIntegerField()
    member = GenericForeignKey("member_type", "member_id")

    membership_role = models.CharField(max_length=50, choices=PlaneMembershipRoleChoices)
    metadata = models.JSONField(default=dict, blank=True)
```

Notes:
- in your environment, plane membership is especially meaningful on `AttachmentUnit`
- membership on `SignalLane` is optional but may be useful for debugging
- some passive artifacts may be shared or transit-scoped

---

### 9.11 Optional `PathIntent`

This can be added in phase 2 if you want policy-vs-reality validation.

```python
class PathIntent(NetBoxModel):
    name = models.CharField(max_length=200)
    source_type = models.ForeignKey(ContentType, related_name="+", on_delete=models.CASCADE)
    source_id = models.PositiveBigIntegerField()
    source = GenericForeignKey("source_type", "source_id")

    destination_type = models.ForeignKey(ContentType, related_name="+", on_delete=models.CASCADE)
    destination_id = models.PositiveBigIntegerField()
    destination = GenericForeignKey("destination_type", "destination_id")

    required_plane_count = models.PositiveIntegerField(default=4)
    required_disjointness = models.CharField(max_length=50, choices=DisjointnessChoices)
    metadata = models.JSONField(default=dict, blank=True)
```

---

## 10. Enumerations / choices

At minimum define the following choice sets:

- `PlantNodeTypeChoices`
- `TerminationPointTypeChoices`
- `AttachmentUnitTypeChoices`
- `SignalLaneKindChoices`
- `SignalEncodingChoices`
- `CoarseEdgeTypeChoices`
- `FineEdgeTypeChoices`
- `TransferMapTypeChoices`
- `LaneMapTypeChoices`
- `GraphResolutionChoices`
- `PlaneMembershipRoleChoices`
- `DisjointnessChoices`

Suggested values:

### `GraphResolutionChoices`
- `container`
- `attachment_unit`
- `signal_lane`

### `TransferMapTypeChoices`
- `identity`
- `shuffle`
- `breakout`
- `polarity_swap`
- `grouping`

### `LaneMapTypeChoices`
- `identity`
- `lane_shuffle`
- `polarity_swap`
- `serdes_grouping`
- `optic_mux`
- `optic_demux`

### `PlaneMembershipRoleChoices`
- `native`
- `shared`
- `transit`
- `cross_plane_exception`

---

## 11. Data source mapping from NetBox core

The plugin’s sync layer should derive graph objects from the following native NetBox objects.

### 11.1 Devices and modules
Used to create `PlantNode` rows for:
- GPU hosts
- leaf switches
- spine switches
- meta-spine switches
- passive devices if represented as devices

### 11.2 Interfaces
Used to create `TerminationPoint`s for:
- physical host and switch ports

May also be used to create `AttachmentUnit`s for:
- child interfaces representing 200G subinterfaces

### 11.3 Front ports / rear ports
Used to create:
- `TerminationPoint`s for passive patch/shuffle objects
- `AttachmentUnit`s where grouped positions are required

### 11.4 Cables
Used to create:
- `CoarseEdge`s

### 11.5 Cable profiles
Used to derive:
- profile-aware expansion of `FineEdge`s
- lane/position transfer information
- internal mapping hints for cable assemblies

### 11.6 Many-to-many port mappings
Used to derive:
- `TransferMap`s
- potentially `LaneMap`s if the passive element’s structure needs finer drill-down

### 11.7 Custom fields / tags
Used to derive:
- fabric identity
- plane number
- roles
- placement hints
- service ownership

---

## 12. Sync architecture

The sync pipeline should be deterministic and idempotent.

### 12.1 Sync stages

#### Stage 1: Extract
Read required NetBox core objects via ORM selectors:
- devices
- interfaces
- child interfaces
- ports
- cables
- cable profiles
- port mappings
- locations / racks if needed

#### Stage 2: Normalize
Convert raw NetBox objects into intermediate DTOs:
- `NodeInput`
- `TerminationInput`
- `AttachmentUnitInput`
- `CableInput`
- `TransferInput`
- `PlaneInput`

#### Stage 3: Materialize graph objects
Create/update:
- `PlantNode`
- `TerminationPoint`
- `AttachmentUnit`
- `SignalLane` if configured
- `CoarseEdge`
- `TransferMap`
- `LaneMap`
- `PlaneMembership`

#### Stage 4: Derive edges
Build:
- `FineEdge`s at attachment-unit resolution
- optionally `FineEdge`s at signal-lane resolution

#### Stage 5: Validate graph integrity
Run graph consistency checks:
- orphaned nodes
- unattached attachment units
- invalid transfer maps
- ambiguous endpoints
- duplicate plane assignments where forbidden

### 12.2 Full rebuild vs incremental refresh

#### Full rebuild
Use when:
- plugin first installed
- major schema or profile changes
- large inventory import
- operator explicitly requests rebuild

#### Incremental refresh
Use when:
- a device changes
- interface/child interface changes
- a cable is added/removed/changed
- passive mappings change

Recommended approach:
- event-driven enqueue of a narrow rebuild scope
- coalesce related changes into a single job when possible

### 12.3 Rebuild scoping
The sync layer should support scoped rebuild by:
- object ID
- rack
- pod
- hall
- fabric
- plane

This prevents every small cable edit from triggering a graph-wide rebuild storm.

---

## 13. Service-layer design

Keep business logic out of views and serializers.

### 13.1 `extractor.py`
Responsibilities:
- query NetBox source objects
- batch/prefetch related data
- return normalized source bundles

### 13.2 `transformer.py`
Responsibilities:
- convert source bundles into graph-oriented inputs
- classify passive structures
- derive container/attachment/lane cardinality
- interpret profile and mapping metadata

### 13.3 `graph_builder.py`
Responsibilities:
- upsert graph models
- manage keys and source relationships
- create/update memberships
- handle deletion of stale derived objects

### 13.4 `resolver.py`
Responsibilities:
- resolve paths at selected graph resolution
- support scope constraints and plane constraints
- return path structures for both API and UI

### 13.5 `traversal.py`
Responsibilities:
- adjacency functions
- BFS/DFS/Dijkstra-like helpers if weighted edges ever appear
- cycle detection
- depth guards

### 13.6 `audits.py`
Responsibilities:
- plane diversity checks
- disjointness audits
- cross-plane contamination checks
- passive artifact sharing analysis

### 13.7 `blast_radius.py`
Responsibilities:
- identify impacted nodes, edges, paths for a failed object
- support failure modes by:
  - node
  - coarse edge
  - fine edge
  - lane

---

## 14. Resolution rules

The plugin should expose explicit graph-resolution modes.

### 14.1 Container resolution
Used for:
- inventory adjacency
- high-level visualization
- rough impact analysis

Objects traversed:
- `PlantNode`
- `TerminationPoint`
- `CoarseEdge`

### 14.2 Attachment-unit resolution
Used for:
- default path resolution
- plane-aware fabric analysis
- operational connectivity validation

Objects traversed:
- `AttachmentUnit`
- `FineEdge`
- `TransferMap`

### 14.3 Signal-lane resolution
Used for:
- forensic debugging
- lane continuity validation
- advanced shuffle/cassette troubleshooting

Objects traversed:
- `SignalLane`
- `FineEdge`
- `LaneMap`

### Resolution policy
Default to **attachment-unit** unless the caller requests otherwise.

---

## 15. API design

Expose the graph through both REST and GraphQL.

### 15.1 REST endpoints

Suggested routes:

```text
/plugins/plant-graph/api/nodes/
/plugins/plant-graph/api/termination-points/
/plugins/plant-graph/api/attachment-units/
/plugins/plant-graph/api/signal-lanes/
/plugins/plant-graph/api/coarse-edges/
/plugins/plant-graph/api/fine-edges/
/plugins/plant-graph/api/fabric-planes/
/plugins/plant-graph/api/plane-memberships/

/plugins/plant-graph/api/resolve-path/
/plugins/plant-graph/api/neighbors/
/plugins/plant-graph/api/blast-radius/
/plugins/plant-graph/api/plane-audit/
/plugins/plant-graph/api/render-subgraph/
/plugins/plant-graph/api/rebuild-graph/
/plugins/plant-graph/api/refresh-scope/
```

### 15.2 `resolve-path` request example

```json
{
  "source_object_type": "netbox_plant_graph.attachmentunit",
  "source_object_id": 12345,
  "destination_object_type": "netbox_plant_graph.attachmentunit",
  "destination_object_id": 67890,
  "plane": 2,
  "resolution": "attachment_unit",
  "max_depth": 128
}
```

### 15.3 `resolve-path` response example

```json
{
  "resolution": "attachment_unit",
  "path_found": true,
  "path": [
    {"object_type": "attachment_unit", "id": 101, "name": "gpu01:p0:au2"},
    {"object_type": "fine_edge", "id": 5001, "edge_type": "derived_cable_segment"},
    {"object_type": "plant_node", "id": 901, "name": "shuffle-module-h1p4-17"},
    {"object_type": "transfer_map", "id": 3201, "mapping_type": "shuffle"},
    {"object_type": "attachment_unit", "id": 202, "name": "leaf17:Eth1/9:au0"}
  ],
  "summary": {
    "planes_touched": [2],
    "shuffle_modules_crossed": 1,
    "coarse_cables_crossed": 3
  }
}
```

### 15.4 GraphQL

GraphQL should expose:
- object retrieval
- adjacency queries
- filtered subgraph traversal
- path resolution for UI clients

Do not try to implement every graph operation as GraphQL first. Use REST for complex procedural path requests; use GraphQL for rich object exploration.

---

## 16. UI design

The first UI should be practical, not cinematic.

### 16.1 Navigation
Add a top-level plugin submenu:
- Graph Overview
- Path Resolver
- Plane Audits
- Blast Radius
- Rebuild Jobs
- Settings/Health

### 16.2 Graph Overview page
Capabilities:
- scope by site/hall/pod
- filter by plane
- choose resolution
- render summary graph and counts
- jump into object details

### 16.3 Path Resolver page
Inputs:
- source object
- destination object optional
- resolution
- plane optional
- maximum depth

Outputs:
- ordered path elements
- path summary
- breakdown by plant object category
- optional lane drill-down

### 16.4 Plane Audit page
Outputs:
- missing plane paths
- shared passive artifacts across planes
- disjointness violations
- inconsistent memberships
- orphaned child interfaces

### 16.5 Blast Radius page
Inputs:
- object selection
- failure mode
- resolution
- scope limits

Outputs:
- impacted paths
- impacted attachment units
- impacted planes
- shared infrastructure hotspots

### 16.6 Object detail badges
On selected NetBox object detail pages via template extension:
- whether object is represented in plant graph
- graph object counts
- plane memberships
- quick links to graph explorer/path resolver

---

## 17. Sync and rebuild jobs

The plugin should ship with explicit background jobs.

### 17.1 `FullGraphRebuildJob`
Inputs:
- scope
- include_signal_lanes
- dry_run

Behavior:
- rebuild all plugin graph artifacts within scope
- produce counts and summary stats

### 17.2 `IncrementalRefreshJob`
Inputs:
- changed object type
- changed object id
- force_neighbor_refresh

Behavior:
- determine rebuild scope
- refresh only affected graph region

### 17.3 `PlaneAuditJob`
Inputs:
- fabric
- plane set
- scope

Behavior:
- run policy checks and persist/report findings

### 17.4 `BlastRadiusJob`
Inputs:
- target object
- failure mode
- resolution

Behavior:
- compute impact set and return persisted result

---

## 18. Validation and integrity rules

At minimum implement the following checks.

### 18.1 Source uniqueness
A single source object should not accidentally produce duplicate graph objects of the same semantic type.

### 18.2 Attachment-unit containment
Every `AttachmentUnit` must belong to exactly one `TerminationPoint`.

### 18.3 Signal-lane containment
Every `SignalLane` must belong to exactly one `AttachmentUnit`.

### 18.4 Coarse edge endpoint validity
A `CoarseEdge` must connect exactly two valid `TerminationPoint`s.

### 18.5 Fine-edge granularity validity
If `resolution == attachment_unit`, lane fields must be null.  
If `resolution == signal_lane`, attachment-unit fields may be null or auxiliary.

### 18.6 Transfer-map integrity
A `TransferMap` must have exactly one owner context:
- owner node xor owner edge

### 18.7 Plane membership sanity
Disallow invalid duplicate memberships where policy says an object must be plane-native to only one plane.

### 18.8 No silent ambiguity
If the plugin cannot deterministically derive a mapping from source data, it should:
- create an explicit warning/finding
- mark the affected graph segment unresolved
- avoid silently fabricating certainty

---

## 19. Policy and audit model

Phase 1 can compute audits on demand.  
Phase 2 should persist findings.

Suggested phase-2 model:

```python
class AuditFinding(NetBoxModel):
    finding_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=32)
    object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    object = GenericForeignKey("object_type", "object_id")
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
```

Suggested finding types:
- missing_plane_membership
- duplicate_plane_assignment
- shared_shuffle_artifact
- unresolved_profile_mapping
- orphaned_attachment_unit
- lane_continuity_break
- path_disjointness_violation

---

## 20. Recommended implementation phases

### Phase 0: bootstrap
Deliver:
- plugin skeleton
- menu and landing page
- health page
- base models and migrations

### Phase 1: container + attachment-unit graph
Deliver:
- `PlantNode`
- `TerminationPoint`
- `AttachmentUnit`
- `CoarseEdge`
- `TransferMap`
- `FabricPlane`
- `PlaneMembership`
- full rebuild job
- path resolver at attachment-unit resolution
- basic UI pages

### Phase 2: signal-lane support
Deliver:
- `SignalLane`
- `LaneMap`
- signal-lane `FineEdge`s
- lane drill-down UI
- lane-aware resolver

### Phase 3: audits and policy
Deliver:
- plane audit job
- blast-radius analysis
- audit findings persistence
- disjointness and contamination checks

### Phase 4: polish and performance
Deliver:
- incremental refresh
- caching
- subgraph rendering optimization
- richer template extensions
- user-facing graph summaries on object detail pages

---

## 21. Performance guidance

### 21.1 Keep the canonical graph relational
Do not start with Neo4j or another external graph database unless the relational approach is proven insufficient. The first version should keep operational complexity low.

### 21.2 Use selective materialization
Materialize:
- attachment-unit graph always
- signal-lane graph only if enabled or if required by environment

### 21.3 Prefetch aggressively in sync jobs
When extracting NetBox objects:
- prefetch related interfaces
- prefetch cable terminations and profiles
- avoid ORM N+1 disasters

### 21.4 Build scope-aware rebuilds
Never make “one cable edited” mean “rebuild the entire planet.”

### 21.5 Cache resolved paths when helpful
Possible future optimization:
- cache path results keyed by resolution + scope + object version fingerprints

---

## 22. Testing strategy

### 22.1 Unit tests
Cover:
- graph model constraints
- mapping derivation rules
- resolution-specific traversal
- validation rules

### 22.2 Integration tests
Use fixtures representing:
- simple point-to-point path
- GPU 800G port with four 200G child interfaces
- shuffle cable at GPU ↔ leaf
- shuffle module at leaf ↔ spine
- lane remap case at signal-lane resolution
- cross-plane violation case

### 22.3 Regression tests
Every bug in mapping derivation or path resolution gets a fixture and a permanent test.

### 22.4 Performance tests
Test:
- full rebuild on realistic pod-sized topology
- path resolution at container vs attachment vs lane resolution
- blast-radius query for high-fanout shuffle artifacts

---

## 23. Example end-to-end scenario

Assume the following real-ish topology:

- GPU server `gpu-r1-p07-u19`
- physical NIC port `p0` at 800G
- four 200G child transport units:
  - `au0` plane 0
  - `au1` plane 1
  - `au2` plane 2
  - `au3` plane 3
- `au2` traverses:
  - host-side breakout mapping
  - GPU-hall shuffle cable
  - hall shuffle module
  - leaf downlink `leaf17:Eth1/9:au0`

At the graph layer this should become:

### Plant nodes
- GPU host
- shuffle cable assembly
- shuffle module
- leaf switch

### Termination points
- `gpu-r1-p07-u19:p0`
- shuffle cable face A
- shuffle cable face B
- shuffle module port A
- shuffle module port B
- `leaf17:Eth1/9`

### Attachment units
- `gpu-r1-p07-u19:p0:au0`
- `gpu-r1-p07-u19:p0:au1`
- `gpu-r1-p07-u19:p0:au2`
- `gpu-r1-p07-u19:p0:au3`
- shuffle-unit group representing plane-2 path
- `leaf17:Eth1/9:au0`

### Optional signal lanes
- `gpu-r1-p07-u19:p0:au2:l0`
- `gpu-r1-p07-u19:p0:au2:l1`
- ...
- `leaf17:Eth1/9:au0:l0`
- ...

### Mappings
- attachment-unit breakout/selection mapping from host-side container to `au2`
- transfer map through shuffle module
- optional lane shuffle/polarity map

This scenario should be included as a fixture and demonstrated in both:
- path resolution
- blast-radius analysis

---

## 24. Suggested coding conventions

- Use a dedicated service layer for graph derivation and resolution
- Use `GenericForeignKey` sparingly and consistently
- Keep graph object naming deterministic and human-readable
- Treat every derived object as reproducible from source data
- Avoid burying semantics in opaque JSON blobs
- Maintain explicit `source` references back to NetBox objects wherever possible
- Log unresolved derivation cases loudly

---

## 25. Suggested first API contracts

Implement these first:

### `POST /resolve-path/`
Must support:
- source object
- destination optional
- plane optional
- resolution
- max depth

### `POST /render-subgraph/`
Must support:
- scope
- plane
- resolution
- include_passive_objects
- include_orphans

### `POST /plane-audit/`
Must support:
- scope
- expected_plane_count
- disjointness mode

### `POST /blast-radius/`
Must support:
- target object
- failure mode
- resolution

---

## 26. Risks and sharp edges

### 26.1 Source-model ambiguity
Some passive semantics may not be fully represented in NetBox inventory. The plugin must tolerate partial truth and flag gaps.

### 26.2 Over-materialization
Persisting every possible lane-level edge everywhere can create graph bloat. Start conservative.

### 26.3 Event storms
Naive incremental refresh can flood the job queue if many related objects change at once.

### 26.4 Scope creep
Do not try to solve every optical or telecom edge case in the first release.

### 26.5 UX overload
Lane-level detail is useful but should not be the default visual mode.

---

## 27. Implementation advice for the coding agent

If an agentic coding assistant is given this document, the first milestone should be:

### Milestone A
- create plugin skeleton
- add plugin config and menu
- implement models:
  - `PlantNode`
  - `TerminationPoint`
  - `AttachmentUnit`
  - `CoarseEdge`
  - `TransferMap`
  - `FabricPlane`
  - `PlaneMembership`
- add migrations
- add admin/object views/tables/filtersets
- implement `FullGraphRebuildJob`
- implement `resolve_path()` at attachment-unit resolution only
- create one fixture for:
  - GPU host with one physical 800G port
  - four 200G child units
  - one shuffle module
  - one leaf switch
- write integration tests for path resolution and plane membership

### Milestone B
- add signal-lane objects and lane maps
- expand resolver for signal-lane resolution
- add blast-radius and plane-audit jobs
- add GraphQL schema and richer UI pages

Do not begin with:
- lane-level visualization
- incremental refresh
- aggressive caching
- exotic policy engine features

Get the graph correct before making it flashy.

---

## 28. Open design questions to settle early

These should be answered before implementation drifts too far:

1. Will 200G child interfaces exist explicitly as NetBox child interfaces everywhere, or will some be synthesized by the plugin?
2. Will signal lanes always be materialized, or created only for selected scopes/object types?
3. How will plane identity be sourced:
   - child interface custom fields?
   - tags?
   - naming conventions?
4. Are shuffle modules modeled as NetBox devices, passive devices, or plugin-native plant nodes?
5. Do we need explicit support for unresolved/ambiguous graph segments?
6. Which object types should receive template-extension badges in v1?
7. What scope granularity is required for rebuild jobs:
   - object
   - rack
   - pod
   - hall
   - fabric

---

## 29. Recommendation summary

Build this as a **NetBox plugin that acts as an adjacent graph engine**.

Keep NetBox as the canonical source for:
- inventory
- physical interfaces and child interfaces
- structured cable objects
- passive port mappings

Use the plugin to provide:
- graph normalization
- multi-resolution topology
- plane-aware path resolution
- optional PAM4 lane drill-down
- blast-radius and validation workflows
- consumer-friendly APIs

The most important modeling rule is this:

> **Physical ports are containers.  
> Attachment units are operational endpoints.  
> Signal lanes are forensic endpoints.**

If the implementation preserves that hierarchy cleanly, the plugin will remain both expressive and survivable.

---

## 30. Immediate next step

Implement **Milestone A** only, with attachment-unit resolution as the operational default.  
Do not add signal-lane persistence until attachment-unit pathing is correct and test-covered.

Once that works, signal-lane support becomes an extension rather than a rescue mission.
