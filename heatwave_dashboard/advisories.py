"""Rule-based, explainable guidance derived from Person 1 forecast and alert data."""

from __future__ import annotations

from typing import Any, Iterable


def _guidance(severity: int) -> dict[str, Any]:
    if severity >= 5:
        return {
            "category": "severe_heat",
            "title": "Severe heat conditions",
            "message": "The system indicates severe heatwave conditions for this location.",
            "actions": [
                "Follow current local authority and IMD heat alerts.",
                "Reduce strenuous outdoor activity during the hottest hours.",
                "Check on older adults, children, and people who may need assistance.",
                "Agricultural teams should review worker schedules and livestock water access.",
            ],
        }
    if severity == 4:
        return {
            "category": "heatwave",
            "title": "Heatwave conditions",
            "message": "The forecast indicates heatwave-level temperatures for this location.",
            "actions": [
                "Plan outdoor work for cooler hours and provide shaded rest breaks.",
                "Keep drinking water available and check on people at higher risk.",
                "Review local heat-action plans and crop or livestock protection measures.",
            ],
        }
    if severity == 3:
        return {
            "category": "high_heat",
            "title": "High temperatures expected",
            "message": "Very hot conditions are forecast; consider low-cost precautions.",
            "actions": [
                "Limit prolonged strenuous work in direct sun where practical.",
                "Use shade and regular rest breaks, especially during peak afternoon heat.",
                "Monitor official forecasts for changes.",
            ],
        }
    return {
        "category": "heat_watch",
        "title": "Heat watch",
        "message": "Warm conditions are forecast; keep routine heat precautions in place.",
        "actions": [
            "Keep track of local temperature updates.",
            "Consider cooler-hour scheduling for outdoor work.",
        ],
    }


def generate_advisories(
    forecasts: Iterable[dict[str, Any]],
    alerts: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create one transparent advisory per forecast location, ranked by severity."""
    alert_by_location: dict[int, dict[str, Any]] = {}
    for alert in alerts:
        location_id = alert["location_id"]
        current = alert_by_location.get(location_id)
        if current is None or alert["severity"] > current["severity"]:
            alert_by_location[location_id] = alert

    advisories = []
    for item in forecasts:
        forecast = item["forecast"]
        alert = alert_by_location.get(item["location_id"])
        if forecast is None:
            advisory = {
                "category": "data_gap",
                "title": "More observations needed",
                "message": "There is not enough recent data to produce a forecast; this is not a low-risk assessment.",
                "actions": ["Check station reporting and consult official local weather updates."],
                "severity": None,
                "basis": "insufficient_data",
            }
        else:
            severity = forecast["severity"]
            if alert is not None:
                severity = max(severity, alert["severity"])
            advisory = _guidance(severity)
            advisory["severity"] = severity
            advisory["basis"] = "active_alert_and_forecast" if alert else "forecast"

        advisory.update({
            "location_id": item["location_id"],
            "name": item["name"],
            "region": item["region"],
            "target_date": item["target_date"],
        })
        advisories.append(advisory)

    advisories.sort(
        key=lambda item: (
            item["severity"] is None,
            -(item["severity"] or 0),
            item["name"],
        )
    )
    return advisories
