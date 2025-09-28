from django.contrib.auth import get_user_model
from rest_framework import serializers

from inventory.models.vehicle import Vehicle
from inventory.models.reservation import (
    VehicleReservation,
    Location,
    ReservationGroup,
    ReservationStatus,
)

User = get_user_model()


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "name", "car_type", "engine_type", "seats", "unlimited_seats", "price_per_day"]


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name"]


class ReservationCreateSerializer(serializers.Serializer):
    vehicle_id = serializers.IntegerField()
    pickup_location_id = serializers.IntegerField()
    return_location_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs):
        if attrs["end_date"] <= attrs["start_date"]:
            raise serializers.ValidationError("end_date must be after start_date.")
        return attrs


class ReservationSerializer(serializers.ModelSerializer):
    vehicle_name = serializers.SerializerMethodField()
    group_status = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)
    group_id = serializers.IntegerField(read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = VehicleReservation
        fields = [
            "id", "user", "vehicle", "vehicle_name",
            "pickup_location", "return_location",
            "start_date", "end_date",
            "group_id", "group_status", "total_price",
        ]
        read_only_fields = ("user", "group_id", "group_status", "total_price")

    def get_vehicle_name(self, obj):
        return getattr(obj, "vehicle_name_snapshot", "") or (str(obj.vehicle) if obj.vehicle else "")

    def get_group_status(self, obj):
        grp = getattr(obj, "group", None)
        return getattr(grp, "status", None)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class AvailabilityVehicleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class AvailabilityResponseSerializer(serializers.Serializer):
    vehicles = AvailabilityVehicleSerializer(many=True)
