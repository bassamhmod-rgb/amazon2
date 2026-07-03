from rest_framework import serializers
from .models import Customer   # ← عدّل اسم الموديل
from .models import PointsTransaction   # ← عدّل اسم الموديل

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'     # ← حتى يرجع كل الحقول
class PointsTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PointsTransaction
        fields = '__all__'     # ← حتى يرجع كل الحقول
