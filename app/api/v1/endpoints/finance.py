"""
Almadan.app - Vision AI Fiş Okuma ve Otonom Bütçe Takip Sistemi Router'ı (Aşama 1.7).

Uç Noktalar:
1. `POST /api/v1/finance/scan-receipt`    : Multipart fiş/fatura görselini Vision AI ile JSON'a ayrıştırır.
2. `POST /api/v1/finance/budgets`         : Kullanıcının aylık kategori bazlı bütçe limitini tanımlar/günceller.
3. `POST /api/v1/finance/transactions`    : Onaylanan harcamayı/geliri kaydeder ve asenkron trigger ile
                                            ilgili ayın `budgets.current_spent` değerini otomatik günceller.
4. `GET /api/v1/finance/budget-summary`   : Kullanıcının o aya ait toplam harcamasını, kategori bazlı limit
                                            doluluk oranlarını (%85 Market, %40 Ulaşım vb.) ve kalan bütçesini döner.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any, Literal
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.security import require_auth_user
from app.services.receipt_vision import (
    ParsedReceiptData,
    ReceiptLineItem,
    analyze_receipt_image,
)
from app.storage import supabase_base_url, supabase_enabled, supabase_headers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _current_month_year() -> str:
    return _utc_now().strftime("%Y-%m")


def _extract_month_year(tx_date: str | date | datetime | None) -> str:
    if tx_date is None:
        return _current_month_year()
    if isinstance(tx_date, (date, datetime)):
        return tx_date.strftime("%Y-%m")
    cleaned = str(tx_date).strip()
    if len(cleaned) >= 7 and cleaned[4] == "-":
        return cleaned[:7]
    return _current_month_year()


# ── Varsayılan Kategori Limitleri (Kullanıcı özel limit belirlemediyse) ─

DEFAULT_CATEGORY_LIMITS: dict[str, float] = {
    "Market/Gıda": 5000.0,
    "Market": 5000.0,
    "Akaryakıt": 4000.0,
    "Ulaşım": 2500.0,
    "Giyim": 4000.0,
    "Restoran": 3000.0,
}
FALLBACK_CATEGORY_LIMIT = 3000.0


# ── İlişkisel Bellek & Supabase Yedekli Finans Veri Deposu ────────
# Yapı:
# _FINANCE_DB["transactions"][user_id][tx_id] = dict
# _FINANCE_DB["budgets"][user_id][f"{month_year}:{category}"] = dict

_FINANCE_DB: dict[str, dict[str, dict[str, dict[str, Any]]]] = {
    "transactions": {},
    "budgets": {},
}


def reset_finance_store() -> None:
    """Test senaryoları için finans ve bütçe tablolarını sıfırlar."""
    for table in _FINANCE_DB.values():
        table.clear()


# ── Pydantic Veri Modelleri ──────────────────────────────────────

class BudgetUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category: str = Field(..., description="Bütçe kategorisi (Örn: Market/Gıda, Ulaşım, Giyim)")
    limit_amount: float = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("limit_amount", "limitAmount"),
        description="Aylık kategori harcama limiti (TL)",
    )
    month_year: str = Field(
        default_factory=_current_month_year,
        validation_alias=AliasChoices("month_year", "monthYear"),
        description="Bütçe dönemi (YYYY-MM)",
    )


class BudgetItemResponse(BaseModel):
    id: str
    user_id: str
    category: str
    limit_amount: float
    current_spent: float
    remaining_amount: float
    usage_percent: float
    usage_label: str
    is_over_budget: bool
    month_year: str


class TransactionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    amount: float = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("amount", "total_amount", "totalAmount"),
        description="İşlem tutarı (TL)",
    )
    type: Literal["income", "expense"] = Field(default="expense", description="İşlem tipi (income / expense)")
    category: str = Field(..., description="Harcama/Gelir kategorisi (Market/Gıda, Akaryakıt, Ulaşım vb.)")
    merchant_name: str = Field(
        ...,
        validation_alias=AliasChoices("merchant_name", "merchantName"),
        description="İşletme / Mağaza adı (Örn: Migros)",
    )
    transaction_date: str = Field(
        default_factory=lambda: _utc_now().strftime("%Y-%m-%d"),
        validation_alias=AliasChoices("transaction_date", "transactionDate", "date"),
        description="İşlem tarihi (YYYY-MM-DD)",
    )
    receipt_image_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("receipt_image_url", "receiptImageUrl"),
    )
    tax_amount: float = Field(
        default=0.0,
        ge=0.0,
        validation_alias=AliasChoices("tax_amount", "taxAmount"),
    )
    items: list[ReceiptLineItem] = Field(default_factory=list)


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    amount: float
    type: Literal["income", "expense"]
    category: str
    merchant_name: str
    transaction_date: str
    receipt_image_url: str | None = None
    tax_amount: float = 0.0
    items: list[ReceiptLineItem] = Field(default_factory=list)
    month_year: str
    budget_updated: bool
    category_current_spent: float
    category_limit_amount: float
    category_usage_percent: float
    category_remaining_amount: float


class BudgetSummaryResponse(BaseModel):
    user_id: str
    month_year: str
    total_limit: float
    total_spent: float
    total_income: float
    remaining_budget: float
    overall_usage_percent: float
    categories: list[BudgetItemResponse]


# ── Supabase Asenkron Yazım Yardımcıları ─────────────────────────

async def _supabase_upsert_finance_row(table: str, row: dict[str, Any]) -> None:
    if not supabase_enabled():
        return
    try:
        headers = {
            **supabase_headers(),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(f"{supabase_base_url()}/rest/v1/{table}", headers=headers, json=row)
    except Exception as exc:
        logger.debug("Supabase finance (%s) yazım hatası: %s", table, exc)


# ── Asenkron Bütçe Trigger Mekanizması ───────────────────────────

async def _trigger_update_budget_on_transaction(
    user_id: str,
    tx_row: dict[str, Any],
) -> dict[str, Any]:
    """
    Harcama (`type == 'expense'`) kaydedildiğinde ilgili ayın (`month_year`) ve
    kategorinin (`category`) `budgets` tablosundaki `current_spent` değerini otonom günceller.
    """
    month_year = _extract_month_year(tx_row.get("transaction_date"))
    category = str(tx_row["category"]).strip()
    amount = float(tx_row["amount"])
    tx_type = tx_row.get("type", "expense")

    user_budgets = _FINANCE_DB["budgets"].setdefault(user_id, {})
    budget_key = f"{month_year}:{category}"
    existing_budget = user_budgets.get(budget_key)

    if existing_budget is None:
        default_limit = DEFAULT_CATEGORY_LIMITS.get(category, FALLBACK_CATEGORY_LIMIT)
        existing_budget = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "category": category,
            "limit_amount": default_limit,
            "current_spent": 0.0,
            "month_year": month_year,
            "updated_at": _utc_now().isoformat(),
            "is_deleted": False,
        }
        user_budgets[budget_key] = existing_budget

    if tx_type == "expense":
        existing_budget["current_spent"] = round(float(existing_budget["current_spent"]) + amount, 2)
        existing_budget["updated_at"] = _utc_now().isoformat()

    if supabase_enabled():
        await _supabase_upsert_finance_row("budgets", existing_budget)

    return existing_budget


def _build_budget_item_response(b_row: dict[str, Any]) -> BudgetItemResponse:
    limit_val = float(b_row["limit_amount"])
    spent_val = float(b_row["current_spent"])
    remaining = round(limit_val - spent_val, 2)
    pct = round((spent_val / limit_val) * 100.0, 2) if limit_val > 0 else 0.0
    cat_name = str(b_row["category"])
    return BudgetItemResponse(
        id=str(b_row["id"]),
        user_id=str(b_row["user_id"]),
        category=cat_name,
        limit_amount=limit_val,
        current_spent=spent_val,
        remaining_amount=remaining,
        usage_percent=pct,
        usage_label=f"%{int(round(pct))} {cat_name}",
        is_over_budget=(spent_val > limit_val),
        month_year=str(b_row["month_year"]),
    )


# ── 1. POST /api/v1/finance/scan-receipt (Vision AI Fiş Okuma) ───

@router.post("/scan-receipt", response_model=ParsedReceiptData)
async def scan_receipt_endpoint(
    file: UploadFile = File(..., description="Fiş veya fatura fotoğrafı (JPEG, PNG, WEBP)"),
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> ParsedReceiptData:
    """
    Multipart/form-data ile yüklenen fiş/fatura görselini Vision AI (`gemini-1.5-pro` / `gpt-4o`)
    ile analiz eder ve ayrıştırılmış JSON (`merchant_name`, `date`, `total_amount`, `tax_amount`, `category`, `items`) döner.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Yüklenen fiş görseli boş olamaz.")

    parsed = await analyze_receipt_image(
        image_bytes=image_bytes,
        mime_type=file.content_type or "image/jpeg",
        filename=file.filename or "",
    )
    return parsed


