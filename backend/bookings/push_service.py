import json
import logging
import os
from py_vapid import Vapid, b64urlencode
from pywebpush import webpush, WebPushException
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from .models import PushSubscription

logger = logging.getLogger(__name__)

_CACHED_VAPID = None


def get_vapid():
    """
    Returns the configured Vapid instance.
    Prioritizes environment variables / Django settings.
    Falls back to a persistent development key if not set.
    """
    global _CACHED_VAPID
    if _CACHED_VAPID is not None:
        return _CACHED_VAPID

    priv_key = getattr(settings, 'VAPID_PRIVATE_KEY', '') or os.environ.get('VAPID_PRIVATE_KEY', '')
    if priv_key:
        try:
            if '-----BEGIN' in priv_key:
                _CACHED_VAPID = Vapid.from_pem(priv_key.encode('utf-8'))
            elif os.path.exists(priv_key):
                _CACHED_VAPID = Vapid.from_file(priv_key)
            else:
                _CACHED_VAPID = Vapid.from_string(priv_key)
            return _CACHED_VAPID
        except Exception as e:
            logger.warning(f"Failed to load VAPID private key from settings: {e}. Generating dev key.")

    # Fallback for development/testing
    vapid_file = os.path.join(settings.BASE_DIR, 'vapid_dev_private.pem')
    if os.path.exists(vapid_file):
        try:
            _CACHED_VAPID = Vapid.from_file(vapid_file)
            return _CACHED_VAPID
        except Exception:
            pass

    # Generate and optionally save dev key
    v = Vapid()
    v.generate_keys()
    try:
        with open(vapid_file, 'wb') as f:
            f.write(v.private_pem())
    except Exception as e:
        logger.debug(f"Could not persist dev VAPID key to file: {e}")

    _CACHED_VAPID = v
    return _CACHED_VAPID


def get_vapid_public_key():
    """
    Returns the uncompressed P-256 public key as a base64url string.
    Suitable for browser pushManager.subscribe({ applicationServerKey: ... }).
    """
    configured = getattr(settings, 'VAPID_PUBLIC_KEY', '') or os.environ.get('VAPID_PUBLIC_KEY', '')
    if configured:
        return configured.strip()

    v = get_vapid()
    raw_pub = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return b64urlencode(raw_pub)


def send_web_push(user, title, body, data=None):
    """
    Dispatches a web push notification to all active PushSubscriptions of the given user.
    The notification payload is informational only (no action buttons).
    Prunes expired subscriptions (HTTP 410 or 404).
    Catches all exceptions gracefully to ensure core transactions never fail.
    """
    if not user:
        return 0

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        return 0

    vapid = get_vapid()
    claim_email = getattr(settings, 'VAPID_CLAIM_EMAIL', '') or 'mailto:support@rentbee.com'
    if not claim_email.startswith('mailto:') and not claim_email.startswith('http'):
        claim_email = f'mailto:{claim_email}'

    payload = json.dumps({
        'title': title,
        'body': body,
        'icon': '/favicon.svg',
        'badge': '/favicon.svg',
        'data': data or {},
    })

    success_count = 0
    dead_ids = []

    for sub in subscriptions:
        sub_info = {
            'endpoint': sub.endpoint,
            'keys': {
                'p256dh': sub.p256dh,
                'auth': sub.auth,
            }
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={'sub': claim_email},
                ttl=86400,
            )
            success_count += 1
        except WebPushException as ex:
            if ex.response is not None and ex.response.status_code in (404, 410):
                dead_ids.append(sub.id)
            else:
                logger.warning(f"WebPushException sending to {sub.endpoint[:40]}: {ex}")
        except Exception as ex:
            logger.warning(f"Unexpected error sending web push: {ex}")

    if dead_ids:
        PushSubscription.objects.filter(id__in=dead_ids).delete()

    return success_count

