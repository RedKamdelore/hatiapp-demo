from database import SessionLocal
import models

db = SessionLocal()

missing = ['Pruzraki', 'NikiWay2', 'CookieZoya', 'Tweedn', 'Old_Monk_ey', 
           'DorianMatsui', 'CeleryBun', 'Polina_Belkin', 'rWbl_49', 
           'Io_Tkhorzh', 'Blg10001', 'Annetta_859', 'KaAnhlie', 'Dybrawka']

print('Проверка регистра username в БД:')
for username in missing:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        user = db.query(models.User).filter(models.User.username == username.lower()).first()
    if not user:
        user = db.query(models.User).filter(models.User.username.ilike(username)).first()
    
    if user:
        print(f'{username}: БД username="{user.username}", arrival={user.arrival_date}')
    else:
        print(f'{username}: НЕ НАЙДЕН в БД')

db.close()
