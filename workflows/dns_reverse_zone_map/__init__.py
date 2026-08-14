"""
DNS Reverse Zone Map workflow initialization.

Single workflow package providing both the navigable UI page (via `sub_pages`, type="ui")
and the flask_restx REST API that reconstructs BAM's implicit in-addr.arpa/ip6.arpa
hierarchy (built from Network DNS Deployment Roles + any explicit reverse Zone objects)
as a browsable tree, plus a read-only list of reverse-DNS maintenance issues.
"""
from typing import Final

from flask import Blueprint
from flask_restx import Api
from main_app import app

type: str = "ui"  # noqa: A001
sub_pages: list[dict[str, str]] = [
    {
        "name": "dns_reverse_zone_map_page",
        "title": "DNS Reverse Zone Map",
        "endpoint": "dns_reverse_zone_map/page",
        "description": "Reverse DNS (in-addr.arpa/ip6.arpa) tree view and maintenance issue list",
    },
]

API_VERSION: Final[str] = "1.0"
API_PREFIX: Final[str] = "/dns_reverse_zone_map/v1"

api_endpoints: Blueprint = Blueprint(
    "dns_reverse_zone_map_api",
    "dns_reverse_zone_map_api",
)

dns_reverse_zone_map_api: Api = Api(
    api_endpoints,
    version=API_VERSION,
    title="DNS Reverse Zone Map API",
    description="REST API for the reverse DNS zone tree view and issue list",
    doc="/doc",
    default_label="DNS Reverse Zone Map",
    validate=True,
)

app.register_blueprint(api_endpoints, url_prefix=API_PREFIX)

from .api import v1

for namespace in v1.namespaces:
    dns_reverse_zone_map_api.add_namespace(namespace)
