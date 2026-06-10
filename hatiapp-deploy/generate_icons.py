"""Генерация иконок для PWA."""
from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size, output_path):
    """Создаёт простую иконку приложения."""
    img = Image.new('RGB', (size, size), color='#4f46e5')
    draw = ImageDraw.Draw(img)
    
    # Рисуем букву "H" белым цветом
    try:
        font_size = int(size * 0.5)
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    text = "H"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]
    
    draw.text((x, y), text, fill='white', font=font)
    
    img.save(output_path)
    print(f"Created: {output_path}")

if __name__ == "__main__":
    static_dir = "static"
    os.makedirs(static_dir, exist_ok=True)
    
    create_icon(192, os.path.join(static_dir, "icon-192.png"))
    create_icon(512, os.path.join(static_dir, "icon-512.png"))
    print("Icons generated successfully!")
