from datetime import datetime
import pytz

kz = pytz.timezone("Asia/Almaty")

def now_kz():
    return datetime.now(kz)