from datetime import date, time

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.entities import (
    AdminRole,
    AdminUser,
    BusinessHour,
    Category,
    Crust,
    DayOfWeek,
    Employee,
    EmployeeStatus,
    MenuItem,
    MenuItemSize,
    PaymentSetting,
    Permission,
    Role,
    RolePermission,
    SizeName,
    StoreSetting,
    Subcategory,
    Topping,
)


def seed_if_empty(db: Session) -> None:
    if db.query(AdminUser).first():
        return

    admin = AdminUser(
        email="admin@pizzahub.com",
        password_hash=hash_password("admin123"),
        first_name="Admin",
        last_name="User",
        role=AdminRole.super_admin,
    )
    db.add(admin)

    perms_data = [
        ("View Dashboard", "dashboard.view", "Dashboard", "Can view dashboard statistics"),
        ("View Orders", "orders.view", "Orders", None),
        ("Create Orders", "orders.create", "Orders", None),
        ("Update Orders", "orders.update", "Orders", None),
        ("Cancel Orders", "orders.cancel", "Orders", None),
        ("View Menu", "menu.view", "Menu", None),
        ("Manage Menu", "menu.manage", "Menu", None),
        ("View Inventory", "inventory.view", "Inventory", None),
        ("Manage Inventory", "inventory.manage", "Inventory", None),
        ("View Customers", "customers.view", "Customers", None),
        ("Manage Customers", "customers.manage", "Customers", None),
        ("View Employees", "employees.view", "Employees", None),
        ("Manage Employees", "employees.manage", "Employees", None),
        ("View Reports", "reports.view", "Reports", None),
        ("Export Reports", "reports.export", "Reports", None),
        ("Manage Settings", "settings.manage", "Settings", None),
        ("Manage Roles", "roles.manage", "Roles", None),
    ]
    perm_objs = []
    for name, code, cat, desc in perms_data:
        p = Permission(name=name, code=code, category=cat, description=desc)
        db.add(p)
        perm_objs.append(p)
    db.flush()

    manager = Role(
        name="Manager",
        description="Full access to all features",
        color="#EF4444",
        is_system_role=True,
    )
    cashier = Role(
        name="Cashier",
        description="Orders and payments",
        color="#3B82F6",
        is_system_role=True,
    )
    kitchen = Role(
        name="Kitchen Staff",
        description="Order status",
        color="#10B981",
        is_system_role=True,
    )
    db.add_all([manager, cashier, kitchen])
    db.flush()

    for p in perm_objs:
        db.add(RolePermission(role_id=manager.id, permission_id=p.id))

    db.add(StoreSetting(store_name="PizzaHub"))

    for d in DayOfWeek:
        db.add(
            BusinessHour(
                day_of_week=d,
                is_open=True,
                open_time=time(10, 0),
                close_time=time(22, 0),
            )
        )

    for method, label in [
        ("cash", "Cash"),
        ("card", "Card"),
        ("online", "Online"),
        ("wallet", "Wallet"),
    ]:
        db.add(PaymentSetting(payment_method=method, display_name=label, is_enabled=True))

    crusts = [
        ("Hand Tossed", 0, 1),
        ("Thin Crust", 0, 2),
        ("Deep Dish", 2, 3),
        ("Stuffed Crust", 2.5, 4),
        ("Gluten Free", 3, 5),
        ("Cauliflower", 3.5, 6),
    ]
    for name, price, so in crusts:
        db.add(Crust(name=name, price=price, sort_order=so))

    cat_pizza = Category(
        name="Pizzas",
        slug="pizzas",
        description="Handcrafted pizzas",
        has_sizes=True,
        display_order=1,
    )
    cat_sides = Category(
        name="Sides",
        slug="sides",
        description="Sides",
        has_sizes=False,
        display_order=2,
    )
    db.add_all([cat_pizza, cat_sides])
    db.flush()

    sub = Subcategory(
        category_id=cat_pizza.id,
        name="Classic Pizzas",
        slug="classic",
        display_order=1,
    )
    db.add(sub)
    db.flush()

    db.add(Topping(name="Pepperoni", category_id=cat_pizza.id, price=1.5, sort_order=1))
    db.add(Topping(name="Mushrooms", category_id=cat_pizza.id, price=0.75, sort_order=2))

    item = MenuItem(
        name="Margherita Pizza",
        slug="margherita-pizza",
        description="Classic tomato, mozzarella, and fresh basil",
        category_id=cat_pizza.id,
        subcategory_id=sub.id,
        base_price=14.99,
        is_featured=True,
    )
    db.add(item)
    db.flush()
    db.add(
        MenuItemSize(menu_item_id=item.id, size_name=SizeName.small, price=10.99, is_default=False)
    )
    db.add(
        MenuItemSize(menu_item_id=item.id, size_name=SizeName.medium, price=14.99, is_default=True)
    )
    db.add(
        MenuItemSize(menu_item_id=item.id, size_name=SizeName.large, price=18.99, is_default=False)
    )

    emp = Employee(
        employee_code="EMP001",
        first_name="Michael",
        last_name="Johnson",
        email="michael@pizzahub.com",
        phone="+1234567890",
        role_id=manager.id,
        hourly_rate=22,
        hire_date=date(2023, 1, 15),
        status=EmployeeStatus.active,
    )
    db.add(emp)

    db.commit()
