import re, requests
from django.db.models import Avg, Sum
from cryptography.fernet import Fernet
from decimal import Decimal
from rest_framework.views import exception_handler
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from trading.models import MT5User, MT5Deal, AccountRating, UserRating
from account.models import Referral, ReferralEarning, ReferalEarningTransaction

User = get_user_model()

def update_lock_count(user, action: str):
    valid_action = ['increase', 'fallback']
    if user.lock_count != 5:
        if action not in valid_action:
            return 0
        if action == 'increase':
            user.lock_count += 1
            user.save()
        if action == 'fallback':
            user.lock_count = 0
            user.save()
            return user.lock_count, False
        if user.lock_count == 5:
            now = timezone.now()
            # Calculate the next minute by adding a timedelta of 1 minute
            next_minute = now + timedelta(minutes=5)
            user.lock_count = 0
            user.lock_duration = next_minute
            user.save()
            return 5, True
        return user.lock_count, True
    return 5, False


def custom_response(status, message, data=None, http_status=status.HTTP_200_OK):
    return Response({
        "status": status,
        "message": message,
        "data": data
    }, status=http_status)


def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Special handling for ValidationError
        if isinstance(exc, ValidationError):
            if isinstance(exc.detail, dict):
                # Get the first error message from the dictionary
                try:
                    first_field = next(iter(exc.detail))
                    first_error = exc.detail[first_field]
                    if isinstance(first_error, list):
                        response.data = {'message': first_error[0]}
                    else:
                        response.data = {'message': first_error}
                except (StopIteration, TypeError):
                    response.data = {'message': 'Validation error occurred'}
            elif isinstance(exc.detail, list):
                response.data = {'message': exc.detail[0]}
            else:
                response.data = {'message': str(exc.detail)}
        # If the exception has a 'message' in its detail, use that
        elif 'message' in response.data:
            response.data = {'message': response.data['message']}
        # Handle case where 'detail' is in response.data
        elif 'detail' in response.data:
            response.data = {'message': response.data['detail']}
        # Otherwise, get the first error from the first field
        else:
            try:
                first_error = next(iter(response.data.values()))
                if isinstance(first_error, list):
                    response.data = {'message': first_error[0]}
                else:
                    response.data = {'message': first_error}
            except (StopIteration, TypeError):
                # Fallback if we can't extract a message
                response.data = {'message': 'An error occurred'}
    return response


def has_no_special_character(value):
    # Check if the username starts with "admin"
    if not re.match(r'^[a-zA-Z0-9]*$', value):
        return False
    return True

def check_special_character(password: str)->bool:
    # Define the regular expression for special characters
    special_char_pattern = r'[!@#$%^&*(),.?":{}|<>]'
    
    # Search for a special character in the password
    if re.search(special_char_pattern, password):
        return True
    else:
        return False

def format_date(date):
    """Generates and returns the formatted date

    Args:
        date (datetime): A datetime obj or DateTimeField
        returns {day}{suffix} of {month} {year}

    Returns:
        str: 4th of december 2024
    """
    day = str(date.day)
    month = date.strftime('%B')
    year = date.year
    #predefine the suffixes
    suffixes = {1: 'st', 2: 'nd', 3: 'rd'}
    
    if int(day[-1]) in suffixes.keys():
        suffix = suffixes[int(day[-1])]
    else:
        suffix = 'th'
        
    return f"{day}{suffix} of {month} {year}"


def get_selected_account(user) -> MT5User:
    q = MT5User.objects.filter(user=user).order_by('-selected_date')
    if q.exists():
        return q.first()
    return None


def award_referral_reward(referral: Referral, amount: int | Decimal, description: str = None):
    """
    Awards a referral reward to the user who referred the given referral.user.

    Only awards if:
    - referral has a referrer (referred_by is not None)
    - referral.reward_used is False
    """
    if not referral.referred_by or referral.reward_used:
        return  # No referrer or already rewarded

    # Ensure Decimal for precision
    amount = Decimal(amount)
    percentage = Decimal(str(settings.REFERRAL_PROFIT_PERCENTAGE)) / Decimal("100")
    reward_amount = percentage * amount

    with transaction.atomic():
        earning, _ = ReferralEarning.objects.get_or_create(user=referral.referred_by)
        earning.amount += reward_amount
        earning.save()

        ReferalEarningTransaction.objects.create(
            user=referral.referred_by,
            transaction_type="credit",
            amount=reward_amount,
            description=description or f"Referral reward from {referral.user.full_name}"
        )

        referral.reward_used = True
        referral.save(update_fields=["reward_used"])


