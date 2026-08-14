"""
Read-only BAM REST v2 access for the reverse-zone map - v2 exclusively, no v1 SDK calls
anywhere in this module (per explicit requirement).

Client construction follows the pattern BlueCat's own builtin workflows (e.g. isp-forwarding,
multiple-view-operations) and other custom Gateway workflows use: prefer the Gateway
session's own `g.user.bam_api.v2` client if the install is configured for it, otherwise
build one by hand and reuse the already-logged-in session's auth - never a separate BAM
login or stored credentials.

Endpoint/field grounding:
- `/configurations`, `/zones` (+ `absoluteName`/`configuration.name` filters) and
  `/zones/{id}/resourceRecords` (HostRecord with `reverseRecord`/`addresses`) are exercised
  by BlueCat's own builtin Gateway workflows (isp-forwarding, multiple-view-operations),
  and independently confirmed against real live data (a real HostRecord lookup returned
  exactly this shape: `reverseRecord: true`, `addresses: [{"type": "IPv4Address",
  "address": "..."}]`).
- `/networks` (flat, top-level, `range` field for CIDR, `configuration.name` filter) and
  `/networks/{id}/deploymentRoles` were confirmed directly against live BAM data: a real
  `/networks` response's own `_links.deploymentRoles` HAL link points at
  `/networks/{id}/deploymentRoles`, proving deployment roles attach to the Network itself in
  BAM's v2 model, not only to Zones.
- No PTR-type GenericRecord is ever fetched here - confirmed live that reverse zones backed
  purely by a Network's deployment role (rather than a manually/explicitly created Zone) are
  generated dynamically by the DNS/DHCP server rather than stored as a persisted Zone with
  real PTR resourceRecord objects (a `dig -x` answer resolved correctly for a network whose
  computed reverse zone name had zero matches under `/zones`, and a configuration-wide PTR
  search under `/resourceRecords` returned zero results). See issue_detector.py's module
  docstring for what that means for issue detection. See the README's Limitations section
  for how this could differ on a BAM install that uses explicit/manually-created reverse
  zones instead.
- `roleType` values (PRIMARY, SECONDARY, HIDDEN_PRIMARY, MULTI_PRIMARY, HIDDEN_MULTI_PRIMARY,
  FORWARDER, ...) are the modern v2 renaming of v1's MASTER/SLAVE/etc, per BlueCat's public
  docs - ACTIVE_DNS_ROLE_TYPES in constants.py is the best-guess "actively serving" subset;
  confirm it against your own BAM's real values (see README).
"""
from flask import g

from bluecat_libraries.address_manager.apiv2.client import Client

from ..utils.constants import ACTIVE_DNS_ROLE_TYPES

PAGE_SIZE = 500


def get_v2_client():
    existing = getattr(getattr(g.user, "bam_api", None), "v2", None)
    if existing is not None:
        return existing
    client = Client(url=g.user.get_api_netloc(), verify=False)
    client.auth = "Basic " + g.user.session_auth
    return client


def _paginate(client, path: str, fields: str, filter_expr: str) -> list:
    offset = 0
    items = []
    while True:
        params = {"fields": fields, "limit": PAGE_SIZE, "offset": offset}
        if filter_expr:
            params["filter"] = filter_expr
        response = client.http_get(path, params=params)
        page = response.get("data", [])
        items.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return items


def list_configuration_names(client) -> list:
    return [c["name"] for c in _paginate(client, "/configurations", "id,name", "") if c.get("name")]


def collect_zones(client, configuration_name: str) -> list:
    """
    One dict per Zone (forward and reverse alike): {"id", "absolute_name"}.

    Zones with no usable absoluteName (e.g. the unnamed root zone, or any entity missing
    the field on live data) are skipped - there's no meaningful arpa path to place them at.
    """
    filter_expr = "configuration.name:eq('{}')".format(configuration_name)
    raw = _paginate(client, "/zones", "id,absoluteName,type", filter_expr)
    results = []
    for z in raw:
        absolute_name = z.get("absoluteName")
        zone_id = z.get("id")
        if not absolute_name or zone_id is None:
            continue
        results.append({"id": str(zone_id), "absolute_name": absolute_name})
    return results


def network_deployment_roles(client, network_id: str) -> list:
    """Raw DNS deployment `roleType` strings for a network (see module docstring)."""
    raw = _paginate(client, "/networks/{}/deploymentRoles".format(network_id), "id,type,roleType", "")
    return [r["roleType"] for r in raw if r.get("roleType")]


def collect_networks(client, configuration_name: str) -> list:
    """One dict per network: {"id", "name", "cidr", "role_types", "has_active_role"}."""
    filter_expr = "configuration.name:eq('{}')".format(configuration_name)
    raw = _paginate(client, "/networks", "id,name,range,type", filter_expr)
    results = []
    for network in raw:
        cidr = network.get("range")
        network_id = network.get("id")
        if not cidr or network_id is None:
            continue
        role_types = network_deployment_roles(client, str(network_id))
        results.append({
            "id": str(network_id),
            "name": network.get("name") or cidr,
            "cidr": cidr,
            "role_types": role_types,
            "has_active_role": has_active_dns_role(role_types),
        })
    return results


def collect_host_records(client, zone_id: str) -> list:
    """One dict per HostRecord in a (forward) zone: {"name", "addresses", "reverse_enabled"}."""
    raw = _paginate(
        client, "/zones/{}/resourceRecords".format(zone_id),
        "id,name,absoluteName,type,reverseRecord,addresses",
        "type:eq('HostRecord')",
    )
    results = []
    for record in raw:
        addresses = [a["address"] for a in record.get("addresses", []) if a.get("address")]
        results.append({
            "name": record.get("absoluteName") or record.get("name"),
            "addresses": addresses,
            "reverse_enabled": bool(record.get("reverseRecord")),
        })
    return results


def has_active_dns_role(role_types: list) -> bool:
    return any(t in ACTIVE_DNS_ROLE_TYPES for t in role_types)
