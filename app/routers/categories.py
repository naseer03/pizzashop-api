from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import CurrentAdmin
from app.models import Category, Subcategory
from app.schemas.menu import CategoryCreate, SubcategoryCreate
from app.utils.responses import err, ok
from app.utils.slug import slugify

router = APIRouter(tags=["categories"])


def _cat_dict(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "description": c.description,
        "has_sizes": c.has_sizes,
        "display_order": c.display_order,
        "is_active": c.is_active,
        "subcategories": [
            {
                "id": s.id,
                "name": s.name,
                "slug": s.slug,
                "display_order": s.display_order,
                "is_active": s.is_active,
            }
            for s in sorted(c.subcategories, key=lambda x: (x.display_order, x.id))
        ],
    }


@router.get("/categories")
def list_categories(_: CurrentAdmin, db: Session = Depends(get_db)):
    rows = db.query(Category).order_by(Category.display_order, Category.id).all()
    return ok([_cat_dict(c) for c in rows])


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    slug = slugify(body.name)
    c = Category(
        name=body.name,
        slug=slug,
        description=body.description,
        has_sizes=body.has_sizes,
        display_order=body.display_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return ok(_cat_dict(c))


@router.put("/categories/{category_id}")
def update_category(category_id: int, body: CategoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Category not found"),
        )
    c.name = body.name
    c.slug = slugify(body.name)
    c.description = body.description
    c.has_sizes = body.has_sizes
    c.display_order = body.display_order
    db.commit()
    db.refresh(c)
    return ok(_cat_dict(c))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Category not found"),
        )
    db.delete(c)
    db.commit()
    return None


@router.post("/categories/{category_id}/subcategories", status_code=status.HTTP_201_CREATED)
def create_subcategory(
    category_id: int, body: SubcategoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)
):
    c = db.get(Category, category_id)
    if not c:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Category not found"),
        )
    slug = slugify(body.name)
    s = Subcategory(
        category_id=category_id,
        name=body.name,
        slug=slug,
        display_order=body.display_order,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return ok(
        {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "display_order": s.display_order,
            "is_active": s.is_active,
        }
    )


@router.put("/subcategories/{sub_id}")
def update_subcategory(sub_id: int, body: SubcategoryCreate, _: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.get(Subcategory, sub_id)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Subcategory not found"),
        )
    s.name = body.name
    s.slug = slugify(body.name)
    s.display_order = body.display_order
    db.commit()
    db.refresh(s)
    return ok(
        {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "display_order": s.display_order,
            "is_active": s.is_active,
        }
    )


@router.delete("/subcategories/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subcategory(sub_id: int, _: CurrentAdmin, db: Session = Depends(get_db)):
    s = db.get(Subcategory, sub_id)
    if not s:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err("RESOURCE_NOT_FOUND", "Subcategory not found"),
        )
    db.delete(s)
    db.commit()
    return None
