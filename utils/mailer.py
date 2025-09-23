import random
from typing import List, Literal
import datetime
from django.core.mail import send_mail,get_connection, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework import status
from utils.helper import format_date

from utils.exception import *

from challenge.models import *
from payment.models import *
from trading.models import *
class Mailer:
    def __init__(self, email=None, service=None):
        self.sender_email = 'noreply@stanumcapital.com' #default sender email
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

        context = {
            'otp_code': otp_code, 'expiry_time': expiry_time, 'date': format_date(timezone.now()), 
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }
            
        self.html_content = render_to_string('emails/otp.html', context)
        self.send_with_template()

    def payment_successful(self, user, challenge: PropFirmChallenge, payment):
        self.subject = "Payment Received Successfully"
        context = {
            'user': user, 'challenge': challenge, 'payment': payment,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }

        self.html_content = render_to_string('emails/payment_received.html', context)
        self.send_with_template()

    def payment_failed(self, user, challenge: PropFirmChallenge, payment):
        self.subject = "Payment Failed"
        context = {
            'user': user, 'challenge': challenge, 'payment': payment,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }

        self.html_content = render_to_string('emails/payment_failed.html', context)
        self.send_with_template()

    def payment_failed(self, user, challenge: PropFirmChallenge, payment):
        self.subject = "Payment Session Expired"
        context = {
            'user': user, 'challenge': challenge, 'payment': payment,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }

        self.html_content = render_to_string('emails/payment_expired.html', context)
        self.send_with_template()

    def wallet_funding_success(self, transaction: PropFirmWalletTransaction):
        self.subject = "Wallet funding successful"
        context = {
            'transaction': transaction,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }
        self.html_content = render_to_string('emails/wallet_funding_success.html', context)
        self.send_with_template()

    def wallet_funding_failed(self, transaction: PropFirmWalletTransaction):
        self.subject = "Wallet funding failed"
        context = {
            'transaction': transaction,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }
        self.html_content = render_to_string('emails/wallet_funding_failed.html', context)
        self.send_with_template()

    def challenge_entry(self, user:MT5User, challenge: PropFirmChallenge, password):
        self.subject = f"Welcome to {settings.GLOBAL_SERVICE_NAME} Prop Challenge"
        context = {
            'user': user, 'challenge': challenge, 'firm_name': settings.GLOBAL_SERVICE_NAME,
            'broker_name': settings.BROKER_NAME, 'server': settings.SERVER_NAME, 'password': password,
            'current_year': settings.CURRENT_YEAR, 'company_name': settings.GLOBAL_SERVICE_NAME
        }
        self.html_content = render_to_string('emails/challenge_entry.html', context)
        self.send_with_template()

    def funded_account_issued(self, user:MT5User, challenge: PropFirmChallenge, password):
        self.subject = f"Funded Account Issued"
        context = {
            'user': user, 'challenge': challenge, 'password': password, 'broker_name': settings.BROKER_NAME,
            'server': settings.SERVER_NAME,'current_year': settings.CURRENT_YEAR, 
            'company_name': settings.GLOBAL_SERVICE_NAME, 'firm_name': settings.GLOBAL_SERVICE_NAME,
        }
        self.html_content = render_to_string('emails/funded_account_issued.html', context)
        self.send_with_template()

    def challenge_passed_1(self, user:MT5User, challenge:PropFirmChallenge):
        self.subject = f"Challenge Phase 1 passed {challenge.name}"
        context = {
            'user': user, 'company_name': settings.GLOBAL_SERVICE_NAME, 'challenge': challenge,
        }
        self.html_content = render_to_string('emails/challenge_passed_1.html', context)
        self.send_with_template()

    def challenge_passed_2(self, user:MT5User, challenge:PropFirmChallenge):
        self.subject = f"Challenge passed {challenge.name}"
        context = {
            'user': user, 'company_name': settings.GLOBAL_SERVICE_NAME, 'challenge': challenge,
        }
        self.html_content = render_to_string('emails/challenge_passed_2.html', context)
        self.send_with_template()

    def challenge_passed(self, user:MT5User, challenge:PropFirmChallenge):
        self.subject = f"Challenge passed {challenge.name}"
        context = {
            'user': user.user, 'company_name': settings.GLOBAL_SERVICE_NAME, 'challenge': challenge,
        }
        self.html_content = render_to_string('emails/challenge_passed.html', context)
        self.send_with_template()

    def challenge_failed(self, user:MT5User, challenge:PropFirmChallenge, failure_reasons:List[str]):
        self.subject = f"Challenge failed {challenge.name}"
        context = {
            'user': user, 'firm_name': settings.GLOBAL_SERVICE_NAME, 'challenge': challenge, 'failure_reasons': failure_reasons,
            'restart_url': f"{settings.FRONTEND_BASE_URL}funding"
        }
        self.html_content = render_to_string('emails/challenge_failed.html', context)
        self.send_with_template()

    def kyc(self, user,  action: Literal[
            'proof_of_id_approved', 'proof_of_id_rejected',
            'proof_of_ha1_approved', 'proof_of_ha1_rejected',
            'proof_of_ha2_approved', 'proof_of_ha2_rejected'
        ]
    ):
        EMAIL_SCENARIOS = {
            "proof_of_id_approved": {
                "subject": "✅ Proof of Identity Approved",
                "title": "Proof of Identity Approved",
                "message": "We’re pleased to inform you that your <strong>Proof of Identity</strong> has been successfully reviewed and approved.",
                "status_banner": "✅ Approved – Proof of Identity Verified",
                "color": "#16a34a",  # green
            },
            "proof_of_id_rejected": {
                "subject": "❌ Proof of Identity Rejected",
                "title": "Proof of Identity Rejected",
                "message": "Unfortunately, your <strong>Proof of Identity</strong> was rejected. Please upload a valid government-issued ID with all details clearly visible.",
                "status_banner": "❌ Rejected – Proof of Identity Failed",
                "color": "#dc2626",  # red
            },
            "proof_of_ha1_approved": {
                "subject": "✅ Proof of Address 1 Approved",
                "title": "Proof of Address 1 Approved",
                "message": "We’re pleased to inform you that your <strong>Proof of Address 1</strong> has been approved.",
                "status_banner": "✅ Approved – Proof of Address 1 Verified",
                "color": "#16a34a",
            },
            "proof_of_ha1_rejected": {
                "subject": "❌ Proof of Address 1 Rejected",
                "title": "Proof of Address 1 Rejected",
                "message": "Unfortunately, your <strong>Proof of Address 1</strong> was rejected. Please upload a valid document showing your address.",
                "status_banner": "❌ Rejected – Proof of Address 1 Failed",
                "color": "#dc2626",
            },
            "proof_of_ha2_approved": {
                "subject": "✅ Proof of Address 2 Approved",
                "title": "Proof of Address 2 Approved",
                "message": "We’re pleased to inform you that your <strong>Proof of Address 2</strong> has been approved.",
                "status_banner": "✅ Approved – Proof of Address 2 Verified",
                "color": "#16a34a",
            },
            "proof_of_ha2_rejected": {
                "subject": "❌ Proof of Address 2 Rejected",
                "title": "Proof of Address 2 Rejected",
                "message": "Unfortunately, your <strong>Proof of Address 2</strong> was rejected. Please upload another valid document showing your address.",
                "status_banner": "❌ Rejected – Proof of Address 2 Failed",
                "color": "#dc2626",
            },
        }

        scenario = EMAIL_SCENARIOS[action]

        context = {
            "user_name": getattr(user, "full_name", ""),
            "company_name": settings.GLOBAL_SERVICE_NAME,
            "year": datetime.date.today().year,
            "title": scenario["title"],
            "message": scenario["message"],
            "status_banner": scenario["status_banner"],
            "color": scenario["color"],
        }

        # subject and html
        self.subject = scenario["subject"]
        self.html_content = render_to_string("emails/verification_update.html", context)

        # send email
        self.send_with_template()

    
    def admin_trade_rule_violation(self, user:MT5User, violation: RuleViolationLog):
        self.subject = f"Violation Notification"
        context = {
            'user': user, 'firm_name': settings.GLOBAL_SERVICE_NAME, 'violation': violation,
        }
        self.html_content = render_to_string('emails/rule_violation/trade_admin.html', context)
        self.send_with_template()  


    def user_trade_rule_violation(self, user:MT5User, violation: RuleViolationLog):
        self.subject = f"Violation Notification"
        context = {
            'user': user, 'firm_name': settings.GLOBAL_SERVICE_NAME, 'violation': violation,
        }
        self.html_content = render_to_string('emails/rule_violation/trade_user.html', context)
        self.send_with_template() 

    def certificate_issued(self, certificate: ChallengeCertificate):
        self.subject = f"Challenge Certificate Issued"
        context = {
            'certificate': certificate, 'firm_name': settings.GLOBAL_SERVICE_NAME,
        }
        self.html_content = render_to_string('emails/certificate_issued.html', context)
        self.send_with_template() 