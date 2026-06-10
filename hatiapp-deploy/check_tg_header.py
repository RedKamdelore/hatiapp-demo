import openpyxl

wb = openpyxl.load_workbook(r'C:\Users\Administrator\Downloads\Анкеты Хати 2026 (1).xlsx')
ws = wb.active
headers = [cell.value for cell in ws[1]]

# Колонка 5 (индекс 5, шестая колонка)
tg_header = headers[5]
print(f'TG header: repr={repr(tg_header)}')
print(f'TG header bytes: {tg_header.encode("utf-8")}')
print(f'TG header hex: {tg_header.encode("utf-8").hex()}')

# Сравним с 'Тг'
expected = 'Тг'
print(f'Expected: repr={repr(expected)}')
print(f'Expected bytes: {expected.encode("utf-8")}')
print(f'Expected hex: {expected.encode("utf-8").hex()}')
print(f'Equal: {tg_header == expected}')

# Посимвольно
print(f'TG header chars: {list(tg_header)}')
print(f'Expected chars: {list(expected)}')
