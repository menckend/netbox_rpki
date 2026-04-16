# Plugin Certification Readiness

This checklist tracks repository and maintainer work needed to qualify `netbox_rpki` for the NetBox Plugin Certification Program.

## Scope

The current certification terms are published at:

- https://github.com/netbox-community/netbox/wiki/Plugin-Certification-Program

Certification is granted per release, not once for the whole plugin. Each release candidate should be checked against this file before publication.

## Repository Criteria

| Requirement | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| OSI-approved license in repo and package metadata | Done | `LICENSE`, `pyproject.toml` | Keep PyPI metadata aligned with the top-level license file. |
| GitHub-hosted source repository | Done | GitHub origin, GitHub workflows, issue templates | None in-repo. |
| NetBox compatibility metadata in README | In progress | `README.md`, `netbox-plugin.yaml` | Keep the README matrix current for every release line and make sure release notes reference the same support window. |
| Reasonably comprehensive tests run as GitHub Workflows | In progress | `.github/workflows/test-certification.yml` | Watch runtime and stabilize failures across both NetBox release anchors. Add browser smoke coverage once the headless path is reliable in CI. |
| Main documentation beyond the top-level README | Done | `docs/`, GitHub Pages workflow | Keep the top-level README as the summary and the Sphinx docs as the detailed reference. |
| README includes screenshots | Done | `README.md`, `images/` | Refresh screenshots when the UI materially changes. |
| README includes dependency summary | Done | `README.md` | Update version ranges when supported external tools change. |
| README includes maintainer contact and user support guidance | Done | `README.md`, `.github/ISSUE_TEMPLATE/` | Revisit if GitHub Discussions, Slack, or commercial support channels are added. |
| README includes a certification-ready icon | Done | `images/netbox-rpki-icon.svg`, `images/netbox-rpki-icon.LICENSE.md`, `README.md` | Keep the asset square, transparent, and CC-licensed. |
| Release notes open with narrative summary | In progress | `CHANGELOG.md` | Standardize every release entry to start with major/minor/patch narrative text, and add a `Breaking Changes` heading whenever needed. |

## Maintainer Criteria

These items cannot be completed purely through repository changes.

| Requirement | Status | Owner | Notes |
| --- | --- | --- | --- |
| Establish GitHub co-maintainer relationship with NetBox Labs | Pending | Lead maintainer | Preferred path is repo transfer to `netbox-community`; alternate paths are maintainers/collaborators in the current org or user account. |
| Establish PyPI break-glass owner access for NetBox Labs | Pending | Lead maintainer | Required so NetBox Labs can publish emergency releases if needed. |
| Prepare certification application email | Pending | Lead maintainer | Include repo URL, PyPI URL, GitHub ID, PyPI user ID, and Slack handle if available. |

## Release Gate

Before cutting a release intended for certification review, verify:

- `README.md` still contains a concise value summary, compatibility matrix, dependency matrix, screenshots, installation steps, maintainer contact, support guidance, and the icon.
- `CHANGELOG.md` opens the new release entry with a brief narrative summary and includes `Breaking Changes` when applicable.
- GitHub Actions CI is green on the supported NetBox anchors.
- The docs site builds successfully and reflects the shipped feature set.
- PyPI metadata matches the repository metadata.

## Near-Term Work Queue

1. Standardize `CHANGELOG.md` release entry format for certification review.
2. Let the new CI workflow run on real branches and tighten failures or flakiness.
3. Decide whether to add a separate browser smoke workflow or keep Playwright as a manual release gate.
4. Complete the GitHub and PyPI co-maintainer setup with NetBox Labs before applying.