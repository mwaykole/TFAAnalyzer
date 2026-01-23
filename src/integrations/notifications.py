"""Notification integrations for Slack and Microsoft Teams."""

from typing import Any

import aiohttp

from src.utils.logging import get_logger

logger = get_logger(__name__)


class SlackNotifier:
    """Send notifications to Slack via webhooks.
    
    Sends analysis summaries to a Slack channel using incoming webhooks.
    """

    def __init__(self, webhook_url: str):
        """Initialize Slack notifier.
        
        Args:
            webhook_url: Slack incoming webhook URL
        """
        self.webhook_url = webhook_url

    async def send_summary(
        self,
        launch_name: str,
        component: str,
        analyses: list[dict[str, Any]],
        launch_id: str = "",
        rp_url: str = "",
    ) -> bool:
        """Send analysis summary to Slack.
        
        Args:
            launch_name: Name of the analyzed launch
            component: Component name
            analyses: List of analysis results
            launch_id: ReportPortal launch ID for linking
            rp_url: ReportPortal base URL for linking
            
        Returns:
            True if notification sent successfully
        """
        product_bugs = sum(1 for a in analyses if a.get("classification") == "Product Bug")
        auto_issues = sum(1 for a in analyses if a.get("classification") == "Test Automation Issue")
        flaky_tests = sum(1 for a in analyses if a.get("classification") == "Flaky Test")
        total = len(analyses)

        # Build launch link if URL provided
        launch_link = ""
        if rp_url and launch_id:
            launch_link = f"\n<{rp_url}/ui/#default/launches/all/{launch_id}|View in ReportPortal>"

        # Determine emoji and urgency
        if product_bugs > 0:
            header_emoji = "🚨"
            color = "#dc2626"  # Red
        elif auto_issues > 0:
            header_emoji = "⚠️"
            color = "#f59e0b"  # Amber
        else:
            header_emoji = "✅"
            color = "#10b981"  # Green

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{header_emoji} TFA Analysis: {launch_name[:50]}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Component:*\n{component}"},
                    {"type": "mrkdwn", "text": f"*Total Failures:*\n{total}"},
                    {"type": "mrkdwn", "text": f"*🐛 Product Bugs:*\n{product_bugs}"},
                    {"type": "mrkdwn", "text": f"*🔧 Auto Issues:*\n{auto_issues}"},
                    {"type": "mrkdwn", "text": f"*⚡ Flaky Tests:*\n{flaky_tests}"},
                ]
            },
        ]

        # Add action required section if product bugs found
        if product_bugs > 0:
            critical_bugs = [
                a for a in analyses 
                if a.get("classification") == "Product Bug" 
                and a.get("severity") in ("CRITICAL", "HIGH")
            ]
            if critical_bugs:
                bug_list = "\n".join(
                    f"• `{b.get('test_name', 'Unknown')[:40]}` - {b.get('severity', 'N/A')}"
                    for b in critical_bugs[:5]
                )
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*⚠️ Critical/High Severity Bugs:*\n{bug_list}"
                    }
                })

        # Add link if available
        if launch_link:
            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": launch_link}
                ]
            })

        payload = {
            "blocks": blocks,
            "attachments": [{"color": color, "blocks": []}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("slack_notification_sent", launch=launch_name)
                        return True
                    else:
                        text = await resp.text()
                        logger.error("slack_notification_failed", status=resp.status, error=text)
                        return False
        except Exception as e:
            logger.error("slack_notification_error", error=str(e))
            return False

    async def send_message(self, text: str) -> bool:
        """Send a simple text message to Slack.
        
        Args:
            text: Message text (supports markdown)
            
        Returns:
            True if sent successfully
        """
        payload = {"text": text}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error("slack_message_error", error=str(e))
            return False


class TeamsNotifier:
    """Send notifications to Microsoft Teams via webhooks."""

    def __init__(self, webhook_url: str):
        """Initialize Teams notifier.
        
        Args:
            webhook_url: Teams incoming webhook URL
        """
        self.webhook_url = webhook_url

    async def send_summary(
        self,
        launch_name: str,
        component: str,
        analyses: list[dict[str, Any]],
        launch_id: str = "",
        rp_url: str = "",
    ) -> bool:
        """Send analysis summary to Teams.
        
        Args:
            launch_name: Name of the analyzed launch
            component: Component name
            analyses: List of analysis results
            launch_id: ReportPortal launch ID for linking
            rp_url: ReportPortal base URL for linking
            
        Returns:
            True if notification sent successfully
        """
        product_bugs = sum(1 for a in analyses if a.get("classification") == "Product Bug")
        auto_issues = sum(1 for a in analyses if a.get("classification") == "Test Automation Issue")
        flaky_tests = sum(1 for a in analyses if a.get("classification") == "Flaky Test")
        total = len(analyses)

        # Determine theme color
        if product_bugs > 0:
            theme_color = "dc2626"
        elif auto_issues > 0:
            theme_color = "f59e0b"
        else:
            theme_color = "10b981"

        # Build adaptive card
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": f"TFA Analysis: {launch_name}",
            "sections": [
                {
                    "activityTitle": f"🤖 Test Failure Analysis",
                    "activitySubtitle": f"Launch: {launch_name}",
                    "facts": [
                        {"name": "Component", "value": component},
                        {"name": "Total Failures", "value": str(total)},
                        {"name": "🐛 Product Bugs", "value": str(product_bugs)},
                        {"name": "🔧 Auto Issues", "value": str(auto_issues)},
                        {"name": "⚡ Flaky Tests", "value": str(flaky_tests)},
                    ],
                    "markdown": True,
                }
            ],
        }

        # Add link to ReportPortal if available
        if rp_url and launch_id:
            card["potentialAction"] = [
                {
                    "@type": "OpenUri",
                    "name": "View in ReportPortal",
                    "targets": [
                        {"os": "default", "uri": f"{rp_url}/ui/#default/launches/all/{launch_id}"}
                    ]
                }
            ]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=card,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("teams_notification_sent", launch=launch_name)
                        return True
                    else:
                        text = await resp.text()
                        logger.error("teams_notification_failed", status=resp.status, error=text)
                        return False
        except Exception as e:
            logger.error("teams_notification_error", error=str(e))
            return False


