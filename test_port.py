import win32com.client

fr = win32com.client.gencache.EnsureDispatch("AddIn.DrvFR_KZ")

for method in [
    "OpenFiscalInv",
    "RegisterSale",
    "RegisterArticleSale",
    "SetFiscalInvParam",
    "Subtotal",
    "Total",
    "CloseFiscalInv"
]:
    try:
        print("=" * 50)
        print(method)
        print(getattr(fr, method).__doc__)
    except Exception as e:
        print(method, e)