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


def build_snapshot(configuration_name: str) -> dict:
    client = bam_v2_client.get_v2_client()

    all_zones = bam_v2_client.collect_zones(client, configuration_name)
    reverse_zones = [z for z in all_zones if reverse_utils.is_reverse_zone_name(z["absolute_name"])]
    forward_zones = [z for z in all_zones if not reverse_utils.is_reverse_zone_name(z["absolute_name"])]

    networks = bam_v2_client.collect_networks(client, configuration_name)

    host_records = []
    for zone in forward_zones:
        host_records.extend(bam_v2_client.collect_host_records(client, zone["id"]))

    _attach_ptr_previews(networks, host_records)

    return {
        "tree": zone_tree.build_tree(reverse_zones, networks),
        "issues": issue_detector.detect_all(networks, host_records),
        "api_calls": client.calls,
    }
