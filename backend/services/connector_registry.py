from __future__ import annotations

from platforms import AspireConnector, CollabstrConnector, ModashConnector, ReachrConnector, UpfluenceConnector


def get_connectors(enabled_platforms: str):
    registry = {
        "reachr": ReachrConnector,
        "modash": ModashConnector,
        "upfluence": UpfluenceConnector,
        "collabstr": CollabstrConnector,
        "aspire": AspireConnector,
    }
    names = [n.strip().lower() for n in enabled_platforms.split(",") if n.strip()]
    connectors = []
    for name in names:
        connector_cls = registry.get(name)
        if connector_cls:
            connectors.append(connector_cls())
    return connectors
