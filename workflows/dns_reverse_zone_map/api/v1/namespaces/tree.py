"""
REST endpoints the reverse-zone map page polls: the list of BAM configurations to choose
from, and a single combined tree+issues snapshot for a chosen configuration.
"""
from flask import request
from flask_restx import Namespace, Resource

from ..services import bam_v2_client, reverse_zone_service

tree_ns = Namespace("tree", description="Reverse DNS zone tree + issue list")


@tree_ns.route("/configurations")
class Configurations(Resource):
    def get(self):
        try:
            client = bam_v2_client.get_v2_client()
            return {"configurations": bam_v2_client.list_configuration_names(client)}, 200
        except Exception as e:
            return {"error": str(e)}, 500


@tree_ns.route("/snapshot")
class Snapshot(Resource):
    """?configuration=<name> - one BAM read pass, returns both the tree and the issue list."""

    def get(self):
        configuration_name = request.args.get("configuration")
        if not configuration_name:
            return {"error": "configuration query param is required"}, 400
        try:
            snapshot = reverse_zone_service.build_snapshot(configuration_name)
        except Exception as e:
            return {"error": str(e)}, 500
        return snapshot, 200


@tree_ns.route("/debug")
class Debug(Resource):
    """
    Temporary diagnostic endpoint - returns raw, unprocessed BAM v2 API responses so real
    field names/values can be confirmed against live data instead of guessed. Remove once
    the /networks and deploymentRoles field mapping is fully verified.

    ?configuration=<name> (required) - raw samples of /networks and /zones under it.
    &cidr=<x.x.x.x/n> (optional) - also finds that exact network by its `range` and fetches
        its raw /networks/{id}/deploymentRoles, to confirm the real roleType string.
    &zone=<absoluteName> (optional) - also finds that exact zone and fetches a raw,
        unfiltered sample of its /resourceRecords, to confirm real HostRecord/PTR field
        names/values (e.g. `addresses`/`reverseRecord` on hosts, `recordType`/`rdata` on PTR).
    &host=<name> (optional) - looks up that HostRecord by name across the whole configuration
        (top-level /resourceRecords, not zone-scoped) to inspect its raw reverseRecord/
        addresses fields directly, without needing to know which zone it's in.

    Also always checks whether ANY PTR-type GenericRecord exists anywhere in the
    configuration (top-level /resourceRecords) - reverse zones that are auto-generated at
    deploy time from a Network's role (rather than manually created as a persisted Zone
    object) may never materialize a queryable PTR record at all, which would mean PTR
    presence has to be inferred from the forward HostRecord's `reverseRecord` flag instead
    of looked up directly.
    """

    def get(self):
        configuration_name = request.args.get("configuration")
        cidr = request.args.get("cidr")
        zone_name = request.args.get("zone")
        host_name = request.args.get("host")
        if not configuration_name:
            return {"error": "configuration query param is required"}, 400
        try:
            client = bam_v2_client.get_v2_client()
            filter_expr = "configuration.name:eq('{}')".format(configuration_name)
            result = {
                "networks_sample": client.http_get("/networks", params={"filter": filter_expr, "limit": 3}),
                "zones_sample": client.http_get("/zones", params={"filter": filter_expr, "limit": 3}),
                "ptr_records_anywhere_in_configuration": client.http_get(
                    "/resourceRecords",
                    params={
                        "filter": "{} and type:eq('GenericRecord') and recordType:eq('PTR')".format(filter_expr),
                        "limit": 5,
                    },
                ),
            }
            if host_name:
                host_filter = "{} and type:eq('HostRecord') and name:eq('{}')".format(filter_expr, host_name)
                result["host_record_lookup"] = client.http_get("/resourceRecords", params={"filter": host_filter})
            if cidr:
                network_filter = "range:eq('{}') and configuration.name:eq('{}')".format(
                    cidr, configuration_name
                )
                network_lookup = client.http_get("/networks", params={"filter": network_filter})
                result["network_lookup"] = network_lookup
                networks_found = network_lookup.get("data", [])
                if networks_found:
                    network_id = networks_found[0].get("id")
                    result["deployment_roles_for_that_network"] = client.http_get(
                        "/networks/{}/deploymentRoles".format(network_id)
                    )
            if zone_name:
                zone_filter = "absoluteName:eq('{}') and configuration.name:eq('{}')".format(
                    zone_name, configuration_name
                )
                zone_lookup = client.http_get("/zones", params={"filter": zone_filter})
                result["zone_lookup"] = zone_lookup
                zones_found = zone_lookup.get("data", [])
                if zones_found:
                    zone_id = zones_found[0].get("id")
                    result["resource_records_sample_for_that_zone"] = client.http_get(
                        "/zones/{}/resourceRecords".format(zone_id), params={"limit": 10}
                    )
            return result, 200
        except Exception as e:
            return {"error": str(e)}, 500
