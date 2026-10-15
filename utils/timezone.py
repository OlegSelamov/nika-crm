from datetime import datetime
import pytz

kz = pytz.timezone("Asia/Almaty")

def now_kz():
    return datetime.now(kz)
def now_kz_for_timestamp():
    """Local Kazakhstan wall time for PostgreSQL TIMESTAMP WITHOUT TIME ZONE.

    PostgreSQL converts timezone-aware Python parameters using the database
    session timezone when inserting into a plain TIMESTAMP column. This can
    silently turn 09:11 in Kazakhstan into 04:11 on a UTC server. Strip the
    timezone *after* converting to Asia/Almaty so sale receipts and history
    preserve Kazakhstan's local clock time regardless of server timezone.

    Do not use for TIMESTAMP WITH TIME ZONE columns.
    """
    return now_kz().replace(tzinfo=None)
