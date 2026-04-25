from fastapi import APIRouter

from . import auth, catalog, kitchen_ws, menu, orders as cashier_orders

router = APIRouter(prefix="/cashier")
router.include_router(auth.router, prefix="/auth", tags=["cashier-auth"])
router.include_router(menu.categories_router, prefix="/categories", tags=["cashier-menu"])
router.include_router(menu.menu_router, prefix="/menu", tags=["cashier-menu"])
router.include_router(catalog.toppings_router, prefix="/toppings", tags=["cashier-menu"])
router.include_router(catalog.crusts_router, prefix="/crusts", tags=["cashier-menu"])
router.include_router(cashier_orders.router, prefix="/orders", tags=["cashier-orders"])
router.include_router(kitchen_ws.router, tags=["cashier-kitchen"])
