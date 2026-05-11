from PIL import Image, ImageEnhance

class ImageEnhancer:
    def __init__(self, color_factor=1.1, contrast_factor=1.1, sharpness_factor=1.2):
        # معاملات التحسين (1.0 تعني بدون تغيير، أكبر من 1.0 تعني زيادة)
        self.color = color_factor       # تحسين تشبع الألوان (توازن البياض التقريبي)
        self.contrast = contrast_factor # زيادة التباين
        self.sharpness = sharpness_factor # زيادة الحدة (الـ Sharpening)

    def process(self, image_path):
        """
        يستقبل مسار الصورة، يطبق التحسينات بالتسلسل، ويعيد الصورة المحسنة
        """
        try:
            img = Image.open(image_path)
            
            # 1. تحسين الألوان
            img = ImageEnhance.Color(img).enhance(self.color)
            
            # 2. تحسين التباين (Contrast)
            img = ImageEnhance.Contrast(img).enhance(self.contrast)
            
            # 3. زيادة الحدة (Sharpness)
            img = ImageEnhance.Sharpness(img).enhance(self.sharpness)
            
            return img
        except Exception as e:
            print(f"Error enhancing {image_path}: {e}")
            return None