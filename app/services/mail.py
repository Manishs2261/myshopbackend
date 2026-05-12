from pathlib import Path
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

_conf: ConnectionConfig | None = None

def _get_conf() -> ConnectionConfig | None:
    global _conf
    if _conf is not None:
        return _conf
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        logger.warning("MAIL_USERNAME/MAIL_PASSWORD not set — email sending disabled.")
        return None
    try:
        _conf = ConnectionConfig(
            MAIL_USERNAME=settings.MAIL_USERNAME,
            MAIL_PASSWORD=settings.MAIL_PASSWORD,
            MAIL_FROM=settings.MAIL_FROM,
            MAIL_PORT=settings.MAIL_PORT,
            MAIL_SERVER=settings.MAIL_SERVER,
            MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
            MAIL_STARTTLS=settings.MAIL_STARTTLS,
            MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
            USE_CREDENTIALS=settings.USE_CREDENTIALS,
            VALIDATE_CERTS=settings.VALIDATE_CERTS,
        )
    except Exception as e:
        logger.error(f"Mail configuration error: {e}")
    return _conf

class MailService:
    @staticmethod
    async def send_otp_email(email: str, otp: str):
        """
        Sends a 6-digit OTP to the user's email for verification.
        """
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
            <h2 style="color: #4A90E2; text-align: center;">Email Verification</h2>
            <p>Hello,</p>
            <p>Your verification code for <strong>{settings.APP_NAME}</strong> is:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #333; background: #f4f4f4; padding: 10px 20px; border-radius: 5px; border: 1px dashed #ccc;">
                    {otp}
                </span>
            </div>
            <p>This code is valid for 10 minutes. Please do not share this code with anyone.</p>
            <p>If you didn't request this, you can safely ignore this email.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888; text-align: center;">
                &copy; {settings.APP_NAME}. All rights reserved.
            </p>
        </div>
        """
        
        message = MessageSchema(
            subject=f"{settings.APP_NAME} - Your Verification Code",
            recipients=[email],
            body=html,
            subtype=MessageType.html
        )

        conf = _get_conf()
        if conf is None:
            logger.warning(f"Email not configured — OTP for {email}: {otp}")
            return
        fm = FastMail(conf)
        try:
            await fm.send_message(message)
            logger.info(f"OTP email sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send OTP email to {email}: {str(e)}")
            if settings.DEBUG:
                print(f"\n[DEV MODE] FAILED TO SEND EMAIL. OTP for {email} is: {otp}\n")

    @staticmethod
    async def send_password_reset_email(email: str, token: str):
        """
        Sends a password reset link to the user's email.
        """
        reset_url = f"https://yourdomain.com/reset-password?token={token}" # TODO: Use setting for frontend URL
        
        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e1e1e1; border-radius: 10px;">
            <h2 style="color: #4A90E2; text-align: center;">Password Reset Request</h2>
            <p>Hello,</p>
            <p>We received a request to reset your password for your <strong>{settings.APP_NAME}</strong> account.</p>
            <p>Click the button below to reset your password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_url}" style="background-color: #4A90E2; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Reset Password
                </a>
            </div>
            <p>This link will expire in 1 hour.</p>
            <p>If you didn't request this, please ignore this email or contact support if you have concerns.</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888; text-align: center;">
                &copy; {settings.APP_NAME}. All rights reserved.
            </p>
        </div>
        """

        message = MessageSchema(
            subject=f"{settings.APP_NAME} - Password Reset Request",
            recipients=[email],
            body=html,
            subtype=MessageType.html
        )

        conf = _get_conf()
        if conf is None:
            logger.warning(f"Email not configured — reset token for {email}: {token}")
            return
        fm = FastMail(conf)
        try:
            await fm.send_message(message)
            logger.info(f"Password reset email sent to {email}")
        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {str(e)}")
            if settings.DEBUG:
                print(f"\n[DEV MODE] FAILED TO SEND EMAIL. Reset Token for {email} is: {token}\n")

mail_service = MailService()
