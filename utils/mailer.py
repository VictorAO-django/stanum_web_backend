import random
from django.core.mail import send_mail,get_connection, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework import status
from utils.helper import format_date

from utils.exception import *

from challenge.models import *
from payment.models import *
class Mailer:
    def __init__(self, email=None, service=None):
        self.sender_email = 'noreply@stanum.com' #default sender email
        self.email = email #receiver email
        self.service = service #service
        
        try:
            #ensure the email is correct
            if isinstance(email, list):
                for i in email:
                    assert i.endswith('.com'), "Incorrect Email Address"
                self.receiver_email_list = [i for i in email] 
            else:
                assert self.email.endswith('.com'), "Incorrect Email Address"
                #create the receivers email list as it should be
                self.receiver_email_list = [self.email] 
        except AssertionError as err:
            #catch and handle the resulting Assertion Error
            raise InvalidEmail(detail=str(err))
        
        #email subject, the value will be provided by the method that handles the mail process
        self.subject = None 
        #email message, the value will be provided by the method that handles the mail process
        self.message = None 
        self.html_content = None
    
    
    def send(self):
        try:
            #ensure that the email subject was provided
            assert self.subject is not None, "provide a mail subject"
            #ensure that the email message was provided
            assert self.message is not None, "provide a mail message"
            send_mail(self.subject, self.message, self.sender_email, self.receiver_email_list, fail_silently=False)
            
        except AssertionError as err:
            #catch and handle the resulting Assertion Error
            raise ErrorOccured(detail= str(err))

    
    def send_with_template(self):
        try:
            #ensure that the email subject was provided
            assert self.subject is not None, "provide a mail subject"
            #ensure that the html content was provided
            assert self.html_content is not None, "provide a html content"
            
            text_content = strip_tags(self.html_content)
            # print(self.html_content)
            
            email = EmailMultiAlternatives(subject=self.subject, body=text_content, from_email=self.sender_email, to=self.receiver_email_list)
            email.attach_alternative(self.html_content, "text/html")
            email.send()
            
        except AssertionError as err:
            #catch and handle the resulting Assertion Error
            raise ErrorOccured(detail= str(err))
        
    def send_otp(self, user, otp_code, expiry_time, event="OTP Verification"):
        """
        Generates an OTP and sends it to the user.
        
        Args:
            user: The user object (Seller/Buyer) who will receive the OTP.
            otp_code: The generated OTP code.
            expiry_time: The expiry time for the OTP.
            event: Event name for which the OTP is generated (default is 'OTP Verification').
        """
        # Subject of the OTP email
        self.subject = f"{event}: Your One-Time Password (OTP)"

        context = {'otp_code': otp_code, 'expiry_time': expiry_time, 'date': format_date(timezone.now())}
            
        self.html_content = render_to_string('emails/otp.html', context)
        self.send_with_template()

    def payment_successful(self, amount, challenge: PropFirmChallenge):
        self.subject = "Payment Received Successfully"
        self.message = f"Your payment of ${amount} for {challenge.name} was received."

        self.send()

    def payment_failed(self, amount, challenge: PropFirmChallenge):
        self.subject = "Payment Failed"
        self.message = f"Your payment of ${amount} for {challenge.name} failed."

        self.send()

    def payment_expired(self, amount, challenge: PropFirmChallenge):
        self.subject = "Payment SessionExpired"
        self.message = f"Your payment session of ${amount} for {challenge.name} has expired."

        self.send()