"""Microsoft Teams notification implementation.

Implements the Notifier interface for sending notifications to Teams.
"""

import aiohttp

from src.domain.interfaces.notifier import Notifier, AnalysisSummary
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TeamsNotifier(Notifier):
    """Send notifications to Microsoft Teams via webhooks.
    
    Implements Notifier interface for Teams incoming webhooks.
    """

    def __init__(self, webhook_url: str):
        """Initialize Teams notifier.
        
        Args:
            webhook_url: Teams incoming webhook URL
        """
        self.webhook_url = webhook_url

    @property
    def channel_name(self) -> str:
        """Get notification channel name."""
        return "teams"

    async def send_summary(self, summary: AnalysisSummary) -> bool:
        """Send analysis summary to Teams.
        
        Args:
            summary: AnalysisSummary with results data
            
        Returns:
            True if notification sent successfully
        """
        # Determine theme color
        if summary.overall_status == "critical":
            theme_color = "dc2626"
        elif summary.overall_status == "warning":
            theme_color = "f59e0b"
        else:
            theme_color = "10b981"

        # Build MessageCard
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": theme_color,
            "summary": f"TFA Analysis: {summary.launch_name}",
            "sections": [
                {
                    "activityTitle": "🤖 Test Failure Analysis",
                    "activitySubtitle": f"Launch: {summary.launch_name}",
                    "facts": [
                        {"name": "Component", "value": summary.component},
                        {"name": "Total Failures", "value": str(summary.total_failures)},
                        {"name": "🐛 Product Bugs", "value": str(summary.product_bugs)},
                        {"name": "🔧 Automation Issues", "value": str(summary.automation_issues)},
                        {"name": "🏗️ Infrastructure Issues", "value": str(summary.infrastructure_issues)},
                        {"name": "⚡ Flaky Tests", "value": str(summary.flaky_tests)},
                    ],
                    "markdown": True,
                }
            ],
        }

        # Add critical bugs section
        if summary.critical_bugs:
            bug_facts = [
                {"name": f"• {b.get('test_name', 'Unknown')[:30]}", 
                 "value": b.get('severity', 'N/A')}
                for b in summary.critical_bugs[:3]
            ]
            card["sections"].append({
                "activityTitle": "⚠️ Critical/High Severity Bugs",
                "facts": bug_facts,
            })

        # Add link to ReportPortal
        if summary.rp_url and summary.launch_id:
            card["potentialAction"] = [
                {
                    "@type": "OpenUri",
                    "name": "View in ReportPortal",
                    "targets": [
                        {"os": "default", 
                         "uri": f"{summary.rp_url}/ui/#default/launches/all/{summary.launch_id}"}
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
                        logger.info("teams_notification_sent", 
                                    launch=summary.launch_name,
                                    component=summary.component)
                        return True
                    else:
                        text = await resp.text()
                        logger.error("teams_notification_failed", 
                                     status=resp.status, error=text)
                        return False
        except Exception as e:
            logger.error("teams_notification_error", error=str(e))
            return False

    async def send_message(self, text: str) -> bool:
        """Send a simple text message to Teams.
        
        Args:
            text: Message text
            
        Returns:
            True if sent successfully
        """
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "text": text,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=card,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("teams_message_sent")
                        return True
                    return False
        except Exception as e:
            logger.error("teams_message_error", error=str(e))
            return False
