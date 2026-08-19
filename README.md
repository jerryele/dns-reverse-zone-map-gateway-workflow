# DNS Reverse Zone Map — BlueCat Gateway Workflow

A [BlueCat Gateway](https://www.bluecatnetworks.com/) custom workflow that reconstructs BAM's
implicit `in-addr.arpa`/`ip6.arpa` hierarchy as a browsable tree (or flat table), and flags a
couple of common reverse-DNS maintenance problems — all read-only, all via BAM's REST v2 API.

## Why this exists

In Address Manager, reverse DNS is often configured by assigning a DNS Deployment Role directly
to an IPv4/IPv6 **Network** object, not by creating a standalone reverse zone the way you would
in a traditional DNS management tool. That makes reverse DNS coverage hard to audit at a glance —
to know whether a given network actually has working reverse DNS, you have to open that network's
properties individually. This workflow reads BAM's configuration and rebuilds the `in-addr.arpa`/
`ip6.arpa` tree you'd expect to see, merging in any explicit reverse Zone objects BAM does have
alongside the "virtual" nodes that only exist via a Network's role assignment.

## What it shows

- **Configuration + DNS View selectors** (top of the page) — both are required before anything
  loads. BAM scopes Zones (and therefore resource records) to a single View each — this is its
  split-horizon mechanism, so the same zone name can exist independently in more than one View —
  so every query here is scoped to whichever View you pick, not just the Configuration. Networks
  are a Configuration-level construct in BAM and aren't View-scoped, so they're unaffected by
  which View is selected.
- **Tree / table display toggle** (top of the main panel — not to be confused with the DNS View
  picker above) — the same data, two shapes. The tree mirrors a traditional DNS zone browser;
  the table flattens every network/zone onto one row each, for scanning or sorting at a glance.
- **Per-network PTR preview** — expandable "▸ N PTR" under each network, in both views. BAM
  does not necessarily store a real PTR resource record for a network whose reverse zone is
  generated dynamically from its deployment role (see "Derived, not authoritative" below) — so
  this list is *derived*: every forward Host Record with reverse DNS enabled whose address falls
  in that network, shown as `address → hostname`.
- **Maintenance issues** — two read-only checks:
  - **Missing reverse role** — a network with real forward addresses in use, but no active DNS
    deployment role, so nothing in it can ever get a working PTR.
  - **Missing / wrong PTR** — the same underlying problem from the host's point of view: an
    individual Host Record has reverse DNS enabled, but its network has no active role.
- **API Calls panel** (bottom of the page, collapsed by default) — every BAM REST v2 call made
  to build the current view, in order, with its path/params, result count, and duration. The
  interaction with BAM isn't a black box; you can see exactly what was fetched (and, for larger
  configurations, exactly why a refresh took as long as it did — one deployment-role lookup per
  network adds up).
- **A persistent progress bar** (top of the page) — loading a configuration means one
  `/networks/{id}/deploymentRoles` call per network plus one `/zones/{id}/resourceRecords` call
  per forward zone, which can add up on a large configuration. The page streams progress over
  Server-Sent Events as each of those finishes, so the bar tracks real done/total counts and
  elapsed time instead of just spinning - and it stays on screen (idle grey → loading blue →
  done green / error red, each labeled with how long it took) rather than disappearing, so a
  fast load doesn't just look like nothing happened.

No write/fix actions are implemented in this version — see "Limitations."

## Derived, not authoritative

This workflow never fetches a PTR-type resource record from BAM. On the install this was built
and tested against, reverse zones backed purely by a Network's deployment role are generated
dynamically by the DNS/DHCP server at deploy/query time — BAM itself never persists a Zone object
or PTR resourceRecord for them. Confirmed directly: `dig -x` against a real address resolved
correctly, while that same address's computed reverse zone name had zero matches under BAM's own
`/zones`, and a configuration-wide search for PTR-type records returned nothing at all. So the
PTR list this workflow shows is *reconstructed* from forward Host Records' `reverseRecord` flag,
not read back from a stored PTR object — it reflects what BAM's own configuration says should be
served, not a live DNS answer.

If your BAM install instead uses explicit, manually-created reverse zones with real static PTR
records, some of this may not apply to you — see "Limitations."

## Installing

1. Copy `workflows/dns_reverse_zone_map/` into your Gateway's `workflows/` directory (`docker cp`
   into the container, a filesystem copy, whatever your install uses) and restart Gateway.