# ── 2. POST /api/v1/finance/budgets (Kategori Bütçe Limiti Tanımlama) ─

@router.post("/budgets", response_model=BudgetItemResponse)
async def upsert_budget_endpoint(
    payload: BudgetUpsertRequest,
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> BudgetItemResponse:
    """Kullanıcının belirli bir ay ve kategori için bütçe limitini oluşturur veya günceller."""
    user_id = str(auth_user["id"])
    category = payload.category.strip()
    month_year = payload.month_year.strip()
    budget_key = f"{month_year}:{category}"

    user_budgets = _FINANCE_DB["budgets"].setdefault(user_id, {})
    existing = user_budgets.get(budget_key)

    if existing is None:
        # O ay içinde daha önce kaydedilmiş harcamalar varsa topla
        user_txs = _FINANCE_DB["transactions"].get(user_id, {})
        existing_spent = sum(
            float(tx["amount"])
            for tx in user_txs.values()
            if tx.get("type") == "expense"
            and tx.get("category") == category
            and _extract_month_year(tx.get("transaction_date")) == month_year
            and not tx.get("is_deleted", False)
        )
        budget_row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "category": category,
            "limit_amount": round(float(payload.limit_amount), 2),
            "current_spent": round(existing_spent, 2),
            "month_year": month_year,
            "updated_at": _utc_now().isoformat(),
            "is_deleted": False,
        }
        user_budgets[budget_key] = budget_row
    else:
        existing["limit_amount"] = round(float(payload.limit_amount), 2)
        existing["updated_at"] = _utc_now().isoformat()
        budget_row = existing

    if supabase_enabled():
        await _supabase_upsert_finance_row("budgets", budget_row)

    return _build_budget_item_response(budget_row)


