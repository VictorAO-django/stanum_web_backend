import random
import datetime
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
# from twilio.rest import Client
from utils.mailer import Mailer
from account.models import *

class UserOtp:
    def __init__(self, email, event):
        self.email = email
        self.event = event 
        self.otp = None
        
    def generate_otp(self):
        """Generate a 4-digit OTP."""
        self.otp = str(random.randint(100000, 999999))
        return self.otp

    def send_otp(self, user):
        assert self.otp != None, "call generate_otp() before send_otp()"
        # Check if an OTP already exists for the user and event
        content_type = ContentType.objects.get_for_model(user)
        existing_otp = OTP.objects.filter(content_type=content_type, object_id=user.id, event=self.event)

        # Generate a new OTP code
        mailer = Mailer(email=user.email, service='vendor') 
        mailer.send_otp(user=user, otp_code=self.otp, expiry_time=5, event=self.event) 

        # If an existing OTP is found, update it; otherwise, create a new OTP
        if existing_otp.exists():
            otp_record = existing_otp.first()
            otp_record.otp_code = self.otp
            otp_record.expires_at = timezone.now() + datetime.timedelta(minutes=10)  # Reset expiry time
            otp_record.is_used = False
            otp_record.save()
        else:
            otp_record = OTP.objects.create(
            content_type=ContentType.objects.get_for_model(user),
            object_id=user.id,
            otp_code=self.otp,
            event=self.event,
        )
          
            
def verify_otp(user, event, otp_code):
    """
    Verify if the provided OTP is correct, not expired, and not used.
    """
    try:
        # Retrieve the latest OTP for the given user and event
        otp_instance = OTP.objects.filter(
            content_type=ContentType.objects.get_for_model(user),
            object_id=user.id,
            event=event,
            is_used=False,  # Ensure the OTP hasn't been used yet
        ).latest('generated_at')  # Get the latest OTP by creation time
        print("OTP", otp_instance.otp_code)
        
        # Check if the OTP has expired
        if otp_instance.has_expired():
            return False  # OTP is not valid

             # Convert both to strings for comparison and strip whitespace
        if str(otp_instance.otp_code).strip() != str(otp_code).strip():
            print(f"Stored OTP: '{otp_instance.otp_code}', Provided OTP: '{otp_code}'")
            return False  # OTP is not valid
        
        # If all checks pass, mark the OTP as used
        otp_instance.is_used = True
        otp_instance.save()

        return True  # OTP is valid

    except OTP.DoesNotExist:
        return False  # OTP is not valid