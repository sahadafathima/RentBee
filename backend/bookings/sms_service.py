import logging
import os
import re
import requests

logger = logging.getLogger(__name__)


class SMSProviderError(Exception):
    """Base exception for all SMS delivery and configuration errors."""
    pass


class SMSConfigurationError(SMSProviderError):
    """Raised when the SMS provider is missing required environment credentials."""
    pass


class SMSSendError(SMSProviderError):
    """Raised when an SMS provider returns an error during message transmission."""
    pass


def mask_phone(phone_number: str) -> str:
    """
    Masks all digits except the last 4 for privacy.
    Preserves optional country code prefix (e.g. +91 ******3210).
    """
    if not phone_number:
        return ""
    phone_str = str(phone_number).strip()
    digits = re.sub(r'\D', '', phone_str)
    if len(digits) <= 4:
        return phone_str

    if digits.startswith('91') and len(digits) == 12:
        return f"+91 {'*' * 6}{digits[-4:]}"
    if phone_str.startswith('+'):
        return f"+{'*' * (len(digits) - 4)}{digits[-4:]}"
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def normalize_to_e164(phone_number: str) -> str:
    """
    Converts phone number to E.164 international format.
    Defaults standard 10-digit Indian numbers to +91 country prefix.
    """
    cleaned = re.sub(r'[\s\-\(\)]', '', str(phone_number).strip())
    if cleaned.startswith('+'):
        return cleaned
    digits = re.sub(r'\D', '', cleaned)
    if len(digits) == 10:
        return f"+91{digits}"
    return f"+{digits}"


class BaseSMSProvider:
    """Base interface for SMS providers."""
    name = "base"

    def send_sms(self, to_number: str, message: str) -> dict:
        raise NotImplementedError


class TwilioSMSProvider(BaseSMSProvider):
    """
    Production SMS provider using Twilio's REST API.
    Configured via standard environment variables:
    - TWILIO_ACCOUNT_SID
    - TWILIO_AUTH_TOKEN
    - TWILIO_FROM_NUMBER
    """
    name = "twilio"

    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self.auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number)

    def send_sms(self, to_number: str, message: str) -> dict:
        if not self.is_configured():
            missing = []
            if not self.account_sid:
                missing.append("TWILIO_ACCOUNT_SID")
            if not self.auth_token:
                missing.append("TWILIO_AUTH_TOKEN")
            if not self.from_number:
                missing.append("TWILIO_FROM_NUMBER")
            raise SMSConfigurationError(
                f"Twilio SMS provider is not configured. Missing environment variable(s): {', '.join(missing)}."
            )

        destination = normalize_to_e164(to_number)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        payload = {
            "From": self.from_number,
            "To": destination,
            "Body": message,
        }

        try:
            response = requests.post(
                url,
                data=payload,
                auth=(self.account_sid, self.auth_token),
                timeout=10,
            )
        except requests.exceptions.RequestException as exc:
            logger.error("Twilio connection failed for destination %s: %s", mask_phone(destination), exc)
            raise SMSSendError(f"Twilio network error during SMS dispatch: {exc}") from exc

        if response.status_code not in (200, 201):
            logger.error(
                "Twilio rejected SMS delivery to %s with status %s: %s",
                mask_phone(destination),
                response.status_code,
                response.text,
            )
            try:
                err_data = response.json()
                err_msg = err_data.get("message", response.text)
            except Exception:
                err_msg = response.text
            raise SMSSendError(f"Twilio SMS delivery failed ({response.status_code}): {err_msg}")

        try:
            resp_json = response.json()
            message_sid = resp_json.get("sid", "")
        except Exception:
            message_sid = ""

        return {
            "success": True,
            "provider": self.name,
            "message_id": message_sid,
            "destination": mask_phone(destination),
        }


def get_sms_provider() -> BaseSMSProvider:
    """
    Returns the configured SMS provider instance.
    Defaults to Twilio.
    """
    provider_name = os.environ.get("SMS_PROVIDER", "twilio").strip().lower()
    if provider_name == "twilio":
        return TwilioSMSProvider()
    # If custom provider specified, instantiate Twilio by default
    return TwilioSMSProvider()


def send_pickup_otp_sms(booking, otp: str) -> dict:
    """
    High-level dispatch function to send pickup OTP SMS to the renter.
    Safety guarantees:
    - Verifies renter has registered phone number.
    - Dispatches through configured SMS provider.
    - Never logs or exposes raw OTP.
    - Returns masked recipient phone number.
    """
    renter_phone = getattr(booking.renter, "phone_number", None)
    if not renter_phone:
        raise ValueError("Renter does not have a registered mobile number for OTP delivery.")

    item_name = booking.item.name if booking.item else "your item"
    message = (
        f"RentBee: Your pickup verification OTP for '{item_name}' "
        f"(Booking #{booking.booking_reference}) is {otp}. "
        f"Valid for 10 minutes. Share this OTP with the host at pickup. Do not share beforehand."
    )

    provider = get_sms_provider()
    result = provider.send_sms(to_number=renter_phone, message=message)

    # Secure log: only masked phone, NEVER the raw OTP
    logger.info(
        "Pickup OTP SMS successfully dispatched for booking %s to %s via %s",
        booking.booking_reference,
        mask_phone(renter_phone),
        provider.name,
    )
    return {
        "success": True,
        "masked_phone": mask_phone(renter_phone),
        "provider": provider.name,
        "message_id": result.get("message_id", ""),
    }
