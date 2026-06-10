import openpyxl

wb = openpyxl.load_workbook(r'C:\Users\Administrator\Downloads\Анкеты Хати 2026 (1).xlsx')
ws = wb.active
headers = [cell.value for cell in ws[1]]

print('Header lengths:')
for i, h in enumerate(headers[:6]):
    if h:
        print(f'{i}: len={len(h)}, bytes={len(h.encode("utf-8"))}, val={repr(h)}')

print()
print('Expected lengths:')
for name in ['Позывной', 'Телефон', 'Тг']:
    print(f'{name}: len={len(name)}, bytes={len(name.encode("utf-8"))}')
    
print()
print('Match tests:')
for name in ['Позывной', 'Телефон', 'Тг']:
    found = name in headers
    print(f'{name} in headers: {found}')
