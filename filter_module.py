import cv2
import imagehash
from PIL import Image
import os

class ImageFilter:
    def __init__(self, blur_threshold=100, hash_cutoff=5):
        # حد اكتشاف الاهتزاز (كلما زاد الرقم، زادت الصرامة)
        self.blur_threshold = blur_threshold
        # حد اكتشاف التكرار (كلما قل الرقم، زاد التطابق المطلوب)
        self.hash_cutoff = hash_cutoff
        self.processed_hashes = []

    def is_blurry(self, image_path):
        """
        يكتشف ما إذا كانت الصورة مهزوزة أو خارج التركيز
        باستخدام خوارزمية التباين (Laplacian Variance)
        """
        image = cv2.imread(image_path)
        if image is None:
            return True # نعتبر الملف التالف صورة سيئة
        
        # Resize for faster blur detection (analysis only)
        image = cv2.resize(image, (640, 480))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        focus_measure = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # إذا كان التركيز أقل من الحد المطلوب، فالصورة مهزوزة
        return focus_measure < self.blur_threshold

    def is_duplicate(self, image_path):
        """
        يكتشف الصور المكررة أو اللقطات المتتالية (Burst shots)
        باستخدام خوارزمية التشفير الإدراكي (Perceptual Hashing)
        """
        try:
            img = Image.open(image_path)
            # نستخدم phash لأنه ممتاز في اكتشاف التشابه حتى لو اختلفت الإضاءة قليلاً
            img_hash = imagehash.phash(img) 
            
            for prev_hash in self.processed_hashes:
                # إذا كان الفارق بين الصورتين أقل من الحد المسموح، فهي مكررة
                if img_hash - prev_hash < self.hash_cutoff:
                    return True
            
            # إذا لم تكن مكررة، نضيفها إلى القائمة لنقارن بها الصور القادمة
            self.processed_hashes.append(img_hash)
            return False
            
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            return True