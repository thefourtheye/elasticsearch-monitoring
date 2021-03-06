import re

from indices import is_white_listed
from tabularize_json import tabularize

try:
    import simplejson as json
except ImportError:
    import json


def sort_by_index(item):
    return item["index"], int(item["shard"]), item["prirep"], item["node"]


def sort_by_size(item):
    return -int(item["store"] or '0'), item["index"], int(item["shard"]), item["prirep"], item["node"]


def table(title, l, sorter=None):
    temp = """
        <table width='100%' border=1 cellpadding=3 cellspacing=0>
        <caption>{0} Shards</caption>
        <tr><th>Index</th><th>Shard</th><th>prirep</th><th>Reason</th><th>Docs</th><th>Size (GB)</th><th>IP</th><th>Node</th></tr>
    """.format(title)
    for item in sorted(l, key=sorter):
        temp += "<tr><td>" + "</td><td>".join([
            item["index"],
            item["shard"],
            item["prirep"],
            item["unassigned.reason"] or "N/A",
            item["docs"] or '0',
            item["store"] or '0',
            item["ip"] or "",
            item["node"] or ""
        ]) + "</td></tr>"
    return temp + "</table><br/>"


def shards(connection, config, health):
    r1 = connection("/_cat/shards?bytes=g&h=index,shard,prirep,state,unassigned.reason,docs,store,ip,node")
    response = r1.read()
    result = {
        "severity": "INFO",
        "title": "Shards",
        "body": ""
    }
    if r1.status != 200:
        result = {
            "severity": "FATAL" if health != "INFO" else health,
            "title": "Shards Check Failed with HTTP Code [{0}]".format(r1.status),
            "body": tabularize(response)
        }
    else:
        shards_data = json.loads(response)
        oversize_limit = config.get("shard_size_limit", 50)  # Giga Bytes

        cfg_whitelisted_indices = config.get("whitelisted_indices", [])
        whitelisted_indices = set(map(lambda x: re.compile(x), cfg_whitelisted_indices))
        is_index_whitelisted = is_white_listed(whitelisted_indices)

        started = [shard for shard in shards_data if shard["state"] == "STARTED"]
        init = [shard for shard in shards_data if shard["state"] == "INITIALIZING"]
        relocating = [shard for shard in shards_data if shard["state"] == "RELOCATING"]
        unassigned = [shard for shard in shards_data if shard["state"] == "UNASSIGNED"]
        oversized = [shard for shard in shards_data if int(shard["store"]) > oversize_limit]

        if init and not all(is_index_whitelisted(i["index"]) for i in init):
            result["severity"] = "WARNING" if health != "FATAL" else "FATAL"
        elif any(s["prirep"] == "p" and not is_index_whitelisted(s["index"]) for s in relocating):
            result["severity"] = "WARNING" if health != "FATAL" else "FATAL"
        elif unassigned and not all(is_index_whitelisted(i["index"]) for i in unassigned):
            result["severity"] = "WARNING" if health != "FATAL" else "FATAL"
        elif oversized:
            result["severity"] = "WARNING"

        result["body"] += """<table width='100%' border=1 cellpadding=3 cellspacing=0>
            <tr><td>Total</td><td>{0}</td></tr>
            <tr><td>Started</td><td>{1}</td></tr>
            <tr><td>Initializing</td><td>{2}</td></tr>
            <tr><td>Relocating</td><td>{3}</td></tr>
            <tr><td>Unassigned</td><td>{4}</td></tr>
            <tr><td>Oversized</td><td>{4}</td></tr>
        </table><br />""".format(
            len(shards_data),
            len(started),
            len(init),
            len(relocating),
            len(oversized)
        )

        if unassigned:
            result["body"] += table("Unassigned", unassigned, sort_by_index)
        if init:
            result["body"] += table("Initializing", init, sort_by_index)
        if relocating:
            result["body"] += table("Relocating", relocating, sort_by_index)
        if oversized:
            result["body"] += table("Oversized", oversized, sort_by_size)

    return result
