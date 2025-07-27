import re
from rest_framework.views import exception_handler
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from datetime import timedelta

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