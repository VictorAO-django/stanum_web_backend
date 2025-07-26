from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils.timezone import now
from account.models import CustomAuthToken  # Adjust the import

class CustomTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', None)
        if not auth_header: 
            return None
        
        try:
            token_type, token = auth_header.split()
            if token_type != 'Bearer':
                return None

            # Decode and validate token
            token = CustomAuthToken.objects.get(access_token=token)

            if token.has_access_expired():
                raise AuthenticationFailed('Access token has expired')
            
            return (token.user, token)

        except CustomAuthToken.DoesNotExist:
            raise AuthenticationFailed('Invalid access token')
        
        except Exception as err:
            raise AuthenticationFailed('Authentication failed. Please login.')

    def authenticate_header(self, request):
        return 'Bearer'