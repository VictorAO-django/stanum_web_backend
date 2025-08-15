import json, io, base64, qrcode, pyotp
from decimal import Decimal
from django.utils.decorators import method_decorator
from django.http import Http404
from django.db.models import Sum, Avg, Count, Max, Min
from django.views.decorators.cache import cache_page
from django.utils.dateparse import parse_datetime
from metaapi_cloud_sdk import MetaApi
from django_filters.rest_framework import DjangoFilterBackend
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.decorators import method_decorator
from datetime import datetime, timedelta
from django.utils.timezone import make_aware
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework import status
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.contrib.auth import user_logged_in, user_logged_out, user_login_failed
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import transaction
from asgiref.sync import async_to_sync
from django.contrib.auth.tokens import default_token_generator

from .models import *
from .serializers import *
from utils.helper import *
from utils.otp import *
from utils.filters import *
from utils.pagination import *


User = get_user_model()

class TokenRefreshView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        operation_summary="Centralized Referesh Token EP",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['refresh_token',],
            properties={
                'refresh_token': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Refresh token"
                )
            }
        ),
        responses={
            200: openapi.Response(
                description="SUCCESS.",
            ),
            400: openapi.Response(
                description="Bad Request.",
                examples={
                    "application/json": {
                        'message': 'Provide the description and message.',
                    }
                }
            ),
        }
    )
    def post(self, request):
        refresh_token = request.data.get('refresh_token')
        print("REFRESH TOKEN", refresh_token)
        try:
            token = CustomAuthToken.objects.get(refresh_token=refresh_token.strip())

            if token.has_refresh_expired():
                return Response({'detail': 'Refresh token expired'}, status=status.HTTP_401_UNAUTHORIZED)
            token.refresh() 
            
            return Response({
                "access_token": token.access_token,
                "refresh_token": token.refresh_token
            }, status=200)
        
        except Exception as e:
            print("REFRESH ERROR", str(e))
            return Response({"message": str(e)}, status=400)
        except AssertionError as e:
            print("REFRESH ERROR", str(e))
            return Response({"message": str(e)}, status=400)
        except CustomAuthToken.DoesNotExist as e:
            print("REFRESH ERROR", str(e))
            return Response({'message': 'Invalid refresh token'}, status=status.HTTP_400_BAD_REQUEST)
    


class SignupView(APIView): 
    authentication_classes = []
    permission_classes=[AllowAny]

    @swagger_auto_schema(
        operation_summary="Sign Up Endpoint",
        operation_description="This is to create an account",
        operation_id="account-creation",
        request_body=RegistrationSerializer,
        manual_parameters=[
            openapi.Parameter(
                name="rf",
                in_=openapi.IN_QUERY,
                description="Referral code from inviter",
                type=openapi.TYPE_STRING,
                required=False
            )
        ],
        responses={
            201: openapi.Response(
                description="Created",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='otp is sent to your email address.'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            ),
            403: openapi.Response(
                description="Forbidden",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='error'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='An error occured.'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            )
        }
    )
    @transaction.atomic
    def post(self, request):
        payload = request.data
        payload['email'] = payload['email'].lower()
        serializer = RegistrationSerializer(data=payload)

        if payload['email']:
            user = User.objects.filter(email=payload['email'])
            if user.exists():
                user=user.first()
                if user.email_verified == False:
                    serializer = RegistrationSerializer(user, data=payload)

        if serializer.is_valid():
            user = serializer.save()
            #send email verification message
            otp = UserOtp(user.email, 'registration')
            otp.generate_otp()
            otp.send_otp(user)

            # Extract referrals
            ref_code = request.query_params.get('rf', '').strip()
            referrer = None

            if ref_code:
                referrer = Referral.objects.filter(code=ref_code).first()

            # Only create referral profile if it doesn't exist
            referral_obj, created = Referral.objects.get_or_create(
                user=user,
                defaults={'referred_by': referrer.user if referrer and referrer.user != user else None}
            )

            return custom_response(
                status="success",
                message=f"otp is sent to your email address.",
                data={'id': user.id, 'email': user.email},
                http_status=status.HTTP_201_CREATED
            )

        return custom_response(
            status="error",
            message = str(next(iter(serializer.errors.values()))[0]),
            data=serializer.errors,
            http_status=status.HTTP_403_FORBIDDEN
        )


