"""
Orchestrates one full BAM REST v2 read pass for a configuration: collect zones/networks/
host records, then build the tree and run issue detection off that single collected
snapshot (rather than re-walking BAM once per API call).

Deployment roles are read directly off each Network via `/networks/{id}/deploymentRoles`
(confirmed against live BAM data - see bam_v2_client.py's module docstring); a network is
NOT assumed to have a matching persisted reverse Zone object at all, since BAM does not
necessarily create one just because a role is configured - that gap is exactly what the
tree view surfaces by showing the network under its computed arpa path regardless.

No PTR resourceRecord is ever fetched from BAM (none exist - see issue_detector.py's
module docstring for why). What the tree/table views show instead is a *derived* PTR
preview per network: every forward HostRecord with `reverseRecord=true` whose address
falls inside that network, i.e. "what this network's dynamically-generated reverse zone
would answer for this address" - computed here from data already collected for issue
detection, not a second BAM round trip.

Every BAM API call made along the way is recorded by bam_v2_client.LoggingClient and
returned as `api_calls`, so the page can show the real interaction behind a page load
instead of it being an opaque black box.

Zones and their resource records are scoped to a single, caller-chosen View (see
bam_v2_client.py's module docstring for why) - Networks are not, since they're a
configuration-level construct in BAM, shared across every view.

build_snapshot() does this as one blocking call; build_snapshot_streaming() is a generator
version of the same logic that yields progress after each network's role lookup and each
forward zone's record fetch, for the page's progress bar (see namespaces/tree.py's
/snapshot_stream, a Server-Sent-Events endpoint built on this generator).
"""
from . import bam_v2_client, issue_detector, reverse_utils, zone_tree


def _attach_ptr_previews(networks: list, host_records: list) -> None:
    for network in networks:
        network["ptr_records"] = [
            {"address": address, "points_to": record["name"]}
            for record in host_records
            if record["reverse_enabled"]
            for address in record["addresses"]
            if reverse_utils.ip_in_network(address, network["cidr"])
        ]


def _assemble_result(client, reverse_zones: list, networks: list, host_records: list) -> dict:
    _attach_ptr_previews(networks, host_records)
    return {
        "tree": zone_tree.build_tree(reverse_zones, networks),
        "issues": issue_detector.detect_all(networks, host_records),
        "api_calls": client.calls,
    }


def build_snapshot(configuration_name: str, view_name: str) -> dict:
    client = bam_v2_client.get_v2_client()

    all_zones = bam_v2_client.collect_zones(client, configuration_name, view_name)
    reverse_zones = [z for z in all_zones if reverse_utils.is_reverse_zone_name(z["absolute_name"])]
    forward_zones = [z for z in all_zones if not reverse_utils.is_reverse_zone_name(z["absolute_name"])]

    networks = bam_v2_client.collect_networks(client, configuration_name)

    host_records = []
    for zone in forward_zones:
        host_records.extend(bam_v2_client.collect_host_records(client, zone["id"]))

    return _assemble_result(client, reverse_zones, networks, host_records)


def build_snapshot_streaming(configuration_name: str, view_name: str):
    """
    Same read as build_snapshot(), but a generator yielding progress dicts as it goes. One
    `/networks/{id}/deploymentRoles` lookup per network and one `/zones/{id}/resourceRecords`
    fetch per forward zone are each a separate BAM round trip - together they're the part
    that can meaningfully take a while on a configuration with many networks/zones, so
    progress is reported once per network and once per forward zone processed.

    Every yielded dict has a "phase" key. The final one has phase="done" and carries the
    full result (same shape build_snapshot() returns) under "result".
    """
    client = bam_v2_client.get_v2_client()

    yield {"phase": "zones", "done": 0, "total": 0}
    all_zones = bam_v2_client.collect_zones(client, configuration_name, view_name)
    reverse_zones = [z for z in all_zones if reverse_utils.is_reverse_zone_name(z["absolute_name"])]
    forward_zones = [z for z in all_zones if not reverse_utils.is_reverse_zone_name(z["absolute_name"])]

    raw_networks = bam_v2_client.list_networks_raw(client, configuration_name)
    total_steps = len(raw_networks) + len(forward_zones)
    done_steps = 0
    yield {"phase": "start", "done": done_steps, "total": total_steps}

    networks = []
    for network in raw_networks:
        role_types = bam_v2_client.network_deployment_roles(client, network["id"])
        networks.append({
            **network,
            "role_types": role_types,
            "has_active_role": bam_v2_client.has_active_dns_role(role_types),
        })
        done_steps += 1
        yield {"phase": "networks", "done": done_steps, "total": total_steps}

    host_records = []
    for zone in forward_zones:
        host_records.extend(bam_v2_client.collect_host_records(client, zone["id"]))
        done_steps += 1
        yield {"phase": "host_records", "done": done_steps, "total": total_steps}

    yield {
        "phase": "done",
        "done": total_steps,
        "total": total_steps,
        "result": _assemble_result(client, reverse_zones, networks, host_records),
    }
