"""Shared UI constants and utilities for console output."""

CLASSIFICATION_ICONS = {
    "Product Bug": "🐛",
    "Test Automation Issue": "🔧",
    "Flaky Test": "⚡",
    "Intermittent Failure": "🔄",
    "Infrastructure Issue": "🌐",
    "Data Issue": "📊",
    "No Defect": "✅",
    "To Investigate": "🔍",
}

CLASSIFICATION_COLORS = {
    "Product Bug": "red",
    "Test Automation Issue": "yellow",
    "Flaky Test": "orange3",
    "Intermittent Failure": "orange3",
    "Infrastructure Issue": "blue",
    "Data Issue": "magenta",
    "No Defect": "green",
    "To Investigate": "white",
}

SEVERITY_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}


def get_icon(classification: str) -> str:
    return CLASSIFICATION_ICONS.get(classification, "❓")


def get_color(classification: str) -> str:
    return CLASSIFICATION_COLORS.get(classification, "white")


def get_severity_icon(severity: str) -> str:
    return SEVERITY_ICONS.get(severity, "⚪")
