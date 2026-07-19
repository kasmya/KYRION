"""Email Automation Bot with SendGrid, Pandas, and tracking."""
import os, logging, time
from typing import List, Dict
import pandas as pd
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, TrackingSettings, ClickTracking, SubscriptionTracking

logging.basicConfig(level=logging.INFO)
SG_API_KEY = os.getenv("SENDGRID_API_KEY", "YOUR_API_KEY")

def load_recipients(csv_path: str) -> pd.DataFrame:
    """Load and validate recipient list."""
    try:
        df = pd.read_csv(csv_path)
        required = ['email', 'name']
        if not all(col in df.columns for col in required):
            raise ValueError(f"CSV must contain columns: {required}")
        return df.dropna(subset=['email'])
    except Exception as e:
        logging.error(f"Failed to load CSV: {e}")
        return pd.DataFrame()

def send_personalized_email(recipient: Dict[str, str], template: str) -> bool:
    """Send email via SendGrid with tracking."""
    try:
        # Personalize content
        body = template.replace("{{name}}", recipient['name'])
        
        message = Mail(
            from_email=Email("noreply@example.com"),
            to_emails=To(recipient['email']),
            subject="Your Personalized Update",
            html_content=Content("text/html", body)
        )
        
        # Enable tracking
        message.tracking_settings = TrackingSettings(
            click_tracking=ClickTracking(enable=True),
            subscription_tracking=SubscriptionTracking(enable=True)
        )
        
        if SG_API_KEY == "YOUR_API_KEY":
            logging.info(f"[STUB] Sent to {recipient['email']}: {body[:50]}...")
            return True
            
        sg = SendGridAPIClient(SG_API_KEY)
        response = sg.send(message)
        if response.status_code in (200, 202):
            logging.info(f"Sent to {recipient['email']}")
            return True
        logging.warning(f"Failed for {recipient['email']}: {response.status_code}")
        return False
    except Exception as e:
        logging.error(f"Error sending to {recipient['email']}: {e}")
        return False

def process_bounces(failed_emails: List[str]):
    """Handle bounces by logging and optionally updating a suppression list."""
    if failed_emails:
        logging.warning(f"Bounces detected for: {failed_emails}")
        # In production, update SendGrid suppression list or internal DB

def run_campaign(csv_path: str, template: str):
    """Execute the email campaign."""
    df = load_recipients(csv_path)
    if df.empty:
        logging.error("No valid recipients found.")
        return
        
    failed = []
    for _, row in df.iterrows():
        success = send_personalized_email(row.to_dict(), template)
        if not success:
            failed.append(row['email'])
        time.sleep(0.1) # Rate limiting
        
    process_bounces(failed)
    logging.info(f"Campaign finished. Success: {len(df) - len(failed)}, Failed: {len(failed)}")

if __name__ == "__main__":
    # Example usage
    # df = pd.DataFrame({'email': ['test@example.com'], 'name': ['Test User']})
    # df.to_csv('recipients.csv', index=False)
    # run_campaign('recipients.csv', "<h1>Hello {{name}}</h1>")
    logging.info("Email bot ready. Provide CSV and template to run.")