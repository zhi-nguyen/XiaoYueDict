from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'first_name', 'last_name')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user

from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

class UserDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'bio', 'avatar', 'date_joined')
        read_only_fields = ('id', 'username', 'date_joined')

    def validate_avatar(self, avatar):
        if not avatar:
            return avatar

        # Mở dữ liệu ảnh bằng Pillow
        img = Image.open(avatar)

        # Chuẩn hóa kích thước tối đa cho Avatar (Giới hạn ở mức 400x400 pixels)
        max_size = (400, 400)
        if img.width > 400 or img.height > 400:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Nén và chuyển định dạng sang WebP
        output = BytesIO()
        
        # Chuyển đổi về hệ màu RGB để tránh lỗi đối với ảnh PNG có nền trong suốt (RGBA)
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Nén với chất lượng 85%
        img.save(output, format='WEBP', quality=85)
        output.seek(0)

        # Đổi tên file extension thành .webp
        new_name = f"{avatar.name.split('.')[0]}.webp"
        return ContentFile(output.read(), name=new_name)

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs.get('old_password')):
            raise serializers.ValidationError({"old_password": "Mật khẩu cũ không chính xác."})
        return attrs
