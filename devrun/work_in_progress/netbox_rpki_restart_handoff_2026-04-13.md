# NetBox RPKI Restart Handoff

Date: 2026-04-13

## Stable Current State

- Slice 2 and slice 3 low-trust changes were selectively reverted.
- Slice 1 is preserved and remains the current baseline.
- The repo is ready for a sequential manual rebuild of slice 2.

## What Was Preserved

- Provider-account roll-up and summary contract work in `netbox_rpki/services/provider_sync_contract.py`
- Latest snapshot and diff summary persistence in `netbox_rpki/services/provider_sync.py`
- Provider-account summary exposure in REST and GraphQL
- Operations dashboard reporting depth for freshness, family coverage, latest snapshot, and latest diff
- Matching slice 1 regression coverage

## What Was Reverted

- Slice 2 snapshot and diff family-rollup surface expansion beyond the slice 1 baseline
- Slice 3 publication-observation evidence plumbing and related parser or reporting changes
- Residual slice 3 evidence-heavy fixture setup in `netbox_rpki/tests/test_api.py` and `netbox_rpki/tests/test_views.py`

## Verification Status

Focused post-revert verification passed.

Command:

```bash
cd /home/mencken/src/netbox-v4.5.7/netbox && \
NETBOX_RPKI_ENABLE=1 \
/home/mencken/.virtualenvs/netbox-4.5.7/bin/python manage.py test --keepdb --noinput \
netbox_rpki.tests.test_provider_sync \
netbox_rpki.tests.test_provider_sync_krill \
netbox_rpki.tests.test_api \
netbox_rpki.tests.test_graphql \
netbox_rpki.tests.test_views \
netbox_rpki.tests.test_urls \
netbox_rpki.tests.test_navigation \
netbox_rpki.tests.test_imported_provider_registry
```

Result: 316 tests, OK.

## Next Step

Rebuild Priority 2 slice 2 manually and sequentially.

Target scope:

- richer family-specific diff views
- family freshness and churn reporting for already imported Krill families
- additive reporting only
- no slice 3 evidence expansion
- no new provider coverage

Primary files to start with:

- `netbox_rpki/services/provider_sync_contract.py`
- `netbox_rpki/services/provider_sync_diff.py`
- `netbox_rpki/detail_specs.py`
- `netbox_rpki/tests/test_provider_sync.py`
- `netbox_rpki/tests/test_provider_sync_krill.py`
- `netbox_rpki/tests/test_api.py`
- `netbox_rpki/tests/test_graphql.py`
- `netbox_rpki/tests/test_views.py`

## Working Tree Notes

- There are still unrelated planning doc changes under `devrun/work_in_progress/`; do not revert them as part of slice 2.
- The large ASPA planning document is unrelated to the slice 2 restart point.
- If the IDE restart kills terminals, restart local services explicitly rather than assuming they survived.