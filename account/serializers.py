from rest_framework import serializers
from .models import *
from utils.helper import *

class RegistrationSerializer(serializers.ModelSerializer):
    password2 = serializers.CharField(style={"input_type":"password"}, write_only=True)
    class Meta:
        model = User
        fields = ["email", "full_name", "date_of_birth", "phone_number", "country", "password", "password2"]
        extra_kwargs = {
            "password" : {"write_only": True}
        }

    def validate_first_name(self, value):
        # Check if the username starts with "admin"
        if not has_no_special_character(value):
            raise serializers.ValidationError("Firstname must only contain letters and numbers, without special characters.")
        return value
    
    def validate_last_name(self, value):
        # Check if the username starts with "admin"
        if not has_no_special_character(value):
            raise serializers.ValidationError("Lastname must only contain letters and numbers, without special characters.")
        return value
    
    def save(self, *args, **kwargs):
        password1 = self.validated_data["password"]
        password2 = self.validated_data["password2"]
        
        if password1 != password2: #check if password correlate
            raise serializers.ValidationError("Password and confirm Password does not match")

        self.validated_data.pop('password2')
        user = super().save(*args, **kwargs)
        user.set_password(password1)
        user.save()
        return user
    

    
class PasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only = True)
    new_password = serializers.CharField(write_only = True)