"""
Tunable constants. ACTIVE_DNS_ROLE_TYPES in particular is a best-guess pending live
verification against your own BAM - check it by opening a network known to have an active
role in a real logged-in session and confirming `GET /networks/{id}/deploymentRoles`'s
`roleType` values match what's listed here, adjusting if your BAM's real values differ.
"""

# BAM REST v2 DeploymentRole `roleType` values that mean "this network's records are
# actually served by a DNS server", as opposed to FORWARDER/RECURSION/STUB/NONE which don't
# imply the network's own records are authoritatively hosted. These are the v2 REST naming
# (PRIMARY/SECONDARY/...), confirmed distinct from v1 SOAP's MASTER/SLAVE naming via
# BlueCat's own v9.6.0 release notes (which added MULTI_PRIMARY/HIDDEN_MULTI_PRIMARY to
# this same set).
ACTIVE_DNS_ROLE_TYPES = [
    "PRIMARY",
    "HIDDEN_PRIMARY",
    "SECONDARY",
    "STEALTH_SECONDARY",
    "MULTI_PRIMARY",
    "HIDDEN_MULTI_PRIMARY",
]