class ResendOtpView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Resend OTP",
        operation_description="Resend OTP to a user who hasn't verified their email.",
        operation_id="resend-otp",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['email'],
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, example='user@example.com'),
            },
        ),
        responses={
            200: openapi.Response(
                description="OTP Resent",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='OTP resent to email'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example={}),
                    },
                )
            ),
            404: openapi.Response(
                description="User Not Found or Already Verified",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='error'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='User not found or already verified.'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example={}),
                    },
                )
            )
        }
    )
    @transaction.atomic
    def post(self, request):
        email = request.data.get('email', '').lower().strip()
        if not email:
            return custom_response(
                status='error',
                message='Email is required.',
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(email=email)
            if user.email_verified:
                return custom_response(
                    status='error',
                    message='User is already verified.',
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            otp = UserOtp(user.email, 'registration')
            otp.generate_otp()
            otp.send_otp(user)

            return custom_response(
                status='success',
                message='OTP has been resent to your email address.',
                data={'id': user.id, 'email': user.email},
                http_status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            return custom_response(
                status='error',
                message='User with this email does not exist.',
                data={},
                http_status=status.HTTP_404_NOT_FOUND
            )



class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    @swagger_auto_schema(
        operation_summary="Login Endpoint",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD),
            },
            required=['email', 'password'],
        ),
    )
    def post(self, request):
        password = request.data["password"]
        try:
            user = User.objects.get(email=request.data['email'].lower(), email_verified=True, is_deleted=False)
            if user.is_locked():
                return custom_response(
                    status="Error",
                    message="Too many attempts, try again in 5 minutes.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            trial_count, trial_valid = update_lock_count(user, 'increase')            
            if user.check_password(password):
                if user.email_verified:
                    # refresh = CustomRefreshToken(user=user, user_id=user.id, email=user.email, user_type='buyer')
                    if user.is_2fa_enabled or user.otp_secret:
                        return custom_response(
                            status="error",
                            message=f"Two Factor Authentication is required",
                            data={},
                            http_status=status.HTTP_409_CONFLICT
                        )
                    
                    token, created = CustomAuthToken.objects.get_or_create(
                        user_type=ContentType.objects.get_for_model(user),
                        user_id=user.id,
                    )
                    if not created:
                        token.refresh()
                    
                    trial_count, trial_valid = update_lock_count(user, 'fallback')

                    user_logged_in.send(sender=user.__class__, request=request, user=user)

                    return custom_response(
                        status="Success",
                        message="Login successful, User Authenticated!",
                        data={
                            'access': token.access_token,
                            'refresh': token.refresh_token,
                            'user': {
                                'email': user.email,
                                'full_name': user.full_name,
                                'referral_link': user.referral_profile.get_referral_link(),
                                'proof_of_identity': ProofOfIdentity.objects.filter(user=user).exists(),
                                'proof_of_address1': ProofOfAddress.objects.filter(user=user, address_type='home_address_1').exists(),
                                'proof_of_address2': ProofOfAddress.objects.filter(user=user, address_type='home_address_2').exists(),
                            },
                        }
                    )
    
                else:
                    return custom_response(
                        status="Error",
                        message=f"Please Verify your email!, you have {5-trial_count} attempt(s) left.",
                        data={},
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            else: 
                user_login_failed.send(sender=user.__class__, credentials={'email': user.email}, request=request)
                return custom_response(
                    status="Error",
                    message=f"Incorrect credentials, you have {5-trial_count} attempt(s) left.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
        except User.DoesNotExist:
            return custom_response(
                status="Error",
                message="Incorrect credentials",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )


class Verify2FALoginView(APIView):
    authentication_classes=[]
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Login Endpoint",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD),
                'code': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=['email', 'password', 'code'],
        ),
    )
    def post(self, request):
        email = request.data.get("email").lower()
        password = request.data.get("password")
        code = request.data.get("code")

        try:
            user = User.objects.get(email=email, email_verified=True, is_deleted=False, is_2fa_enabled=True)
            if user.is_locked():
                return custom_response(
                    status="Error",
                    message="Too many attempts, try again in 5 minutes.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            trial_count, trial_valid = update_lock_count(user, 'increase')            
            if user.check_password(password):
                if user.email_verified:
                    if user.is_2fa_enabled:
                        if not code:
                            return custom_response(
                                status="Error",
                                message=f"OTP code required!, you have {5-trial_count} attempt(s) left.",
                                data={},
                                http_status=status.HTTP_400_BAD_REQUEST
                            )
                        totp = pyotp.TOTP(user.otp_secret)
                        if not totp.verify(code):
                            return custom_response(
                                status="Error",
                                message=f"Invalid OTP code!, you have {5-trial_count} attempt(s) left.",
                                data={},
                                http_status=status.HTTP_400_BAD_REQUEST
                            )
                       
                    token, created = CustomAuthToken.objects.get_or_create(
                        user_type=ContentType.objects.get_for_model(user),
                        user_id=user.id,
                    )
                    if not created:
                        token.refresh()
                    
                    trial_count, trial_valid = update_lock_count(user, 'fallback')

                    user_logged_in.send(sender=user.__class__, request=request, user=user)

                    return custom_response(
                        status="Success",
                        message="Login successful, User Authenticated!",
                        data={
                            'access': token.access_token,
                            'refresh': token.refresh_token,
                            'user': {
                                'email': user.email,
                                'full_name': user.full_name,
                                'referral_link': user.referral_profile.get_referral_link(),
                                'proof_of_identity': ProofOfIdentity.objects.filter(user=user).exists(),
                                'proof_of_address1': ProofOfAddress.objects.filter(user=user, address_type='home_address_1').exists(),
                                'proof_of_address2': ProofOfAddress.objects.filter(user=user, address_type='home_address_2').exists(),
                            },
                        }
                    )
    
                else:
                    return custom_response(
                        status="Error",
                        message=f"Please Verify your email!, you have {5-trial_count} attempt(s) left.",
                        data={},
                        http_status=status.HTTP_403_FORBIDDEN
                    )
            else: 
                user_login_failed.send(sender=user.__class__, credentials={'email': user.email}, request=request)
                return custom_response(
                    status="Error",
                    message=f"Incorrect credentials, you have {5-trial_count} attempt(s) left.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
        except User.DoesNotExist:
            return custom_response(
                status="Error",
                message="Incorrect credentials",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )


class AccountVerificationView(APIView):
    authentication_classes = []
    permission_classes=[AllowAny]
    
    @swagger_auto_schema(
        operation_summary="Account Email Verification Endpoint",
        operation_description="This is to verify user email with otp",
        operation_id="email-otp-verification",
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Account email verified'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            ),
            403: openapi.Response(
                description="Forbidden",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='error'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Invalid OTP'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            )
        }
    )
    def get(self, request, id, otp):
        user = get_object_or_404(User, id=id)
        if not verify_otp(user, 'registration', otp):
            return custom_response(
                status="error",
                message=f"Invalid OTP.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        user.email_verified = True #This toogles to True
        user.save()

        # refresh = CustomRefreshToken(user_id=user.id, email=user.email, user_type='buyer')
        token, created = CustomAuthToken.objects.get_or_create(
            user_type=ContentType.objects.get_for_model(user),
            user_id=user.id,
        )
        if not created:
            token.refresh() 

        return custom_response(
            status="success",
            message=f"Email verified.",
            data={
                'access': str(token.access_token),
                'refresh': str(token.refresh_token),
                'user': {
                    'email': user.email,
                    'full_name': user.full_name,
                },
            },
        )



class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        token = CustomAuthToken.objects.filter(user_type=ContentType.objects.get_for_model(user), user_id=user.id)
        if token.exists():
            token.delete()
            user_logged_out.send(sender=user.__class__, request=request, user=user)

        return custom_response(
            status="success",
            message="Logout successful",
            data={},
        )



class ForgetPasswordView(APIView):
    authentication_classes = []
    permission_classes=[AllowAny]
    
    @swagger_auto_schema(
        operation_summary="Forget Password Endpoint",
        operation_description="Authentication token is required",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
            },
            required=['email'],
        ),
        operation_id="forget-password",
        responses={
            200: "Successful, Reset link has been sent to email!",
            404: "No user found with this email",
        }
    )
    def post(self, request):
        email = request.data["email"].lower()
        data = {}
        try:
            user = User.objects.get(email=email, email_verified=True)
            #send email verification message
            otp = UserOtp(user.email, 'password reset')
            otp.generate_otp()
            otp.send_otp(user)

            return custom_response(
                status="success",
                message=f"An OTP has been sent to your email",
                data = {'id': user.id}
            )
        
        except User.DoesNotExist:
            return custom_response(
                status="success",
                message=f"User not found.",
                data = {},
                http_status=status.HTTP_404_NOT_FOUND
            )
        
class PasswordResetOTPValidationView(APIView):
    authentication_classes = []
    permission_classes=[AllowAny]
    
    @swagger_auto_schema(
        operation_summary="Reset Password Token Validation Endpoint",
        operation_id="reset-password-otp-verification",
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Account email verified'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            ),
            403: openapi.Response(
                description="Forbidden",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='error'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Invalid OTP'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            )
        }
    )
    def get(self, request, id, otp):
        user = get_object_or_404(User, id=id, email_verified=True)
        if not verify_otp(user, 'password reset', otp):
            return custom_response(
                status="error",
                message=f"Invalid OTP.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        #Generate a unique token for password reset if user exist in database
        token = default_token_generator.make_token(user)
        return custom_response(
            status="success",
            message=f"OTP validated.",
            data={'id': user.id,  'token': token},
        )
    
class PasswordResetView(APIView):
    authentication_classes = []
    permission_classes=[AllowAny]
    
    @swagger_auto_schema(
        operation_summary="Reset Password Token Validation Endpoint",
        operation_id="reset-password-otp-verification",
        request_body=PasswordResetSerializer,
        responses={
            200: openapi.Response(
                description="Success",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Account email verified'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            ),
            403: openapi.Response(
                description="Forbidden",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='error'),
                        'message': openapi.Schema(type=openapi.TYPE_STRING, example='Invalid OTP'),
                        'data': openapi.Schema(type=openapi.TYPE_OBJECT, example="{}"),
                    }
                )
            )
        }
    )
    def post(self, request, id, token):
        serializer = PasswordResetSerializer(data=request.data)
        user = get_object_or_404(User, id=id, email_verified=True)
        if serializer.is_valid():
            if default_token_generator.check_token(user,token):
                new_password = serializer.validated_data['new_password']
                user.set_password(new_password)
                user.save()

                # refresh = CustomRefreshToken(user_id=user.id, email=user.email, user_type='buyer')
                token, created = CustomAuthToken.objects.get_or_create(
                    user_type=ContentType.objects.get_for_model(user),
                    user_id=user.id,
                )
                if not created:
                    token.refresh() 

                return custom_response(
                    status="success",
                    message=f"Password reset successfull.",
                    data={},
                )
            return custom_response(
                status="error occured",
                message=f"Invalid Token.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        return custom_response(
            status="Error occured",
            message=f"Invalid Data.",
            data=serializer.errors,
            http_status=status.HTTP_403_FORBIDDEN
        )
    


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        request_body=ChangePasswordSerializer,
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        data = {}
            
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']
    
            user = request.user
            if user.check_password(old_password):
                if check_special_character(new_password) == False:
                    return Response({"message": "Password must contains a special character."}, status=status.HTTP_400_BAD_REQUEST)
                user.set_password(new_password)
                user.save()

                token, created = CustomAuthToken.objects.get_or_create(
                    user_type=ContentType.objects.get_for_model(user),
                    user_id=user.id,
                )
                token.rotate_access_token()

                return custom_response(
                    status="success",
                    message="Password Change Successful",
                    data={}
                )
            else:
                return custom_response(
                    status="error",
                    message="Your current password is incorrect",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN
                )
        else:
            return custom_response(
                status="error",
                message=str(next(iter(serializer.errors.values()))[0]),
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )


class ReferralDetailView(APIView):
    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name="start_date",
                in_=openapi.IN_QUERY,
                description="Statistics Start Date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE,
                required=False
            ),
            openapi.Parameter(
                name="end_date",
                in_=openapi.IN_QUERY,
                description="Statistics End Date (YYYY-MM-DD)",
                type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE,
                required=False
            )
        ],
    )
    def get(self, request, *args, **kwargs):
        user=request.user
        start_date_str = request.query_params.get('start_date', '').strip()
        end_date_str = request.query_params.get('end_date', '').strip()

        # Parse dates safely
        start_date = None
        end_date = None
        date_format = "%Y-%m-%d"
        try:
            if start_date_str:
                start_date = make_aware(datetime.datetime.strptime(start_date_str, date_format))
            if end_date_str:
                end_date = make_aware(datetime.datetime.strptime(end_date_str, date_format))
        except ValueError:
            return custom_response(
                status="error",
                message="Invalid date format. Use YYYY-MM-DD.",
                http_status=status.HTTP_400_BAD_REQUEST
            )
        
        ref = get_object_or_404(Referral, user=user)
        earning, _ = ReferralEarning.objects.get_or_create(user=user)

        # Build filters dynamically
        earning_filters = {'user': user, 'transaction_type': 'credit'}
        referrals_filters = {'referred_by': user}

        if start_date:
            earning_filters['created_at__gte'] = start_date
            referrals_filters['created_at__gte'] = start_date
        if end_date:
            earning_filters['created_at__lte'] = end_date
            referrals_filters['created_at__lte'] = end_date

        earning_transactions = ReferalEarningTransaction.objects.filter(**earning_filters).aggregate(
            reward=Sum('amount')
        )

        referrals = Referral.objects.filter(**referrals_filters)
        

        return custom_response(
            status="success",
            message="Referral details retrieved",
            data={
                'link': ref.get_referral_link(),
                'balance': earning.amount,
                'stats': {
                    'count': referrals.count(),
                    'reward': earning_transactions['reward'] or 0.00
                }
            }
        )



