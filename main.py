import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import requests

"""
Python 3.12

Перед запуском создайте файл authorizationToken.txt рядом с файлом main.py
Файл authorizationToken.txt должен содержать строку вида vk1.a.RrNgC******
Для получения токена отройте страницу консоли RuStore, 
нажмите на клавиатуре F12, См. картинку cookie_f12.png
"""
# Конфигурация
start_date = datetime.date.fromisoformat('2023-06-01')


@dataclass
class AppInfo:
    appId: int
    packageName: str
    appName: str


@dataclass
class Purchase:
    invoice_id: str
    amount_current: float
    invoice_date: str
    invoice_status: str
    purchase_id: str

    def to_tsv_row(self):
        return f"{self.invoice_date};{self.invoice_id};{self.invoice_status};{self.purchase_id};{self.amount_current}\n"


HEADERS: Dict[str, str] = {}

try:
    with open("authorizationToken.txt", 'r') as token_file:
        HEADERS['Authorization'] = token_file.readline().strip()
except Exception:
    print("Не удалось прочитать токен, см. инструкцию в шапке!")
    exit(1)


def load_apps() -> Dict[int, AppInfo]:
    """Загружает информацию о приложениях пользователя."""
    response = requests.get(
        "https://backapi.rustore.ru/applicationData/retrieveUserApps",
        headers=HEADERS
    )
    response.raise_for_status()  # Проверяем успешность запроса

    apps_data = response.json()["body"]["content"]
    return {
        item['appId']: AppInfo(
            appId=item['appId'],
            packageName=item['packageName'],
            appName=item['appName']
        )
        for item in apps_data
    }


def map_purchase(raw_purchase: Dict) -> Purchase:
    """Преобразует сырые данные покупки в объект Purchase."""
    amount = raw_purchase['amount_create'] or 0
    return Purchase(
        invoice_id=raw_purchase['invoice_id'],
        amount_current=amount,
        invoice_date=raw_purchase['invoice_date'],
        invoice_status=raw_purchase['invoice_status'],
        purchase_id=raw_purchase['purchase_id'],
    )


def fetch_purchases(
        app_id: int,
        date_from: datetime.date,
        page: int = 0
) -> List[Purchase]:
    """
    Загружает покупки приложения с пагинацией.

    Args:
        app_id: ID приложения
        date_from: начальная дата выборки
        page: номер страницы (для пагинации)

    Returns:
        Список объектов Purchase
    """
    date_to = datetime.date.today()
    size = 250
    status = "confirmed"

    url = (
        f"https://api.rustore.ru/invoices-history/public/v1/apps/{app_id}/invoice-payments?"
        f"dateFrom={date_from}&dateTo={date_to}&page={page}"
        f"&invoiceStatuses={status}&size={size}"
    )

    print(f'Страница {page}')
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()

    raw_purchases = response.json()['body']['invoices']
    purchases = [map_purchase(p) for p in raw_purchases]

    if len(purchases) < size:
        return purchases
    else:
        return purchases + fetch_purchases(app_id, date_from, page + 1)


def generate_date_range(start_date: datetime.date) -> List[datetime.date]:
    """Генерирует список дат от start_date до сегодняшнего дня."""
    dates = []
    current_date = start_date
    while current_date <= datetime.date.today():
        dates.append(current_date)
        current_date += datetime.timedelta(days=1)
    return dates


def calculate_daily_revenue(
        purchases: List[Purchase],
        start_date: datetime.date
) -> Dict[datetime.date, float]:
    """
    Рассчитывает дневную выручку по покупкам.

    Args:
        purchases: список покупок
        start_date: начальная дата для расчёта

    Returns:
        Словарь: дата → сумма выручки за день
    """
    daily_revenue: Dict[datetime.date, float] = {}
    for purchase in purchases:
        purchase_date = datetime.datetime.strptime(
            purchase.invoice_date[:10], "%Y-%m-%d"
        ).date()
        if purchase_date >= start_date:
            daily_revenue[purchase_date] = (
                    daily_revenue.get(purchase_date, 0) +
                    purchase.amount_current / 100
            )
    return daily_revenue


def save_revenue_report(
        app_info: AppInfo,
        daily_revenue: Dict[datetime.date, float],
        start_date: datetime.date
):
    """Сохраняет отчёт о выручке в файл."""
    filename = Path(f"revenue/{app_info.appName}.txt")
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, 'w') as file:
        for date in generate_date_range(start_date):
            revenue = int(daily_revenue.get(date, 0))
            file.write(f"{date}\t{revenue}\n")


def save_purchases_report(
        app_info: AppInfo,
        purchases: List[Purchase]
):
    """Сохраняет отчёт о покупках в файл."""
    filename = Path(f"purchases/{app_info.appName}.csv")
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, 'w') as file:
        file.writelines(purchase.to_tsv_row() for purchase in purchases)


def collect_data(start_date: datetime.date):
    """
    Собирает данные о покупках и выручке для всех приложений.

    Args:
        start_date: начальная дата выборки данных
    """
    apps = load_apps()

    for app_id, app_info in apps.items():
        print("=" * 50)
        print(app_info.appName)
        print("=" * 50)
        purchases = fetch_purchases(app_id, start_date)
        print("-" * 50)
        print(f"Количество покупок: {len(purchases)}")

        total_revenue = sum(p.amount_current / 100 for p in purchases)
        print(f"Общая выручка: {total_revenue:.2f}")

        save_purchases_report(app_info, purchases)

        daily_revenue = calculate_daily_revenue(purchases, start_date)
        save_revenue_report(app_info, daily_revenue, start_date)


if __name__ == "__main__":
    collect_data(start_date)
