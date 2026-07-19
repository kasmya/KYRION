"""
Email Automation Bot with SendGrid integration and tracking.

Features:
- Read recipient list from CSV
- Personalize email content with templates
- Send via SendGrid API
- Track opens, clicks, and bounces
- Handle errors and logging
"""

import os
import logging
import csv
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import json
import time

import pandas as pd
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Email, To, Content, Subject, 
    Personalization, TrackingSettings, ClickTracking,
    OpenTracking, BypassListManagement
)
import jinja2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmailTemplate:
    """Email template manager with Jinja2 support."""
    
    def __init__(self, template_dir: str = "templates"):
        """
        Initialize template manager.
        
        Args:
            template_dir: Directory containing email templates
        """
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(exist_ok=True)
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.template_dir)),
            autoescape=True
        )
        
        # Create default template if none exists
        default_template = self.template_dir / "default.html"
        if not default_template.exists():
            default_template.write_text("""
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #4CAF50; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background: #f9f9f9; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #777; }
        .button { display: inline-block; padding: 10px 20px; background: #4CAF50; 
                  color: white; text-decoration: none; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ subject }}</h1>
        </div>
        <div class="content">
            <p>Dear {{ recipient_name }},</p>
            {{ content }}
            {% if call_to_action %}
            <p style="text-align: center;">
                <a href="{{ call_to_action_url }}" class="button">{{ call_to_action }}</a>
            </p>
            {% endif %}
        </div>
        <div class="footer">
            <p>{{ company_name }} | {{ company_address }}</p>
            <p><a href="{{ unsubscribe_url }}">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>
            """)
    
    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render email template with context.
        
        Args:
            template_name: Template file name
            context: Template variables
            
        Returns:
            Rendered HTML string
        """
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except jinja2.TemplateError as e:
            logger.error(f"Template rendering error: {str(e)}")
            raise

class RecipientManager:
    """Manages recipient lists and segmentation."""
    
    def __init__(self):
        """Initialize recipient manager."""
        self.recipients = pd.DataFrame()
        self.segments = {}
    
    def load_from_csv(self, filepath: str) -> pd.DataFrame:
        """
        Load recipients from CSV file.
        
        Args:
            filepath: Path to CSV file
            
        Returns:
            DataFrame with recipient data
        """
        try:
            df = pd.read_csv(filepath)
            
            # Validate required columns
            required_cols = ['email', 'name']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            # Clean email addresses
            df['email'] = df['email'].str.strip().str.lower()
            df = df[df['email'].notna() & (df['email'] != '')]
            
            # Remove duplicates
            df = df.drop_duplicates(subset=['email'])
            
            # Add metadata
            df['added_at'] = datetime.now().isoformat()
            df['status'] = 'active'
            
            self.recipients = df
            logger.info(f"Loaded {len(df)} recipients from {filepath}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading recipients: {str(e)}", exc_info=True)
            raise
    
    def segment_recipients(self, criteria: Dict[str, Any]) -> pd.DataFrame:
        """
        Segment recipients based on criteria.
        
        Args:
            criteria: Segmentation criteria
            
        Returns:
            Segmented DataFrame
        """
        if self.recipients.empty:
            raise ValueError("No recipients loaded")
        
        mask = pd.Series([True] * len(self.recipients))
        
        for column, value in criteria.items():
            if column in self.recipients.columns:
                if isinstance(value, list):
                    mask &= self.recipients[column].isin(value)
                else:
                    mask &= self.recipients[column] == value
        
        return self.recipients[mask]
    
    def get_recipient_stats(self) -> Dict[str, Any]:
        """Get recipient statistics."""
        if self.recipients.empty:
            return {}
        
        stats = {
            'total': len(self.recipients),
            'active': len(self.recipients[self.recipients['status'] == 'active']),
            'unsubscribed': len(self.recipients[self.recipients['status'] == 'unsubscribed']),
            'bounced': len(self.recipients[self.recipients['status'] == 'bounced']),
        }
        
        return stats

class SendGridEmailSender:
    """Email sender using SendGrid API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize SendGrid sender.
        
        Args:
            api_key: SendGrid API key (uses env var if not provided)
        """
        self.api_key = api_key or os.getenv('SENDGRID_API_KEY', '')
        self.client = SendGridAPIClient(self.api_key) if self.api_key else None
        self.tracking_data = []
        
        if not self.api_key:
            logger.warning("SendGrid API key not configured. Emails will be logged only.")
    
    def create_personalization(
        self, recipient_email: str, recipient_name: str,
        custom_data: Dict[str, Any] = None
    ) -> Personalization:
        """
        Create personalized email.
        
        Args:
            recipient_email: Recipient email address
            recipient_name: Recipient name
            custom_data: Custom substitution data
            
        Returns:
            Personalization object
        """
        personalization = Personalization()
        
        # Add recipient
        personalization.add_to(To(
            email=recipient_email,
            name=recipient_name,
            substitutions={
                '-name-': recipient_name,
                '-email-': recipient_email,
            }
        ))
        
        # Add custom substitutions
        if custom_data:
            for key, value in custom_data.items():
                personalization.add_dynamic_template_data({key: value})
        
        return personalization
    
    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        from_email: str = "noreply@example.com",
        from_name: str = "Company Name",
        custom_args: Dict[str, str] = None,
        categories: List[str] = None
    ) -> Dict[str, Any]:
        """
        Send single email via SendGrid.
        
        Args:
            to_email: Recipient email
            to_name: Recipient name
            subject: Email subject
            html_content: HTML email content
            from_email: Sender email
            from_name: Sender name
            custom_args: Custom tracking arguments
            categories: Email categories for tracking
            
        Returns:
            Response data
        """
        try:
            # Create message
            message = Mail(
                from_email=Email(from_email, from_name),
                subject=Subject(subject),
                html_content=Content("text/html", html_content)
            )
            
            # Add personalization
            personalization = Personalization()
            personalization.add_to(To(to_email, to_name))
            
            if custom_args:
                for key, value in custom_args.items():
                    personalization.add_custom_arg(key, value)
            
            message.add_personalization(personalization)
            
            # Enable tracking
            tracking_settings = TrackingSettings()
            tracking_settings.click_tracking = ClickTracking(enable=True)
            tracking_settings.open_tracking = OpenTracking(enable=True)
            message.tracking_settings = tracking_settings
            
            # Add categories
            if categories:
                for category in categories:
                    message.add_category(category)
            
            # Send or stub
            if self.client:
                response = self.client.send(message)
                
                result = {
                    'email': to_email,
                    'status': 'sent' if response.status_code == 202 else 'failed',
                    'status_code': response.status_code,
                    'message_id': response.headers.get('X-Message-Id'),
                    'timestamp': datetime.now().isoformat()
                }
            else:
                # Stub for testing without API key
                logger.info(f"[STUB] Would send email to {to_email}: {subject}")
                result = {
                    'email': to_email,
                    'status': 'stubbed',
                    'status_code': 202,
                    'message_id': f"stub_{int(time.time())}",
                    'timestamp': datetime.now().isoformat()
                }
            
            self.tracking_data.append(result)
            return result
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}", exc_info=True)
            
            result = {
                'email': to_email,
                'status': 'failed',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            self.tracking_data.append(result)
            return result
    
    def send_bulk_emails(
        self,
        recipients: pd.DataFrame,
        template_manager: EmailTemplate,
        template_name: str,
        template_context: Dict[str, Any],
        subject: str,
        batch_size: int = 100,
        delay_between_batches: float = 1.0
    ) -> pd.DataFrame:
        """
        Send bulk emails to multiple recipients.
        
        Args:
            recipients: DataFrame of recipients
            template_manager: EmailTemplate instance
            template_name: Template file name
            template_context: Base template context
            subject: Email subject
            batch_size: Number of emails per batch
            delay_between_batches: Delay between batches in seconds
            
        Returns:
            DataFrame with sending results
        """
        results = []
        total_recipients = len(recipients)
        
        for batch_start in range(0, total_recipients, batch_size):
            batch_end = min(batch_start + batch_size, total_recipients)
            batch = recipients.iloc[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//batch_size + 1}: "
                       f"recipients {batch_start+1}-{batch_end} of {total_recipients}")
            
            for _, recipient in batch.iterrows():
                # Personalize context
                personalized_context = template_context.copy()
                personalized_context['recipient_name'] = recipient['name']
                personalized_context['recipient_email'] = recipient['email']
                
                # Add any additional recipient-specific data
                for col in recipient.index:
                    if col not in ['email', 'name']:
                        personalized_context[f'recipient_{col}'] = recipient[col]
                
                # Render template
                html_content = template_manager.render(template_name, personalized_context)
                
                # Personalize subject
                personalized_subject = subject.replace('{{name}}', recipient['name'])
                
                # Send email
                result = self.send_email(
                    to_email=recipient['email'],
                    to_name=recipient['name'],
                    subject=personalized_subject,
                    html_content=html_content,
                    custom_args={
                        'recipient_id': str(recipient.get('id', '')),
                        'campaign': template_context.get('campaign_name', 'default')
                    },
                    categories=['bulk_email', template_context.get('campaign_name', 'default')]
                )
                
                results.append(result)
            
            # Delay between batches
            if batch_end < total_recipients:
                time.sleep(delay_between_batches)
        
        return pd.DataFrame(results)
    
    def get_sending_stats(self) -> Dict[str, int]:
        """Get email sending statistics."""
        if not self.tracking_data:
            return {}
        
        df = pd.DataFrame(self.tracking_data)
        
        stats = {
            'total': len(df),
            'sent': len(df[df['status'] == 'sent']),
            'stubbed': len(df[df['status'] == 'stubbed']),
            'failed': len(df[df['status'] == 'failed']),
        }
        
        return stats

class EmailTracker:
    """Tracks email events (opens, clicks, bounces)."""
    
    def __init__(self, tracking_file: str = "email_tracking.json"):
        """
        Initialize tracker.
        
        Args:
            tracking_file: File to store tracking data
        """
        self.tracking_file = Path(tracking_file)
        self.events = self._load_events()
    
    def _load_events(self) -> List[Dict[str, Any]]:
        """Load tracking events from file."""
        if self.tracking_file.exists():
            try:
                with open(self.tracking_file, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_events(self) -> None:
        """Save tracking events to file."""
        with open(self.tracking_file, 'w') as f:
            json.dump(self.events, f, indent=2)
    
    def record_open(self, message_id: str, email: str) -> None:
        """
        Record email open event.
        
        Args:
            message_id: SendGrid message ID
            email: Recipient email
        """
        event = {
            'type': 'open',
            'message_id': message_id,
            'email': email,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
        self._save_events()
        logger.debug(f"Open recorded: {email}")
    
    def record_click(self, message_id: str, email: str, url: str) -> None:
        """
        Record link click event.
        
        Args:
            message_id: SendGrid message ID
            email: Recipient email
            url: Clicked URL
        """
        event = {
            'type': 'click',
            'message_id': message_id,
            'email': email,
            'url': url,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
        self._save_events()
        logger.debug(f"Click recorded: {email} -> {url}")
    
    def record_bounce(self, message_id: str, email: str, reason: str) -> None:
        """
        Record bounce event.
        
        Args:
            message_id: SendGrid message ID
            email: Recipient email
            reason: Bounce reason
        """
        event = {
            'type': 'bounce',
            'message_id': message_id,
            'email': email,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
        self._save_events()
        logger.warning(f"Bounce recorded: {email} - {reason}")
    
    def get_stats(self, campaign_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tracking statistics.
        
        Args:
            campaign_name: Filter by campaign
            
        Returns:
            Statistics dictionary
        """
        if not self.events:
            return {}
        
        df = pd.DataFrame(self.events)
        
        opens = len(df[df['type'] == 'open'])
        clicks = len(df[df['type'] == 'click'])
        bounces = len(df[df['type'] == 'bounce'])
        
        unique_opens = df[df['type'] == 'open']['email'].nunique()
        unique_clicks = df[df['type'] == 'click']['email'].nunique()
        
        total_sent = len(set(df['email']))
        
        stats = {
            'total_sent': total_sent,
            'total_opens': opens,
            'unique_opens': unique_opens,
            'open_rate': f"{(unique_opens / total_sent * 100):.1f}%" if total_sent > 0 else "0%",
            'total_clicks': clicks,
            'unique_clicks': unique_clicks,
            'click_rate': f"{(unique_clicks / total_sent * 100):.1f}%" if total_sent > 0 else "0%",
            'total_bounces': bounces,
            'bounce_rate': f"{(bounces / total_sent * 100):.1f}%" if total_sent > 0 else "0%",
        }
        
        return stats
    
    def export_stats(self, filepath: str) -> None:
        """
        Export tracking statistics to CSV.
        
        Args:
            filepath: Output CSV path
        """
        df = pd.DataFrame(self.events)
        df.to_csv(filepath, index=False)
        logger.info(f"Tracking data exported to {filepath}")