class LoginHistoryView(generics.ListAPIView):
    serializer_class=LoginHistorySerializer
    pagination_class=LargeResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        queryset = LoginHistory.objects.filter(user=user).order_by('-id')
        return queryset
    

class CloseAccountView(APIView):
    def delete(self, request, *args, **kwargs):
        user=request.user
        user.is_deleted = True
        user.save()

        token = CustomAuthToken.objects.filter(user_type=ContentType.objects.get_for_model(user), user_id=user.id)
        token.delete()
        
        return custom_response(
            status="success",
            message="Account closed successfully",
            data={},
        )
    


class UserDataView(generics.RetrieveUpdateAPIView):
    serializer_class=UserDataSerializer
    http_method_names = ['get', 'patch']

    def get_object(self):
        return self.request.user
        


class DocumentTypeListView(generics.ListAPIView):
    serializer_class = DocumentTypeSerializer

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                name='type',
                in_=openapi.IN_QUERY,
                description='Filter document types by category',
                type=openapi.TYPE_STRING,
                enum=[choice[0] for choice in DocumentType.TYPE_CHOICES],
                required=False
            )
        ],
        operation_description="Retrieve the list of available document types. Optionally filter by `type`."
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = DocumentType.objects.filter(is_active=True)
        doc_type = self.request.query_params.get('type', None)

        if doc_type:
            valid_types = [choice[0] for choice in DocumentType.TYPE_CHOICES]
            if doc_type in valid_types:
                queryset = queryset.filter(type=doc_type)

        return queryset
    

