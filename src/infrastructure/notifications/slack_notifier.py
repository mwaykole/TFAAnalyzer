"""Slack notification implementation.

Implements the Notifier interface for sending notifications to Slack.
"""

import aiohttp

from src.domain.interfaces.notifier import Notifier, AnalysisSummary
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SlackNotifier(Notifier):
    """Send notifications to Slack via webhooks.
    
    Implements Notifier interface for Slack incoming webhooks.
    """

    def __init__(self, webhook_url: str):
        """Initialize Slack notifier.
        
        Args:
            webhook_url: Slack incoming webhook URL
        """
        self.webhook_url = webhook_url

    @property
    def channel_name(self) -> str:
        """Get notification channel name."""
        return "slack"

    async def send_summary(self, summary: AnalysisSummary) -> bool:
        """Send analysis summary to Slack.
        
        Args:
            summary: AnalysisSummary with results data
            
        Returns:
            True if notification sent successfully
        """
        # Determine emoji and color based on status
        if summary.overall_status == "critical":
            header_emoji = "🚨"
            color = "#dc2626"  # Red
        elif summary.overall_status == "warning":
            header_emoji = "⚠️"
            color = "#f59e0b"  # Amber
        else:
            header_emoji = "✅"
            color = "#10b981"  # Green

        # Build launch link
        launch_link = ""
        if summary.rp_url and summary.launch_id:
            launch_link = f"\n<{summary.rp_url}/ui/#default/launches/all/{summary.launch_id}|View in ReportPortal>"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{header_emoji} TFA Analysis: {summary.launch_name[:50]}",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Component:*\n{summary.component}"},
                    {"type": "mrkdwn", "text": f"*Total Failures:*\n{summary.total_failures}"},
                    {"type": "mrkdwn", "text": f"*🐛 Product Bugs:*\n{summary.product_bugs}"},
                    {"type": "mrkdwn", "text": f"*🔧 Auto Issues:*\n{summary.automation_issues}"},
                    {"type": "mrkdwn", "text": f"*🏗️ Infra Issues:*\n{summary.infrastructure_issues}"},
                    {"type": "mrkdwn", "text": f"*⚡ Flaky Tests:*\n{summary.flaky_tests}"},
                ]
            },
        ]

        # Add critical bugs section
        if summary.critical_bugs:
            bug_list = "\n".join(
                f"• `{b.get('test_name', 'Unknown')[:40]}` - {b.get('severity', 'N/A')}"
                for b in summary.critical_bugs[:5]
            )
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*⚠️ Critical/High Severity Bugs:*\n{bug_list}"
                }
            })

        # Add link
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
                        logger.info("slack_notification_sent", 
                                    launch=summary.launch_name,
                                    component=summary.component)
                        return True
                    else:
                        text = await resp.text()
                        logger.error("slack_notification_failed", 
                                     status=resp.status, error=text)
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
                    if resp.status == 200:
                        logger.info("slack_message_sent")
                        return True
                    return False
        except Exception as e:
            logger.error("slack_message_error", error=str(e))
            return False
