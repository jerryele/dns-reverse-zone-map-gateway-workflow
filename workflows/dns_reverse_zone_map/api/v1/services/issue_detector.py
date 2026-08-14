"""
Detects reverse-DNS maintenance issues from already-collected BAM data (see
bam_v2_client.py) - pure functions, no BAM API calls of their own, so detection logic can
be tested against fixture data independently of a live Gateway session.

Only two categories are implemented, not three. "Orphan PTR" (a stale PTR pointing at a
forward name that no longer exists) was dropped after live testing against a BAM install
whose reverse zones are backed purely by a Network's deployment role: the DNS/DHCP server
generates those reverse zones dynamically rather than BAM storing a persisted Zone with
real PTR resourceRecord objects - confirmed by a real `dig -x` answer resolving correctly
for a network whose computed reverse zone name had zero matches under BAM's own `/zones`,
and a configuration-wide `/resourceRecords` search for PTR-type GenericRecords returning
zero results anywhere. With no persisted PTR object to ever go stale, "orphan PTR" isn't
something the BAM REST API can detect on its own in that setup (would require live DNS
resolution + comparison, out of scope per the read-only, BAM-API-only design) - so it's
not implemented rather than left as a check that could never find anything, or worse,
guessed at with invented data. See the README's Limitations section - a BAM install using
explicit/manually-created reverse zones with real static PTR records may behave
differently, and this check could be revisited there.
"""
from . import reverse_utils


def _normalize_name(name: str) -> str:
    return (name or "").strip(".").lower()


def find_missing_reverse_role(networks: list, host_records: list) -> list:
    """Networks with in-use forward addresses but no active DNS deployment role."""
    issues = []
    for network in networks:
        if network["has_active_role"]:
            continue
        in_use = [
            address
            for record in host_records
            for address in record["addresses"]
            if reverse_utils.ip_in_network(address, network["cidr"])
        ]
        if in_use:
            issues.append({
                "category": "missing_reverse_role",
                "network_id": network["id"],
                "network_name": network["name"],
                "cidr": network["cidr"],
                "role_types": network["role_types"],
                "sample_addresses": in_use[:5],
                "address_count": len(in_use),
            })
    return issues


def find_missing_or_wrong_ptr(networks: list, host_records: list) -> list:
    """
    Host records with reverseRecord=true whose address falls in a network with no active
    DNS deployment role - the PTR that record is asking for cannot actually be served.

    This is the host-level view of the same root cause as find_missing_reverse_role's
    network-level view (a network with real hosts but no role gets flagged there; here,
    each individual affected host is named) - not comparing against an actual PTR record,
    since none exists to compare against (see module docstring).
    """
    issues = []
    for record in host_records:
        if not record["reverse_enabled"]:
            continue
        for address in record["addresses"]:
            network = next(
                (n for n in networks if reverse_utils.ip_in_network(address, n["cidr"])), None
            )
            if network is None or network["has_active_role"]:
                continue
            issues.append({
                "category": "missing_or_wrong_ptr",
                "host_name": record["name"],
                "address": address,
                "network_cidr": network["cidr"],
                "reason": "reverse DNS enabled on this host, but its network has no active DNS deployment role",
            })
    return issues


def detect_all(networks: list, host_records: list) -> dict:
    return {
        "missing_reverse_role": find_missing_reverse_role(networks, host_records),
        "missing_or_wrong_ptr": find_missing_or_wrong_ptr(networks, host_records),
    }
