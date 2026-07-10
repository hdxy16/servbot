# FILE: ./bot/actual_api.py
import asyncio
import decimal
import ssl
import urllib3
import requests
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
old_request = requests.Session.request
def new_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    return old_request(self, method, url, **kwargs)
requests.Session.request = new_request

def _unverified_context(*args, **kwargs):
    ctx = ssl._create_unverified_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

ssl.create_default_context = _unverified_context
ssl._create_default_https_context = _unverified_context

from actual import Actual
from actual.queries import (
    create_transaction, 
    get_account, 
    get_budgets, 
    get_payees, 
    create_payee,
    get_transactions,
    get_categories,
    get_category_groups
)
from config import ACTUAL_URL, ACTUAL_PASSWORD, ACTUAL_SYNC_ID, ACTUAL_ACCOUNT_NAME

def _get_actual_session():
    if not ACTUAL_URL or not ACTUAL_PASSWORD or not ACTUAL_SYNC_ID:
        raise ValueError("Відсутні дані для підключення до Actual Budget.")
    return Actual(
        base_url=ACTUAL_URL,
        password=ACTUAL_PASSWORD,
        file=ACTUAL_SYNC_ID,
        data_dir="/tmp/actual_cache"
    )

def _check_is_current_month(t_date, current_month_dash: str, current_month_int: str) -> bool:
    if not t_date: return False
    if isinstance(t_date, int):
        return str(t_date).startswith(current_month_int)
    elif hasattr(t_date, 'strftime'):
        return t_date.strftime("%Y-%m") == current_month_dash
    elif isinstance(t_date, str):
        return t_date.startswith(current_month_dash) or t_date.replace("-", "").startswith(current_month_int)
    return False

def _get_budget_data_sync() -> dict:
    try:
        with _get_actual_session() as actual:
            now = datetime.now()
            current_month_dash = now.strftime("%Y-%m")
            current_month_int = now.strftime("%Y%m")
            
            # 1. Витрати
            spent_per_cat = {}
            for t in get_transactions(actual.session):
                if _check_is_current_month(getattr(t, 'date', None), current_month_dash, current_month_int):
                    cat = getattr(t, 'category', None)
                    if cat:
                        raw_amt = getattr(t, 'amount', 0)
                        amt = float(raw_amt or 0) / 100.0
                        spent_per_cat[cat.id] = spent_per_cat.get(cat.id, 0.0) + amt
                        
            # 2. Ліміти
            budgeted_per_cat = {}
            for b in get_budgets(actual.session):
                b_month = str(getattr(b, 'month', '')).replace("-", "")
                if b_month == current_month_int:
                    cat = getattr(b, 'category', None)
                    if cat:
                        raw_amt = getattr(b, 'amount', 0)
                        budgeted_per_cat[cat.id] = float(raw_amt or 0) / 100.0
            
            # 3. Маппінг Груп
            cat_groups = get_category_groups(actual.session)
            group_map = {g.id: g.name for g in cat_groups}
            
            result = {
                "month": current_month_dash,
                "total_balance": 0.0,
                "groups": {}
            }
            
            categories = get_categories(actual.session)
            for cat in categories:
                # ФІЛЬТР СИСТЕМНИХ КАТЕГОРІЙ
                if getattr(cat, 'hidden', False) or getattr(cat, 'is_income', False):
                    continue
                if cat.name.lower() in ["income", "дохід", "starting balances"]:
                    continue
                    
                budgeted = budgeted_per_cat.get(cat.id, 0.0)
                spent = spent_per_cat.get(cat.id, 0.0)
                
                # Приховуємо повністю порожні категорії
                if budgeted == 0 and spent == 0:
                    continue
                    
                balance = budgeted + spent
                result["total_balance"] += balance
                
                group_name = group_map.get(getattr(cat, 'group_id', None), "Інше")
                if group_name.lower() in ["income", "дохід"]:
                    continue
                    
                if group_name not in result["groups"]:
                    result["groups"][group_name] = {
                        "balance": 0.0,
                        "budgeted": 0.0,
                        "spent": 0.0,
                        "categories": []
                    }
                    
                grp = result["groups"][group_name]
                grp["balance"] += balance
                grp["budgeted"] += budgeted
                grp["spent"] += spent
                
                grp["categories"].append({
                    "name": cat.name,
                    "budgeted": budgeted,
                    "spent": spent,
                    "balance": balance
                })
                
            # Сортування алфавітом
            for g in result["groups"].values():
                g["categories"].sort(key=lambda x: x["name"])
                
            return result
    except Exception as e:
        print(f"Помилка генерації даних API: {e}")
        return None

