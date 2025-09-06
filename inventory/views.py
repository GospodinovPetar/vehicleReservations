
from datetime import date
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token

from .models import Vehicle, Location, Reservation
from .pricing import RateTable, quote_total

def home(request):
    locations = Location.objects.all()
    ctx = {"locations": locations}
    return render(request, "home.html", ctx)

def search(request):
    start = request.GET.get("start")
    end = request.GET.get("end")
    pickup_id = request.GET.get("pickup_location")
    return_id = request.GET.get("return_location")
    locations = Location.objects.all()
    ctx = {"locations": locations, "start": start, "end": end, "pickup_location": pickup_id, "return_location": return_id}

    if not start or not end:
        return render(request, "home.html", ctx)

    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    pickup = Location.objects.filter(id=pickup_id).first() if pickup_id else None
    retloc = Location.objects.filter(id=return_id).first() if return_id else None

    # available vehicles
    avail_ids = Reservation.available_vehicle_ids(start_date, end_date, pickup, retloc)
    vehicles = Vehicle.objects.filter(id__in=avail_ids).prefetch_related("prices","vehicle_locations__location")
    results = []
    for v in vehicles:
        prices = {p.period_type: float(p.amount) for p in v.prices.all()}
        rt = RateTable(day=prices.get("day"), week=prices.get("week"), month=prices.get("month"), currency=v.currency)
        quote = quote_total(start_date, end_date, rt)
        results.append({"vehicle": v, "quote": quote})

    ctx["results"] = results
    return render(request, "home.html", ctx)

@login_required
@require_http_methods(["POST"])
def reserve(request):
    payload = request.POST
    v = get_object_or_404(Vehicle, id=payload.get("vehicle"))
    # Choose provided locations or sensible defaults from the vehicle availability
    pickup_id = payload.get("pickup_location")
    return_id = payload.get("return_location")
    if pickup_id:
        pickup = get_object_or_404(Location, id=pickup_id)
    else:
        pickup = v.vehicle_locations.filter(can_pickup=True).select_related("location").first().location
    if return_id:
        ret = get_object_or_404(Location, id=return_id)
    else:
        # default to a 'can_return' spot; prefer default_return locations when available
        vl_qs = v.vehicle_locations.filter(can_return=True).select_related("location")
        ret = (vl_qs.filter(location__is_default_return=True).first() or vl_qs.first()).location
    start = date.fromisoformat(payload.get("start"))
    end = date.fromisoformat(payload.get("end"))

    r = Reservation(user=request.user, vehicle=v, pickup_location=pickup, return_location=ret, start_date=start, end_date=end, currency=v.currency)
    try:
        r.clean()
    except Exception as e:
        messages.error(request, str(e))
        return redirect("/search/?start=%s&end=%s" % (start.isoformat(), end.isoformat()))

    # compute price
    prices = {p.period_type: float(p.amount) for p in v.prices.all()}
    quote = quote_total(start, end, RateTable(day=prices.get("day"), week=prices.get("week"), month=prices.get("month"), currency=v.currency))
    r.total_price = quote["total"]
    r.save()
    messages.success(request, "Reservation created!")
    return redirect("/reservations/")

@login_required
def reservations(request):
    res = Reservation.objects.filter(user=request.user).select_related("vehicle","pickup_location","return_location").all()
    return render(request, "reservations.html", {"reservations": res})

@login_required
@require_http_methods(["POST"])
def cancel_reservation(request, pk):
    from django.http import Http404
    try:
        r = Reservation.objects.get(pk=pk, user=request.user)
    except Reservation.DoesNotExist:
        raise Http404
    if r.status not in ("PENDING","CONFIRMED"):
        messages.error(request, "Cannot cancel this reservation.")
    else:
        r.status = "CANCELLED"
        r.save(update_fields=["status"])
        messages.success(request, "Reservation cancelled.")
    return redirect("/reservations/")

@login_required
@require_http_methods(["POST"])
def reject_reservation(request, pk):
    from django.http import Http404
    try:
        r = Reservation.objects.get(pk=pk, user=request.user)
    except Reservation.DoesNotExist:
        raise Http404
    if r.status != "PENDING":
        messages.error(request, "Only pending reservations can be rejected.")
    else:
        r.status = "REJECTED"
        r.save(update_fields=["status"])
        messages.success(request, "Reservation rejected.")
    return redirect("/reservations/")

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("/")
    else:
        form = UserCreationForm()
    return render(request, "auth.html", {"form": form, "title": "Register"})

def login_view(request):
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            next_url = request.GET.get("next") or "/"
            return redirect(next_url)
    else:
        form = AuthenticationForm(request)
    return render(request, "auth.html", {"form": form, "title": "Login"})

def logout_view(request):
    logout(request)
    return redirect("/")