2. Add a page-permission entry to your **custom workspace's** `permissions.json` (a platform
   requirement for any new Gateway workflow, not specific to this one — without it the page
   exists but never appears in the nav):
   ```json
   "dns_reverse_zone_map": {
     "dns_reverse_zone_map_page": ["all", "admin"]
   }
   ```
3. Open **DNS Reverse Zone Map** in Gateway's nav, pick a Configuration and then a DNS View, and
   the tree/table loads automatically.

No credentials to configure — it reuses the Gateway session's own BAM authentication
(`g.user.bam_api.v2`, falling back to a hand-built v2 client using the session's auth) the same
way BlueCat's own builtin workflows do.

## Verifying against your own BAM

Two things in this workflow are best-guesses that should be confirmed against your install
rather than trusted blindly:

- `ACTIVE_DNS_ROLE_TYPES` in `api/v1/utils/constants.py` — the `roleType` values (`PRIMARY`,
  `SECONDARY`, `HIDDEN_PRIMARY`, ...) that count as "this network's records are actually being
  served." These are BAM v2's documented naming, but confirm them against a network you know has
  a working role.
- The `/networks` endpoint's shape (`range` field for CIDR, `configuration.name` filter) — used
  here, but not exercised by any other BlueCat builtin workflow available for reference at build
  time, so it was taken from BlueCat's own published API usage rather than code proven on the
  target install.

A built-in diagnostic endpoint helps with both, and with debugging in general — it returns raw,
unprocessed BAM API responses instead of this workflow's own interpretation of them:

```
GET /dns_reverse_zone_map/v1/tree/debug?configuration=<name>
  &cidr=<x.x.x.x/n>       (optional - looks up that exact network + its deploymentRoles)
  &zone=<absoluteName>    (optional - looks up that exact zone + a sample of its resourceRecords)
  &host=<name>            (optional - looks up a HostRecord by name anywhere in the configuration)
```

## API

| Method | Path | What |
|---|---|---|
| `GET` | `/dns_reverse_zone_map/v1/tree/configurations` | List of BAM configurations to choose from |
| `GET` | `/dns_reverse_zone_map/v1/tree/views?configuration=<name>` | DNS Views under that configuration to choose from |
| `GET` | `/dns_reverse_zone_map/v1/tree/snapshot?configuration=<name>&view=<name>` | One blocking read: the tree + the issue list, scoped to that View |
| `GET` | `/dns_reverse_zone_map/v1/tree/snapshot_stream?configuration=<name>&view=<name>` | Same data as `/snapshot`, streamed as Server-Sent Events with progress after each network/zone - what the page itself uses |
| `GET` | `/dns_reverse_zone_map/v1/tree/debug?configuration=<name>&...` | Raw BAM API responses, for verifying field mappings against your own install |

## Limitations

- **Read-only.** No fix/write actions — every finding is meant to be acted on by hand in BAM.
- **Built and tested against Network-role-based reverse DNS.** If your BAM uses explicit,
  manually-created reverse zones with real persisted PTR records instead, the derived-PTR-preview
  and "missing/wrong PTR" logic may need rework to compare against those real records rather than
  reconstructing from forward Host Records — an "orphan PTR" check (a stale PTR with no matching
  forward record) was deliberately left unimplemented for this reason; see
  `api/v1/services/issue_detector.py`'s module docstring.
- **No live DNS resolution.** Everything comes from BAM's own configuration via REST v2 — this
  can tell you what BAM *thinks* should be served, not confirm what a resolver actually answers.
- **IPv6 reverse zones (`ip6.arpa`) are implemented from the same CIDR/nibble math as IPv4** but
  weren't validated against a real IPv6 deployment during development — sanity-check your own
  `ip6.arpa` tree before relying on it.
- **Large configurations**: every network's deployment roles are fetched with a separate API
  call, and PTR previews are derived from every forward Host Record in the configuration — this
  is fine for typical lab/mid-size environments, but wasn't load-tested against a very large BAM.
  The address-to-network matching behind PTR previews and issue detection is a single indexed
  pass (each network/address parsed once), not the three separate re-parsing passes earlier
  versions did, but it's still a linear scan per address, not a proper interval index — a
  configuration with a very large number of networks *and* a very large number of host records
  could still be slow on that step specifically.

## License

MIT — see [LICENSE](LICENSE).
