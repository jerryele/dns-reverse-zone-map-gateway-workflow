"""
Pure helpers for turning IPv4/IPv6 CIDRs and BAM zone absoluteNames into a shared,
root-first label path (no BAM API calls here - kept separate so the path math can be
unit tested without a live Gateway session).

A path like ["arpa", "in-addr", "10", "0", "1"] represents the zone "1.0.10.in-addr.arpa"
(root "arpa" first, most specific label last) - reversing the path and joining with "."
recovers the zone's absoluteName.
"""
import ipaddress


def cidr_to_arpa_path(cidr: str) -> list:
    """
    Compute the in-addr.arpa/ip6.arpa path a network's reverse zone would live at.

    Reverse DNS can only delegate on octet (IPv4) / nibble (IPv6) boundaries, so a
    prefix that isn't aligned to one (e.g. /27) maps to the same path as the enclosing
    /24 - multiple such networks legitimately collapse onto one tree leaf.
    """
    network = ipaddress.ip_network(cidr, strict=False)
    if network.version == 4:
        octet_count = network.prefixlen // 8
        octets = str(network.network_address).split(".")[:octet_count]
        return ["arpa", "in-addr"] + octets
    nibble_count = network.prefixlen // 4
    nibbles = network.network_address.exploded.replace(":", "")[:nibble_count]
    return ["arpa", "ip6"] + list(nibbles)


def zone_name_to_arpa_path(absolute_name: str) -> list:
    """Split a BAM zone absoluteName like '1.0.10.in-addr.arpa' into a root-first path."""
    labels = absolute_name.strip(".").split(".")
    return list(reversed(labels))


def path_to_name(path: list) -> str:
    """Inverse of zone_name_to_arpa_path/cidr_to_arpa_path - rebuild the dotted zone name."""
    return ".".join(reversed(path))


def is_reverse_arpa_path(path: list) -> bool:
    return len(path) >= 2 and path[0] == "arpa" and path[1] in ("in-addr", "ip6")


def is_reverse_zone_name(absolute_name: str) -> bool:
    name = absolute_name.strip(".").lower()
    return name.endswith("in-addr.arpa") or name.endswith("ip6.arpa")


def ip_in_network(ip_address: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip_address) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def build_address_network_index(networks: list, host_records: list) -> tuple:
    """
    One pass over host records x networks, with every CIDR/address string parsed exactly
    once (not re-parsed on every comparison), instead of three separate consumers
    (PTR preview, missing-reverse-role, missing/wrong-PTR) each independently calling
    ip_in_network() - on a configuration with many networks and host records, the repeated
    ipaddress parsing (not the O(networks x records) shape itself) was what actually made
    this step slow, and it ran with no progress reporting, right after the progress bar
    had already reached 100% from the per-network/per-zone fetch loop - looking exactly
    like the load had frozen at the very end.

    Returns (records_by_network, network_id_by_address):
    - records_by_network: {network_id: [{"address", "record"}, ...]} - every host record
      address that falls inside that network, regardless of reverse_enabled.
    - network_id_by_address: {address: network_id} - the same matches, keyed the other way,
      for going straight from one address to its network.
    """
    parsed_networks = []
    for network in networks:
        try:
            parsed_networks.append((network, ipaddress.ip_network(network["cidr"], strict=False)))
        except ValueError:
            continue

    records_by_network = {network["id"]: [] for network in networks}
    network_id_by_address = {}
    for record in host_records:
        for address in record["addresses"]:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError:
                continue
            for network, parsed_cidr in parsed_networks:
                if parsed_address in parsed_cidr:
                    records_by_network[network["id"]].append({"address": address, "record": record})
                    network_id_by_address[address] = network["id"]
                    break
    return records_by_network, network_id_by_address