def _get_recent_payees_sync() -> list:
    try:
        with _get_actual_session() as actual:
            payees = get_payees(actual.session)
            valid_payees = [p.name for p in payees if p.name and not getattr(p, 'tombstone', False) and not getattr(p, 'transfer_acct', False)]
            seen = set()
            unique_payees = [x for x in valid_payees if not (x in seen or seen.add(x))]
            return unique_payees[:10]
    except Exception:
        return []

def _add_expense_sync(amount: float, category_name: str, payee_name: str, notes: str) -> str:
    try:
        with _get_actual_session() as actual:
            account = get_account(actual.session, ACTUAL_ACCOUNT_NAME)
            if not account: return f"❌ Рахунок '{ACTUAL_ACCOUNT_NAME}' не знайдено!"

            cat_obj = None
            for cat in get_categories(actual.session):
                if cat.name.lower() == category_name.lower():
                    cat_obj = cat
                    break
            
            if not cat_obj: return f"❌ Категорію '{category_name}' не знайдено."

            payee_obj = None
            if payee_name and payee_name != "[Не вказано]":
                for p in get_payees(actual.session):
                    if p.name.lower() == payee_name.lower():
                        payee_obj = p
                        break
                if not payee_obj:
                    payee_obj = create_payee(actual.session, payee_name)
                    actual.commit()

            amount_dec = decimal.Decimal(str(-abs(amount)))

            create_transaction(
                actual.session, datetime.utcnow().date(), account,
                payee=payee_obj, notes=notes if notes != "[Не вказано]" else None,
                category=cat_obj, amount=amount_dec, cleared=True
            )
            actual.commit()
            
            # Рахуємо новий баланс
            current_month_dash = datetime.utcnow().strftime("%Y-%m")
            current_month_int = datetime.utcnow().strftime("%Y%m")
            budgeted = 0.0
            
            for b in get_budgets(actual.session):
                b_month = str(getattr(b, 'month', '')).replace("-", "")
                if getattr(b, 'category', None) and b.category.id == cat_obj.id and b_month == current_month_int:
                    raw_b = getattr(b, 'amount', 0)
                    budgeted = float(raw_b or 0) / 100.0
                    break
                    
            spent = 0.0
            for t in get_transactions(actual.session):
                if _check_is_current_month(getattr(t, 'date', None), current_month_dash, current_month_int):
                    if getattr(t, 'category', None) and t.category.id == cat_obj.id:
                        raw_t = getattr(t, 'amount', 0)
                        spent += float(raw_t or 0) / 100.0
                        
            new_balance = budgeted + spent
            return f"✅ <b>Успішно додано!</b>\nПоточний залишок у <b>{category_name}</b>: {new_balance:.2f}€"
            
    except Exception as e:
        return f"❌ Помилка запису в Actual: {e}"

# Асинхронні обгортки
async def get_budget_data() -> dict: return await asyncio.to_thread(_get_budget_data_sync)
async def get_recent_payees() -> list: return await asyncio.to_thread(_get_recent_payees_sync)
async def add_expense_to_actual(amount: float, category: str, payee: str, notes: str) -> str:
    return await asyncio.to_thread(_add_expense_sync, amount, category, payee, notes)