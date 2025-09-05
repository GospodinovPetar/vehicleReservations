
from rest_framework import serializers
from inventory.models import Vehicle, VehiclePrice, Location, VehicleLocation

class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "is_default_return", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

class VehiclePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehiclePrice
        fields = ["id", "vehicle", "period_type", "amount", "currency", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

class VehicleLocationSerializer(serializers.ModelSerializer):
    location = LocationSerializer()
    class Meta:
        model = VehicleLocation
        fields = ["id", "location", "can_pickup", "can_return"]

class VehicleSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()
    locations = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = [
            "id","name","type","engine_type","seats","unlimited_passengers",
            "price_per_day","currency","created_at","updated_at","prices","locations",
        ]
        read_only_fields = ["created_at","updated_at"]

    def get_locations(self, obj):
        qs = obj.vehicle_locations.select_related("location")
        return [
            {
                "location": LocationSerializer(vl.location).data,
                "can_pickup": vl.can_pickup,
                "can_return": vl.can_return,
            }
            for vl in qs
        ]

    def get_prices(self, obj):
        return {
            "day": float(obj.price_per_day),
            "week": float(obj.week_price),
            "month": float(obj.month_price),
            "currency": obj.currency,
        }
