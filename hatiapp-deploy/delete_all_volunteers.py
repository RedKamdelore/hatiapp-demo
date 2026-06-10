from database import SessionLocal
import models

db = SessionLocal()

# Удаляем ВСЕХ волонтёров
deleted = db.query(models.User).filter(models.User.role == 'volunteer').delete(synchronize_session=False)
db.commit()
print(f'Удалено волонтёров: {deleted}')

# Проверим остаток
remaining = db.query(models.User).count()
print(f'Осталось пользователей (admin/leader/lotos): {remaining}')

# Покажем кто остался
users = db.query(models.User).all()
for u in users:
    print(f'  {u.username} ({u.role})')

db.close()