class EmailAutomationBot:
    """Main email automation bot."""
    
    def __init__(self, sendgrid_api_key: Optional[str] = None):
        """
        Initialize email bot.
        
        Args:
            sendgrid_api_key: SendGrid API key
        """
        self.template_manager = EmailTemplate()
        self.recipient_manager = RecipientManager()
        self.email_sender = SendGridEmailSender(sendgrid_api_key)
        self.tracker = EmailTracker()
        self.campaign_history = []
    
    def run_campaign(
        self,
        recipient_file: str,
        campaign_name: str,
        subject: str,
        template_name: str = "default.html",
        template_context: Optional[Dict[str, Any]] = None,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Run complete email campaign.
        
        Args:
            recipient_file: CSV file with recipients
            campaign_name: Campaign identifier
            subject: Email subject
            template_name: Email template file
            template_context: Template variables
            test_mode: If True, send only to first recipient
            
        Returns:
            Campaign results
        """
        logger.info(f"Starting campaign: {campaign_name}")
        
        try:
            # Load recipients
            recipients = self.recipient_manager.load_from_csv(recipient_file)
            
            if test_mode:
                recipients = recipients.head(1)
                logger.info("Test mode: sending to first recipient only")
            
            # Prepare template context
            context = template_context or {}
            context.update({
                'campaign_name': campaign_name,
                'company_name': 'Your Company',
                'company_address': '123 Main St, City, Country',
                'unsubscribe_url': 'https://example.com/unsubscribe',
                'current_year': datetime.now().year
            })
            
            # Send emails
            results_df = self.email_sender.send_bulk_emails(
                recipients=recipients,
                template_manager=self.template_manager,
                template_name=template_name,
                template_context=context,
                subject=subject
            )
            
            # Record campaign
            campaign_record = {
                'campaign_name': campaign_name,
                'timestamp': datetime.now().isoformat(),
                'recipients': len(recipients),
                'results': self.email_sender.get_sending_stats(),
                'test_mode': test_mode
            }
            
            self.campaign_history.append(campaign_record)
            
            # Export results
            results_file = f"campaign_{campaign_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            results_df.to_csv(results_file, index=False)
            
            logger.info(f"Campaign completed: {campaign_name}")
            
            return campaign_record
            
        except Exception as e:
            logger.error(f"Campaign failed: {str(e)}", exc_info=True)
            raise
    
    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive campaign report."""
        report = {
            'generated_at': datetime.now().isoformat(),
            'campaign_history': self.campaign_history,
            'email_stats': self.email_sender.get_sending_stats(),
            'tracking_stats': self.tracker.get_stats(),
            'recipient_stats': self.recipient_manager.get_recipient_stats()
        }
        
        # Save report
        report_file = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Report generated: {report_file}")
        
        return report

def main():
    """Example usage of email automation bot."""
    
    # Create sample recipients CSV for demo
    sample_recipients = pd.DataFrame({
        'email': ['user1@example.com', 'user2@example.com', 'user3@example.com'],
        'name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
        'company': ['Acme Corp', 'Tech Inc', 'Startup LLC'],
        'plan': ['premium', 'basic', 'premium']
    })
    
    sample_file = "sample_recipients.csv"
    sample_recipients.to_csv(sample_file, index=False)
    
    # Initialize bot
    bot = EmailAutomationBot()
    
    # Run campaign
    try:
        campaign_result = bot.run_campaign(
            recipient_file=sample_file,
            campaign_name="welcome_series",
            subject="Welcome to {{name}}!",
            template_name="default.html",
            template_context={
                'content': '<p>Thank you for joining our platform!</p>',
                'call_to_action': 'Get Started',
                'call_to_action_url': 'https://example.com/start'
            },
            test_mode=True
        )
        
        print("\n" + "="*50)
        print("CAMPAIGN RESULTS")
        print("="*50)
        print(json.dumps(campaign_result, indent=2))
        
        # Generate report
        report = bot.generate_report()
        print("\n" + "="*50)
        print("CAMPAIGN REPORT")
        print("="*50)
        print(f"Total recipients: {report['recipient_stats'].get('total', 0)}")
        print(f"Emails sent: {report['email_stats'].get('sent', 0)}")
        
    except Exception as e:
        logger.error(f"Error running campaign: {str(e)}", exc_info=True)

if __name__ == "__main__":
    main()
