"""
Pure tree-building logic for the reverse-zone map - merges already-collected BAM data by
root-first label path (see reverse_utils.py) into a nested dict the frontend renders as an
expandable tree. No BAM API calls here, so this is unit-testable against fixture data alone.
"""
from . import reverse_utils


def _get_or_create_child(node: dict, label: str) -> dict:
    for child in node["children"]:
        if child["label"] == label:
            return child
    child = {"label": label, "children": [], "zone_ids": [], "networks": []}
    node["children"].append(child)
    return child


def build_tree(reverse_zones: list, networks: list) -> dict:
    """
    reverse_zones: dicts from bam_v2_client.collect_zones() (already filtered to
        in-addr.arpa/ip6.arpa names) - i.e. an explicit Zone object BAM already has.
    networks: dicts from bam_v2_client.collect_networks(), each already annotated by
        reverse_zone_service with "role_types"/"has_active_role" from whichever reverse
        zone matches that network's computed arpa path.

    Each node carries `zone_ids` (BAM Zone ids that exist at exactly this path - usually 0
    or 1) and `networks` (network summaries whose computed arpa path lands exactly here -
    the "virtual" reverse-zone nodes that only exist via a Network's role assignment, with
    no persisted Zone object behind them, which is the gap this workflow exists to surface).
    """
    root = {"label": "arpa", "children": [], "zone_ids": [], "networks": []}

    for zone in reverse_zones:
        path = reverse_utils.zone_name_to_arpa_path(zone["absolute_name"])
        node = root
        for label in path[1:]:
            node = _get_or_create_child(node, label)
        node["zone_ids"].append(zone["id"])

    for network in networks:
        path = reverse_utils.cidr_to_arpa_path(network["cidr"])
        node = root
        for label in path[1:]:
            node = _get_or_create_child(node, label)
        node["networks"].append(network)

    return root
