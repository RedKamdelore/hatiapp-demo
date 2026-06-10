import openpyxl
from database import SessionLocal
import models

# Получаем ТГ из Excel
wb = openpyxl.load_workbook(r'C:\Users\Administrator\Downloads\Анкеты Хати 2026 (1).xlsx')
ws = wb.active
excel_tgs = set()
excel_rows = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    if len(row) > 5 and row[5]:
        tg = str(row[5]).strip().lower()
        excel_tgs.add(tg)
        excel_rows[tg] = {
            'pozyvnoy': row[0] if len(row) > 0 else None,
            'phone': row[4] if len(row) > 4 else None,
        }

# Получаем волонтёров без дат из БД
db = SessionLocal()
users_no_dates = db.query(models.User).filter(
    models.User.arrival_date == None,
    models.User.role == 'volunteer'
).all()

print(f"Волонтёров без дат в БД: {len(users_no_dates)}")
print(f"Уникальных ТГ в Excel: {len(excel_tgs)}")
print()

in_excel = []
not_in_excel = []

for user in users_no_dates:
    username = user.username.lower()
    if username in excel_tgs:
        in_excel.append({
            'username': user.username,
            'full_name': user.full_name,
            'excel_pozyvnoy': excel_rows[username]['pozyvnoy'],
            'excel_phone': excel_rows[username]['phone'],
        })
    else:
        not_in_excel.append({
            'username': user.username,
            'full_name': user.full_name,
        })

print(f"Есть в Excel: {len(in_excel)}")
for u in in_excel:
    print(f"  {u['username']} ({u['full_name']}) - в Excel: {u['excel_pozyvnoy']}, тел: {u['excel_phone']}")

print()
print(f"НЕТ в Excel: {len(not_in_excel)}")
for u in not_in_excel:
    print(f"  {u['username']} ({u['full_name']})")

db.close()