class SubmitProofOfIdentityView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=ProofOfIdentitySerializer
    )
    def post(self, request, *args, **kwargs):
        user = request.user

        # Prevent multiple pending submissions
        if ProofOfIdentity.objects.filter(user=user, status="pending").exists():
            return custom_response(
                status="error",
                message="Document already submitted and pending review.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = ProofOfIdentitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=user)  # Ensure user is set
            return custom_response(
                status="success",
                message="Document uploaded. Admin will review within 24 hours.",
                data={}
            )

        # Extract first error safely
        first_error = next(iter(serializer.errors.values()))[0] if serializer.errors else "Invalid data"
        return custom_response(
            status="error",
            message=str(first_error),
            data={},
            http_status=status.HTTP_403_FORBIDDEN
        )
    
    def get(self, request, *args, **kwargs):
        user = request.user
        proof = ProofOfIdentity.objects.filter(user=user)
        if proof.exists():
            return Response(
                data=ProofOfIdentitySerializer(proof.first()).data,
                status=status.HTTP_200_OK
            )
        return Response(data={}, status=status.HTTP_200_OK)


class SubmitProofOfAddressView(APIView):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=ProofOfAddressSerializer
    )
    def post(self, request, *args, **kwargs):
        user = request.user
        data = request.data
        # Prevent multiple pending submissions
        if ProofOfAddress.objects.filter(user=user, status="pending", address_type=data['address_type']).exists():
            return custom_response(
                status="error",
                message="Document already submitted and pending review.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )

        serializer = ProofOfAddressSerializer(data=data)
        if serializer.is_valid():
            serializer.save(user=user)  # Ensure user is set
            return custom_response(
                status="success",
                message="Document uploaded. Admin will review within 24 hours.",
                data={}
            )

        # Extract first error safely
        first_error = next(iter(serializer.errors.values()))[0] if serializer.errors else "Invalid data"
        return custom_response(
            status="error",
            message=str(first_error),
            data={},
            http_status=status.HTTP_403_FORBIDDEN
        )
    
    def get(self, request, *args, **kwargs):
        user = request.user
        proof = ProofOfAddress.objects.filter(user=user)
        if proof.exists():
            return Response(
                data=ProofOfAddressSerializer(proof, many=True).data,
                status=status.HTTP_200_OK
            )
        return Response(data=[], status=status.HTTP_200_OK)


class TwoFASetupView(generics.GenericAPIView):
    
    def get(self, request):
        """Generate (or return existing) secret and QR code."""
        user = request.user

        if user.is_2fa_enabled:
            return custom_response(
                status="error",
                message="2FA already enabled",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        # Use existing secret if present, otherwise generate and store
        if not user.otp_secret:
            user.otp_secret = pyotp.random_base32()
            user.save(update_fields=["otp_secret"])

        uri = pyotp.TOTP(user.otp_secret).provisioning_uri(
            name=user.email,
            issuer_name="Stanumcapital"
        )

        # Create QR code
        qr = qrcode.make(uri)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return custom_response(
            status="success",
            message="2FA details retrieved",
            data={
                "secret": user.otp_secret,
                "qr_code_base64": qr_base64
            }
        )

    def post(self, request):
        """Verify OTP and enable 2FA."""
        otp = request.data.get("otp")
        user = request.user

        if not otp:
            return custom_response(
                status="error",
                message="Missing OTP",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        if not user.otp_secret:
            return custom_response(
                status="error",
                message="No OTP secret found. Please start setup again.",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        totp = pyotp.TOTP(user.otp_secret)
        if not totp.verify(otp):
            return custom_response(
                status="error",
                message="Invalid OTP",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        user.is_2fa_enabled = True
        user.save()

        return custom_response(
            status="success",
            message="2FA enabled successfully",
            data={}
        )
