from django.urls import path
from django.contrib.auth.decorators import login_required, permission_required
from .views.admins_managers import (
    manager_required,
    manager_dashboard,
    demote_user,
    promote_manager,
    unblock_user,
    block_user,
    delete_user,
    edit_user,
    create_user,
    admin_dashboard,
)
from .views.auth import (
    profile_edit,
    profile_change_password,
    profile_view,
    forgot_password_confirm,
    forgot_password_start,
    verify_email,
    register,
    logout_view,
    login_view,
)
from .views.locations import (
    location_delete,
    location_edit,
    location_create,
    location_list,
)
from .views.reservations import (
    user_reservations,
    reservation_group_complete,
    reservation_complete,
    reservation_cancel,
    reservation_reject,
    reservation_approve,
    reservation_update,
    reservation_group_reject,
    reservation_group_approve,
    reservation_list,
)
from .views.vehicles import vehicle_delete, vehicle_edit, vehicle_create, vehicle_list

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("register/", register, name="register"),
    path("verify-email/", verify_email, name="verify-email"),
    path("forgot-password/", forgot_password_start, name="forgot-password-start"),
    path(
        "forgot-password/confirm/",
        forgot_password_confirm,
        name="forgot-password-confirm",
    ),
    path("profile/", profile_view, name="profile"),
    path("profile/<int:pk>/", profile_view, name="profile-detail"),
    path("profile/edit/", profile_edit, name="profile-edit"),
    path(
        "profile/profile-change-password/",
        profile_change_password,
        name="profile-change-password",
    ),
    path("admin/dashboard/", login_required(admin_dashboard), name="admin-dashboard"),
    path("admin/users/create/", login_required(create_user), name="admin-create-user"),
    path(
        "admin/users/<int:pk>/edit/", login_required(edit_user), name="admin-edit-user"
    ),
    path(
        "admin/users/<int:pk>/delete/",
        login_required(delete_user),
        name="admin-delete-user",
    ),
    path(
        "admin/users/<int:pk>/block/",
        login_required(block_user),
        name="admin-block-user",
    ),
    path(
        "admin/users/<int:pk>/unblock/",
        login_required(unblock_user),
        name="admin-unblock-user",
    ),
    path(
        "admin/users/<int:pk>/promote/",
        login_required(promote_manager),
        name="admin-promote-manager",
    ),
    path(
        "admin/users/<int:pk>/demote/",
        login_required(demote_user),
        name="admin-demote-user",
    ),
    path(
        "manager/dashboard/",
        login_required(manager_dashboard),
        name="manager-dashboard",
    ),
    path(
        "manager/vehicles/",
        login_required(
            manager_required(
                permission_required("inventory.view_vehicle", raise_exception=True)(
                    vehicle_list
                )
            )
        ),
        name="vehicle-list",
    ),
    path(
        "manager/vehicles/add/",
        login_required(
            manager_required(
                permission_required("inventory.add_vehicle", raise_exception=True)(
                    vehicle_create
                )
            )
        ),
        name="vehicle-create",
    ),
    path(
        "manager/vehicles/<int:pk>/edit/",
        login_required(
            manager_required(
                permission_required("inventory.change_vehicle", raise_exception=True)(
                    vehicle_edit
                )
            )
        ),
        name="vehicle-edit",
    ),
    path(
        "manager/vehicles/<int:pk>/delete/",
        login_required(
            manager_required(
                permission_required("inventory.delete_vehicle", raise_exception=True)(
                    vehicle_delete
                )
            )
        ),
        name="vehicle-delete",
    ),
    path(
        "manager/reservations/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.view_reservationgroup", raise_exception=True
                )(reservation_list)
            )
        ),
        name="reservation-list",
    ),
    path(
        "manager/reservations/<int:pk>/approve/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_group_approve)
            )
        ),
        name="reservation-group-approve",
    ),
    path(
        "manager/reservations/<int:pk>/reject/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_group_reject)
            )
        ),
        name="reservation-group-reject",
    ),
    path(
        "manager/reservations/<int:pk>/update/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_update)
            )
        ),
        name="reservation-update",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/approve/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_approve)
            )
        ),
        name="reservation-approve",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/reject/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_reject)
            )
        ),
        name="reservation-reject",
    ),
    path(
        "manager/reservations/reservation/<int:pk>/cancel/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_cancel)
            )
        ),
        name="reservation_group_cancel",
    ),
    path(
        "manager/reservations/<int:pk>/complete/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_complete)
            )
        ),
        name="reservation-complete",
    ),
    path(
        "manager/reservations/group/<int:pk>/complete/",
        login_required(
            manager_required(
                permission_required(
                    "inventory.change_reservationgroup", raise_exception=True
                )(reservation_group_complete)
            )
        ),
        name="reservation_group_complete",
    ),
    path(
        "manager/locations/",
        login_required(
            manager_required(
                permission_required("inventory.view_location", raise_exception=True)(
                    location_list
                )
            )
        ),
        name="location-list",
    ),
    path(
        "manager/locations/create/",
        login_required(
            manager_required(
                permission_required("inventory.add_location", raise_exception=True)(
                    location_create
                )
            )
        ),
        name="location-create",
    ),
    path(
        "manager/locations/<int:pk>/edit/",
        login_required(
            manager_required(
                permission_required("inventory.change_location", raise_exception=True)(
                    location_edit
                )
            )
        ),
        name="location-edit",
    ),
    path(
        "manager/locations/<int:pk>/delete/",
        login_required(
            manager_required(
                permission_required("inventory.delete_location", raise_exception=True)(
                    location_delete
                )
            )
        ),
        name="location-delete",
    ),
    path(
        "my-reservations/", login_required(user_reservations), name="user-reservations"
    ),
]
