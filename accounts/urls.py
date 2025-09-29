from django.urls import path
from django.contrib.auth.decorators import login_required, permission_required
from . import views

app_name = "accounts"

urlpatterns = [
    # ---------- Auth ----------
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register, name="register"),
    path("verify-email/", views.verify_email, name="verify-email"),
    path("forgot-password/", views.forgot_password_start, name="forgot-password-start"),
    path("forgot-password/confirm/", views.forgot_password_confirm, name="forgot-password-confirm"),

    # ---------- Profile ----------
    path("profile/", views.profile_view, name="profile"),
    path("profile/<int:pk>/", views.profile_view, name="profile-detail"),
    path("profile/edit/", views.profile_edit, name="profile-edit"),
    path("profile/profile-change-password/", views.profile_change_password, name="profile-change-password"),

    # ---------- Admin (views already role-protected) ----------
    path("admin/dashboard/", login_required(views.admin_dashboard), name="admin-dashboard"),
    path("admin/users/create/", login_required(views.create_user), name="admin-create-user"),
    path("admin/users/<int:pk>/edit/", login_required(views.edit_user), name="admin-edit-user"),
    path("admin/users/<int:pk>/delete/", login_required(views.delete_user), name="admin-delete-user"),
    path("admin/users/<int:pk>/block/", login_required(views.block_user), name="admin-block-user"),
    path("admin/users/<int:pk>/unblock/", login_required(views.unblock_user), name="admin-unblock-user"),
    path("admin/users/<int:pk>/promote/", login_required(views.promote_manager), name="admin-promote-manager"),
    path("admin/users/<int:pk>/demote/", login_required(views.demote_user), name="admin-demote-user"),

    # ---------- Manager dashboard ----------
    path("manager/dashboard/", login_required(views.manager_dashboard), name="manager-dashboard"),

    # ---------- Vehicles (secured like Locations; views also have decorators) ----------
    path(
        "manager/vehicles/",
        login_required(
            views.manager_required(
                permission_required("inventory.view_vehicle", raise_exception=True)(views.vehicle_list)
            )
        ),
        name="vehicle-list",
    ),
    path(
        "manager/vehicles/add/",
        login_required(
            views.manager_required(
                permission_required("inventory.add_vehicle", raise_exception=True)(views.vehicle_create)
            )
        ),
        name="vehicle-create",
    ),
    path(
        "manager/vehicles/<int:pk>/edit/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_vehicle", raise_exception=True)(views.vehicle_edit)
            )
        ),
        name="vehicle-edit",
    ),
    path(
        "manager/vehicles/<int:pk>/delete/",
        login_required(
            views.manager_required(
                permission_required("inventory.delete_vehicle", raise_exception=True)(views.vehicle_delete)
            )
        ),
        name="vehicle-delete",
    ),

    # ---------- Reservations (manager) ----------
    path(
        "manager/reservations/",
        login_required(
            views.manager_required(
                permission_required("inventory.view_reservationgroup", raise_exception=True)(views.reservation_list)
            )
        ),
        name="reservation-list",
    ),
    path(
        "manager/reservations/<int:pk>/approve/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(
                    views.reservation_group_approve
                )
            )
        ),
        name="reservation-group-approve",
    ),
    path(
        "manager/reservations/<int:pk>/reject/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(
                    views.reservation_group_reject
                )
            )
        ),
        name="reservation-group-reject",
    ),
    path(
        "manager/reservations/<int:pk>/update/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(views.reservation_update)
            )
        ),
        name="reservation-update",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/approve/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(views.reservation_approve)
            )
        ),
        name="reservation-approve",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/reject/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(views.reservation_reject)
            )
        ),
        name="reservation-reject",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/cancel/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(views.reservation_cancel)
            )
        ),
        name="reservation_group_cancel",
    ),
    path(
        "manager/reservations/<int:pk>/complete/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(views.reservation_complete)
            )
        ),
        name="reservation-complete",
    ),
    path(
        "manager/reservations/group/<int:pk>/complete/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_reservationgroup", raise_exception=True)(
                    views.reservation_group_complete
                )
            )
        ),
        name="reservation_group_complete",
    ),

    # ---------- Locations (manager) ----------
    path(
        "manager/locations/",
        login_required(
            views.manager_required(
                permission_required("inventory.view_location", raise_exception=True)(views.location_list)
            )
        ),
        name="location-list",
    ),
    path(
        "manager/locations/create/",
        login_required(
            views.manager_required(
                permission_required("inventory.add_location", raise_exception=True)(views.location_create)
            )
        ),
        name="location-create",
    ),
    path(
        "manager/locations/<int:pk>/edit/",
        login_required(
            views.manager_required(
                permission_required("inventory.change_location", raise_exception=True)(views.location_edit)
            )
        ),
        name="location-edit",
    ),
    path(
        "manager/locations/<int:pk>/delete/",
        login_required(
            views.manager_required(
                permission_required("inventory.delete_location", raise_exception=True)(views.location_delete)
            )
        ),
        name="location-delete",
    ),

    # ---------- User’s own reservations ----------
    path("my-reservations/", login_required(views.user_reservations), name="user-reservations"),
]
