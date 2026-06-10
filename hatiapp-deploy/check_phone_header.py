import openpyxl

wb = openpyxl.load_workbook(r'C:\Users\Administrator\Downloads\Анкеты Хати 2026 (1).xlsx')
ws = wb.active
headers = [cell.value for cell in ws[1]]

# Проверим все заголовки
for i, h in enumerate(headers[:6]):
    if h:
        print(f'{i}: hex={h.encode("utf-8").hex()}')

print()
# Проверим Телефон
phone_header = headers[4]
expected_phone = 'Телефон'
print(f'Phone header hex: {phone_header.encode("utf-8").hex()}')
print(f'Expected phone hex: {expected_phone.encode("utf-8").hex()}')
print(f'Phone equal: {phone_header == expected_phone}')