# ── 3. POST /api/v1/finance/transactions (Harcama Kaydı & Otonom Bütçe Trigger) ─

@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction_endpoint(
    payload: TransactionCreateRequest,
    background_tasks: BackgroundTasks,
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> TransactionResponse:
    """
    Onaylanan fiş veya manuel harcama/gelir işlemini `transactions` tablosuna kaydeder
    ve asenkron trigger ile ilgili ayın `budgets` tablosundaki `current_spent` değerini günceller.
    """
    user_id = str(auth_user["id"])
    tx_id = str(payload.id or uuid.uuid4())
    tx_date = str(payload.transaction_date).strip()
    month_year = _extract_month_year(tx_date)

    tx_row: dict[str, Any] = {
        "id": tx_id,
        "user_id": user_id,
        "amount": round(float(payload.amount), 2),
        "type": payload.type,
        "category": payload.category.strip(),
        "merchant_name": payload.merchant_name.strip(),
        "transaction_date": tx_date,
        "receipt_image_url": payload.receipt_image_url,
        "tax_amount": round(float(payload.tax_amount), 2),
        "items": [item.model_dump() for item in payload.items],
        "updated_at": _utc_now().isoformat(),
        "is_deleted": False,
    }

    user_txs = _FINANCE_DB["transactions"].setdefault(user_id, {})
    user_txs[tx_id] = tx_row

    if supabase_enabled():
        background_tasks.add_task(_supabase_upsert_finance_row, "transactions", tx_row)

    # Asenkron Bütçe Düşümü Trigger'ı
    updated_budget = await _trigger_update_budget_on_transaction(user_id, tx_row)
    b_resp = _build_budget_item_response(updated_budget)

    return TransactionResponse(
        id=tx_id,
        user_id=user_id,
        amount=tx_row["amount"],
        type=payload.type,
        category=tx_row["category"],
        merchant_name=tx_row["merchant_name"],
        transaction_date=tx_date,
        receipt_image_url=payload.receipt_image_url,
        tax_amount=tx_row["tax_amount"],
        items=payload.items,
        month_year=month_year,
        budget_updated=(payload.type == "expense"),
        category_current_spent=b_resp.current_spent,
        category_limit_amount=b_resp.limit_amount,
        category_usage_percent=b_resp.usage_percent,
        category_remaining_amount=b_resp.remaining_amount,
    )


# ── 4. GET /api/v1/finance/budget-summary (Aylık Bütçe ve Doluluk Analitiği) ─

@router.get("/budget-summary", response_model=BudgetSummaryResponse)
async def get_budget_summary_endpoint(
    month_year: str | None = Query(
        default=None,
        description="Özetlenecek ay (YYYY-MM, örn: 2026-11). Boş bırakılırsa cari ay alınır.",
    ),
    auth_user: dict[str, Any] = Depends(require_auth_user),
) -> BudgetSummaryResponse:
    """
    Kullanıcının ilgili aya ait toplam harcamasını, kategori bazlı limit doluluk oranlarını
    (Örn: %85 Market/Gıda, %40 Ulaşım) ve kalan bütçesini hesaplayıp döner.
    """
    user_id = str(auth_user["id"])
    target_month = (month_year or _current_month_year()).strip()

    user_budgets = _FINANCE_DB["budgets"].get(user_id, {})
    user_txs = _FINANCE_DB["transactions"].get(user_id, {})

    # İlgili aydaki kategori bütçelerini topla
    category_items: list[BudgetItemResponse] = []
    for b_row in user_budgets.values():
        if b_row.get("month_year") == target_month and not b_row.get("is_deleted", False):
            category_items.append(_build_budget_item_response(b_row))

    # Doluluk oranına göre azalan sırala (en kritik kategoriler en üstte)
    category_items.sort(key=lambda x: x.usage_percent, reverse=True)

    # İlgili aydaki gelirleri hesapla
    total_income = round(
        sum(
            float(tx["amount"])
            for tx in user_txs.values()
            if tx.get("type") == "income"
            and _extract_month_year(tx.get("transaction_date")) == target_month
            and not tx.get("is_deleted", False)
        ),
        2,
    )

    total_limit = round(sum(c.limit_amount for c in category_items), 2)
    total_spent = round(sum(c.current_spent for c in category_items), 2)
    remaining_budget = round(total_limit - total_spent, 2)
    overall_pct = round((total_spent / total_limit) * 100.0, 2) if total_limit > 0 else 0.0

    return BudgetSummaryResponse(
        user_id=user_id,
        month_year=target_month,
        total_limit=total_limit,
        total_spent=total_spent,
        total_income=total_income,
        remaining_budget=remaining_budget,
        overall_usage_percent=overall_pct,
        categories=category_items,
    )
