from database import SessionLocal
import models

db = SessionLocal()

missing = ['pruzraki', 'nikiway2', 'cookiezoya', 'tweedn', 'old_monk_ey', 
           'dorianmatsui', 'celerybun', 'polina_belkin', 'rwbl_49', 
           'io_tkhorzh', 'blg10001', 'annetta_859', 'kaanhlie', 'dybrawka']

print('Проверка lowercase username в БД:')
for username in missing:
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        print(f'{username}: БД username="{user.username}", arrival={user.arrival_date}')
    else:
        print(f'{username}: НЕ НАЙДЕН в БД')

db.close()