def get_client_ip(request):
    """Get the real client IP address even if behind a proxy."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_browser_info(request):
    ua_string = request.META.get('HTTP_USER_AGENT', '')

    # Look for major browsers
    match = re.search(r'(Chrome|Firefox|Safari|Edge|Opera|MSIE|Trident)\/([\d.]+)', ua_string)
    if match:
        browser, version = match.groups()
        # Map "Trident" to "Internet Explorer"
        if browser == "Trident":
            browser = "Internet Explorer"
        return f"{browser} {version}"

    return "Unknown Browser"


def split_full_name(full_name: str) -> tuple[str, str]:
    """
    Split a full name into first_name and last_name.

    Returns:
        (first_name, last_name) as a tuple.
        If only one name is provided, last_name will be empty.
        If empty string is given, both will be empty.
    """
    if not full_name or not full_name.strip():
        return ("", "")

    parts = full_name.strip().split()

    if len(parts) == 1:
        return (parts[0], "")

    return (parts[0], " ".join(parts[1:]))


def create_mt5_account(
    base_url: str,
    account_data: dict
) -> tuple[str, str] | None:
    """
    Calls the CreateAccount API endpoint to create an MT5 account.

    Args:
        base_url (str): The base URL of your API (e.g. "https://yourdomain.com/api").
        token (str): Authentication token (JWT or DRF token).
        account_data (dict): Payload matching NewAccountData TypedDict.

    Returns:
        tuple: (mt5_user_id, password) if success
        None: if failure
    """
    url = f"{base_url}/account/create"
    headers = {
        "X-BRIDGE-SECRET": settings.BRIDGE_SECRET,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=account_data, headers=headers)
        print(url, account_data)
        response.raise_for_status()

        data = response.json()
        if data.get("status") == "success":
            mt5_user = data["data"]["mt5_user_login"]
            password = data["data"]["password"]
            return mt5_user, password
        else:
            print("Error:", data.get("message"))
            return None

    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
    

def send_bridge_test_req(base_url):
    url = f"{base_url}/test"
    headers = {
        "X-BRIDGE-SECRET": settings.BRIDGE_SECRET,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        print("Successfull req")
        return
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None

# For encrypting trading passwords (if needed)
def encrypt_password(password):
    key = settings.MT5ACCOUNT_PASSWORD_KEY  # Store securely
    f = Fernet(key)
    return f.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    key = settings.MT5ACCOUNT_PASSWORD_KEY
    f = Fernet(key)
    return f.decrypt(encrypted_password.encode()).decode()


def average_winning_trade(login=None):
    qs = MT5Deal.objects.filter(
        login=login,
        deleted=False,
        entry=1,           # only closing deals
        profit__gt=0       # winning trades
    )

    avg_win = qs.aggregate(avg=Avg("profit"))["avg"]
    return avg_win or 0


def average_losing_trade(login=None):
    qs = MT5Deal.objects.filter(
        login=login,
        deleted=False,
        entry=1,
        profit__lt=0
    )

    avg_loss = qs.aggregate(avg=Avg("profit"))["avg"]
    return avg_loss or 0


def calculate_profit_factor(login: int):
    # exclude deleted deals
    deals = MT5Deal.objects.filter(login=login, deleted=False)

    gross_profit = deals.filter(profit__gt=0).aggregate(total=Sum("profit"))["total"] or 0
    gross_loss = deals.filter(profit__lt=0).aggregate(total=Sum("profit"))["total"] or 0

    gross_loss = abs(gross_loss)  # make it positive

    if gross_loss == 0:  # prevent division by zero
        return float('inf') if gross_profit > 0 else 0

    return gross_profit / gross_loss


def calculate_win_ratio(login=None):
    qs = MT5Deal.objects.filter(
        login=login,
        deleted=False,
        entry=1  # only closing deals
    )

    total_trades = qs.count()
    winning_trades = qs.filter(profit__gt=0).count()

    if total_trades == 0:
        return 0  # avoid division by zero

    return (winning_trades / total_trades) * 100


def calculate_user_rating(user:MT5User):
    accounts = user.accounts.all().select_related("rating")
    if not accounts:
        return None

    # Example: weighted average (funded > evaluation)
    weights = {"funded": 2, "challenge": 1.5, "evaluation": 1}
    total_score, total_weight = 0, 0

    for acc in accounts:
        if hasattr(acc, "rating"):
            weight = weights.get(acc.account_type, 1)
            total_score += float(acc.rating.score) * weight
            total_weight += weight

    avg_score = total_score / total_weight if total_weight else 0
    stars = round(avg_score / 20)

    # Save/update
    rating, _ = UserRating.objects.get_or_create(user=user)
    rating.score = avg_score
    rating.stars = stars
    rating.save()

    return rating
