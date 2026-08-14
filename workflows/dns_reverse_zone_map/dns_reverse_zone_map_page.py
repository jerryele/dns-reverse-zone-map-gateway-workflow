import os

from flask import send_from_directory
from main_app import app

from bluecat import route
from bluecat.gateway.decorators import page_exc_handler, require_permission


@route(app, "/dns_reverse_zone_map/page")
@page_exc_handler(default_message="Failed to load DNS Reverse Zone Map workflow.")
@require_permission("dns_reverse_zone_map_page")
def dns_reverse_zone_map_page():
    return send_from_directory(os.path.dirname(os.path.abspath(str(__file__))), "dnsReverseZoneMapPage/index.html")
