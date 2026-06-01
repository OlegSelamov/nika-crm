import clr

clr.AddReference(r"C:\Program Files (x86)\Newton\Драйвер ККМ\Примеры\C#\WinPortTest\obj\x86\Debug\Interop.AddInLib.dll")

import AddInLib

print("Содержимое AddInLib:")
print(dir(AddInLib))