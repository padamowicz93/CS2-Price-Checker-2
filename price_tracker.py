import os
import ssl
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests


BASE_URL = "https://api.skinport.com/v1"

SKIN_NAME = os.getenv("SKIN_NAME", "M4A4 | Mecha Industries (Battle-Scarred)")
APP_ID = int(os.getenv("APP_ID", "730"))
CURRENCY = os.getenv("CURRENCY", "PLN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Warsaw")


def get_json(endpoint: str, params: dict[str, Any]) -> Any:
    url = f"{BASE_URL}/{endpoint}"

    headers = {
        "Accept-Encoding": "br",
        "User-Agent": "cs2-skin-price-tracker/1.0",
    }

    response = requests.get(url, params=params, headers=headers, timeout=30)

    if response.status_code == 406:
        raise RuntimeError(
            "Skinport zwrócił 406. Najczęściej oznacza to brak lub problem z headerem Accept-Encoding: br."
        )

    response.raise_for_status()
    return response.json()


def fetch_current_item() -> Optional[dict[str, Any]]:
    data = get_json(
        "items",
        {
            "app_id": APP_ID,
            "currency": CURRENCY,
            "tradable": 1,
        },
    )

    for item in data:
        if item.get("market_hash_name") == SKIN_NAME:
            return item

    return None


def fetch_sales_history() -> Optional[dict[str, Any]]:
    data = get_json(
        "sales/history",
        {
            "app_id": APP_ID,
            "currency": CURRENCY,
            "market_hash_name": SKIN_NAME,
        },
    )

    if isinstance(data, list):
        for item in data:
            if item.get("market_hash_name") == SKIN_NAME:
                return item
        return data[0] if data else None

    if isinstance(data, dict):
        return data

    return None


def fmt_price(value: Any) -> str:
    if value is None:
        return "brak danych"

    try:
        return f"{float(value):.2f} {CURRENCY}"
    except (TypeError, ValueError):
        return f"{value} {CURRENCY}"


def fmt_value(value: Any) -> str:
    if value is None:
        return "brak danych"
    return str(value)


def format_history_period(history: dict[str, Any], key: str, label: str) -> str:
    period = history.get(key) or {}

    return (
        f"{label}:\n"
        f"  min:    {fmt_price(period.get('min'))}\n"
        f"  max:    {fmt_price(period.get('max'))}\n"
        f"  avg:    {fmt_price(period.get('avg'))}\n"
        f"  median: {fmt_price(period.get('median'))}\n"
        f"  volume: {fmt_value(period.get('volume'))}"
    )


def build_email(current_item: dict[str, Any], history: Optional[dict[str, Any]]) -> tuple[str, str]:
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S %Z")

    min_price = current_item.get("min_price")
    subject = f"CS2 Skin Update: {SKIN_NAME}"

    if min_price is not None:
        subject += f" - {fmt_price(min_price)}"

    item_page = current_item.get("item_page", "brak linku")

    lines = [
        f"CS2 Skin Price Update",
        f"",
        f"Skin: {SKIN_NAME}",
        f"Czas raportu: {now}",
        f"",
        f"Skinport - aktualne oferty:",
        f"  Najniższa cena:   {fmt_price(current_item.get('min_price'))}",
        f"  Najwyższa cena:   {fmt_price(current_item.get('max_price'))}",
        f"  Średnia cena:     {fmt_price(current_item.get('mean_price'))}",
        f"  Mediana:          {fmt_price(current_item.get('median_price'))}",
        f"  Suggested price:  {fmt_price(current_item.get('suggested_price'))}",
        f"  Liczba ofert:     {fmt_value(current_item.get('quantity'))}",
        f"",
    ]

    if history:
        lines.extend(
            [
                "Skinport - historia sprzedaży:",
                format_history_period(history, "last_24_hours", "Ostatnie 24h"),
                "",
                format_history_period(history, "last_7_days", "Ostatnie 7 dni"),
                "",
                format_history_period(history, "last_30_days", "Ostatnie 30 dni"),
                "",
                format_history_period(history, "last_90_days", "Ostatnie 90 dni"),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Skinport - historia sprzedaży:",
                "  Brak danych historycznych.",
                "",
            ]
        )

    lines.extend(
        [
            "Link:",
            item_page,
            "",
            "Ten e-mail został wygenerowany automatycznie przez GitHub Actions.",
        ]
    )

    body = "\n".join(lines)
    return subject, body


def send_email(subject: str, body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("EMAIL_FROM") or smtp_user
    email_to = os.getenv("EMAIL_TO")

    missing = [
        name
        for name, value in {
            "SMTP_HOST": smtp_host,
            "SMTP_PORT": smtp_port,
            "SMTP_USER": smtp_user,
            "SMTP_PASSWORD": smtp_password,
            "EMAIL_TO": email_to,
        }.items()
        if not value
    ]

    if missing:
        print("Brakuje ustawień SMTP, więc nie wysyłam maila.")
        print("Brakujące zmienne:", ", ".join(missing))
        print("")
        print("DRY RUN - treść maila:")
        print("=" * 60)
        print("Subject:", subject)
        print("")
        print(body)
        print("=" * 60)
        return

    msg = EmailMessage()
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = subject
    msg.set_content(body)

    port = int(smtp_port)
    context = ssl.create_default_context()

    if port == 465:
        with smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=30) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

    print(f"E-mail wysłany do: {email_to}")


def main() -> None:
    print(f"Pobieram dane dla: {SKIN_NAME}")

    current_item = fetch_current_item()

    if current_item is None:
        raise RuntimeError(f"Nie znaleziono itemu na Skinport: {SKIN_NAME}")

    history = fetch_sales_history()

    subject, body = build_email(current_item, history)

    print("Raport wygenerowany poprawnie.")
    print("")
    print(body)
    print("")

    send_email(subject, body)


if __name__ == "__main__":
    main()
